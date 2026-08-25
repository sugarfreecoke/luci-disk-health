#!/bin/sh
#
# 离线打包成 .apk（OpenWrt 新版 apk 包格式，不依赖 SDK）
# ------------------------------------------------------------------
# .apk 本质是一个 gzip 压缩的 tar，内含 .PKGINFO 控制文件与文件树。
# 本机无需 apk-tools，由 Python 标准库直接生成。
# 注意：未做签名，在目标机安装时需用 ``apk add --allow-untrusted``。
#
# 用法：
#   sh build-apk.sh            # 产物输出到 ./out/
#   sh build-apk.sh --out DIR
#
set -e

SRC=$(cd "$(dirname "$0")" && pwd)
cd "$SRC"

if ! command -v python3 >/dev/null 2>&1 && ! command -v python >/dev/null 2>&1; then
	echo "错误：未找到 python3 / python，无法运行打包引擎。" >&2
	exit 1
fi
PY=python3
command -v python3 >/dev/null 2>&1 || PY=python

exec "$PY" tools/pack_common.py apk "$@"
