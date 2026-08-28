# 提交指南：把 luci-app-disk-health 提交到 ImmortalWrt 社区

> 维护者署名：**sugarfreecoke**
> 适用版本：luci-app-disk-health v1.0.0
> 目标平台：OpenWrt 22.03+ / **ImmortalWrt 24.10（opkg 与 apk 均可）** / iStoreOS

本文件给你两条提交路径，并附「可直接复制」的 PR 描述与论坛帖子。
**明天提交前，只需做两件小事**：① 把截图补进帖子模板的占位处；② 确认你要投的仓库地址（见下）。

---

## 〇、提交前自检清单

- [ ] `Makefile` 中 `PKG_MAINTAINER:=sugarfreecoke`（已改好 ✅）
- [ ] `PKG_LICENSE:=Apache-2.0`，源码头部有 `SPDX-License-Identifier`（已具备 ✅）
- [ ] Lua 文件语法无误（`luac -p luasrc/model/disk_health.lua` 不报错）
- [ ] `./build-ipk.sh` 能正常产出 `.ipk`（本地已验证 ✅）
- [ ] `po/zh_Hans/disk_health.po` 与 `po/en/disk_health.po` 关键串齐全
- [ ] 仓库根目录含 `README.md` / `LICENSE` / `CONTRIBUTING.md`（已具备 ✅）
- [ ] 准备 1~2 张截图（设备总览页、NAND 寿命估算页）

---

## 一、路径 A：GitHub PR 到 ImmortalWrt 软件源（推荐，长期可装）

ImmortalWrt 的社区软件源通常是 **`immortalwrt/immortalwrt-packages`**
（提交前请确认该仓库当前是否接受 luci-app 类 PR；若其要求进 luci feed，按对应仓库结构放置即可，目录名保持 `luci-app-disk-health`）。

### 1.1 目录结构（PR 里应呈现的形态）

把本仓库内容放进软件源根目录下的 **`luci-app-disk-health/`**：

```
immortalwrt-packages/
└── luci-app-disk-health/
    ├── Makefile                  # 已含 PKG_MAINTAINER:=sugarfreecoke
    ├── luasrc/
    │   ├── controller/disk_health.lua
    │   ├── model/disk_health.lua
    │   ├── model/cbi/disk_health.lua
    │   └── view/disk_health/overview.htm
    ├── root/
    │   ├── etc/config/disk_health
    │   └── usr/share/rpcd/acl.d/luci-app-disk-health.json
    ├── po/
    │   ├── zh_Hans/disk_health.po
    │   └── en/disk_health.po
    ├── README.md
    ├── LICENSE
    └── CONTRIBUTING.md
```

> 说明：`.github/`、`tools/`、`out/`、`release-v1.0.0/`、`*.rar` 等属于本机构建/发布产物，
> **不需要**提交到软件源（软件源用 OpenWrt 构建系统从 `Makefile` 编译，不用本仓库的 `tools/pack_common.py`）。

### 1.2 可直接复制的 PR 标题与描述

**标题**
```
luci-app-disk-health: add disk health monitor (SMART / eMMC / NAND life)
```

**描述（Markdown，直接粘贴）**
```markdown
### luci-app-disk-health — 磁盘健康监控

在 LuCI「服务 → 磁盘健康」中监控存储设备的健康状态、剩余寿命与通电时长。

**支持的设备类型**
- NVMe / SATA / USB：通过 `smartctl`（JSON 优先，文本回退）读取 SMART
- eMMC：优先 sysfs `life_time`/`pre_eol_info`，回退 `mmc extcsd read`
- **raw NAND（MTK / 高通硬路由）**：UBI 管理型读取平均/最大擦除计数与坏块数
  估算剩余寿命；裸 MTD 读取坏块与 ECC 失败次数。寿命为「估算值」并明确标注。

**特性**
- 设备总览卡片（型号 / 容量 / 接口 / 挂载点）
- 健康分级（良好 / 警告 / 危险）与关键指标（健康度、剩余寿命、通电小时、温度等）
- SMART 属性展开、原始输出弹窗
- 依赖自检（smartmontools / mmc-utils 为可选依赖，缺失时给友好提示）
- 设置页：缓存时间、温度/寿命阈值、跳过休眠盘、显示 USB 等

**技术要点**
- 纯脚本包，`LUCI_PKGARCH:=all`，一次编译全平台可用
- `smartmontools` / `mmc-utils` 设为可选依赖（NAND 硬路由无需安装）
- 已带 GitHub Actions 多架构自动构建（x86_64 / aarch64 / arm）

**测试**
- 在 ImmortalWrt 24.10 (aarch64_cortex-a53, opkg) 上 `opkg install` 后页面正常
- 在 x86_64 OpenWrt 24.10 上 `smartctl` 设备读取正常
- NAND 设备（MT7981）能显示擦除计数估算寿命

Maintainer: @sugarfreecoke
```

