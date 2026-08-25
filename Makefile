# SPDX-License-Identifier: Apache-2.0
#
# luci-app-disk-health —— OpenWrt / iStoreOS 硬盘健康监控
#
# 用法（放入 OpenWrt SDK 或源码树的 package/luci-app-disk-health/ 下）：
#   make package/luci-app-disk-health/compile V=s
#
# 说明：
#   * 本包为纯脚本包，LUCI_PKGARCH:=all，一次编译可在 x86_64 / aarch64 /
#     armv7 等所有平台安装。
#   * smartmontools / mmc-utils 故意写成“可选依赖”而不是硬依赖：
#     NAND 硬路由根本不需要 mmc-utils，NAND-only 设备也不需要 smartmontools，
#     插件在缺失时会给出友好提示而不是报错。若希望安装即可用，
#     可把下面 LUCI_DEPENDS 里注释掉的两项打开。

include $(TOPDIR)/rules.mk

PKG_NAME:=luci-app-disk-health
PKG_VERSION:=1.0.0
PKG_RELEASE:=1

PKG_LICENSE:=Apache-2.0
PKG_MAINTAINER:=luci-app-disk-health authors

LUCI_TITLE:=LuCI support for Disk Health Monitor (磁盘健康)
LUCI_DESCRIPTION:=Monitor health, remaining life and power-on hours of NVMe / SATA / eMMC / USB storage devices.
LUCI_DEPENDS:=+luci-base +luci-compat +luci-lib-jsonc
#LUCI_DEPENDS:=+luci-base +luci-compat +luci-lib-jsonc +smartmontools +mmc-utils
LUCI_PKGARCH:=all

define Package/$(PKG_NAME)/conffiles
/etc/config/disk_health
endef

# 安装后清理 LuCI 的菜单/模块缓存，否则新菜单不会立刻出现
define Package/$(PKG_NAME)/postinst
#!/bin/sh
[ -n "$${IPKG_INSTROOT}" ] && exit 0
rm -f /tmp/luci-indexcache* /tmp/luci-modulecache/* 2>/dev/null
rm -f /tmp/luci_disk_health_cache.json 2>/dev/null
exit 0
endef

define Package/$(PKG_NAME)/postrm
#!/bin/sh
rm -f /tmp/luci-indexcache* /tmp/luci-modulecache/* 2>/dev/null
rm -f /tmp/luci_disk_health_cache.json 2>/dev/null
exit 0
endef

include $(TOPDIR)/feeds/luci/luci.mk

# 调用 luci.mk 提供的 BuildPackage
