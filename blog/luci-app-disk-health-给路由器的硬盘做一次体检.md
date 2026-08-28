---
title: "给你的路由器硬盘做一次体检：我写了一个 LuCI 磁盘健康插件"
date: 2026-08-28
tags: [OpenWrt, ImmortalWrt, iStoreOS, 路由器, NAS, 硬盘健康, SMART, NAND]
categories: [折腾记录]
---

## 起因：路由器里那块没人管的盘

玩软路由的朋友大概都有同款焦虑：N100 小主机里插着一块二手 NVMe，7×24 小时跑着下载和 Docker，它到底还剩多少寿命？温度高不高？写入了多少 TB？——Windows 上有 CrystalDiskInfo，Linux 桌面有 smartctl，可路由器的 LuCI 界面里，什么都没有。

OpenWrt 官方源的 `luci-app-smartinfo` 年久失修，不支持 NVMe JSON 输出，更不认识 eMMC 和 NAND。于是动手自己写了一个：**luci-app-disk-health**。

## 它能做什么

打开 LuCI → 服务 → 磁盘健康，每块盘一张卡片：

- **健康徽章**：良好 / 警告 / 危险，绿黄红三色，扫一眼就知道有没有盘要挂；
- **关键指标**：剩余寿命百分比、通电小时数、当前温度、开机次数、累计写入量；
- **SMART 属性展开**：重映射扇区、坏块这些"死亡预告"异常时会高亮；
- **原始输出弹窗**：一键看 `smartctl -x` 全文，发帖求助直接截图。

支持 NVMe、SATA、USB（自动 sat 桥接重试）、eMMC（sysfs 优先，回退 `mmc extcsd read`）。

## 最难啃的部分：给硬路由的 NAND 估算寿命

x86 软路由好办，SMART 一把梭。但 MTK7981、IPQ8071 这类硬路由只有 raw NAND——它**根本没有**"剩余寿命 %"这种寄存器。

翻内核文档后发现，UBI 层其实暴露了每个 PEB 的**擦除计数（EC）**：`mean_ec`、`max_ec`、坏块数。虽然拿不到精确百分比，但「平均擦除计数 ÷ 颗粒额定擦写次数」足够给出一个可信的估算。额定次数芯片不上报，只能靠人选：

> SLC ≈ 100000 次 ｜ MLC ≈ 10000 次 ｜ TLC ≈ 3000 次 ｜ QLC ≈ 1000 次

所以插件里做了一个按钮组：检测到 NAND 后，卡片上直接出现 **SLC / MLC / TLC / QLC / 自定义**，点一下寿命估算立刻刷新。不确定颗粒就选自定义，填厂商标称值。

（顺带一提：EC 计数重刷固件后会归零，历史磨损会丢——这是 raw NAND 的物理现实，插件里也如实标注了"估算值"。）

## 一场和 .ipk 包格式的搏斗

做这个插件过程中最魔幻的经历，是包格式本身。

最初的 `.ipk` 在 ImmortalWrt 24.10 上传时被 opkg 判 **Malformed package file**。逐字节排查后发现是新版 opkg 改了规矩：

1. 外层不再是 ar 归档，而是 **gzip 包裹的 POSIX tar**（文件头 `1f 8b 08`）；
2. tar 成员必须带 `./` 前缀且**目录项齐全**：`./debian-binary`、`./control.tar.gz`、`./data.tar.gz`；
3. control 里的 postinst / postrm 必须 **0755 权限 + 纯 LF 换行**。

CRLF 换行会让 BusyBox 的维护脚本直接炸掉。最后我写了一个纯 Python 标准库的打包引擎（连 `ar` 命令都不依赖），外加一个"三点校验"脚本把上面三条逐一实测通过，才算彻底驯服了它。这套打包代码也开源在仓库的 `tools/` 里，做其他 LuCI 插件的朋友可以直接抄走。

## 怎么装

按你的系统对号入座，所有包都在项目的 [Releases](https://github.com/sugarfreecoke/luci-app-disk-health/releases) 里：

| 系统 | 包 | 命令 / 操作 |
| --- | --- | --- |
| iStoreOS | `istore/*.tar.gz` | iStore → 手动安装 → 上传 |
| ImmortalWrt 24.10（apk） | `apk/*.apk` | `apk add --allow-untrusted <包>` |
| OpenWrt / ImmortalWrt（opkg） | `opkg/*.ipk` | 网页上传 或 `opkg install <包>` |
| 都不行 | `scripts/*.run` | `chmod +x` 后直接执行，自动识别包管理器 |

建议先装上可选依赖（NAND 机器可以不装）：

```sh
opkg install smartmontools mmc-utils
```

## 怎么删

```sh
# 通用：项目自带的卸载脚本
ssh root@路由IP 'sh -s' < uninstall.sh

# 或者当初用 opkg / apk 正常装的：
opkg remove luci-app-disk-health
apk del luci-app-disk-health
```

iStoreOS 用户直接在商店里点卸载即可。

## 已验证的环境

- **x86_64**：N100 / J4125 软路由（SATA、M.2 NVMe、USB 盒子）
- **ARM 开发板**：RK3566 / RK3399 / RK3528（eMMC、TF 卡）
- **ARM 硬路由**：MT7981 / MT7986 / IPQ6000 / IPQ8071（eMMC / NAND）

兼容 OpenWrt 22.03+、ImmortalWrt 24.10（opkg / apk 都行）、iStoreOS 最新版。

## 写在最后

项目已开源：**[github.com/sugarfreecoke/luci-app-disk-health](https://github.com/sugarfreecoke/luci-app-disk-health)**（Apache-2.0）。

准备提交到 ImmortalWrt 官方源，PR 模板都写好了。如果你也在用硬路由跑下载、当轻 NAS，不妨给盘做个体检——别等数据没了才想起 SMART 这回事。

有问题欢迎来 GitHub 提 Issue，或者直接用插件里的"原始输出"功能把 `smartctl -x` 贴过来，一起排查。