---

## 二、路径 B：ImmortalWrt 社区 / 论坛发帖（适合先让用户体验）

适合发到 ImmortalWrt 社区论坛或交流群。下面是可直接复制的帖子（把 `[截图]` 占位换成图片即可）。

**帖子标题**
```
【分享】luci-app-disk-health —— 路由器磁盘健康监控（支持 NAND 寿命估算）
```

**帖子正文（Markdown，直接粘贴）**
```markdown
## 简介
luci-app-disk-health 是一个 OpenWrt / ImmortalWrt / iStoreOS 的 LuCI 插件，
在「服务 → 磁盘健康」里直观展示存储设备的健康状态、剩余寿命与通电时长。

## 功能
- 自动发现 NVMe / SATA / USB / eMMC / SD / MTD，卡片式总览
- 健康分级（良好/警告/危险）+ 关键指标（健康度、剩余寿命、通电小时、温度、坏块等）
- SMART 属性展开、原始输出弹窗
- 依赖自检：smartctl / mmc 缺失时给友好提示而非报错
- **NAND 寿命估算**：MTK / 高通硬路由的 raw NAND 也能看磨损了
  （UBI 读擦除计数估算剩余寿命，页面明确标注“估算值”）
- **NAND 闪存类型一键切换**：检测到 NAND 时，设备卡片内提供 SLC / MLC / TLC / QLC / 自定义
  按钮，按路由器实际颗粒选择额定擦写次数，寿命估算立即刷新（也可在设置页选择）

## 截图
[截图1：设备总览页]
[截图2：NAND 寿命估算页（MT7981）]

## 安装
方式一（软件源编译，推荐）：
把 luci-app-disk-health 目录放入 immortalwrt-packages 后编译，
或直接 `opkg install luci-app-disk-health`。

方式二（ImmortalWrt 24.10 apk）：
apk add --allow-untrusted luci-app-disk-health_*.apk

方式三（iStoreOS）：用商店「本地安装」上传 istore 应用包。

## 可选依赖
opkg install smartmontools   # SATA / NVMe / USB
opkg install mmc-utils       # eMMC（部分内核已通过 sysfs 暴露寿命，可不装）

## 说明
- NAND 寿命为估算值，非厂商精确百分比，实际以厂商工具为准。
- 纯脚本包，全平台通用。

维护者：sugarfreecoke ｜ 许可证：Apache-2.0
仓库：<在此填入你的 GitHub 仓库地址>
```

---

## 三、提交注意事项（避免在评审/发帖时被质疑）

1. **apk 未签名**：ImmortalWrt 24.10 默认 apk 包管理器，离线打的 `.apk` 需
   `apk add --allow-untrusted`。正式进软件源后由构建系统签名，无需你手动签名。
2. **依赖可选**：`smartmontools` / `mmc-utils` 是可选依赖，NAND 硬路由可不装。
   若希望“装完即用”，可在 `Makefile` 的 `LUCI_DEPENDS` 取消注释这两项的注释行。
3. **NAND 寿命是估算**：务必在说明里保留“估算值”字样，避免被误读为精确健康度。
4. **菜单路径**：`admin/services/disk_health`（服务 → 磁盘健康）。
5. **i18n**：简体中文为源语言，`po/en` 为英文翻译；新增界面文案请同步两个 `.po`。
6. **署名一致**：仓库、`Makefile` 的 `PKG_MAINTAINER`、帖子/PR 中的维护者均用
   **sugarfreecoke**。

---

## 四、附：本仓库已有但“不要”提交进软件源的文件

| 文件/目录 | 用途 | 是否进软件源 |
|---|---|---|
| `tools/pack_common.py` 等 | 本机离线打包引擎 | ❌ |
| `out/` | 本地打包产物 | ❌ |
| `release-v1.0.0/` | 分类发布包 | ❌ |
| `diskheal-release-v1.0.0.rar` | 压缩发布包 | ❌ |
| `.github/workflows/build.yml` | 本仓库 CI | 可选（软件源有自己的 CI） |
| `Makefile` / `luasrc/` / `root/` / `po/` / `README.md` / `LICENSE` | 插件本体 | ✅ |
```
