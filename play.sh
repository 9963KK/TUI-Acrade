#!/bin/sh
# 从源码构建并启动游戏厅（需要 Go 1.26+）。开发来源的 Python 游戏使用 TUI_ARCADE_PYTHON 或 PATH 中的 python3。
# scripts/install-tplay.sh 安装的 tplay 命令会调用本脚本。
set -e
cd -- "$(dirname -- "$0")"
# 只在平台源码比现有程序新时才重新构建，避免每次启动都等待链接。
if [ ! -x bin/tplay ] || [ -n "$(find platform \( -name '*.go' -o -name go.mod -o -name go.sum \) -newer bin/tplay -print | head -n 1)" ]; then
    (cd platform && go build -o ../bin/tplay ./cmd/tplay)
fi
exec ./bin/tplay "$@"
