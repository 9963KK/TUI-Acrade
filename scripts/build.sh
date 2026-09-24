#!/bin/sh
# 交叉编译首版支持的 4 个目标（docs/architecture.md 1.4），输出到 dist/<目标>/。
# 用法：scripts/build.sh [版本号]
set -e
cd -- "$(dirname -- "$0")/../platform"
version=${1:-dev}
for target in macos-x86_64:darwin/amd64 macos-arm64:darwin/arm64 linux-x86_64:linux/amd64 windows-x86_64:windows/amd64; do
    name=${target%%:*}
    platform=${target#*:}
    suffix=""
    [ "${platform%/*}" = windows ] && suffix=".exe"
    CGO_ENABLED=0 GOOS=${platform%/*} GOARCH=${platform#*/} \
        go build -trimpath -ldflags "-s -w -X main.version=$version" -o "../dist/$name/tplay$suffix" ./cmd/tplay
    echo "dist/$name/tplay$suffix"
done
