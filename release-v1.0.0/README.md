# luci-app-disk-health 发布包 v1.0.0

> 磁盘健康监控插件（含 SATA/NVMe/eMMC/NAND 寿命读取）。
> 生成日期：2026-08-26。所有包已通过结构校验。

## 目录与适用平台

| 目录 | 文件 | 适用平台 / 安装方式 |
|---|---|---|
| `opkg/` | `luci-app-disk-health_1.0.0-1_all.ipk` | **原生 OpenWrt 24.10 / 仍用 opkg 的 ImmortalWrt**（网页上传或 `opkg install`）。**已按新版 opkg 格式验证**（gzip 外层、`./debian-binary`+`./control.tar.gz`+`./data.tar.gz`、control 纯 LF、postinst/postrm 0755）。 |
| `apk/` | `luci-app-disk-health_1.0.0-1_all.apk` | **ImmortalWrt 24.10 默认 apk 包管理器**。SSH：`apk add --allow-untrusted <包>`。 |
| `istore/` | `istore-app-disk-health-v1.0.0.tar.gz` / `.zip` | **iStoreOS / ArgonTheme 商店「本地安装」**。其 `install.sh` 直接释放文件，绕开 opkg 的 Malformed 限制；商店内有卸载按钮。 |
| `scripts/` | `dh_setup.sh` | 任意平台 SSH 一行兜底安装器（`sh dh_setup.sh`，自动检测 opkg/apk，必要时直接释放 `data.tar.gz`）。 |
| `scripts/` | `uninstall.sh` | 卸载脚本（当初是绕 opkg 装的，故用此脚本而非 `opkg remove`）。 |
| `scripts/` | `luci-app-disk-health_install-1.0.0-1.run` | 旧式 run 安装包装壳，等同 dh_setup.sh，保留备用。 |
| `icon/` | `icon.png` | 商店卡片图标。 |

## 通用装机指引

1. **ImmortalWrt 24.10（opkg）** —— 用 `opkg/` 下的 `.ipk`，网页上传或：
   ```sh
   scp opkg/luci-app-disk-health_1.0.0-1_all.ipk root@<路由IP>:/tmp/
   ssh root@<路由IP> 'opkg install /tmp/luci-app-disk-health_1.0.0-1_all.ipk'
   ```
2. **ImmortalWrt 24.10（apk）** —— 用 `apk/` 下的 `.apk`：
   ```sh
   scp apk/luci-app-disk-health_1.0.0-1_all.apk root@<路由IP>:/tmp/
   ssh root@<路由IP> 'apk add --allow-untrusted /tmp/luci-app-disk-health_1.0.0-1_all.apk'
   ```
3. **iStoreOS / ArgonTheme** —— 网页上传 `istore/` 下的 `.tar.gz`（不要用裸 ipk 上传，会被 opkg 判 Malformed）。
4. **任意平台兜底** —— `scripts/dh_setup.sh` 一行 `sh` 安装。

## 卸载

```sh
# 方式一：脚本（推荐，与绕 opkg 安装对应）
ssh root@<路由IP> 'sh -s' < scripts/uninstall.sh
# 方式二：若当初是 opkg 成功装的，也可用
ssh root@<路由IP> 'opkg remove luci-app-disk-health'
```

## 校验

- `opkg/` 的 `.ipk` 已用 `tools/verify_three_points.py` 通过三点校验
  （gzip 文件头 / 外层三成员 / control 0755+LF）。
- 各包 MD5 见 `MANIFEST.txt`。
- 重打包：`python tools/pack_common.py all --out out`
- 重建 iStore 应用包：`python tools/build_istore_app.py`

## 注意

- `out/` 目录下还有 `luci-app-disk-health_data.b64` / `luci-app-disk-health_data.tar.gz`
  等**中间产物**，未纳入本发布包；发布以本目录为准。
