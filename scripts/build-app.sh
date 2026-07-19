#!/bin/bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
CONFIGURATION="${CONFIGURATION:-release}"
APP="$ROOT/dist/HotkeyMaster.app"
CONTENTS="$APP/Contents"
MACOS="$CONTENTS/MacOS"
RESOURCES="$CONTENTS/Resources"

cd "$ROOT"
swift build -c "$CONFIGURATION" --product HotkeyMaster
BIN_DIR="$(swift build -c "$CONFIGURATION" --show-bin-path)"
clang coredisplay_helper.c -framework CoreGraphics -o "$BIN_DIR/coredisplay_helper"

rm -rf "$APP"
mkdir -p "$MACOS" "$RESOURCES"
cp "$BIN_DIR/HotkeyMaster" "$MACOS/HotkeyMaster"
cp "$BIN_DIR/coredisplay_helper" "$RESOURCES/coredisplay_helper"
cp "$ROOT/Resources/Info.plist" "$CONTENTS/Info.plist"
cp "$ROOT/icons/HotkeyMaster.icns" "$RESOURCES/HotkeyMaster.icns"
chmod 755 "$MACOS/HotkeyMaster" "$RESOURCES/coredisplay_helper"
plutil -lint "$CONTENTS/Info.plist"
codesign --force --deep --sign - "$APP"
codesign --verify --deep --strict --verbose=1 "$APP"
echo "$APP"
