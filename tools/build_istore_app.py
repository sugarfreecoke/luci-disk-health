"""Build an iStore-app tarball for luci-app-disk-health.

iStore-app format (iStore商店应用包约定):
  istore-app-disk-health-v1.0.0.tar.gz
  ├── manifest.json          # iStore 后端读取的元数据
  ├── icon.png               # 128x128 应用图标
  ├── install.sh             # 安装入口（被 iStore 后端调用）
  ├── uninstall.sh           # 卸载入口（被 iStore 后端调用）
  ├── README.md              # 长描述（可选）
  ├── LICENSE                # 许可
  └── packages/
      └── data.tar.gz        # 实际插件文件（来自官方 .ipk 的 data.tar.gz）

iStore 后端拿到这个 tarball 后会：
  1. 解压到 ~/.isvns/<name>/
  2. 读 manifest.json 渲染商店卡片
  3. 点「安装」→ 跑 install.sh
  4. 点「卸载」→ 跑 uninstall.sh
"""
import io
import os
import json
import gzip
import shutil
import tarfile
import tempfile
import hashlib
import pathlib

ROOT = pathlib.Path(__file__).parent.parent
OUT = ROOT / "out"
PACKAGE = pathlib.Path(tempfile.mkdtemp(prefix="dh_istore_"))

# 1) 应用元数据
MANIFEST = {
    "name": "disk-health",
    "title": "磁盘健康监控",
    "version": "1.0.0",
    "description": (
        "在 LuCI 中显示 NVMe / SATA / eMMC / SD / USB / VirtIO 硬盘的健康度、"
        "剩余寿命、温度与已用时长，并支持读取硬路由 NAND 闪存（UBI / 裸 MTD）"
        "的擦除计数估算寿命与坏块率。一键在「服务 → 磁盘健康」查看。"
    ),
    "category": "system",
    "tags": ["系统", "监控", "NAS", "硬件"],
    "author": "luci-app-disk-health project",
    "homepage": "https://github.com/yourname/luci-app-disk-health",
    "license": "Apache-2.0",
    "arch": "all",
    "size": "约 32 KB",
    "icon": "icon.png",
    "screenshots": [],
    "install": "./install.sh",
    "uninstall": "./uninstall.sh",
    "depends": [],
    "conflicts": [],
    "init": "manual",
}

# 2) install.sh —— 走和 dh_setup.sh 同样的逻辑，但额外给 iStore 后端留 hook
INSTALL_SH = """#!/bin/sh
# iStore-app install hook for luci-app-disk-health
# 由 iStore 后端调用，与之前 dh_setup.sh 等价
printf '\\n==> [disk-health] 开始安装...\\n'

# 提取 data.tar.gz（与应用 tarball 在同一目录的 packages/ 子目录）
HERE=\"$(cd \"$(dirname \"$0\")\"; pwd)\"
PAYLOAD=\"$HERE\"/packages/data.tar.gz
if [ ! -f \"$PAYLOAD\" ]; then
    printf '[!!!] 找不到 %s，请重新下载本应用\\n' \"$PAYLOAD\" >&2
    exit 1
fi

# 1) 直接把 data.tar.gz 解到 /（iStore 沙箱内已是 root）
printf '==> 释放文件到 / ...\\n'
tar -xzf \"$PAYLOAD\" -C /
if [ $? -ne 0 ]; then
    printf '[!!!] tar 释放失败\\n' >&2
    exit 1
fi

# 2) 清理 luci 缓存 + reload 服务
printf '==> 清理缓存并重启服务 ...\\n'
rm -rf /tmp/luci-* 2>/dev/null || true
/etc/init.d/rpcd restart  2>/dev/null || true
/etc/init.d/uhttpd restart 2>/dev/null || true

# 3) 验证
if [ -f /usr/lib/lua/luci/controller/disk_health.lua ]; then
    printf '\\n[OK] 安装完成。打开 LuCI -> 服务 -> 磁盘健康 查看。\\n'
    exit 0
else
    printf '\\n[!!!] 控制器文件未落地，请检查 overlay 写权限\\n' >&2
    exit 1
fi
"""

