# luci-app-disk-health · 磁盘健康

[![License](https://img.shields.io/badge/license-Apache--2.0-blue.svg)](LICENSE)
[![Version](https://img.shields.io/badge/version-1.0.0-green.svg)](release-v1.0.0/)
[![OpenWrt](https://img.shields.io/badge/OpenWrt-22.03%20%7C%2024.10-blue.svg)](https://openwrt.org)
[![ImmortalWrt](https://img.shields.io/badge/ImmortalWrt-24.10-purple.svg)](https://immortalwrt.org)
[![iStoreOS](https://img.shields.io/badge/iStoreOS-24.10-orange.svg)](https://istoreos.com)
[![Maintainer](https://img.shields.io/badge/maintainer-sugarfreecoke-8A2BE2.svg)](https://github.com/sugarfreecoke)

一个面向 **OpenWrt / ImmortalWrt / iStoreOS** 的 LuCI 硬盘健康监控插件。
在路由器 Web 管理界面里直观查看 NVMe / SATA / eMMC / USB / NAND 存储设备的
健康状态、剩余寿命、通电时长与温度——**连 MTK / 高通硬路由的 raw NAND 也能估算寿命**。

> 维护者：[sugarfreecoke](https://github.com/sugarfreecoke) ｜ 许可证：Apache-2.0
>
> 想把它提交进 ImmortalWrt 官方源？请看 **[docs/ImmortalWrt提交指南.md](docs/ImmortalWrt提交指南.md)**（含可直接复制的 PR 描述与论坛帖模板）。

---

## ✨ 功能特性

- **设备总览**：自动发现全部物理块设备（NVMe / SATA / USB / eMMC / SD / MTD），卡片式展示设备名、型号、容量、接口类型与挂载点。
- **健康状态分级**：良好 / 警告 / 危险，绿 / 黄 / 红三色徽章一目了然。
- **关键指标**：健康度百分比、剩余寿命、通电小时数、当前温度、开机次数、累计写入量、可用保留空间等。
- **SMART 属性展开**：可展开查看重映射扇区数、温度、通电时间、坏块等关键 SMART 属性，异常高亮提示。
- **原始输出弹窗**：一键查看 `smartctl -x` 或 `mmc extcsd read` 原始输出，便于排查。
- **NAND 闪存寿命估算**：UBI 管理型 NAND 读取平均 / 最大擦除计数与坏块数估算剩余寿命；裸 MTD 读取坏块与 ECC 失败次数。页面明确标注"估算值"。
- **NAND 闪存类型一键切换**：检测到 NAND 时，设备卡片内提供 **SLC / MLC / TLC / QLC / 自定义** 按钮组（SLC≈100000 / MLC≈10000 / TLC≈3000 / QLC≈1000 次额定擦写），选择后寿命估算立即刷新；也可在设置页选择。
- **依赖自检**：启动即检测 `smartctl` / `mmc` 是否安装，缺失时给出友好提示而非报错。
- **设置页**：缓存时间、温度 / 寿命告警阈值、是否跳过休眠盘、是否显示 USB 设备均可调。

### 设备类型与采集后端

| 设备类型 | 识别特征 | 采集命令 / 数据来源 |
| --- | --- | --- |
| NVMe | `/dev/nvmeXnY` | `smartctl -a`（优先 JSON，回退文本） |
| SATA / 机械盘 | `/dev/sdX` | `smartctl -a`（优先 JSON，回退文本） |
| USB 存储 | 总线为 USB | `smartctl -a -d sat`（自动重试 sat 桥接） |
| eMMC | `/dev/mmcblkX` | 优先 sysfs `life_time/pre_eol_info`，回退 `mmc extcsd read` |
| SD / TF 卡 | `/dev/mmcblkX`（type=SD） | 无标准健康寄存器，提示"不提供健康信息" |
| NAND / SPI 闪存 | `/dev/mtdX` | UBI 管理型读 `max_ec`/`mean_ec`/`bad_peb_count` 估算寿命；裸 MTD 读坏块 / ECC 失败（仅提示） |

### 已验证适配平台

| 平台 | 典型硬件 | 支持的检测 |
| --- | --- | --- |
| x86_64 | N100 / J4125 迷你主机 | SATA、M.2 NVMe、USB |
| ARM 开发板 | RK3566 / RK3399 / RK3528 | eMMC、MicroSD、USB，部分 M.2 NVMe |
| ARM 硬路由 | MT7981 / MT7986 / IPQ6000 / IPQ8071 | eMMC / NAND（NAND 经 UBI 擦除计数估算寿命） |

---

## 📦 第一步：选对安装包

所有安装包都在 [`release-v1.0.0/`](release-v1.0.0/) 目录（或 GitHub Releases 页），按你的系统对号入座：

| 你的系统 | 用哪个包 | 安装方式 |
| --- | --- | --- |
| **iStoreOS / 带iStore的固件** | `istore/istore-app-disk-health-v1.0.0.tar.gz`（或 `.zip`） | iStore 商店 → 手动上传安装（**不要传裸 .ipk**，会被判 Malformed） |
| **ImmortalWrt 24.10（apk 包管理器）** | `apk/luci-app-disk-health_1.0.0-1_all.apk` | SSH：`apk add --allow-untrusted` |
| **原生 OpenWrt / ImmortalWrt（opkg）** | `opkg/luci-app-disk-health_1.0.0-1_all.ipk` | 网页上传 或 `opkg install`（已按新版 opkg 格式验证） |
| **不确定 / 上述都不行** | `scripts/luci-app-disk-health_install-1.0.0-1.run` | SSH 直接执行的自解压安装器，自动检测 opkg / apk |
| **终极兜底** | `scripts/dh_setup.sh` | SSH 一行 `sh dh_setup.sh`，自动装依赖 + 释放文件 |

> 📄 各包的 MD5 校验值见 [`release-v1.0.0/MANIFEST.txt`](release-v1.0.0/MANIFEST.txt)；
> `.ipk` 已通过三点结构校验（gzip 文件头 `1f8b08` / 外层三成员 `./debian-binary`+`./control.tar.gz`+`./data.tar.gz` / postinst 0755+LF），兼容 ImmortalWrt 24.10 的新版 opkg。

---

## 🚀 第二步：安装

### 安装前：可选依赖

插件把 `smartmontools` / `mmc-utils` 设为**可选依赖**（NAND 硬路由用不到），缺失时会在页面顶部提示。建议提前安装：

```sh
opkg update
opkg install smartmontools   # SATA / NVMe / USB 检测
opkg install mmc-utils       # eMMC 检测（部分内核已通过 sysfs 暴露寿命，可不装）
```

### 方式 1 · iStoreOS（图形界面，最简单）

1. 下载 `istore/istore-app-disk-health-v1.0.0.tar.gz` 到电脑；
2. 打开 LuCI → **iStore** → 右上角 **手动安装** → 上传该文件；
3. 安装完成后在 **服务 → 磁盘健康** 打开。商店内自带卸载按钮。

### 方式 2 · ImmortalWrt 24.10（apk 包管理器）

```sh
# 电脑上把包传到路由器
scp apk/luci-app-disk-health_1.0.0-1_all.apk root@<路由IP>:/tmp/
# SSH 进路由器安装
ssh root@<路由IP>
apk add --allow-untrusted /tmp/luci-app-disk-health_1.0.0-1_all.apk
```

### 方式 3 · 原生 OpenWrt / ImmortalWrt（opkg）

**网页上传**：LuCI → 系统 → 软件包 → 上传软件包 → 选择 `.ipk` 文件 → 安装。

**或 SSH 命令行**：

```sh
scp opkg/luci-app-disk-health_1.0.0-1_all.ipk root@<路由IP>:/tmp/
ssh root@<路由IP> 'opkg install /tmp/luci-app-disk-health_1.0.0-1_all.ipk'
```

### 方式 4 · 自解压安装器（.run，通用）

```sh
scp scripts/luci-app-disk-health_install-1.0.0-1.run root@<路由IP>:/tmp/
ssh root@<路由IP> 'chmod +x /tmp/luci-app-disk-health_install-1.0.0-1.run && /tmp/luci-app-disk-health_install-1.0.0-1.run'
```

安装器内置 `.ipk` + `.apk` 双包，运行时自动检测 `opkg` / `apk` 选择对应文件；
若 opkg 拒绝安装，会自动"保底释放"文件到系统，并以**控制器文件是否真实存在**为成功标准。

### 方式 5 · 一行脚本兜底（dh_setup.sh）

```sh
ssh root@<路由IP> 'sh -s' < scripts/dh_setup.sh
```

自动检测包管理器、安装依赖、释放插件文件，任何平台都能用。

### 安装后

- 浏览器打开 LuCI → **服务 → 磁盘健康**；
- 页面首屏立即出现，采集（smartctl 可能耗时数秒）在后台进行；
- 可点 **重新检测** 强制刷新，或勾选 **每 60 秒自动刷新**；
- 若列表为空或 404，先 `Ctrl+F5` 强刷浏览器缓存。

---

## 🗑️ 卸载

**方式一：卸载脚本（推荐，与任何安装方式兼容）**

```sh
ssh root@<路由IP> 'sh -s' < scripts/uninstall.sh
```

**方式二：包管理器卸载（当初是 opkg / apk 正常安装的）**

```sh
opkg remove luci-app-disk-health
# 或 apk 系：
apk del luci-app-disk-health
```

**方式三：iStoreOS**：iStore 商店 → 已安装 → 磁盘健康 → 卸载按钮。

> 卸载脚本会移除插件文件与 UCI 配置，不涉及任何网络/IP 操作，可放心在路由器终端直接粘贴执行。

---

## 📖 使用指南

1. **总览页**：每块盘一张卡片，展示健康徽章、温度、寿命、通电时长；点击卡片可展开 SMART 属性。
2. **NAND 硬路由**：检测到 NAND 时卡片内出现 **SLC / MLC / TLC / QLC / 自定义** 按钮，按实际闪存颗粒选择即可；不确定时选"自定义"并填入厂商标称的 P/E 循环次数（TLC 常见 3000 次）。
3. **设置页**（服务 → 磁盘健康 → 设置）：缓存时间、温度 / 寿命告警阈值、跳过休眠盘、显示 USB 设备。
4. **原始输出**：卡片内"查看原始输出"可看 `smartctl -x` 全文，方便发帖求助时附上。

### NAND 寿命为什么是"估算值"？

raw NAND 不像 NVMe SMART 或 eMMC EXT_CSD 有标准的"剩余寿命 %"寄存器。
UBI 管理型 NAND 暴露**擦除计数（EC）**，本插件用「平均擦除计数 ÷ 额定擦写次数」估算；
额定次数芯片不上报，需按颗粒类型选择。注意：EC 计数在重刷 / 格式化后会归零，历史磨损会丢失。

---

## ❓ 常见问题

<details>
<summary><b>提示 "SMART 工具未安装"</b></summary>

执行 `opkg install smartmontools` 后刷新页面。
</details>

<details>
<summary><b>eMMC 显示 N/A</b></summary>

旧版 eMMC 4.4 及以下未实现寿命寄存器；新版内核通过 sysfs 暴露寿命，若仍无则装 `mmc-utils` 读取 EXT_CSD。
</details>

<details>
<summary><b>安装显示成功，但页面 404（No page is registered at '/admin/.../disk_health'）</b></summary>

说明控制器文件没真正装进 `/usr/lib/lua/luci/...`。用 `.run` 安装器重装（新版已改为以控制器文件存在为成功标准），或 SSH 手动兜底：

```sh
tar -xzf /tmp/data.tar.gz -C /        # 从安装包解出的 data.tar.gz
rm -f /tmp/luci-indexcache* /tmp/luci-modulecache*
/etc/init.d/rpcd restart && /etc/init.d/uhttpd restart
```

然后浏览器 `Ctrl+F5` 强刷。
</details>

<details>
<summary><b>iStoreOS 网页上传 .ipk 报 Malformed package file</b></summary>

这是 iStoreOS 上传页的已知行为，不是包的问题。请改用 `istore/` 下的商店包上传，或用 `scripts/` 下的 SSH 方式安装。
</details>

<details>
<summary><b>页面空白 / 报错</b></summary>

查看 `logread | grep disk-health`。插件已对所有异常做容错，不会返回 Lua 500 错误页。
</details>

---

## 🔨 从源码构建

### 免 SDK 离线打包（纯 Python 标准库）

```sh
./build-ipk.sh    # 生成 .ipk（opkg 系）
./build-apk.sh    # 生成 .apk（apk 系）
./make-run.sh     # 生成 .run 自解压安装器
# 一次性全出：python3 tools/pack_common.py all
# 校验包结构：python3 tools/pack_common.py verify --file out/xxx.ipk
```

### OpenWrt SDK / 源码树编译

```sh
cp -r luci-app-disk-health/ <openwrt>/package/luci-app-disk-health/
cd <openwrt>
make menuconfig   # LuCI -> Applications -> luci-app-disk-health
make package/luci-app-disk-health/compile V=s
```

### 校验脚本

```sh
python tools/verify_three_points.py   # ipk 三点结构校验
python tools/lua_syntax_check.py      # Lua 语法校验
```

---

## 📁 项目结构

```
luci-app-disk-health/
├── Makefile                          # OpenWrt SDK 打包（纯脚本包，LUCI_PKGARCH=all）
├── build-ipk.sh / build-apk.sh / make-run.sh   # 免 SDK 打包入口
├── luasrc/
│   ├── controller/disk_health.lua    # 菜单入口 + JSON 接口（/api/data、/api/raw、set_nand）
│   ├── model/disk_health.lua         # 硬件抽象层：设备发现 / 分派 / 解析 / 缓存
│   ├── model/cbi/disk_health.lua     # 设置页（CBI）
│   └── view/disk_health/overview.htm # 总览页（模板 + 原生 JS）
├── root/
│   ├── etc/config/disk_health        # 默认 UCI 配置
│   └── usr/share/rpcd/acl.d/luci-app-disk-health.json   # rpcd ACL
├── po/zh_Hans/ · po/en/              # 翻译
├── tools/                            # 打包引擎 + 校验脚本（纯 Python 标准库）
├── release-v1.0.0/                   # ✅ 预编译发布包（按平台分类 + MANIFEST）
├── docs/                             # 说明页(index.html) / 提交指南 / 上游计划
├── blog/                             # 博客分享文章
├── .github/workflows/build.yml       # GitHub Actions 自动构建
├── LICENSE                           # Apache-2.0
└── CONTRIBUTING.md                   # 贡献指南
```

---

## 🤝 贡献与社区

- 欢迎 Issue / PR，提交规范见 [CONTRIBUTING.md](CONTRIBUTING.md)；
- 提交到 ImmortalWrt 官方源的完整流程与 PR / 论坛帖模板见 [docs/ImmortalWrt提交指南.md](docs/ImmortalWrt提交指南.md)；
- 插件可视化介绍页（可部署到 GitHub Pages）：[docs/index.html](docs/index.html)。

## 📄 许可证

[Apache-2.0](LICENSE) © 2026 [sugarfreecoke](https://github.com/sugarfreecoke)
