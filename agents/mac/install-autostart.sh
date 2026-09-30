#!/usr/bin/env bash
# Installs the Mac agent as a LaunchAgent: starts at login, restarts if it crashes.
# Remove it again with ./uninstall-autostart.sh
set -euo pipefail

LABEL="com.local.assistant-agent"
DIR="$(cd "$(dirname "$0")" && pwd)"
ROOT="$(cd "$DIR/../.." && pwd)"
PYTHON="$DIR/.venv/bin/python3"
LOG="$HOME/Library/Logs/assistant-agent.log"
PLIST="$HOME/Library/LaunchAgents/$LABEL.plist"

# Backend port comes from the repository .env (defaults to 8000).
PORT=8000
if [ -f "$ROOT/.env" ]; then
  PORT="$(awk -F= '/^BACKEND_PORT=/{print $2}' "$ROOT/.env" | tail -1)"
  PORT="${PORT:-8000}"
fi
SERVER="ws://localhost:$PORT/ws/devices"

if [ ! -x "$PYTHON" ]; then
  echo "Creating the agent's virtualenv..."
  python3 -m venv "$DIR/.venv"
  "$DIR/.venv/bin/pip" install --quiet -r "$DIR/requirements.txt"
fi

mkdir -p "$HOME/Library/LaunchAgents"
cat > "$PLIST" <<PLIST_EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key><string>$LABEL</string>
    <key>ProgramArguments</key>
    <array>
        <string>$PYTHON</string>
        <string>$DIR/agent.py</string>
        <string>--server</string>
        <string>$SERVER</string>
    </array>
    <key>WorkingDirectory</key><string>$DIR</string>
    <key>RunAtLoad</key><true/>
    <key>KeepAlive</key><true/>
    <key>StandardOutPath</key><string>$LOG</string>
    <key>StandardErrorPath</key><string>$LOG</string>
</dict>
</plist>
PLIST_EOF

launchctl bootout "gui/$UID/$LABEL" 2>/dev/null || true
launchctl bootstrap "gui/$UID" "$PLIST" 2>/dev/null || launchctl load "$PLIST"

echo "Installed: $LABEL"
echo "  server: $SERVER"
echo "  log:    $LOG"
echo "The agent now starts at login. It keeps retrying while the backend is down."
