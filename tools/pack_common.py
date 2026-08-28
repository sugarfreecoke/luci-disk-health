#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
luci-app-disk-health 离线打包引擎（纯 Python，无外部依赖）
================================================================

不依赖 OpenWrt SDK / ar / gzip 等外部命令，用 Python 标准库生成：

  * .ipk  —— ar 归档：debian-binary + control.tar.gz + data.tar.gz
  * .apk  —— gzip 压缩的 tar（OpenWrt 新版 apk 包格式），含 .PKGINFO
  * .run  —— 自解压安装器：POSIX shell 头 + tar.gz 负载（install.sh + 包文件 + 可选 deps）

并提供 ``verify`` 子命令做结构级校验（解 ar / 读 tar / 模拟提取 .run）。

适用场景：只是想装个插件，不想为编译拉一整套 SDK；或在 CI 里产出可安装包。

用法：
  python3 tools/pack_common.py ipk  [--out DIR]
  python3 tools/pack_common.py apk  [--out DIR]
  python3 tools/pack_common.py run  [--out DIR] [--deps DIR]
  python3 tools/pack_common.py all  [--out DIR] [--deps DIR]
  python3 tools/pack_common.py verify --file <path.ipk|.apk|.run>

说明：
  * 本机无 `ar`/`gzip` 也能生成合法的 .ipk / .apk（ar 格式与 gzip 均用标准库实现）。
  * .apk 未做签名，在目标机上需用 ``apk add --allow-untrusted`` 安装（脚本内已处理）。
  * .run 为全自包含：内置 .ipk 与 .apk，运行时自动检测 opkg/apk 并选择对应文件，
    依赖 smartmontools / mmc-utils 优先用离线 deps/ 目录，其次在线 opkg/apk 安装。
