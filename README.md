# luci-app-disk-health

[![License](https://img.shields.io/badge/license-Apache--2.0-blue.svg)](LICENSE)
[![OpenWrt](https://img.shields.io/badge/OpenWrt-22.03%20%7C%2024.10-blue.svg)](https://openwrt.org)
[![iStoreOS](https://img.shields.io/badge/iStoreOS-24.10-orange.svg)](https://istoreos.com)

OpenWrt / iStoreOS 的 LuCI 硬盘健康监控插件。用于监控 x86 与 ARM 平台上
NVMe / SATA / eMMC / USB 存储设备的健康状态、剩余寿命与已通电时长，
让你在路由器 Web 管理界面里直观了解存储设备的真实状况。

---

## 一、功能特性

- **设备总览**：自动发现全部物理块设备（NVMe / SATA / USB / eMMC / SD / MTD），
  以卡片列表展示设备名、型号、容量、接口类型与挂载点。
- **健康状态分级**：良好 / 警告 / 危险，并用绿 / 黄 / 红三色徽章标识。
- **关键指标**：健康度百分比、剩余寿命、已使用时长（通电小时）、当前温度、
  开机次数、累计写入量、可用保留空间等。
- **SMART 属性展开**：可展开查看关键 SMART 属性（重映射扇区数、温度、
  通电时间、坏块等），异常属性会高亮提示。
- **原始输出弹窗**：一键查看 `smartctl -x` 或 `mmc extcsd read` 的原始输出，便于排查。
- **依赖自检**：启动即检测 `smartctl` / `mmc` 是否安装；缺失时在页面顶部给出
  **友好提示**而非抛出 Lua 错误。
- **NAND / SPI 闪存**：MTK / 高通硬路由仅有 NAND，无 SMART/EXT_CSD 寿命寄存器，
  插件会列出 MTD 分区并明确提示“暂不支持健康检测”，不会崩溃。
- **设置页**：可调缓存时间、温度 / 寿命告警阈值、是否跳过休眠盘、是否显示 USB 设备。

---

## 二、设备类型与采集后端

| 设备类型        | 识别特征        | 采集命令 / 数据来源                         |
| --------------- | --------------- | ------------------------------------------- |
| NVMe            | `/dev/nvmeXnY`  | `smartctl -a`（优先 JSON，回退文本）        |
| SATA / 机械盘   | `/dev/sdX`      | `smartctl -a`（优先 JSON，回退文本）        |
| USB 存储        | 总线为 USB      | `smartctl -a -d sat`（自动重试 sat 桥接）   |
| eMMC            | `/dev/mmcblkX`  | 优先 sysfs `life_time/pre_eol_info`，回退 `mmc extcsd read` |
| SD / TF 卡      | `/dev/mmcblkX`（type=SD） | 无标准健康寄存器，提示“不提供健康信息” |
| NAND / SPI 闪存 | `/dev/mtdX`     | 仅列出 `/proc/mtd` 分区，不做健康检测       |

采集优先级严格遵循需求 3.4：
`sd/hd → smartctl` → `nvme → smartctl` → `mmcblk → mmc/sysfs` → `mtd → 跳过`。

---

## 三、目录结构

```
luci-app-disk-health/
├── Makefile                          # OpenWrt SDK 打包（纯脚本包，LUCI_PKGARCH=all）
├── build-ipk.sh                      # 免 SDK，纯 Python 直接打包成 .ipk
├── build-apk.sh                      # 免 SDK，纯 Python 直接打包成 .apk（OpenWrt 新版）
├── make-run.sh                       # 生成 .run 自解压全自包含安装器
├── README.md                         # 本文件
├── luasrc/
│   ├── controller/disk_health.lua    # 菜单入口 + JSON 接口（/api/data、/api/raw）
│   ├── model/
│   │   ├── disk_health.lua           # 硬件抽象层(HAL)：发现/分派/解析/缓存
│   │   └── cbi/disk_health.lua       # 设置页（CBI）
│   └── view/disk_health/overview.htm # 设备总览页面（模板 + 原生 JS 轮询）
├── root/
│   ├── etc/config/disk_health        # 默认 UCI 配置
│   └── usr/share/rpcd/acl.d/
│       └── luci-app-disk-health.json # 访问控制（新 ACL 体系）
├── po/
│   ├── zh_Hans/disk_health.po        # 简体中文（源语言）
│   └── en/disk_health.po             # 英文翻译（可选）
├── tools/
│   └── pack_common.py                # 离线打包引擎（ar/gzip/tar 纯标准库实现）
├── .github/workflows/build.yml        # GitHub Actions：多架构自动构建 ipk
├── LICENSE                            # 许可证（Apache-2.0）
└── CONTRIBUTING.md                    # 贡献指南
```

---

## 四、安装依赖

插件把 `smartmontools` / `mmc-utils` 设为**可选依赖**（NAND 硬路由根本用不到），
缺失时会按设备类型给出提示。建议提前安装：

```sh
opkg update
opkg install smartmontools        # 支持 SATA / NVMe / USB
opkg install mmc-utils            # 支持 eMMC（部分内核已通过 sysfs 暴露寿命，可不装）
```

---

## 五、安装插件（三种方式）

### 方式 A：OpenWrt SDK / 源码树编译（推荐，最规范）

1. 把本目录放到 OpenWrt 源码树：
   ```sh
   # 在 OpenWrt 源码根目录
   mkdir -p package/luci-app-disk-health
   cp -r luci-app-disk-health/* package/luci-app-disk-health/
   ```
2. 更新 feeds 并编译：
   ```sh
   ./scripts/feeds update luci
   ./scripts/feeds install luci-base
   make menuconfig        # 选上 LuCI -> Applications -> luci-app-disk-health
   make package/luci-app-disk-health/compile V=s
   ```
3. 产物在 `bin/packages/<arch>/luci/luci-app-disk-health_*.ipk`。

### 方式 B：免 SDK 离线打包（纯 Python，无需 ar/gzip/SDK）

本仓库自带 `tools/pack_common.py` 打包引擎，**只依赖 Python 标准库**，
即使系统没有 `ar` / `gzip` / `openssl` 也能产出合法安装包。三个薄壳脚本直接调用它：

```sh
# 1) 生成 .ipk（opkg 系，OpenWrt/iStoreOS 通用）
./build-ipk.sh
# 产物：out/luci-app-disk-health_1.0.0-1_all.ipk

# 2) 生成 .apk（apk 系，OpenWrt 24.10+ 新版包管理器）
./build-apk.sh
# 产物：out/luci-app-disk-health_1.0.0-1_all.apk
# 注意：未签名，目标机安装时需 apk add --allow-untrusted <file>

# 3) 生成 .run 自解压全自包含安装器（推荐给最终用户）
./make-run.sh
# 产物：out/luci-app-disk-health_install-1.0.0-1.run
```

> 想一次性三样都出：`python3 tools/pack_common.py all`
> 想校验已生成的包：`python3 tools/pack_common.py verify --file out/xxx.ipk`

### 方式 C：手动放置（仅调试用，不推荐）

```sh
# 在路由器上
mkdir -p /usr/lib/lua/luci/controller /usr/lib/lua/luci/model/cbi \
         /usr/lib/lua/luci/view/disk_health /usr/share/rpcd/acl.d
cp luasrc/controller/disk_health.lua      /usr/lib/lua/luci/controller/
cp luasrc/model/disk_health.lua           /usr/lib/lua/luci/model/
cp luasrc/model/cbi/disk_health.lua       /usr/lib/lua/luci/model/cbi/
cp luasrc/view/disk_health/overview.htm    /usr/lib/lua/luci/view/disk_health/
cp root/etc/config/disk_health            /etc/config/
cp root/usr/share/rpcd/acl.d/luci-app-disk-health.json /usr/share/rpcd/acl.d/
rm -f /tmp/luci-indexcache* /tmp/luci-modulecache/*
```

---

## 六、使用

1. 用 `opkg install` 或 `scp` 上传 `.ipk` 后安装：
   ```sh
   opkg install luci-app-disk-health_1.0.0-1_all.ipk
   ```
   - **.apk（apk 系）**：`apk add --allow-untrusted luci-app-disk-health_1.0.0-1_all.apk`
   - **.run 安装器**：上传到路由器后直接执行，会自动装依赖并装插件：
     ```sh
     chmod +x luci-app-disk-health_install-1.0.0-1.run
     ./luci-app-disk-health_install-1.0.0-1.run
     ```
     `.run` 内置 `.ipk` + `.apk`，运行时会自动检测 `opkg`/`apk` 并选对应文件；
     依赖 `smartmontools`/`mmc-utils` 优先用离线 `deps/` 目录（把对应 `.ipk`/`.apk`
     放进该目录，再 `./make-run.sh --deps ./deps` 即可打入），否则尝试在线安装。
2. 浏览器打开路由器 LuCI → **服务 → 磁盘健康**。
3. 页面首屏立即出现，采集（smartctl 可能耗时数秒）在后台进行；可点“重新检测”
   强制刷新，或勾选“每 60 秒自动刷新”。
4. 进入 **服务 → 磁盘健康 → 设置** 调整采集行为与告警阈值。

---

## 七、常见问题

- **提示 “SMART 工具未安装”**：执行 `opkg install smartmontools` 后刷新页面。
- **eMMC 显示 N/A**：旧版 eMMC 4.4 及以下未实现寿命寄存器；新版内核通过
  sysfs 暴露寿命，若仍无则装 `mmc-utils` 读取 EXT_CSD。
- **“NAND 闪存健康检测暂不支持”**：MT7981 / IPQ6000 等硬路由只有 NAND，
  没有 SMART/EXT_CSD 类寿命寄存器，这是硬件限制，仅能列出分区。
- **页面空白 / 报错**：查看日志 `logread | grep disk-health`，通常是命令缺失或
  输出异常，插件已对所有异常做容错，不会返回 Lua 500 错误页。

- **安装显示成功却 404（No page is registered at '/admin/.../disk_health'）**：
  说明 LuCI 没加载到控制器文件，即文件其实没装进 `/usr/lib/lua/luci/...`。
  多因目标机 opkg 拒绝了我们手打的 `.ipk`（旧版曾报 `Malformed package file`），
  而安装器的「保底释放」逻辑当时依赖 `PIPESTATUS`（BusyBox ash 中为空 → 误判成功）导致没触发。
  **修复版安装器已改为「以控制器文件是否真实存在为准」的保底**，可彻底解决。
  若仍异常，SSH 进路由手动修复（最稳妥）：
  ```sh
  # 方式一：直接把 .ipk 内的 data.tar.gz 释放到系统
  opkg install /tmp/luci-app-disk-health_*.ipk 2>/dev/null || \
    ( cd /tmp && tar -xzf "$(opkg status luci-app-disk-health >/dev/null 2>&1; echo /dev/null)" 2>/dev/null )
  # 更直接的兜底（从 .run 解出的 data.tar.gz）：
  tar -xzf /path/to/data.tar.gz -C /
  rm -f /tmp/luci-indexcache /tmp/luci-modulecache
  /etc/init.d/rpcd restart
  /etc/init.d/uhttpd restart
  ```
  重装或修复后**务必浏览器 `Ctrl+F5` 强刷**，再进「服务 → 磁盘健康」。

---

## 八、适配平台

- **x86_64**：N100 / J4125 等迷你主机（SATA、M.2 NVMe、USB）。
- **ARM 开发板 / 迷你路由**：RK3566 / RK3399 / RK3528（eMMC、MicroSD、USB，
  部分支持 M.2 NVMe）。
- **ARM 硬路由刷机方案**：MT7981 / MT7986 / IPQ6000 / IPQ8071（仅 eMMC / NAND，
  无 SATA/NVMe）。

兼容 OpenWrt 22.03 及以上与 iStoreOS 最新版。