# 3) uninstall.sh —— iStore 后端调用，与之前写的 out/uninstall.sh 等价
UNINSTALL_SH = """#!/bin/sh
# iStore-app uninstall hook for luci-app-disk-health
printf '\\n==> [disk-health] 开始卸载...\\n'

FILES='
/etc/config/disk_health
/usr/lib/lua/luci/controller/disk_health.lua
/usr/lib/lua/luci/model/disk_health.lua
/usr/lib/lua/luci/model/cbi/disk_health.lua
/usr/lib/lua/luci/po/en/disk_health.po
/usr/lib/lua/luci/po/zh_Hans/disk_health.po
/usr/lib/lua/luci/view/disk_health/overview.htm
/usr/share/rpcd/acl.d/luci-app-disk-health.json
'
DIRS='
/usr/lib/lua/luci/view/disk_health
/usr/lib/lua/luci/model/cbi
'
removed=0
for f in $FILES; do
    if [ -f \"$f\" ]; then
        rm -f \"$f\"
        removed=$((removed + 1))
    fi
done
for d in $DIRS; do
    [ -d \"$d\" ] && [ -z \"$(ls -A \"$d\" 2>/dev/null)\" ] && rmdir \"$d\" 2>/dev/null
done

rm -rf /tmp/luci-* 2>/dev/null || true
/etc/init.d/rpcd restart  2>/dev/null || true
/etc/init.d/uhttpd restart 2>/dev/null || true

if [ -f /usr/lib/lua/luci/controller/disk_health.lua ]; then
    printf '[!!!] 控制器文件仍在，卸载可能未完成\\n' >&2
    exit 1
fi
printf '[OK] 已删除 %d 个文件，卸载完成。请刷新 LuCI 页面。\\n' \"$removed\"
exit 0
"""

# 4) 长描述（iStore 商店卡片下方）
README = """# 磁盘健康监控 (luci-app-disk-health)

一个在 LuCI 中实时展示 **NVMe / SATA / eMMC / SD / USB / VirtIO 硬盘**健康度与
**剩余寿命** 的轻量插件，特别适合 iStoreOS / OpenWrt 软路由、NAS、ARM 硬路由场景。

## 功能特性

| 设备类型     | 来源                | 能力                                                 |
| ------------ | ------------------- | ---------------------------------------------------- |
| NVMe         | `smartctl`          | 健康度 / 温度 / 寿命% / 累计写入 / 可用保留空间       |
| SATA / HDD   | `smartctl`          | 健康度 / 温度 / 重映射扇区 / 寿命%                    |
| USB          | `smartctl`          | 健康度 / 温度 / 寿命% (部分 UASP 桥接)               |
| eMMC         | sysfs + mmc extcsd  | 寿命% (life_time) / EOL 状态 / pre_eol_info          |
| SD           | sysfs + mmc extcsd  | 寿命% / EOL 状态                                     |
| VirtIO       | `smartctl`          | 健康度 / 温度                                         |
| **NAND 闪存** | UBI / MTD sysfs    | **擦除计数估算寿命** / 坏块率 / ECC 失败 / UBI 只读   |

## 特色亮点

- **真正支持硬路由 NAND**：MT7981 / IPQ6000 等 ubionly 方案的路由器
  自动读取 UBI 的 `max_ec` / `mean_ec` / `bad_peb_count`，按用户配置的
  `nand_rated_cycles` 估算剩余寿命。
- **依赖自检**：插件会自动检测 `smartctl` / `mmc` 命令是否存在，
  缺失时给出可一键粘贴的 `opkg install` 命令。
- **零架构依赖**：纯 Lua + 配置文件，`LUCI_PKGARCH=all`，不挑平台。
- **可调阈值**：温度/寿命/坏块告警阈值、所有可调参数都在设置页一键改。

## 安装方法

### 方法 1：iStore 商店（推荐）
在 iStore 商店搜索 `disk-health` → 点击安装。

### 方法 2：手动上传
下载 `istore-app-disk-health-v1.0.0.tar.gz` 后，到 iStoreOS 后台，
进入 iStore 商店 → 本地安装 → 上传 tarball。

### 方法 3：SSH
```sh
scp istore-app-disk-health-v1.0.0.tar.gz root@192.168.1.1:/tmp/
ssh root@192.168.1.1
tar -xzf /tmp/istore-app-disk-health-v1.0.0.tar.gz -C /tmp/
sh /tmp/disk-health/install.sh
```

## 卸载

iStore 商店点卸载按钮，或：
```sh
sh /tmp/disk-health/uninstall.sh
```

## 许可

Apache-2.0
"""


