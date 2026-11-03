#!/usr/bin/env bash
# install-autostart.sh — make the MCP SuperAssistant proxy start automatically at login,
# so the Perplexity Free setup keeps working with no manual steps and no agent.
#   macOS:  launchd agent   ~/Library/LaunchAgents/ai.perplexity-connector-proxy.plist
#   Linux:  systemd user unit ~/.config/systemd/user/perplexity-connector-proxy.service
# Remove again with ./uninstall-autostart.sh
set -euo pipefail
cd "$(dirname "$0")"
HERE="$(pwd)"
SCRIPT="$HERE/start-proxy.sh"
chmod +x "$SCRIPT"

if [[ -z "${GITHUB_PAT:-}" && ! -f .github-pat && ! -f "$HOME/.config/perplexity-connector/github-pat.txt" ]]; then
  echo "WARNING: no PAT found yet. start-proxy.sh will fail at boot until you add one:" >&2
  echo "  echo github_pat_... > $HERE/.github-pat" >&2
fi

if [[ "$(uname -s)" == "Darwin" ]]; then
  PLIST="$HOME/Library/LaunchAgents/ai.perplexity-connector-proxy.plist"
  mkdir -p "$HOME/Library/LaunchAgents"
  cat > "$PLIST" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key><string>ai.perplexity-connector-proxy</string>
  <key>ProgramArguments</key>
  <array><string>/bin/bash</string><string>$SCRIPT</string></array>
  <key>WorkingDirectory</key><string>$HERE</string>
  <key>RunAtLoad</key><true/>
  <key>KeepAlive</key><true/>
  <key>StandardOutPath</key><string>$HOME/Library/Logs/perplexity-connector-proxy.log</string>
  <key>StandardErrorPath</key><string>$HOME/Library/Logs/perplexity-connector-proxy.err.log</string>
</dict>
</plist>
EOF
  launchctl unload "$PLIST" 2>/dev/null || true
  launchctl load "$PLIST"
  echo "Installed launchd agent: $PLIST"
  echo "Logs: ~/Library/Logs/perplexity-connector-proxy*.log   — it starts now and at every login."
elif command -v systemctl >/dev/null 2>&1; then
  UNIT_DIR="$HOME/.config/systemd/user"
  mkdir -p "$UNIT_DIR"
  cat > "$UNIT_DIR/perplexity-connector-proxy.service" <<EOF
[Unit]
Description=MCP SuperAssistant proxy for Perplexity Free + GitHub
After=network-online.target

[Service]
Type=simple
WorkingDirectory=$HERE
ExecStart=/bin/bash $SCRIPT
Restart=always
RestartSec=5

[Install]
WantedBy=default.target
EOF
  systemctl --user daemon-reload
  systemctl --user enable --now perplexity-connector-proxy.service
  echo "Installed systemd user unit: $UNIT_DIR/perplexity-connector-proxy.service"
  echo "Status: systemctl --user status perplexity-connector-proxy   Logs: journalctl --user -u perplexity-connector-proxy -f"
else
  echo "Unsupported platform ($(uname -s)). Run ./start-proxy.sh manually or add it to your DE's autostart." >&2
  exit 1
fi
