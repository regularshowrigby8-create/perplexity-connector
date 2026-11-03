#!/usr/bin/env bash
# uninstall-autostart.sh — remove the proxy autostart installed by install-autostart.sh
set -euo pipefail
if [[ "$(uname -s)" == "Darwin" ]]; then
  PLIST="$HOME/Library/LaunchAgents/ai.perplexity-connector-proxy.plist"
  launchctl unload "$PLIST" 2>/dev/null || true
  rm -f "$PLIST"
  echo "Removed launchd agent."
elif command -v systemctl >/dev/null 2>&1; then
  systemctl --user disable --now perplexity-connector-proxy.service 2>/dev/null || true
  rm -f "$HOME/.config/systemd/user/perplexity-connector-proxy.service"
  systemctl --user daemon-reload
  echo "Removed systemd user unit."
else
  echo "Nothing to remove on this platform."
fi