def main():
    # 1) 取最新的 data.tar.gz（从新格式 ipk 外层 tar 中抽 data.tar.gz）
    ipk = OUT / "luci-app-disk-health_1.0.0-1_all.ipk"
    assert ipk.exists(), f"missing {ipk}"

    with gzip.GzipFile(ipk) as gz:
        with tarfile.open(fileobj=gz) as tf:
            cand = None
            for n in tf.getnames():
                if n.replace("./", "") == "data.tar.gz":
                    cand = n
                    break
            assert cand is not None, "ipk 中找不到 data.tar.gz"
            data_tar_gz = tf.extractfile(cand).read()

    # 2) 组装应用目录（PACKAGE 已是系统临时目录，保证不存在）
    if PACKAGE.exists():
        shutil.rmtree(PACKAGE, ignore_errors=True)
    PACKAGE.mkdir(parents=True)
    (PACKAGE / "packages").mkdir()

    # 3) 写各文件
    (PACKAGE / "manifest.json").write_text(
        json.dumps(MANIFEST, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    shutil.copy(OUT / "icon.png", PACKAGE / "icon.png")
    (PACKAGE / "install.sh").write_text(INSTALL_SH, encoding="utf-8")
    (PACKAGE / "install.sh").chmod(0o755)
    (PACKAGE / "uninstall.sh").write_text(UNINSTALL_SH, encoding="utf-8")
    (PACKAGE / "uninstall.sh").chmod(0o755)
    (PACKAGE / "README.md").write_text(README, encoding="utf-8")
    (PACKAGE / "LICENSE").write_text(
        "Apache License, Version 2.0 (full text: https://www.apache.org/licenses/LICENSE-2.0)\n",
        encoding="utf-8",
    )
    (PACKAGE / "packages" / "data.tar.gz").write_bytes(data_tar_gz)

    # 4) 打包
    tar_path = OUT / "istore-app-disk-health-v1.0.0.tar.gz"
    if tar_path.exists():
        tar_path.unlink()
    with tarfile.open(tar_path, "w:gz") as tar:
        tar.add(PACKAGE, arcname="disk-health", recursive=True)
    # 也输出 zip 版（iStore 后端两种都支持）
    shutil.make_archive(str(OUT / "istore-app-disk-health-v1.0.0"), "zip", PACKAGE)

    # 5) 打印清单与指纹
    md5 = hashlib.md5(open(tar_path, "rb").read()).hexdigest()
    size_kb = len(open(tar_path, "rb").read()) // 1024
    print(f"Built: {tar_path.name}  ({size_kb} KB, md5={md5})")
    print("Contents:")
    with tarfile.open(tar_path, "r:gz") as tar:
        for m in sorted(tar.getmembers(), key=lambda x: x.name):
            print(f"  {m.size:>7}  {m.name}")
    shutil.rmtree(PACKAGE, ignore_errors=True)


if __name__ == "__main__":
    main()
