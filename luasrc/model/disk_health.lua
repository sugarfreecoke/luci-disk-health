--[[
luci-app-disk-health  /  硬件抽象层 (HAL)
------------------------------------------------------------------
本模块负责：
  1. 发现系统中所有块设备（/sys/block + block info）
  2. 按设备类型分派到不同的采集后端：
       sdX / hdX / vdX  -> smartctl
       nvmeXnY          -> smartctl
       mmcblkX          -> sysfs(life_time/pre_eol_info) 或 mmc extcsd read
       mtdX             -> 不支持，仅列出
  3. 把各种五花八门的原始输出，归一化成统一的数据结构返回给上层：
       { name, path, type, model, size, health, life, temp, hours, ... }

设计说明（为什么这么做）：
  * smartctl 优先使用 `-j`(JSON) 输出，解析最可靠；若固件/版本不支持
    JSON，则自动回退到传统文本解析，两条路径都实现。
  * eMMC 优先读 sysfs 的 life_time / pre_eol_info（新内核直接暴露，
    不需要装 mmc-utils），失败再退回 `mmc extcsd read`。
  * 所有外部命令调用都包在 pcall/容错里，任何一个设备解析失败只影响
    该设备自身（error 字段），绝不让整个页面 500。
--]]

local fs    = require "nixio.fs"
local uci   = require("luci.model.uci").cursor()

local M = {}

M.CACHE_FILE = "/tmp/luci_disk_health_cache.json"

-- ================================================================
-- 一、基础工具函数
-- ================================================================

--- 去掉首尾空白
local function trim(s)
	if type(s) ~= "string" then return nil end
	s = s:gsub("^%s+", "")
	s = s:gsub("%s+$", "")
	return s
end
M.trim = trim

--- 写系统日志，便于 `logread | grep disk-health` 排查问题
function M.log(msg)
	local m = tostring(msg or "")
	m = m:gsub("[\r\n]+", " ")
	m = m:gsub("'", "")          -- 防止破坏 shell 单引号
	m = m:sub(1, 400)
	os.execute("logger -t luci-disk-health '" .. m .. "' 2>/dev/null")
end

--- 读取小文件（sysfs 用），返回去空白后的字符串或 nil
local function readf(path)
	local ok, res = pcall(function() return fs.readfile(path) end)
	if not ok or not res then return nil end
	res = trim(res)
	if res == "" then return nil end
	return res
end
M.readf = readf

--- 执行外部命令，返回 stdout 与退出码。stderr 被丢弃。
-- 用 `echo __RC__:$?` 的方式把退出码带回来，因为 Lua 5.1 的
-- io.popen:close() 拿不到真实退出状态。
local function run(cmd)
	local out, rc = "", -1
	local ok = pcall(function()
		local p = io.popen("(" .. cmd .. ") 2>/dev/null; echo \"__RC__:$?\"")
		if not p then return end
		out = p:read("*a") or ""
		p:close()
	end)
	if not ok then return "", -1 end
	rc = tonumber(out:match("__RC__:(%d+)%s*$") or "") or -1
	out = out:gsub("__RC__:%d+%s*$", "")
	return out, rc
end
M.run = run

--- 检测命令是否存在（结果缓存，避免重复 fork）
local cmd_cache = {}
function M.have_cmd(name)
	if cmd_cache[name] ~= nil then return cmd_cache[name] end
	local found = false
	for _, p in ipairs({ "/usr/sbin/", "/usr/bin/", "/sbin/", "/bin/" }) do
		if fs.access(p .. name, "x") then found = true end
	end
	if not found then
		local out = run("command -v " .. name)
		if trim(out or "") ~= "" then found = true end
	end
	cmd_cache[name] = found
	return found
end

--- 字节数 -> 人类可读
function M.fmt_size(bytes)
	local b = tonumber(bytes or 0) or 0
	if b <= 0 then return "N/A" end
	local units = { "B", "KiB", "MiB", "GiB", "TiB", "PiB" }
	local i = 1
	local v = b
	while v >= 1024 and i < #units do
		v = v / 1024
		i = i + 1
	end
	if i >= 4 then
		return string.format("%.2f %s", v, units[i])
	end
	return string.format("%.0f %s", v, units[i])
end

--- 小时数 -> "1234 小时 (51 天)"
function M.fmt_hours(h)
	local n = tonumber(h or "")
	if not n or n < 0 then return nil end
	local days = math.floor(n / 24)
	if days >= 1 then
		return string.format("%d 小时 (约 %d 天)", n, days)
	end
	return string.format("%d 小时", n)
end

--- 读取插件配置（缺省值兜底，配置文件不存在也不会报错）
function M.config()
	local function g(k, d)
		local v
		pcall(function() v = uci:get("disk_health", "main", k) end)
		if v == nil or v == "" then return d end
		return v
	end
	return {
		cache_ttl    = tonumber(g("cache_ttl", 60))   or 60,
		skip_standby = (g("skip_standby", "0") == "1"),
		temp_warn    = tonumber(g("temp_warn", 55))   or 55,
		temp_crit    = tonumber(g("temp_crit", 65))   or 65,
		life_warn    = tonumber(g("life_warn", 20))   or 20,
		life_crit    = tonumber(g("life_crit", 10))   or 10,
		show_usb     = (g("show_usb", "1") == "1"),
	}