"""

import os
import re
import io
import sys
import time
import argparse
import tempfile
import shutil
import tarfile
import gzip

# ---------------------------------------------------------------------------
# 路径与包元信息
# ---------------------------------------------------------------------------
# ROOT = luci-app-disk-health/  （即本文件所在目录的上一级）
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def read_pkg_meta():
    """优先从 Makefile 读取版本，读不到则用内置默认值。"""
    meta = {
        "PKG": "luci-app-disk-health",
        "VER": "1.0.0",
        "REL": "1",
        "ARCH": "all",
        "MAINTAINER": "disk-health",
    }
    mk = os.path.join(ROOT, "Makefile")
    if os.path.isfile(mk):
        txt = open(mk, encoding="utf-8", errors="ignore").read()
        mapping = (("PKG_NAME", "PKG"), ("PKG_VERSION", "VER"), ("PKG_RELEASE", "REL"))
        for var, key in mapping:
            m = re.search(r"^%s:\=\s*(.+)$" % re.escape(var), txt, re.M)
            if m:
                meta[key] = m.group(1).strip()
    return meta


META = read_pkg_meta()
PKG = META["PKG"]
VER = META["VER"]
REL = META["REL"]
ARCH = META["ARCH"]
MAINTAINER = META["MAINTAINER"]

DEPENDS = ["luci-base", "luci-compat", "luci-lib-jsonc"]


# ---------------------------------------------------------------------------
# 基础工具函数
# ---------------------------------------------------------------------------
def copy_tree(src, dst):
    """递归拷贝目录（仅文件），自动创建目标目录。"""
    for root, _dirs, files in os.walk(src):
        rel = os.path.relpath(root, src)
        target = dst if rel == "." else os.path.join(dst, rel)
        os.makedirs(target, exist_ok=True)
        for f in files:
            shutil.copy2(os.path.join(root, f), os.path.join(target, f))


def dir_size(path):
    """返回目录字节数。"""
    total = 0
    for root, _d, files in os.walk(path):
        for f in files:
            try:
                total += os.path.getsize(os.path.join(root, f))
            except OSError:
                pass
    return total


# control 里需要可执行位的脚本（按文件名判定，避免跨平台 stat 误判）
EXEC_NAMES = {"postinst", "preinst", "postrm", "prerm"}


def build_tar_bytes(stage, fmt=tarfile.USTAR_FORMAT, prefix="./"):
    """
    把 stage 目录打成 gzip 压缩的 tar，返回 bytes。

    关键兼容性点（针对新版 opkg / apk，以及 ImmortalWrt 24.10 的新格式 .ipk）：
      * USTAR 格式（非 GNU_FORMAT），避免 GNU 长名/Pax 头被老旧 tar 解析器排斥。
      * 每个成员名以 prefix('./') 开头（如 ./usr/lib/lua/...），并包含**完整中间目录项**
        （./usr/、./usr/lib/、./usr/lib/luci/ …），目录 0755、文件 0644。
      * 可执行脚本（postinst/postrm/preinst/prerm）权限 0755，其余 0644。
      * mtime 固定为 0，保证可复现（相同输入产出相同哈希）。
      * 排序保证「父目录先于子项」出现（旧 tar / opkg 顺序敏感，否则 wfopen 报错）。
    """
    buf = io.BytesIO()
    with gzip.GzipFile(fileobj=buf, mode="wb", mtime=0) as gz:
        with tarfile.open(fileobj=gz, mode="w", format=fmt) as tf:
            # 根目录项 ./
            root_ti = tarfile.TarInfo(prefix + ".")
            root_ti.type = tarfile.DIRTYPE
            root_ti.mode = 0o755
            root_ti.mtime = 0
            root_ti.uid = 0
            root_ti.gid = 0
            tf.addfile(root_ti)

            # 收集所有路径（目录 + 文件），按路径字典序 —— 保证父目录在前
            paths = []
            for root, dirs, files in os.walk(stage):
                for d in sorted(dirs):
                    paths.append((os.path.join(root, d), True))
                for f in sorted(files):
                    paths.append((os.path.join(root, f), False))
            for full, is_dir in sorted(paths, key=lambda x: x[0]):
                rel = os.path.relpath(full, stage).replace(os.sep, "/")
                if is_dir:
                    arc = prefix + rel + "/"
                    ti = tarfile.TarInfo(arc)
                    ti.type = tarfile.DIRTYPE
                    ti.mode = 0o755
                else:
                    arc = prefix + rel
                    ti = tarfile.TarInfo(arc)
                    ti.type = tarfile.REGTYPE
                    ti.mode = 0o755 if os.path.basename(full) in EXEC_NAMES else 0o644
                ti.mtime = 0
                ti.uid = 0
                ti.gid = 0
                if is_dir:
                    tf.addfile(ti)
                else:
                    ti.size = os.path.getsize(full)
                    with open(full, "rb") as fh:
                        tf.addfile(ti, fh)
    return buf.getvalue()


# ---------------------------------------------------------------------------
# 数据树（control.tar.gz / data.tar.gz / apk 共用）
# ---------------------------------------------------------------------------
def stage_data(stage):
    """
    根据插件源码组织根文件系统树到 stage 目录：
      * luasrc/       -> /usr/lib/lua/luci/
      * root/         -> /（配置文件、ACL 等）
      * po/           -> /usr/lib/lua/luci/po/<lang>/（源码级 i18n，运行时需 po2lmo 才生效）
    """
    # luasrc -> /usr/lib/lua/luci
    lua_dst = os.path.join(stage, "usr", "lib", "lua", "luci")
    os.makedirs(lua_dst, exist_ok=True)
    copy_tree(os.path.join(ROOT, "luasrc"), lua_dst)

    # root -> 根
    root_src = os.path.join(ROOT, "root")
    if os.path.isdir(root_src):
        copy_tree(root_src, stage)

    # po -> /usr/lib/lua/luci/po/<lang>/
    po_src = os.path.join(ROOT, "po")
    if os.path.isdir(po_src):
        for lang in sorted(os.listdir(po_src)):
            src = os.path.join(po_src, lang)
            if os.path.isdir(src):
                dst = os.path.join(stage, "usr", "lib", "lua", "luci", "po", lang)
                os.makedirs(dst, exist_ok=True)
                copy_tree(src, dst)


def write_control(ctrl_dir, inst_size):
    """生成 control.tar.gz 所需的 control / conffiles / postinst / postrm。"""
    control = (
        "Package: %s\n"
        "Version: %s-%s\n"
        "Depends: libc, %s\n"
        "Source: feeds/luci/applications/%s\n"
        "SourceName: %s\n"
        "License: MIT\n"
        "Section: luci\n"
        "SourceDateEpoch: %d\n"
        "Maintainer: %s\n"
        "Architecture: %s\n"
        "Installed-Size: %d\n"
        "Description: LuCI support for Disk Health Monitor (磁盘健康)\n"
        " Monitor NVMe / SATA / eMMC / USB storage health,\n"
        " remaining life and power-on hours.\n"
    ) % (
        PKG,
        VER,
        REL,
        ", ".join(DEPENDS),
        PKG,
        PKG,
        int(time.time()),
        MAINTAINER,
        ARCH,
        inst_size,
    )
    with open(os.path.join(ctrl_dir, "control"), "w", encoding="utf-8", newline="\n") as f:
        f.write(control)

    with open(os.path.join(ctrl_dir, "conffiles"), "w", encoding="utf-8", newline="\n") as f:
        f.write("/etc/config/disk_health\n")

    # postinst / postrm：清 LuCI 缓存，使新菜单立即生效
    hook = (
        "#!/bin/sh\n"
        "[ -n \"${IPKG_INSTROOT}\" ] && exit 0\n"
        "rm -f /tmp/luci-indexcache* /tmp/luci-modulecache/* 2>/dev/null\n"
        "rm -f /tmp/luci_disk_health_cache.json 2>/dev/null\n"
        "exit 0\n"
    )
    for name in ("postinst", "postrm"):
        p = os.path.join(ctrl_dir, name)
        with open(p, "w", encoding="utf-8", newline="\n") as f:
            f.write(hook)
        os.chmod(p, 0o755)


def build_pkginfo():
    """生成 apk 的 .PKGINFO 控制文件内容。"""
    lines = [
        "pkgname = %s" % PKG,
        "pkgver = %s-r%s" % (VER, REL),
        "arch = %s" % ARCH,
        "origin = %s" % PKG,
        "maintainer = %s" % MAINTAINER,
        "license = MIT",
        "section = luci",
        "builddate = %d" % int(time.time()),
        "size = 0",
        "url = https://github.com/",
    ]
    for d in DEPENDS:
        lines.append("depend = %s" % d)
    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------------------
# ar 归档写入（.ipk 容器）
# ---------------------------------------------------------------------------
def write_ar(members, out_path):
    """
    写入与 GNU binutils `ar` 字节级兼容的 ar 归档。

    严格按 binutils 头部格式（共 60 字节）：
      name   16  左对齐，空格补齐
      mtime  12  左对齐十进制
      uid     6  左对齐十进制
      gid     6  左对齐十进制
      mode    8  左对齐八进制（如 100644）
      size   10  左对齐十进制
      结尾    2  "`\\n"
    奇数长度成员后补一个 '\\n'。

    注意：必须完全对齐 GNU ar（binutils）格式——数字字段右对齐、空格填充，
    mode 字段为八进制。早期实现用左对齐/零填充会被 opkg 判为 "Malformed package file"。
    """
    with open(out_path, "wb") as f:
        f.write(b"!<arch>\n")
        for name, data in members:
            name_b = name.encode("utf-8")
            if len(name_b) > 16:
                raise ValueError("ar 成员名过长: %s" % name)
            # Debian/dpkg/opkg 标准：普通成员名以 '/' 结尾（特殊成员 '/' 与 '//' 除外），
            # 其余用空格补齐到 16 字节。缺尾 '/' 会被部分 opkg 解析器判为 Malformed。
            if len(name_b) < 16 and name_b not in (b"/", b"//"):
                name_field = name_b + b"/" + b" " * (15 - len(name_b))
            else:
                name_field = name_b + b" " * (16 - len(name_b))
            size = len(data)
            # 完全对齐 GNU ar（binutils）格式：数字字段右对齐、空格填充、mode 为八进制。
            header = (
                name_field
                + ("%12d" % 0).encode()               # mtime（右对齐十进制）
                + ("%6d" % 0).encode()                # uid
                + ("%6d" % 0).encode()                # gid
                + ("%8o" % 0o100644).encode()         # mode（右对齐八进制，如 "  100644"）
                + ("%10d" % size).encode()            # size（右对齐十进制）
                + b"`\n"                              # 结尾标记
            )
            assert len(header) == 60, "ar header 长度异常: %d" % len(header)
            f.write(header)
            f.write(data)
            if size % 2 == 1:                         # 奇数长度补一个换行
                f.write(b"\n")


def read_ar(out_path):
    """读取 ar 归档，返回 list[(name, data)]，用于 verify。"""
    members = []
    with open(out_path, "rb") as f:
        magic = f.read(8)
        if magic != b"!<arch>\n":
            raise ValueError("不是有效的 ar 归档（magic 不匹配）")
        while True:
            header = f.read(60)
            if len(header) < 60:
                break
            name = header[0:16].rstrip(b" ").rstrip(b"/").decode("utf-8", "ignore")
            size = int(header[48:58].decode("ascii").strip() or "0")
            data = f.read(size)
            if size % 2 == 1:
                f.read(1)  # 跳过补齐字节
            members.append((name, data))
    return members


# ---------------------------------------------------------------------------
# 各产物构建
# ---------------------------------------------------------------------------
def build_ipk(out_dir):
    """生成【新版 opkg 格式】的 .ipk：外层是 gzip 压缩的 POSIX tar 归档，
    成员依次为 ./debian-binary、./control.tar.gz、./data.tar.gz（均带 ./ 前缀）。"""
    tmp = tempfile.mkdtemp(prefix="dh_ipk_")
    try:
        stage = os.path.join(tmp, "data")
        os.makedirs(stage)
        stage_data(stage)

        ctrl = os.path.join(tmp, "control")
        os.makedirs(ctrl)
        write_control(ctrl, inst_size=dir_size(stage))

        data_gz = build_tar_bytes(stage)
        ctrl_gz = build_tar_bytes(ctrl)
        debian = b"2.0\n"

        out = os.path.join(out_dir, "%s_%s-%s_%s.ipk" % (PKG, VER, REL, ARCH))
        buf = io.BytesIO()
        with gzip.GzipFile(fileobj=buf, mode="wb", mtime=0) as gz:
            with tarfile.open(fileobj=gz, mode="w", format=tarfile.USTAR_FORMAT) as tf:
                for arcname, data in (
                    ("./debian-binary", debian),
                    ("./control.tar.gz", ctrl_gz),
                    ("./data.tar.gz", data_gz),
                ):
                    ti = tarfile.TarInfo(arcname)
                    ti.type = tarfile.REGTYPE
                    ti.size = len(data)
                    ti.mode = 0o644
                    ti.mtime = 0
                    ti.uid = 0
                    ti.gid = 0
                    tf.addfile(ti, io.BytesIO(data))
        with open(out, "wb") as f:
            f.write(buf.getvalue())
        return out
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def build_apk(out_dir):
    tmp = tempfile.mkdtemp(prefix="dh_apk_")
    try:
        stage = os.path.join(tmp, "data")
        os.makedirs(stage)
        stage_data(stage)
        # apk 控制信息：放到包根 .PKGINFO
        with open(os.path.join(stage, ".PKGINFO"), "w", encoding="utf-8", newline="\n") as f:
            f.write(build_pkginfo())
        # .apk 本质就是 gzip tar；Alpine apk 原生格式路径不带 ./ 前缀（usr/lib/...）
        out = os.path.join(out_dir, "%s_%s-%s_%s.apk" % (PKG, VER, REL, ARCH))
        with open(out, "wb") as f:
            f.write(build_tar_bytes(stage, prefix=""))
        return out
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


# ---------------------------------------------------------------------------
# .run 自解压安装器
# ---------------------------------------------------------------------------
RUN_HEADER = (
    "#!/bin/sh\n"
    "# luci-app-disk-health self-extracting installer\n"
    "# 该文件由 tools/pack_common.py 生成，请勿手工编辑\n"
    "set -e\n"
    'ME="$0"\n'
    'TMPD="$(mktemp -d 2>/dev/null || mktemp -d -t dh)"\n'
    'trap \'rm -rf "$TMPD"\' EXIT\n'
    'echo "==> 解压安装包到 $TMPD"\n'
    "sed '1,/^__DH_PAYLOAD__$/d' \"$ME\" | tar -xz -C \"$TMPD\"\n"
    'cd "$TMPD"\n'
    "exec sh ./install.sh\n"
    "__DH_PAYLOAD__\n"
)

INSTALL_SH = r"""#!/bin/sh
# luci-app-disk-health 安装脚本（由 .run 自解压后执行）
# 行为：自动检测 opkg/apk -> 装依赖(离线deps优先, 其次在线) -> 装插件 -> 刷缓存
#
# 兼容性说明：
#   * OpenWrt / iStoreOS 默认 /bin/sh 为 BusyBox ash。
#   * BusyBox ash 不支持 `set +e` / `set -e` 的 `+/-` 复合写法
#     （会报 "set: illegal option +"），也较老版本对 `set -e` 的处理有差异。
#   * 因此本脚本不依赖 `set -e/+e`，而是逐条用 `|| true` / `|| echo` 容错，
#     保证任意一步失败都不会让整个安装中止（继续尝试下一步）。

