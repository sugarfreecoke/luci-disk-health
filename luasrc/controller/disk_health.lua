--[[
luci-app-disk-health / Controller
------------------------------------------------------------------
职责：
  1. 注册 LuCI 菜单（服务 -> 磁盘健康）
  2. 提供 JSON 接口给前端 JS 轮询：
       admin/services/disk_health/api/data       全部设备健康数据
       admin/services/disk_health/api/raw/<dev>  单设备原始输出
  3. 所有接口都做异常兜底，返回结构化 JSON 而不是 Lua 500 错误页
--]]

module("luci.controller.disk_health", package.seeall)

function index()
	-- 依赖 luci.model.disk_health，但即使该模块出错也要保证菜单可见
	local page = entry({ "admin", "services", "disk_health" }, firstchild(), _("磁盘健康"), 60)
	page.dependent = false
	-- 注意：iStoreOS 24.10 的 Web 登录用户默认不会被授予自定义 ACL，
	-- 带 acl_depends 的菜单会被静默隐藏。个人路由器上省略该项，让菜单无条件显示。

	entry({ "admin", "services", "disk_health", "overview" },
		template("disk_health/overview"), _("设备总览"), 10)

	entry({ "admin", "services", "disk_health", "settings" },
		cbi("disk_health"), _("设置"), 20)

	-- JSON API（leaf 节点，不出现在菜单里）
	local api = entry({ "admin", "services", "disk_health", "api" }, call("action_api"))
	api.leaf = true
	api.hidden = true
end

--- 统一输出 JSON
local function reply(tbl)
	luci.http.prepare_content("application/json")
	luci.http.write_json(tbl)
end

--- API 分发：/api/data 、/api/raw/<device>
function action_api(...)
	local args = { ... }
	local act  = args[1] or "data"

	-- 延迟 require，避免 model 语法/环境问题导致整个 controller 加载失败
	local ok, dh = pcall(require, "luci.model.disk_health")
	if not ok or not dh then
		reply({
			ok    = false,
			error = "内部模块加载失败：" .. tostring(dh),
		})
		return
	end

	if act == "data" then
		local force = (luci.http.formvalue("refresh") == "1")
		local okc, data = pcall(dh.collect, force)
		if not okc or type(data) ~= "table" then
			dh.log("collect 失败: " .. tostring(data))
			reply({
				ok    = false,
				error = "采集磁盘信息失败，请查看系统日志（logread | grep disk-health）",
			})
			return
		end
		data.ok = true
		reply(data)
		return
	end

	if act == "raw" then
		local name = args[2]
		local out, err = dh.raw_output(name)
		if not out then
			reply({ ok = false, error = err or "获取失败" })
			return
		end
		reply({ ok = true, name = name, raw = out })
		return
	end

	luci.http.status(404, "Not Found")
	reply({ ok = false, error = "未知接口" })
end