end

-- 健康等级：good < warn < danger，取最差
local RANK = { unknown = 0, good = 1, warn = 2, danger = 3 }
local function worse(a, b)
	if (RANK[b] or 0) > (RANK[a] or 0) then return b end
	return a
end
M.worse = worse

function M.status_text(st)
	if st == "good"   then return "良好" end
	if st == "warn"   then return "警告" end
	if st == "danger" then return "危险" end
	return "未知"
end

-- ================================================================
-- 二、设备发现
-- ================================================================

-- 需要忽略的虚拟/伪块设备
local SKIP_PATTERNS = {
	"^loop", "^ram", "^zram", "^dm%-", "^md%d", "^sr%d",
	"^mtdblock", "^ubi", "^nbd", "^fd%d", "^zd%d",
}

local function should_skip(name)
	for _, p in ipairs(SKIP_PATTERNS) do
		if name:match(p) then return true end
	end
	return false
end

--- 通过 sysfs 真实路径判断设备挂在哪条总线上
local function dev_bus(name)
	local rp = ""
	pcall(function() rp = fs.realpath("/sys/block/" .. name) or "" end)
	if rp == "" then return nil end
	if rp:match("/usb%d") or rp:match("usb%d+/") then return "USB" end
	if rp:match("/nvme")       then return "NVMe" end
	if rp:match("/mmc_host/")  then return "MMC"  end
	if rp:match("/ata%d")      then return "SATA" end
	if rp:match("/virtio")     then return "VirtIO" end
	return nil
end

--- 判断设备类型（接口）：SATA / NVMe / USB / eMMC / SD / VirtIO / 未知
local function classify(name)
	if name:match("^nvme") then return "NVMe" end

	if name:match("^mmcblk") then
		-- /sys/block/mmcblk0/device/type 内容为 "MMC" 或 "SD"
		local t = readf("/sys/block/" .. name .. "/device/type")
		if t == "SD" then return "SD" end
		return "eMMC"
	end

	if name:match("^vd") then return "VirtIO" end

	if name:match("^sd") or name:match("^hd") then
		local bus = dev_bus(name)
		if bus == "USB" then return "USB" end
		-- removable=1 且总线未识别时，大概率是 USB 读卡器
		if readf("/sys/block/" .. name .. "/removable") == "1" and bus == nil then
			return "USB"
		end
		return bus or "SATA"
	end

	return "未知"
end
M.classify = classify

--- 从 sysfs 抓取设备静态属性
local function sysfs_info(name)
	local base  = "/sys/block/" .. name
	local d     = base .. "/device"
	local dev   = {
		name = name,
		path = "/dev/" .. name,
		type = classify(name),
	}

	-- 容量：/sys/block/x/size 恒为 512 字节单位
	local sectors = tonumber(readf(base .. "/size") or "") or 0
	dev.size_bytes = sectors * 512
	dev.size       = M.fmt_size(dev.size_bytes)

	-- 型号：SATA/USB 用 device/model，NVMe 用 device/model，eMMC 用 device/name
	dev.model = readf(d .. "/model") or readf(d .. "/name")
	if not dev.model and name:match("^nvme") then
		-- nvme0n1 -> 取控制器节点 /sys/class/nvme/nvme0/model
		local ctrl = name:match("^(nvme%d+)")
		if ctrl then dev.model = readf("/sys/class/nvme/" .. ctrl .. "/model") end
	end
	dev.model = dev.model or "未知型号"

	dev.serial   = readf(d .. "/serial")
	dev.firmware = readf(d .. "/fwrev") or readf(d .. "/rev") or readf(d .. "/firmware_rev")
	dev.vendor   = readf(d .. "/vendor")

	local rot = readf(base .. "/queue/rotational")
	dev.rotational = (rot == "1")
	dev.removable  = (readf(base .. "/removable") == "1")

	-- 机械盘 / 固态 的粗判：NVMe 与 rotational=0 视为固态
	if dev.type == "eMMC" or dev.type == "SD" or dev.type == "NVMe" then
		dev.media = "闪存"
	elseif dev.rotational then
		dev.media = "机械硬盘"
	else
		dev.media = "固态硬盘"
	end

	return dev
end

