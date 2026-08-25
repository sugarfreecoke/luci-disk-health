#!/bin/sh
#
# 离线打包成 .ipk（不依赖 OpenWrt SDK / ar / gzip）
# ------------------------------------------------------------------
# 本脚本只是 tools/pack_common.py 的薄包装：真正的 ar 归档与压缩由
# 纯 Python 标准库完成，因此即使系统里没有 ar / gzip 也能产出合法 .ipk。
#
# 用法：
#   sh build-ipk.sh            # 产物输出到 ./out/
#   sh build-ipk.sh --out DIR  # 指定输出目录
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

exec "$PY" tools/pack_common.py ipk "$@"