printf '\n############################################\n'
printf '#   luci-app-disk-health 安装程序\n'
printf '############################################\n\n'

WORK="$(cd "$(dirname "$0")" && pwd)"

# 1) 检测包管理器
if command -v opkg >/dev/null 2>&1; then
    PM=opkg
elif command -v apk >/dev/null 2>&1; then
    PM=apk
else
    printf '错误：未找到 opkg 或 apk，无法安装。请确认运行环境为 OpenWrt / iStoreOS。\n' >&2
    exit 1
fi
printf '检测到包管理器：%s\n' "$PM"

# 2) 安装依赖 smartmontools / mmc-utils
#    优先用离线 deps/ 目录；若失败再走在线；在线失败也不退出，只提示。
#    先尝试刷新软件源（离线环境会失败，属正常，继续用本地包即可）。
printf '==> 刷新软件源列表（opkg update，可选）\n'
opkg update 2>&1 | tail -3 || printf '    （opkg update 失败，可能是离线环境，继续使用本地包）\n'
printf '==> 安装依赖 smartmontools / mmc-utils\n'
if [ "$PM" = opkg ]; then
    if ls "$WORK"/deps/*.ipk >/dev/null 2>&1; then
        printf '    使用离线依赖包...\n'
        opkg install "$WORK"/deps/*.ipk 2>&1 | tail -3 || true
    fi
    opkg install smartmontools mmc-utils 2>&1 | tail -3 || \
        printf '    （在线安装依赖失败，可稍后手动：opkg install smartmontools mmc-utils）\n'
else
    if ls "$WORK"/deps/*.apk >/dev/null 2>&1; then
        printf '    使用离线依赖包...\n'
        apk add --allow-untrusted "$WORK"/deps/*.apk 2>&1 | tail -3 || true
    fi
    apk add smartmontools mmc-utils 2>&1 | tail -3 || \
        printf '    （在线安装依赖失败，可稍后手动：apk add smartmontools mmc-utils）\n'
fi

# 3) 安装插件本体
#    策略：优先尝试用包管理器（opkg/apk）安装，把包登记到数据库，便于日后卸载；
#          无论包管理器成败，最后都以「目标控制器文件是否真的存在」为准——
#          缺失则直接把 data.tar.gz 释放到 /（纯脚本包适用，最稳妥）。
#    注意：不要使用 ${PIPESTATUS} 判定成败（BusyBox ash 中常为空，会误判为成功），
#          这里改用 `cmd && ... || ...` 与「文件存在性」双重判定。
printf '==> 安装 luci-app-disk-health\n'
if [ "$PM" = opkg ]; then
    opkg install "$WORK"/*.ipk >/tmp/dh_opkg.log 2>&1 \
        && printf '    [OK] 已通过 opkg 安装\n' \
        || printf '    opkg 安装失败，将走保底释放：\n%s\n' "$(tail -3 /tmp/dh_opkg.log)"
else
    apk add --allow-untrusted "$WORK"/*.apk >/tmp/dh_apk.log 2>&1 \
        && printf '    [OK] 已通过 apk 安装\n' \
        || printf '    apk 安装失败，将走保底释放：\n%s\n' "$(tail -3 /tmp/dh_apk.log)"
fi
# 保底：控制器文件必须存在，否则直接释放 data.tar.gz 到系统根目录
if [ ! -f /usr/lib/lua/luci/controller/disk_health.lua ]; then
    printf '    [保底] 控制器文件缺失，直接释放 data.tar.gz 到 /\n'
    tar -xzf "$WORK"/data.tar.gz -C / 2>&1 | tail -8 || true
fi
# 二次校验
if [ -f /usr/lib/lua/luci/controller/disk_health.lua ]; then
    printf '    [OK] 控制器已就位：/usr/lib/lua/luci/controller/disk_health.lua\n'
else
    printf '    [!!!] 控制器仍未安装，请检查磁盘空间 / 只读 overlay 文件系统\n'
fi

# 4) 刷新 LuCI 缓存并重启相关服务
printf '==> 刷新 LuCI 缓存并重启服务\n'
rm -rf /tmp/luci-* 2>/dev/null || true
/etc/init.d/rpcd restart 2>/dev/null || true
/etc/init.d/uhttpd restart 2>/dev/null || true

printf '\n完成！请登录 LuCI，进入「服务 -> 磁盘健康」查看。\n'
exit 0
"""


def build_run(out_dir, deps_dir=None):
    # 内置 .ipk 与 .apk，确保 opkg / apk 系统都能装
    ipk = build_ipk(out_dir)
    apk = build_apk(out_dir)

    tmp = tempfile.mkdtemp(prefix="dh_run_")
    try:
        payload = os.path.join(tmp, "payload")
        os.makedirs(payload)
        shutil.copy(ipk, payload)
        shutil.copy(apk, payload)

        # 额外内置 data.tar.gz（文件系统树）：当 opkg/apk 拒收 .ipk/.apk 时，
        # 作为「直接释放文件」的保底方案（本插件为纯脚本包，无编译产物，适用）。
        stage = os.path.join(tmp, "data")
        os.makedirs(stage)
        stage_data(stage)
        with open(os.path.join(payload, "data.tar.gz"), "wb") as f:
            f.write(build_tar_bytes(stage))

        # 可选离线依赖
        if deps_dir and os.path.isdir(deps_dir):
            shutil.copytree(deps_dir, os.path.join(payload, "deps"))

        # 安装脚本（强制 LF 换行，避免 Windows \r\n 在 BusyBox ash 下解析异常）
        install_path = os.path.join(payload, "install.sh")
        with open(install_path, "w", encoding="utf-8", newline="\n") as f:
            f.write(INSTALL_SH)
        os.chmod(install_path, 0o755)

        payload_gz = build_tar_bytes(payload)
        out = os.path.join(out_dir, "%s_install-%s-%s.run" % (PKG, VER, REL))
        with open(out, "wb") as f:
            f.write(RUN_HEADER.encode("utf-8"))
            f.write(payload_gz)
        return out
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


# ---------------------------------------------------------------------------
# 校验
# ---------------------------------------------------------------------------
def _read_outer(path):
    """读取外层归档：若是 gzip(tar) 新格式返回 (tarfile, 提取器)；否则回退 ar。"""
    with open(path, "rb") as f:
        head = f.read(2)
    if head == b"\x1f\x8b":
        gz = gzip.GzipFile(path)
        tf = tarfile.open(fileobj=gz)
        return tf, True
    raise ValueError(".ipk 不是新版 gzip(tar) 格式（文件头=%r）" % head)


def _extract_inner(path, member):
    """从 ipk 外层 tar 中取出 control.tar.gz / data.tar.gz 的字节。"""
    with open(path, "rb") as f:
        head = f.read(2)
    assert head == b"\x1f\x8b"
    with gzip.GzipFile(path) as gz:
        with tarfile.open(fileobj=gz) as tf:
            names = tf.getnames()
            cand = None
            for n in names:
                if n.replace("./", "") == member:
                    cand = n
                    break
            if cand is None:
                raise ValueError("外层 tar 缺少 %s（现有: %s）" % (member, names))
            return tf.extractfile(cand).read()


def verify_ipk(path):
    with open(path, "rb") as f:
        head = f.read(2)
    if head != b"\x1f\x8b":
        raise ValueError(".ipk 不是新版 gzip(tar) 格式（文件头=%r）" % head)
    # 1) 外层成员
    with gzip.GzipFile(path) as gz:
        with tarfile.open(fileobj=gz) as tf:
            outer = [n.replace("./", "") for n in tf.getnames()]
    for need in ("debian-binary", "control.tar.gz", "data.tar.gz"):
        if need not in outer:
            raise ValueError("外层 tar 缺少成员: %s（现有: %s）" % (need, outer))
    # 2) debian-binary 内容
    db = _extract_inner(path, "debian-binary")
    if db != b"2.0\n":
        raise ValueError("debian-binary 内容异常: %r" % db)
    # 3) control.tar.gz：成员需带 ./、脚本需 0755、且不得含 CRLF
    ctrl = _extract_inner(path, "control.tar.gz")
    with gzip.GzipFile(fileobj=io.BytesIO(ctrl)) as gz:
        with tarfile.open(fileobj=gz) as tf:
            for m in tf.getmembers():
                if not m.name.startswith("./"):
                    raise ValueError("control.tar.gz 成员缺 ./ 前缀: %s" % m.name)
                base = m.name.split("/")[-1]
                if base in EXEC_NAMES:
                    if not (m.mode & 0o111):
                        raise ValueError("脚本 %s 缺少可执行位 (mode=%o)" % (m.name, m.mode))
                    body = tf.extractfile(m).read()
                    if b"\r\n" in body:
                        raise ValueError("脚本 %s 含 CRLF 换行" % m.name)
    # 4) data.tar.gz：成员需带 ./、含完整目录项、文件 0644、核心文件齐全
    data = _extract_inner(path, "data.tar.gz")
    with gzip.GzipFile(fileobj=io.BytesIO(data)) as gz:
        with tarfile.open(fileobj=gz) as tf:
            members = tf.getmembers()
            # 注意：Python tarfile 读回时会对目录名剥掉尾 '/'，但写盘字节仍带 '/'。
            # 这里补回尾 '/' 以保证与严格 extractor 的命名一致。
            dnames = []
            for m in members:
                n = m.name
                if m.isdir() and not n.endswith("/"):
                    n = n + "/"
                dnames.append(n)
            if any(not n.startswith("./") for n in dnames):
                raise ValueError("data.tar.gz 存在缺 ./ 前缀的成员")
            # 目录项：至少应出现 ./usr/lib/lua/luci/controller/ 这类中间目录
            need_dirs = ["./usr/", "./usr/lib/", "./usr/lib/lua/",
                         "./usr/lib/lua/luci/controller/"]
            miss_dirs = [d for d in need_dirs if d not in dnames]
            if miss_dirs:
                raise ValueError("data.tar.gz 缺目录项: %s" % miss_dirs)
            # 文件权限 0644 校验（排除目录）
            for m in members:
                if m.isfile() and (m.mode & 0o777) != 0o644:
                    raise ValueError("data.tar.gz 文件权限非 0644: %s (%o)" % (m.name, m.mode))
            checks = [
                "./usr/lib/lua/luci/controller/disk_health.lua",
                "./usr/lib/lua/luci/model/disk_health.lua",
                "./usr/lib/lua/luci/view/disk_health/overview.htm",
                "./etc/config/disk_health",
                "./usr/share/rpcd/acl.d/luci-app-disk-health.json",
            ]
            missing = [c for c in checks if c not in dnames]
            if missing:
                raise ValueError("data.tar.gz 缺少核心文件: %s" % missing)
    print("[OK] .ipk 新格式校验通过：外层 gzip(tar) 三成员齐备，"
          "control LF+0755，data 带 ./ 前缀与目录项，核心文件齐全(%d个)" % len(dnames))


def verify_apk(path):
    with tarfile.open(path, "r:gz") as tf:
        files = tf.getnames()
    if "./.PKGINFO" not in files and ".PKGINFO" not in files:
        raise ValueError(".apk 缺少 .PKGINFO")
    checks = [
        "usr/lib/lua/luci/controller/disk_health.lua",
        "usr/lib/lua/luci/model/disk_health.lua",
        "usr/lib/lua/luci/view/disk_health/overview.htm",
    ]
    missing = [c for c in checks if c not in files]
    if missing:
        raise ValueError(".apk 缺少文件: %s" % missing)
    print("[OK] .apk  .PKGINFO 存在, 核心文件齐全(%d个)" % len(files))


def verify_run(path):
    with open(path, "rb") as f:
        blob = f.read()
    marker = b"__DH_PAYLOAD__\n"
    idx = blob.find(marker)
    if idx < 0:
        raise ValueError(".run 未找到负载标记")
    payload = blob[idx + len(marker):]
    with gzip.GzipFile(fileobj=io.BytesIO(payload)) as gz:
        with tarfile.open(fileobj=gz) as tf:
            # 兼容带/不带 ./ 前缀两种命名
            files = [n.lstrip("./") for n in tf.getnames()]
    for need in ("install.sh", "data.tar.gz"):
        if need not in files:
            raise ValueError(".run 负载缺少: %s" % need)
    ipk_ok = any(n.endswith(".ipk") for n in files)
    apk_ok = any(n.endswith(".apk") for n in files)
    if not (ipk_ok and apk_ok):
        raise ValueError(".run 负载应包含 .ipk 与 .apk")
    print("[OK] .run  负载含 install.sh + data.tar.gz + .ipk + .apk (%d个条目)" % len(files))


def verify(path):
    if path.endswith(".ipk"):
        verify_ipk(path)
    elif path.endswith(".apk"):
        verify_apk(path)
    elif path.endswith(".run"):
        verify_run(path)
    else:
        raise ValueError("未知后缀，无法校验: %s" % path)


# ---------------------------------------------------------------------------
# 命令行入口
# ---------------------------------------------------------------------------
def main(argv=None):
    ap = argparse.ArgumentParser(description="luci-app-disk-health 离线打包引擎")
    sub = ap.add_subparsers(dest="cmd", required=True)

    for c in ("ipk", "apk", "run", "all"):
        p = sub.add_parser(c)
        p.add_argument("--out", default=os.path.join(ROOT, "out"), help="输出目录")
        if c in ("run", "all"):
            p.add_argument("--deps", default=None, help="离线依赖目录（可选）")

    pv = sub.add_parser("verify")
    pv.add_argument("--file", required=True, help="待校验的 .ipk/.apk/.run 路径")

    args = ap.parse_args(argv)

    if args.cmd == "verify":
        verify(args.file)
        return 0

    os.makedirs(args.out, exist_ok=True)
    if args.cmd == "ipk":
        out = build_ipk(args.out)
        print("生成: %s" % out)
    elif args.cmd == "apk":
        out = build_apk(args.out)
        print("生成: %s" % out)
    elif args.cmd == "run":
        out = build_run(args.out, getattr(args, "deps", None))
        print("生成: %s" % out)
    elif args.cmd == "all":
        i = build_ipk(args.out)
        a = build_apk(args.out)
        r = build_run(args.out, getattr(args, "deps", None))
        print("生成: %s\n生成: %s\n生成: %s" % (i, a, r))
    return 0


if __name__ == "__main__":
    sys.exit(main())
