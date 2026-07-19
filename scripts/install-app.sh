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

echo "Installed: $DESTINATION"
if [ -d "$BACKUP_APP" ]; then echo "Legacy backup: $BACKUP_APP"; fi
