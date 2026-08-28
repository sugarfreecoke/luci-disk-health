#!/bin/sh
# luci-app-disk-health uninstaller
# 适用于 dh_setup.sh / .run 安装的版本（绕开 opkg 安装，所以 opkg 看不到这个包）
# 等价于 iStore 应用商店的「卸载」按钮
printf '\n==> luci-app-disk-health 卸载器\n'

# 要删除的文件列表（与 data.tar.gz 释放的文件完全一致）
FILES="
/etc/config/disk_health
/usr/lib/lua/luci/controller/disk_health.lua
/usr/lib/lua/luci/model/disk_health.lua
/usr/lib/lua/luci/model/cbi/disk_health.lua
/usr/lib/lua/luci/po/en/disk_health.po
/usr/lib/lua/luci/po/zh_Hans/disk_health.po
/usr/lib/lua/luci/view/disk_health/overview.htm
/usr/share/rpcd/acl.d/luci-app-disk-health.json
"
# 可能存在的空目录
DIRS="
/usr/lib/lua/luci/view/disk_health
/usr/lib/lua/luci/model/cbi
"

removed=0
missing=0
for f in $FILES; do
    if [ -f "$f" ]; then
        rm -f "$f"
        printf '  - removed %s\n' "$f"
        removed=$((removed + 1))
    else
        missing=$((missing + 1))
    fi
done
for d in $DIRS; do
    if [ -d "$d" ] && [ -z "$(ls -A "$d" 2>/dev/null)" ]; then
        rmdir "$d" 2>/dev/null && printf '  - removed empty dir %s\n' "$d"
    fi
done

# 清缓存、reload 服务
rm -rf /tmp/luci-* 2>/dev/null || true
/etc/init.d/rpcd restart  2>/dev/null || true
/etc/init.d/uhttpd restart 2>/dev/null || true

if [ -f /usr/lib/lua/luci/controller/disk_health.lua ]; then
    printf '\n[!!!] 控制器文件仍在，卸载可能未完成，请检查磁盘只读状态。\n'
    exit 1
fi
printf '\n[OK] 已删除 %d 个文件，卸载完成。请刷新 LuCI 页面（左侧菜单「服务」应已不再显示「磁盘健康」）。\n' "$removed"
exit 0
