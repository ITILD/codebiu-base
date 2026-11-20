#!/usr/bin/env bash
# ==============================================================================
# 打包 Android APK（Flutter）
#   ./build_android.sh            release 分架构 -> dist/CodeBiu-<abi>.apk
#   FAT=1 ./build_android.sh      全架构单包（体积大）
#   DEBUG=1 ./build_android.sh    debug 包
# 依赖: flutter SDK、JDK17、Android SDK（默认 ~/android-sdk）
# ==============================================================================
source "$(dirname "$0")/../lib.sh"

APP_DIR="$FLUTTER_DIR"
DIST="$CLIENT_DIST"

resolve_flutter() {
    local bin="${FLUTTER_BIN:-$(command -v flutter || true)}"
    [ -z "$bin" ] && [ -x "$HOME/flutter/bin/flutter" ] && bin="$HOME/flutter/bin/flutter"
    [ -n "$bin" ] && [ -x "$bin" ] || die "找不到 flutter：装到 ~/flutter，或设 FLUTTER_BIN"
    echo "$bin"
}

FLUTTER="$(resolve_flutter)"
export ANDROID_HOME="${ANDROID_HOME:-$HOME/android-sdk}"
[ -d "$ANDROID_HOME" ] || die "缺少 Android SDK：装到 ~/android-sdk，或设 ANDROID_HOME"

cd "$APP_DIR"
mkdir -p android "$DIST"
echo "sdk.dir=$ANDROID_HOME" > android/local.properties

MODE="release"
[ "${DEBUG:-0}" = "1" ] && MODE="debug"

if [ "${FAT:-0}" = "1" ]; then
    log "flutter build apk --$MODE（全架构）"
    "$FLUTTER" build apk --"$MODE"
    cp "build/app/outputs/flutter-apk/app-$MODE.apk" "$DIST/CodeBiu-$MODE-all.apk"
else
    log "flutter build apk --$MODE --split-per-abi（分架构）"
    "$FLUTTER" build apk --"$MODE" --split-per-abi
    for f in build/app/outputs/flutter-apk/app-*-"$MODE".apk; do
        [ -f "$f" ] || continue
        abi="$(basename "$f" | sed -E "s/app-(.+)-$MODE\\.apk/\\1/")"
        cp "$f" "$DIST/CodeBiu-$abi.apk"
    done
fi

log "完成，产物在 $DIST:"
ls -lh "$DIST"/*.apk | awk '{printf "  %s\t%s\n", $5, $9}'
[ "$MODE" = "release" ] && warn "release 包当前为 debug 签名，正式发布前请配置自有 keystore"