--- 用 `block info` 补充分区的文件系统 / 挂载点 / UUID 信息
-- block info 输出形如：
--   /dev/sda1: UUID="xxx" LABEL="data" VERSION="1.0" TYPE="ext4"
--   /dev/sda2: UUID="yyy" TYPE="swap"
-- 我们把它按父设备归类，挂载点则从 /proc/self/mounts 取。
function M.block_info()
	local map = {}
	if not M.have_cmd("block") then return map end
	local out = run("block info")
	if not out or out == "" then return map end

	-- 先建立 设备 -> 挂载点 表
	local mounts = {}
	local mf = fs.readfile("/proc/self/mounts") or ""
	for line in mf:gmatch("[^\n]+") do
		local src, dst = line:match("^(%S+)%s+(%S+)")
		if src and dst and src:match("^/dev/") then
			dst = dst:gsub("\\040", " ")
			mounts[src] = mounts[src] or dst
		end
	end

	for line in out:gmatch("[^\n]+") do
		local devpath = line:match("^(/dev/%S+):")
		if devpath then
			local part = {
				path  = devpath,
				fstype = line:match('TYPE="([^"]*)"'),
				label  = line:match('LABEL="([^"]*)"'),
				uuid   = line:match('UUID="([^"]*)"'),
				mount  = mounts[devpath],
			}
			-- 推导父设备名：/dev/sda1 -> sda，/dev/nvme0n1p2 -> nvme0n1，
			-- /dev/mmcblk0p3 -> mmcblk0
			local base = devpath:gsub("^/dev/", "")
			local parent = base:match("^(%a+%d*n%d+)p%d+$")   -- nvme0n1p1
				or base:match("^(mmcblk%d+)p%d+$")            -- mmcblk0p1
				or base:match("^(%a+)%d+$")                   -- sda1
				or base
			map[parent] = map[parent] or {}
			table.insert(map[parent], part)
		end
	end
	return map
end

--- 列出所有物理块设备（不含分区），返回静态信息数组
function M.list_devices()
	local list = {}
	local names = {}

	local ok = pcall(function()
		for name in fs.dir("/sys/block") do
			if name and not should_skip(name) then
				table.insert(names, name)
			end
		end
	end)
	if not ok then
		M.log("无法枚举 /sys/block")
		return list
	end

	table.sort(names)

	local cfg  = M.config()
	local bmap = M.block_info()

	for _, name in ipairs(names) do
		local okd, dev = pcall(sysfs_info, name)
		if okd and dev and dev.size_bytes and dev.size_bytes > 0 then
			if dev.type == "USB" and not cfg.show_usb then
				-- 用户在设置里关闭了 USB 设备显示
			else
				dev.partitions = bmap[name] or {}
				-- 取第一个有挂载点的分区，方便在列表里显示
				for _, p in ipairs(dev.partitions) do
					if p.mount then dev.mount = p.mount break end
				end
				table.insert(list, dev)
			end
		elseif not okd then
			M.log("读取 sysfs 失败: " .. name)
		end
	end

	return list
end

-- ================================================================
-- 三、smartctl 后端（SATA / NVMe / USB）
-- ================================================================

-- 关注的 SMART 属性 ID -> 中文说明
M.ATTR_NAMES = {
	[1]   = "读取错误率",
	[5]   = "重映射扇区数",
	[9]   = "通电时间",
	[10]  = "主轴重试次数",
	[12]  = "开机次数",
	[160] = "不可恢复错误数",
	[169] = "剩余寿命",
	[173] = "闪存擦写均衡计数",
	[177] = "磨损均衡计数",
	[179] = "已用保留块",
	[181] = "程序失败次数",
	[182] = "擦除失败次数",
	[187] = "无法纠正的错误",
	[188] = "命令超时次数",
	[190] = "气流温度",
	[194] = "温度",
	[196] = "重映射事件计数",
	[197] = "当前待映射扇区数",
	[198] = "脱机无法纠正扇区数",
	[199] = "UDMA CRC 错误数",
	[202] = "剩余寿命百分比",
	[231] = "SSD 剩余寿命",
	[232] = "可用保留空间",
	[233] = "闪存剩余寿命",
	[241] = "累计写入量",
	[242] = "累计读取量",
}

-- 这些属性的“归一化值(value)”本身就代表剩余寿命百分比
local LIFE_ATTRS = { 231, 233, 202, 177, 173, 169, 232 }
-- 这些属性的原始值大于 0 即代表磁盘存在物理损伤
local BAD_ATTRS  = { [5] = 1, [197] = 1, [198] = 1, [187] = 1, [188] = 0 }

--- 构造 smartctl 命令。-n standby 可避免唤醒休眠中的机械盘。
local function smart_cmd(path, extra, cfg)
	local c = "smartctl"
	if cfg.skip_standby then c = c .. " -n standby" end
	if extra then c = c .. " " .. extra end
	return c .. " -a " .. path
end

