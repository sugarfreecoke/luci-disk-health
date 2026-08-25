# 贡献指南 (Contributing)

感谢你关注 `luci-app-disk-health`！欢迎提交 Issue 与 Pull Request。

## 提交流程

1. Fork 本仓库并 clone 到本地。
2. 新建分支：`git checkout -b fix/xxx` 或 `feat/xxx`。
3. 修改代码，确保：
   - Lua 文件语法正确（可用 `python tools/pack_common.py` 之外的 `luac -p` 校验）；
   - 修改后运行 `./build-ipk.sh` 能正常产出 `.ipk`；
   - 关键逻辑与复杂解析补充中文注释。
4. 提交信息用中文或英文均可，建议说明「为什么改」。
5. 推送分支并发起 Pull Request，描述改动点与测试方法。

## 代码约定

- **菜单路径**：目前注册在 LuCI 左侧「服务 → 磁盘健康」(`admin/services/disk_health`)。
  若调整菜单，需同步修改 `controller/disk_health.lua` 与 `view/disk_health/overview.htm`
  中的 API 路径（`build_url("admin/services/disk_health/api/...")`）。
- **新增设备类型**：在 `luasrc/model/disk_health.lua` 的硬件抽象层新增采集函数，
  并接入 `list_disks()` 的分派逻辑，对外保持统一数据结构。
- **兼容性**：目标机是 BusyBox ash（不是 bash），shell 脚本不要使用 `set +e`、
  `PIPESTATUS`、`echo -e` 等 GNU 增强特性。
- **健壮性**：所有外部命令调用都要容错，单设备失败不得导致整个页面崩溃。

## 许可证

本项目采用 **Apache-2.0**。提交即表示你同意你的贡献在相同许可证下发布。
