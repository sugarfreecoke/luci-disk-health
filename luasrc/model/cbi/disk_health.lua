--[[
luci-app-disk-health / CBI 设置页
------------------------------------------------------------------
提供少量可调参数，避免把阈值硬编码在代码里：
  * 缓存时间：smartctl 调用有开销，且可能唤醒休眠硬盘
  * 跳过休眠盘：机械盘节能场景下非常有用（-n standby）
  * 温度 / 寿命阈值：不同盘的容忍度不同，允许用户自行调整

说明：所有面向用户的文字都用 _() 包裹，便于 po/ 目录做国际化翻译。
--]]

local dh = nil
local ok, mod = pcall(require, "luci.model.disk_health")
if ok then dh = mod end

local m = Map("disk_health", _("磁盘健康 - 设置"),
	_("调整磁盘健康页面的采集行为与告警阈值。修改后返回“设备总览”并点击刷新即可生效。"))

-- 依赖状态提示（不抛错，只是友好提示）
if dh then
	local tips = {}
	if dh.have_cmd("smartctl") then
		table.insert(tips, "<span style=\"color:#16a34a\">✔ smartctl 已安装</span>")
	else
		table.insert(tips, "<span style=\"color:#dc2626\">✘ smartctl 未安装（opkg install smartmontools）</span>")
	end
	if dh.have_cmd("mmc") then
		table.insert(tips, "<span style=\"color:#16a34a\">✔ mmc 已安装</span>")
	else
		table.insert(tips, "<span style=\"color:#ca8a04\">△ mmc 未安装（eMMC 可能无法读取寿命，opkg install mmc-utils）</span>")
	end
	m.description = m.description .. "<br /><br />" .. table.concat(tips, " &nbsp;|&nbsp; ")
end

local s = m:section(NamedSection, "main", "disk_health", _("采集设置"))
s.addremove = false
s.anonymous = true

local o = s:option(Value, "cache_ttl", _("数据缓存时间（秒）"),
	_("两次真实采集之间的最小间隔，0 表示不缓存。建议 30~300，避免频繁唤醒硬盘。"))
o.datatype = "uinteger"
o.default  = "60"
o.rmempty  = false

o = s:option(Flag, "skip_standby", _("跳过休眠中的硬盘"),
	_("启用后使用 <code>smartctl -n standby</code>，不会为了读取 SMART 而唤醒已休眠的机械盘。"))
o.default = "0"
o.rmempty = false

o = s:option(Flag, "show_usb", _("显示 USB 存储设备"),
	_("关闭后列表中不再显示 U 盘 / USB 移动硬盘。"))
o.default = "1"
o.rmempty = false

local s2 = m:section(NamedSection, "main", "disk_health", _("告警阈值"))
s2.addremove = false
s2.anonymous = true

o = s2:option(Value, "temp_warn", _("温度警告阈值（°C）"))
o.datatype = "uinteger"
o.default  = "55"
o.rmempty  = false

o = s2:option(Value, "temp_crit", _("温度危险阈值（°C）"))
o.datatype = "uinteger"
o.default  = "65"
o.rmempty  = false

o = s2:option(Value, "life_warn", _("剩余寿命警告阈值（%）"),
	_("剩余寿命低于该值时标记为“警告”。"))
o.datatype = "uinteger"
o.default  = "20"
o.rmempty  = false

o = s2:option(Value, "life_crit", _("剩余寿命危险阈值（%）"),
	_("剩余寿命低于该值时标记为“危险”。"))
o.datatype = "uinteger"
o.default  = "10"
o.rmempty  = false

-- 保存后清理缓存，让新阈值立刻生效
function m.on_after_commit(self)
	pcall(function()
		require("nixio.fs").unlink("/tmp/luci_disk_health_cache.json")
	end)
end

return m
