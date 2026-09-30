#!/usr/bin/env bash
# Removes the Mac agent LaunchAgent installed by ./install-autostart.sh
set -euo pipefail

LABEL="com.local.assistant-agent"
PLIST="$HOME/Library/LaunchAgents/$LABEL.plist"

launchctl bootout "gui/$UID/$LABEL" 2>/dev/null || launchctl unload "$PLIST" 2>/dev/null || true
rm -f "$PLIST"
echo "Removed: $LABEL"