--- 解析 smartctl 的 JSON 输出（smartmontools >= 7.0 支持 -j）
local function parse_smart_json(txt, dev, cfg)
	local jsonc = require "luci.jsonc"
	local okj, j = pcall(function() return jsonc.parse(txt) end)
	if not okj or type(j) ~= "table" then return false end

	dev.source = "smartctl(json)"

	-- ---------- 静态信息补全 ----------
	if j.model_name     then dev.model    = j.model_name end
	if j.serial_number  then dev.serial   = j.serial_number end
	if j.firmware_version then dev.firmware = j.firmware_version end
	if j.user_capacity and tonumber(j.user_capacity.bytes or 0) > 0 then
		dev.size_bytes = tonumber(j.user_capacity.bytes)
		dev.size = M.fmt_size(dev.size_bytes)
	end

	-- ---------- 通用信息 ----------
	if j.temperature and j.temperature.current then
		dev.temp = tonumber(j.temperature.current)
	end
	if j.power_on_time and j.power_on_time.hours then
		dev.hours = tonumber(j.power_on_time.hours)
	end
	if j.power_cycle_count then dev.power_cycles = tonumber(j.power_cycle_count) end

	local st = "unknown"
	if j.smart_status ~= nil and j.smart_status.passed ~= nil then
		dev.smart_passed = j.smart_status.passed and true or false
		st = dev.smart_passed and "good" or "danger"
	end

	-- ---------- NVMe 专有健康日志 ----------
	local nv = j.nvme_smart_health_information_log
	if type(nv) == "table" then
		local used = tonumber(nv.percentage_used or "")
		if used then
			dev.life      = math.max(0, 100 - used)   -- 剩余寿命
			dev.health_pct = dev.life
			dev.used_pct  = used
		end
		if nv.available_spare then dev.spare = tonumber(nv.available_spare) end
		if nv.power_on_hours  then dev.hours = tonumber(nv.power_on_hours) end
		if nv.power_cycles    then dev.power_cycles = tonumber(nv.power_cycles) end
		if nv.media_errors    then dev.media_errors = tonumber(nv.media_errors) end
		if nv.unsafe_shutdowns then dev.unsafe_shutdowns = tonumber(nv.unsafe_shutdowns) end
		if nv.critical_warning then dev.critical_warning = tonumber(nv.critical_warning) end
		-- 写入量：data_units_written 单位为 1000 * 512 字节
		if nv.data_units_written then
			dev.written = M.fmt_size(tonumber(nv.data_units_written) * 512 * 1000)
		end
		if nv.data_units_read then
			dev.read = M.fmt_size(tonumber(nv.data_units_read) * 512 * 1000)
		end

		-- NVMe 健康判定
		if (dev.critical_warning or 0) ~= 0 then st = worse(st, "danger") end
		if dev.spare and dev.spare < 10       then st = worse(st, "danger") end
		if dev.life then
			if dev.life <= cfg.life_crit then st = worse(st, "danger")
			elseif dev.life <= cfg.life_warn then st = worse(st, "warn") end
		end
		if (dev.media_errors or 0) > 0 then st = worse(st, "warn") end
		if st == "unknown" then st = "good" end
	end

	-- ---------- ATA SMART 属性表 ----------
	local at = j.ata_smart_attributes
	if type(at) == "table" and type(at.table) == "table" then
		dev.attrs = {}
		local by_id = {}
		for _, a in ipairs(at.table) do
			local id  = tonumber(a.id or "")
			local raw = a.raw or {}
			local item = {
				id     = id,
				name   = a.name,
				cn     = M.ATTR_NAMES[id or -1],
				value  = tonumber(a.value or ""),
				worst  = tonumber(a.worst or ""),
				thresh = tonumber(a.thresh or ""),
				raw    = raw.string or tostring(raw.value or ""),
				raw_num = tonumber(raw.value or ""),
			}
			table.insert(dev.attrs, item)
			if id then by_id[id] = item end
		end

		st = M.eval_ata(dev, by_id, cfg, st)
	end

	if st == "unknown" and dev.smart_passed ~= nil then
		st = dev.smart_passed and "good" or "danger"
	end
	dev.status = st
	return true
end

--- 根据 ATA SMART 属性计算健康度与状态
-- 逻辑说明：
--   * 固态盘：若存在“剩余寿命类”属性，直接用其归一化值当剩余寿命；
--   * 机械盘：无寿命属性，用坏道相关属性做扣分，得出一个估算健康度；
--   * 温度、待映射扇区等异常会把状态往 warn/danger 拉。
function M.eval_ata(dev, by_id, cfg, st)
	-- 通电时间 / 开机次数 / 温度
	if by_id[9]  and by_id[9].raw_num  then
		-- 有些盘 raw 里写的是 "1234h+56m"，raw_num 仍是小时数
		dev.hours = dev.hours or by_id[9].raw_num
	end
	if by_id[12] and by_id[12].raw_num then
		dev.power_cycles = dev.power_cycles or by_id[12].raw_num
	end
	if not dev.temp then
		local t = (by_id[194] and by_id[194].raw_num) or (by_id[190] and by_id[190].raw_num)
		-- 部分盘 raw 是 "35 (Min/Max 20/45)"，raw_num 取低字节即当前温度
		if t and t > 0 and t < 200 then dev.temp = t end
	end
	-- 累计写入量（LBA 数 * 512）
	if by_id[241] and by_id[241].raw_num and by_id[241].raw_num > 0 then
		dev.written = M.fmt_size(by_id[241].raw_num * 512)
	end

	-- 1) 剩余寿命类属性
	for _, id in ipairs(LIFE_ATTRS) do
		local a = by_id[id]
		if a and a.value and a.value >= 0 and a.value <= 100 then
			dev.life = a.life or a.value
			dev.life_from = string.format("%d %s", id, a.name or "")
			break
		end
	end

	-- 2) 物理损伤扣分
	local penalty, bad = 0, {}
	for id, _ in pairs(BAD_ATTRS) do
		local a = by_id[id]
		if a and a.raw_num and a.raw_num > 0 then
			table.insert(bad, string.format("%s=%s", a.cn or a.name or id, a.raw))
			if id == 5 or id == 197 or id == 198 then
				-- 坏道类：出现即扣分，数量越多扣得越狠（对数增长）
				penalty = penalty + math.min(40, 10 + math.floor(math.log(a.raw_num + 1) * 6))
				st = worse(st, (a.raw_num >= 10) and "danger" or "warn")
			elseif id == 187 then
				penalty = penalty + 10
				st = worse(st, "warn")
			end
		end
	end
	if #bad > 0 then dev.bad_attrs = table.concat(bad, ", ") end

	-- 3) 归一化值低于阈值也算异常
	for _, a in ipairs(dev.attrs or {}) do
		if a.value and a.thresh and a.thresh > 0 and a.value <= a.thresh then
			st = worse(st, "danger")
			dev.threshold_fail = (dev.threshold_fail and dev.threshold_fail .. ", " or "")
				.. (a.cn or a.name or tostring(a.id))
		end
	end

	-- 4) 计算健康度
	if dev.life then
		dev.health_pct = math.max(0, math.min(100, dev.life - penalty))
		if dev.life <= cfg.life_crit then st = worse(st, "danger")
		elseif dev.life <= cfg.life_warn then st = worse(st, "warn") end
	else
		dev.health_pct = math.max(0, 100 - penalty)
		dev.health_estimated = true      -- 标记为“估算值”
	end

	-- 5) 温度判定
	if dev.temp then
		if dev.temp >= cfg.temp_crit then st = worse(st, "danger")
		elseif dev.temp >= cfg.temp_warn then st = worse(st, "warn") end
	end

	if st == "unknown" then st = "good" end
	return st
