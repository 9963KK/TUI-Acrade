#!/bin/zsh
cd -- "${0:A:h}" || exit 1
# 从 Finder 双击启动时 PATH 不含 Homebrew，补上 Go 与 Python 的常见位置。
export PATH="/opt/homebrew/bin:/usr/local/bin:$PATH"
exec ./play.sh "$@"
