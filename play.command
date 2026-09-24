#!/bin/zsh
cd -- "${0:A:h}" || exit 1
exec /opt/homebrew/bin/python3 -m arcade