end

--- 传统文本输出解析（当 -j 不可用时的回退路径）
local function parse_smart_text(txt, dev, cfg)
	dev.source = "smartctl(text)"

	dev.model    = txt:match("Device Model:%s*(.-)\n")
		or txt:match("Model Number:%s*(.-)\n")
		or txt:match("Product:%s*(.-)\n") or dev.model
	dev.serial   = txt:match("Serial Number:%s*(.-)\n") or dev.serial
	dev.firmware = txt:match("Firmware Version:%s*(.-)\n") or dev.firmware
	dev.model    = trim(dev.model or "") ~= "" and trim(dev.model) or dev.model

	local st = "unknown"
	local hs = txt:match("SMART overall%-health self%-assessment test result:%s*(%u+)")
		or txt:match("SMART Health Status:%s*(%u+)")
	if hs then
		dev.smart_passed = (hs == "PASSED" or hs == "OK")
		st = dev.smart_passed and "good" or "danger"
	end

	-- 通用字段
	local t = txt:match("Temperature:%s*(%d+) Celsius")
		or txt:match("Current Temperature:%s*(%d+) Celsius")
		or txt:match("Temperature_Celsius%s+0x%x+%s+%d+%s+%d+%s+%d+%s+%S+%s+%S+%s+%S+%s+(%d+)")
	if t then dev.temp = tonumber(t) end

	local h = txt:match("Power On Hours:%s*([%d,]+)")
		or txt:match("Power_On_Hours%s+0x%x+%s+%d+%s+%d+%s+%d+%s+%S+%s+%S+%s+%S+%s+(%d+)")
	if h then dev.hours = tonumber((h:gsub(",", ""))) end

	local pc = txt:match("Power Cycles:%s*([%d,]+)")
	if pc then dev.power_cycles = tonumber((pc:gsub(",", ""))) end

	-- NVMe 文本格式
	local used = txt:match("Percentage Used:%s*(%d+)%%")
	if used then
		dev.used_pct = tonumber(used)
		dev.life = math.max(0, 100 - dev.used_pct)
		dev.health_pct = dev.life
	end
	local spare = txt:match("Available Spare:%s*(%d+)%%")
	if spare then dev.spare = tonumber(spare) end
	local cw = txt:match("Critical Warning:%s*0x(%x+)")
	if cw then dev.critical_warning = tonumber(cw, 16) end
	local me = txt:match("Media and Data Integrity Errors:%s*([%d,]+)")
	if me then dev.media_errors = tonumber((me:gsub(",", ""))) end
	local duw = txt:match("Data Units Written:%s*([%d,]+)")
	if duw then
		dev.written = M.fmt_size(tonumber((duw:gsub(",", ""))) * 512 * 1000)
	end

	-- ATA 属性表：ID# ATTRIBUTE_NAME FLAG VALUE WORST THRESH TYPE UPDATED WHEN_FAILED RAW_VALUE
	local by_id = {}
	dev.attrs = {}
	for line in txt:gmatch("[^\n]+") do
		local id, nm, _, val, wst, thr, rest =
			line:match("^%s*(%d+)%s+(%S+)%s+(0x%x+)%s+(%d+)%s+(%d+)%s+(%d+)%s+(.+)$")
		if id then
			local raw = rest:match("(%S+)%s*$") or ""
			-- WHEN_FAILED 字段可能是 "-" 或 "FAILING_NOW"，raw 取最后一段
			local rawnum = tonumber((raw:match("^(%d+)") or ""))
			local item = {
				id      = tonumber(id),
				name    = nm,
				cn      = M.ATTR_NAMES[tonumber(id)],
				value   = tonumber(val),
				worst   = tonumber(wst),
				thresh  = tonumber(thr),
				raw     = raw,
				raw_num = rawnum,
			}
			table.insert(dev.attrs, item)
			by_id[item.id] = item
			if rest:match("FAILING_NOW") then st = worse(st, "danger") end
		end
	end

	if #dev.attrs > 0 then
		st = M.eval_ata(dev, by_id, cfg, st)
	else
		-- NVMe 分支的健康判定
		if (dev.critical_warning or 0) ~= 0 then st = worse(st, "danger") end
		if dev.spare and dev.spare < 10 then st = worse(st, "danger") end
		if dev.life then
			if dev.life <= cfg.life_crit then st = worse(st, "danger")
			elseif dev.life <= cfg.life_warn then st = worse(st, "warn") end
		end
		if dev.temp then
			if dev.temp >= cfg.temp_crit then st = worse(st, "danger")
			elseif dev.temp >= cfg.temp_warn then st = worse(st, "warn") end
		end
		if st == "unknown" and dev.smart_passed ~= nil then
			st = dev.smart_passed and "good" or "danger"
		end
	end

	dev.status = st
	return true
