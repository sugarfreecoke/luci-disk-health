# 把 luci-app-disk-health 推进为 OpenWrt 内置功能 · 路线图与 Issue 草稿

> 目标：让这个插件从「个人仓库的第三方包」变成 OpenWrt 官方可安装（乃至默认内置）的功能。
> 本文包含：(1) 战略分层 (2) 投递路径与仓库归属 (3) 分步路线图 (4) 可直接贴到 GitHub 的 Issue 草稿。

---

## 一、先厘清「内置」的两个层次（决定你的发力点）

| 层次 | 含义 | 难度 | 社区接受门槛 |
| --- | --- | --- | --- |
| **L1 · 进官方 feed** | 仓库合并进 `openwrt/luci` 的 `applications/`，之后所有人 `opkg install luci-app-disk-health` 即可安装 | 中 | 需通过 buildbot CI + 1 名 maintainer 审阅 |
| **L2 · 默认内置进镜像** | 进入某些 target 的 `DEFAULT_PACKAGES`（如 x86/64 NAS 设备），出厂/编译镜像自带 | 高 | 需更廣共识 + 占用体积评审 + 长期维护承诺 |

**建议策略**：先冲 L1（进官方 feed），这是现实可达的一步；L2 等 L1 站稳、有足够用户呼声后再单独提案。
不要一上来就要求「默认内置」，容易被以「增加体积/维护负担」驳回。

---

## 二、投递到哪个仓库？（关键，别投错）

OpenWrt 是**多仓库**结构，LuCI 应用有专门归属：

- `openwrt/openwrt` —— 主源码（buildroot、target、base 包），**不是** luci-app 投放地
- `openwrt/luci` —— **LuCI 界面与 `luci-app-*` 应用都在这里**，路径 `applications/luci-app-disk-health/`
- `openwrt/packages` —— 非 LuCI 的普通软件包 feed

✅ **结论：投递到 `openwrt/luci` 仓库，放在 `applications/` 下。**
我们现有结构（Makefile + `luasrc/` + `po/` + `root/usr/share/rpcd/acl.d/`）已经天然符合它的布局，几乎不用大改。

---

## 三、分步路线图

1. **自查重复（必做）**：先在 forum.openwrt.org 搜 "disk health / SMART / luci storage"，确认没有官方或 WIP 的同类 app。若有，考虑贡献代码而非新建。
2. **社区预热（最重要的一步）**：在 OpenWrt Forum 发帖提案，标题如
   `[Feature Proposal] Built-in disk/SSD health monitoring in LuCI`。
   目的：探需求、找维护者、规避被拒风险。**OpenWrt 极度看重共识，先讨论再写码能省几轮返工。**
3. **开 Issue 跟踪**：在 `openwrt/luci` 开一个 Feature Request issue（草稿见第四节），把论坛讨论结论带进去。
4. **代码达标改造**：
   - 确认 `PKG_LICENSE`/`SPDX` 头、`PKG_MAINTAINER` 真实有效；
   - `smartmontools`/`mmc-utils` 维持**可选依赖**，绝不自动拉大包；
   - 补齐 `DEPENDS` 与 `PKGARCH=all`（已是纯脚本包，满足）；
   - 若想更「正统」，未来可把数据采集抽成 `ubus`/`rpcd` 后端，让 CLI 与 LuCI 共用——但首版保持纯 Lua 更容易合入。
5. **提交 PR**：fork `openwrt/luci` → 新建分支 → 把本目录放到 `applications/luci-app-disk-health/` → 开 PR。
   PR 会自动触发 buildbot 多架构构建（我们 `.github/workflows/build.yml` 的逻辑可参考，但官方用他们自己的 CI）。
6. **评审与迭代**：根据 maintainer 与 CI 反馈修（`sh -n` 检查脚本、Lua 风格、i18n 完整性等）。
7. **（进阶）推动 L2**：在 x86/64 NAS 类设备的 `DEFAULT_PACKAGES` 提案加入，需单独发帖争取共识。

---

## 四、可直接贴到 GitHub 的 Issue 草稿

> 仓库：`openwrt/luci` → New Issue → 选 “Feature request / package proposal”
> 语言用**英文**（OpenWrt 国际社区与 mailing list 工作语言）。下面的 `<repo-url>` 替换成你 push 后的地址。

---

### Title
`[Feature Request] Add luci-app-disk-health: integrated storage health monitoring in LuCI`

### Body

**Summary**
Propose adding `luci-app-disk-health` to the official LuCI applications feed: a web UI to monitor storage
health (health %, remaining life, power-on hours, temperature) for NVMe / SATA / USB / eMMC devices running on
OpenWrt routers and appliances.

**Problem**
OpenWrt now powers many storage-bearing devices (x86 NAS boxes, ARM boards with eMMC/NVMe), yet there is no
built-in way to see SMART / eMMC life-time data from LuCI. Today users must SSH in and run `smartctl` manually;
`smartmontools` has no UI, and ad-hoc scripts are fragmented and unmaintained.

**Proposal**
A LuCI application with a hardware-abstraction layer:
- Device discovery via sysfs + block info
- NVMe / SATA / USB → `smartctl -a` (JSON preferred, text fallback; USB auto `-d sat`)
- eMMC → sysfs `life_time` / `pre_eol_info`, fallback to `mmc extcsd read`
- MTD / NAND → UBI-managed NAND reads `max_ec`/`mean_ec`/`bad_peb_count` to *estimate* remaining
  life (clearly labeled as an estimate, not a precise %); raw MTD reads `bad_blocks`/`ecc_failures`.
  Rated P/E cycles are configurable (`nand_rated_cycles`) since the chip does not expose them.
- **Optional** dependencies (`smartmontools`, `mmc-utils`): when missing, the page shows a friendly banner
  instead of a Lua 500 error
- Health grading (good / warning / critical) with a settings page (thresholds, cache TTL, USB toggle, skip idle disks)

**Why in-tree (not just another feed)**
- Broad device coverage makes it generally useful across the fleet
- Optional deps keep the footprint minimal on devices without SMART
- Already packaged to OpenWrt conventions: `Makefile` (SPDX, `PKGARCH=all`), `po` i18n (zh/en),
  rpcd ACL, CBI settings, CI build

**Footprint / dependency considerations (for review)**
- `smartmontools` is large; we keep it a *soft/optional* dependency — never auto-pulled unless the user enables
  SMART features
- Pure Lua + shell, no compiled backend and no new long-running service
- Open to discussion: a future `ubus`/`rpcd` backend could expose data for both CLI and LuCI

**Scope & current status**
- Repo: `<repo-url>` — already includes Makefile, HAL model, CBI settings, overview view, zh/en po, ACL, CI build
- Logic validated via an offline harness; needs on-device validation across targets (x86, RK3566, eMMC boards)

**Request for feedback**
- Is there existing or overlapping work (e.g., a storage status page) we should build on?
- Preference: keep LuCI-only Lua, or move collection into a `ubus`/`rpcd` backend?
- Interest in making it a default package for x86/64 NAS profiles (L2)?
- Volunteers for co-maintainership?

---

## 五、给你的行动清单（下一步）

- [ ] 把本地仓库 `git push` 到你的 GitHub（先 `git remote add origin <url>` + `git push -u origin main`）
- [ ] 在 forum.openwrt.org 发预热帖（见第三节第 2 步）
- [ ] 在 `openwrt/luci` 开 Issue（用第四节草稿）
- [ ] 根据社区反馈微调代码（重点：依赖可选化、维护者信息）
- [ ] fork `openwrt/luci` 提交 PR
