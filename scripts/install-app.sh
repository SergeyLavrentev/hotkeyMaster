#!/bin/bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SOURCE_APP="$ROOT/dist/HotkeyMaster.app"
DESTINATION="${INSTALL_DESTINATION:-/Applications/HotkeyMaster.app}"
DESTINATION_DIR="$(dirname "$DESTINATION")"
STAMP="$(date +%Y%m%d-%H%M%S)"
BACKUP_ROOT="$HOME/Library/Application Support/HotkeyMaster/LegacyBackup"
BACKUP_APP="$BACKUP_ROOT/HotkeyMaster-$STAMP.app"
STAGING_APP="$DESTINATION_DIR/.HotkeyMaster-$STAMP.installing.app"
PREVIOUS_APP="$DESTINATION_DIR/.HotkeyMaster-$STAMP.previous.app"

if [ ! -d "$SOURCE_APP" ]; then
    echo "Missing $SOURCE_APP; run make app first" >&2
    exit 1
fi

SOURCE_BINARY="$SOURCE_APP/Contents/MacOS/HotkeyMaster"
if [ ! -x "$SOURCE_BINARY" ]; then
    echo "Missing executable $SOURCE_BINARY; run make app first" >&2
    exit 1
fi

NEWER_INPUT="$(find "$ROOT/Sources" "$ROOT/Package.swift" "$ROOT/Resources" "$ROOT/scripts/build-app.sh" -newer "$SOURCE_BINARY" -print -quit)"
if [ -n "$NEWER_INPUT" ]; then
    echo "Stale $SOURCE_APP: $NEWER_INPUT is newer; run make app first" >&2
    exit 1
fi

mkdir -p "$BACKUP_ROOT"
rm -rf "$STAGING_APP" "$PREVIOUS_APP"
ditto "$SOURCE_APP" "$STAGING_APP"
codesign --verify --deep --strict "$STAGING_APP"

if [ -d "$DESTINATION" ]; then
    ditto "$DESTINATION" "$BACKUP_APP"
    mv "$DESTINATION" "$PREVIOUS_APP"
fi

restore_previous() {
    rm -rf "$DESTINATION"
    if [ -d "$PREVIOUS_APP" ]; then mv "$PREVIOUS_APP" "$DESTINATION"; fi
    rm -rf "$STAGING_APP"
}
trap restore_previous ERR

mv "$STAGING_APP" "$DESTINATION"
codesign --verify --deep --strict "$DESTINATION"
trap - ERR
rm -rf "$PREVIOUS_APP"

# Native builds use SMAppService. Remove the old Python-era LaunchAgent so
# macOS does not invoke the same bundle a second time at login.
LEGACY_LAUNCH_AGENT="$HOME/Library/LaunchAgents/com.slavrentev.hotkeymaster.plist"
if [ -f "$LEGACY_LAUNCH_AGENT" ]; then
    launchctl bootout "gui/$(id -u)/com.slavrentev.hotkeymaster" 2>/dev/null || true
    rm -f "$LEGACY_LAUNCH_AGENT"
    echo "Removed legacy startup item: $LEGACY_LAUNCH_AGENT"
fi

echo "Installed: $DESTINATION"
if [ -d "$BACKUP_APP" ]; then echo "Legacy backup: $BACKUP_APP"; fi