end

--- SATA / NVMe / USB 统一采集入口
function M.probe_smart(dev, cfg)
	if not M.have_cmd("smartctl") then
		dev.status = "unknown"
		dev.error  = "smartmontools 未安装"
		return dev
	end

	-- 第一次尝试：JSON 输出
	local out, rc = run(smart_cmd(dev.path, "-j", cfg))

	-- USB 桥接芯片经常需要显式指定 -d sat；识别失败时重试
	local need_sat = (out == "" ) or out:match("Unknown USB bridge")
		or out:match("Please specify device type with the %-d option")
	if need_sat then
		local o2 = run(smart_cmd(dev.path, "-j -d sat", cfg))
		if o2 and o2:match("^%s*{") then out = o2 end
	end

	if out and out:match("^%s*{") then
		local okp, done = pcall(parse_smart_json, out, dev, cfg)
		if okp and done then
			dev.raw_ok = true
			return dev
		end
		M.log("JSON 解析失败，回退文本模式: " .. dev.name)
	end

	-- 回退：传统文本输出
	out, rc = run(smart_cmd(dev.path, nil, cfg))
	if need_sat or (out == "" or not out:match("smartctl")) then
		local o2 = run(smart_cmd(dev.path, "-d sat", cfg))
		if o2 and o2:match("smartctl") then out = o2 end
	end

	-- 休眠盘：rc 位 1 置位且提示 STANDBY
	if out and out:match("Device is in STANDBY") then
		dev.status = "unknown"
		dev.error  = "磁盘处于休眠状态，未唤醒检测"
		return dev
	end

	if not out or trim(out) == "" then
		dev.status = "unknown"
		dev.error  = "获取失败（smartctl 无输出，退出码 " .. tostring(rc) .. "）"
		M.log("smartctl 无输出: " .. dev.path .. " rc=" .. tostring(rc))
		return dev
	end

	if out:match("Unavailable %- device lacks SMART capability")
		or out:match("SMART support is: Unavailable") then
		dev.status = "unknown"
		dev.error  = "该设备不支持 SMART"
		return dev
	end

	local okp = pcall(parse_smart_text, out, dev, cfg)
	if not okp then
		dev.status = "unknown"
		dev.error  = "解析 smartctl 输出失败"
		M.log("解析 smartctl 文本失败: " .. dev.path)
	end
	return dev
end

-- ================================================================
-- 四、eMMC / SD 后端
-- ================================================================

-- EXT_CSD_PRE_EOL_INFO 取值含义
local PRE_EOL = {
	[0] = { text = "未定义", st = "unknown" },
	[1] = { text = "正常",   st = "good"   },
	[2] = { text = "警告（保留块已消耗 80%）", st = "warn"   },
	[3] = { text = "紧急（保留块即将耗尽）",   st = "danger" },
}

--- 把 DEVICE_LIFE_TIME_EST 的等级值(1~11)换算成剩余寿命百分比
-- 0x01 = 已使用 0%~10%，0x02 = 10%~20% …… 0x0A = 90%~100%，0x0B = 已超出寿命
local function life_from_est(v)
	if not v or v < 1 then return nil, nil end
	if v >= 11 then return 0, "已超出设计寿命" end
	local left = 100 - (v - 1) * 10
	local desc = string.format("已使用 %d%%~%d%%", (v - 1) * 10, v * 10)
	return left, desc
end

