#!/usr/bin/env bash
# ==============================================================================
# 一键: Flutter 客户端 → Android APK 打包（release 分架构，体积极小）
# 产物: 本目录 dist/ 下 CodeBiu-<abi>.apk
#   arm64-v8a    现代安卓手机（绝大多数情况装这个）
#   armeabi-v7a  旧机型
#   x86_64       模拟器
# 可选环境变量:
#   FAT=1     打全架构单包 app-release.apk（兼容所有设备，体积大）
#   DEBUG=1   打 debug 包（默认 release）
#   FLUTTER_BIN=... / ANDROID_HOME=...  覆盖工具路径
# 依赖: flutter SDK, JDK17, Android SDK（默认 ~/android-sdk，脚本自动写 local.properties）
# 注意: 当前为 debug 签名（flutter 模板默认），对外正式发布需自建 keystore 配置签名
# ==============================================================================
source "$(dirname "${BASH_SOURCE[0]}")/../docker_dev/lib.sh"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DIST="$SCRIPT_DIR/dist"
APP_DIR="$REPO_ROOT/code/frontend/flutter"

resolve_flutter() {
    local bin="${FLUTTER_BIN:-$(command -v flutter || true)}"
    [ -z "$bin" ] && [ -x "$HOME/flutter/bin/flutter" ] && bin="$HOME/flutter/bin/flutter"
    [ -n "$bin" ] && [ -x "$bin" ] || die "找不到 flutter：安装到 ~/flutter 或导出 PATH，或设 FLUTTER_BIN"
    echo "$bin"
}

FLUTTER="$(resolve_flutter)"
export ANDROID_HOME="${ANDROID_HOME:-$HOME/android-sdk}"
[ -d "$ANDROID_HOME" ] || die "缺少 Android SDK：装到 ~/android-sdk 或设 ANDROID_HOME"

cd "$APP_DIR"
mkdir -p android
echo "sdk.dir=$ANDROID_HOME" > android/local.properties

MODE="release"
[ "${DEBUG:-0}" = "1" ] && MODE="debug"

if [ "${FAT:-0}" = "1" ]; then
    log "flutter build apk --$MODE（全架构单包）"
    "$FLUTTER" build apk --"$MODE"
    mkdir -p "$DIST"
    cp "build/app/outputs/flutter-apk/app-$MODE.apk" "$DIST/CodeBiu-$MODE-all.apk"
else
    log "flutter build apk --$MODE --split-per-abi（分架构）"
    "$FLUTTER" build apk --"$MODE" --split-per-abi
    mkdir -p "$DIST"
    for f in build/app/outputs/flutter-apk/app-*-"$MODE".apk; do
        [ -f "$f" ] || continue
        abi="$(basename "$f" | sed -E "s/app-(.+)-$MODE\\.apk/\\1/")"
        cp "$f" "$DIST/CodeBiu-$abi.apk"
    done
fi

log "完成，产物清单："
ls -lh "$DIST"/*.apk | awk '{printf "  %s\t%s\n", $5, $9}'
[ "$MODE" = "release" ] && warn "当前 release 包为 debug 签名，正式发布前请配置自有 keystore"
