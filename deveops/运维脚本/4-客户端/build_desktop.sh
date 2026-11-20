#!/usr/bin/env bash
# ==============================================================================
# 打包 Linux 桌面端（Flutter）
#   ./build_desktop.sh               bundle + tar.gz + AppImage
#   SKIP_APPIMAGE=1 ./build_desktop.sh   只出 bundle 与 tar.gz
# 产物: dist/CodeBiu-x86_64.AppImage / codebiu-linux-x64.tar.gz
# 依赖: flutter SDK、clang/cmake/ninja/libgtk-3-dev、curl、ImageMagick(magick)
# ==============================================================================
source "$(dirname "$0")/../lib.sh"

require_cmd curl
require_cmd magick

APP_DIR="$FLUTTER_DIR"
DIST="$CLIENT_DIST"
BUNDLE="$APP_DIR/build/linux/x64/release/bundle"

resolve_flutter() {
    local bin="${FLUTTER_BIN:-$(command -v flutter || true)}"
    [ -z "$bin" ] && [ -x "$HOME/flutter/bin/flutter" ] && bin="$HOME/flutter/bin/flutter"
    [ -n "$bin" ] && [ -x "$bin" ] || die "找不到 flutter：装到 ~/flutter，或设 FLUTTER_BIN"
    echo "$bin"
}

FLUTTER="$(resolve_flutter)"

log "[1/4] flutter build linux --release"
cd "$APP_DIR"
"$FLUTTER" build linux --release

log "[2/4] 收集 bundle 产物 -> dist/"
rm -rf "$DIST/codebiu-linux-x64" "$DIST/codebiu-linux-x64.tar.gz"
mkdir -p "$DIST"
cp -r "$BUNDLE" "$DIST/codebiu-linux-x64"
tar -C "$DIST" -czf "$DIST/codebiu-linux-x64.tar.gz" codebiu-linux-x64

if [ "${SKIP_APPIMAGE:-0}" = "1" ]; then
    log "跳过 AppImage 封装(SKIP_APPIMAGE=1)"
else
    log "[3/4] 组装 AppDir"
    WORK="$(mktemp -d)"
    trap 'rm -rf "$WORK"' EXIT
    APPIMAGE_DIR="$WORK/codebiu.AppDir"
    mkdir -p "$APPIMAGE_DIR/usr/bin"
    cp -r "$BUNDLE"/* "$APPIMAGE_DIR/usr/bin/"
    magick -background none "$FRONTEND_DIR/public/favicon.svg" -resize 256x256 "$APPIMAGE_DIR/codebiu.png"
    printf '[Desktop Entry]\nType=Application\nName=CodeBiu\nComment=CodeBiu AI 助手客户端\nExec=codebiu\nIcon=codebiu\nTerminal=false\nCategories=Utility;\n' \
        > "$APPIMAGE_DIR/codebiu.desktop"
    printf '#!/bin/sh\nHERE="$(readlink -f "$0" | xargs dirname)"\nexec "$HERE/usr/bin/codebiu" "$@"\n' \
        > "$APPIMAGE_DIR/AppRun"
    chmod +x "$APPIMAGE_DIR/AppRun"

    log "[4/4] 封装 AppImage（appimagetool 自动下载缓存）"
    CACHE="$(dirname "$0")/.cache"
    mkdir -p "$CACHE"
    TOOL="$CACHE/appimagetool-x86_64.AppImage"
    if [ ! -x "$TOOL" ]; then
        URL="https://github.com/AppImage/appimagetool/releases/download/continuous/appimagetool-x86_64.AppImage"
        ok=0
        for u in "$URL" "https://mirror.ghproxy.com/$URL" "https://gh-proxy.com/$URL"; do
            if curl -sL --max-time 120 -o "$TOOL" "$u" && [ "$(stat -c%s "$TOOL")" -gt 1000000 ]; then
                ok=1; break
            fi
        done
        [ "$ok" = "1" ] || die "appimagetool 下载失败（可手动放到 $TOOL）"
        chmod +x "$TOOL"
    fi
    ARCH=x86_64 APPIMAGE_EXTRACT_AND_RUN=1 "$TOOL" "$APPIMAGE_DIR" "$DIST/CodeBiu-x86_64.AppImage" >/dev/null
    chmod +x "$DIST/CodeBiu-x86_64.AppImage"
fi

log "完成，产物在 $DIST:"
ls -lh "$DIST" | tail -n +2 | awk '{printf "  %s\t%s\n", $5, $9}'