--- 优先从 sysfs 读取 eMMC 寿命（新内核 mmc 驱动直接暴露，无需 mmc-utils）
local function emmc_sysfs(dev)
	local d = "/sys/block/" .. dev.name .. "/device/"
	local lt = readf(d .. "life_time")        -- 形如 "0x01 0x01"
	local eol = readf(d .. "pre_eol_info")    -- 形如 "0x01"
	if not lt and not eol then return false end

	dev.source = "sysfs"
	if lt then
		local a, b = lt:match("0x(%x+)%s+0x(%x+)")
		if not a then a = lt:match("0x(%x+)") end
		local va = tonumber(a or "", 16)
		local vb = tonumber(b or "", 16)
		-- Type A = SLC 区块，Type B = MLC 区块，取更差的一个
		local best = nil
		if va and va > 0 then best = va end
		if vb and vb > 0 then best = math.max(best or 0, vb) end
		if best then
			local left, desc = life_from_est(best)
			dev.life = left
			dev.life_desc = desc
			dev.health_pct = left
		end
		dev.life_raw = lt
	end
	if eol then
		local v = tonumber(eol:match("0x(%x+)") or eol, 16) or tonumber(eol)
		local info = PRE_EOL[v or -1]
		if info then
			dev.eol_text = info.text
			dev.status = worse(dev.status or "unknown", info.st)
		end
	end
	return true
end

--- 回退方案：调用 mmc-utils 读取 EXT_CSD
local function emmc_mmc_utils(dev, cfg)
	if not M.have_cmd("mmc") then return false end
	local out, rc = run("mmc extcsd read " .. dev.path)
	if not out or trim(out) == "" then
		M.log("mmc extcsd read 无输出: " .. dev.path .. " rc=" .. tostring(rc))
		return false
	end
	dev.source = "mmc extcsd"
	dev.raw_ok = true

	-- 兼容 mmc-utils 不同版本的两种输出格式：
	--   eMMC Life Time Estimation A [EXT_CSD_DEVICE_LIFE_TIME_EST_TYP_A]: 0x01
	--   Device life time estimation type A [DEVICE_LIFE_TIME_EST_TYP_A: 0x01]
	local function grab(key)
		local s = out:match(key .. "[^\n]-0x(%x+)")
		return tonumber(s or "", 16)
	end

	local va = grab("LIFE_TIME_EST_TYP_A")
	local vb = grab("LIFE_TIME_EST_TYP_B")
	local best = nil
	if va and va > 0 then best = va end
	if vb and vb > 0 then best = math.max(best or 0, vb) end
	if best then
		local left, desc = life_from_est(best)
		dev.life = left
		dev.life_desc = desc
		dev.health_pct = left
		dev.life_raw = string.format("A=0x%02x B=0x%02x", va or 0, vb or 0)
	end

	local eol = grab("PRE_EOL_INFO")
	local info = PRE_EOL[eol or -1]
	if info then
		dev.eol_text = info.text
		dev.status = worse(dev.status or "unknown", info.st)
	end

	return (best ~= nil) or (info ~= nil)
end

--- eMMC / SD 采集入口
function M.probe_mmc(dev, cfg)
	dev.status = dev.status or "unknown"

	-- eMMC 没有通电小时数寄存器，明确置为不可用
	dev.hours_na = true

	-- 补充制造商 / 生产日期等信息
	local d = "/sys/block/" .. dev.name .. "/device/"
	dev.firmware = dev.firmware or readf(d .. "fwrev")
	dev.mfg_date = readf(d .. "date")
	dev.mfg_id   = readf(d .. "manfid")

	if dev.type == "SD" then
		dev.status = "unknown"
		dev.error  = "SD/TF 卡不提供标准健康信息（无 SMART / EXT_CSD 寿命寄存器）"
		return dev
	end

	-- 1) 先试 sysfs（零依赖）
	local ok1 = false
	pcall(function() ok1 = emmc_sysfs(dev) end)

	-- 2) sysfs 拿不到寿命时再调 mmc-utils
	if not dev.life then
		local ok2 = false
		pcall(function() ok2 = emmc_mmc_utils(dev, cfg) end)
		if not ok1 and not ok2 then
			dev.status = "unknown"
			if not M.have_cmd("mmc") then
				dev.error = "mmc-utils 未安装，且内核未导出寿命信息"
			else
				dev.error = "获取失败（该 eMMC 未实现寿命寄存器，常见于旧版 eMMC 4.4 及以下）"
			end
			return dev
		end
	end

	-- 3) 根据剩余寿命做最终状态判定
	if dev.life then
		if dev.life <= cfg.life_crit then
			dev.status = worse(dev.status, "danger")
		elseif dev.life <= cfg.life_warn then
			dev.status = worse(dev.status, "warn")
		else
			dev.status = worse(dev.status, "good")
		end
	end
	if dev.status == "unknown" and dev.eol_text then dev.status = "good" end

	return dev
end

-- ================================================================
-- 五、统一采集入口 + 缓存
-- ================================================================

--- 按设备类型分派到对应后端（第 3.4 节的优先级逻辑）
function M.probe(dev, cfg)
	cfg = cfg or M.config()
	local t = dev.type
	if t == "eMMC" or t == "SD" then
		return M.probe_mmc(dev, cfg)
	elseif t == "NVMe" or t == "SATA" or t == "USB" or t == "VirtIO" then
		return M.probe_smart(dev, cfg)
	else
		dev.status = "unknown"
		dev.error  = "未识别的设备类型，跳过健康检测"
		return dev
	end
