#!/bin/sh
#
# 生成 .run 自解压安装器（全自包含：内置 .ipk + .apk + 可选离线依赖）
# ------------------------------------------------------------------
# 产物是一个 POSIX shell 脚本：运行时自解压后自动检测 opkg/apk，
# 先装依赖（deps/ 离线优先，其次在线 opkg/apk），再装插件并刷新缓存。
#
# 用法：
#   sh make-run.sh                       # 输出到 ./out/
#   sh make-run.sh --out DIR             # 指定输出目录
#   sh make-run.sh --deps ./deps         # 把离线依赖 .ipk/.apk 一并打入
#
# 在路由器上安装：
#   chmod +x luci-app-disk-health_install-*.run
#   ./luci-app-disk-health_install-*.run
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

exec "$PY" tools/pack_common.py run "$@"