end

--- 采集全部设备信息，返回可直接 JSON 序列化的表
-- @param force  true 时忽略缓存强制重新采集
function M.collect(force)
	local cfg   = M.config()
	local jsonc = require "luci.jsonc"

	-- 读缓存：smartctl 调用有开销（且可能唤醒硬盘），默认 60 秒内复用
	if not force and cfg.cache_ttl > 0 then
		local raw = fs.readfile(M.CACHE_FILE)
		if raw then
			local ok, c = pcall(function() return jsonc.parse(raw) end)
			if ok and type(c) == "table" and tonumber(c.time or 0) then
				if (os.time() - tonumber(c.time)) < cfg.cache_ttl then
					c.cached = true
					return c
				end
			end
		end
	end

	local result = {
		time      = os.time(),
		cached    = false,
		deps      = {
			smartctl = M.have_cmd("smartctl"),
			mmc      = M.have_cmd("mmc"),
			block    = M.have_cmd("block"),
		},
		devices   = {},
		mtd       = {},
		summary   = { total = 0, good = 0, warn = 0, danger = 0, unknown = 0 },
	}

	local devs = M.list_devices()
	for _, dev in ipairs(devs) do
		local ok, err = pcall(function() M.probe(dev, cfg) end)
		if not ok then
			dev.status = "unknown"
			dev.error  = "获取失败（内部异常）"
			M.log("probe 异常 " .. tostring(dev.name) .. ": " .. tostring(err))
		end

		-- 归一化输出字段，前端不需要再做判空
		dev.status      = dev.status or "unknown"
		dev.status_text = M.status_text(dev.status)
		dev.hours_text  = M.fmt_hours(dev.hours) or "N/A"
		dev.temp_text   = dev.temp and (tostring(dev.temp) .. " °C") or "N/A"
		dev.health_text = dev.health_pct and (string.format("%d%%", dev.health_pct)) or "N/A"
		dev.life_text   = dev.life and (string.format("%d%%", dev.life)) or "N/A"

		result.summary.total = result.summary.total + 1
		result.summary[dev.status] = (result.summary[dev.status] or 0) + 1
		table.insert(result.devices, dev)
	end

	-- NAND / MTD：不支持健康检测，单独列出
	local okm, mtd = pcall(M.list_mtd)
	if okm and mtd then result.mtd = mtd end

	-- 写缓存（失败不影响主流程）
	pcall(function()
		local enc = jsonc.stringify(result)
		if enc then fs.writefile(M.CACHE_FILE, enc) end
	end)

	return result
end

--- 获取某个设备的原始命令输出（详情页“原始信息”用）
function M.raw_output(name)
	-- 只允许纯字母数字的设备名，防止命令注入
	if type(name) ~= "string" or not name:match("^[%w:]+$") then
		return nil, "非法设备名"
	end
	if not fs.access("/sys/block/" .. name) then
		return nil, "设备不存在"
	end

	local cfg  = M.config()
	local path = "/dev/" .. name
	local t    = classify(name)

	if t == "eMMC" or t == "SD" then
		local sysinfo = {}
		local d = "/sys/block/" .. name .. "/device/"
		for _, k in ipairs({ "name", "type", "manfid", "oemid", "date",
		                     "fwrev", "hwrev", "serial", "life_time",
		                     "pre_eol_info", "ocr", "cid", "csd" }) do
			local v = readf(d .. k)
			if v then table.insert(sysinfo, string.format("%-14s = %s", k, v)) end
		end
		local head = "# sysfs (" .. d .. ")\n" .. table.concat(sysinfo, "\n") .. "\n"
		if M.have_cmd("mmc") then
			local out = run("mmc extcsd read " .. path)
			return head .. "\n# mmc extcsd read " .. path .. "\n" .. (out or ""), nil
		end
		return head .. "\n# mmc 命令未安装，无法读取 EXT_CSD\n", nil
	end

	if not M.have_cmd("smartctl") then
		return nil, "smartmontools 未安装"
	end
	local out = run("smartctl -x " .. path)
	if not out or trim(out) == "" then
		out = run("smartctl -x -d sat " .. path)
	end
	if not out or trim(out) == "" then
		return nil, "命令无输出"
	end
	return out, nil
end

--- 列出 MTD 分区（NAND），只做展示，不做健康检测
function M.list_mtd()
	local list = {}
	local content = fs.readfile("/proc/mtd")
	if not content then return list end
	for line in content:gmatch("[^\n]+") do
		-- mtd0: 00080000 00020000 "u-boot"
		local dev, size, esize, nm = line:match("^(mtd%d+):%s+(%x+)%s+(%x+)%s+\"([^\"]*)\"")
		if dev then
			local bytes = tonumber(size, 16) or 0
			table.insert(list, {
				name       = dev,
				path       = "/dev/" .. dev,
				label      = nm,
				size_bytes = bytes,
				size       = M.fmt_size(bytes),
				erasesize  = M.fmt_size(tonumber(esize, 16) or 0),
			})
		end
	end
	return list
end

return M
