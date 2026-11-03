#!/usr/bin/env bash
# doctor.sh — self-check for the Perplexity Free + MCP SuperAssistant setup.
# Run this anytime, no agent needed:  ./doctor.sh
# Override the proxy endpoint if you started it on another port:  PROXY_URL=http://localhost:3999/mcp ./doctor.sh
set -uo pipefail
cd "$(dirname "$0")"
fail=0
ok()   { echo "  [OK]   $1"; }
bad()  { echo "  [FAIL] $1"; fail=1; }
warn() { echo "  [WARN] $1"; }

echo "1) Node.js 18+"
if command -v node >/dev/null 2>&1; then
  major="$(node -v | sed 's/^v//; s/\..*$//')"
  if [[ "$major" -ge 18 ]]; then ok "node $(node -v)"; else bad "node $(node -v) is too old — install Node 18+"; fi
else
  bad "node not found — install Node.js 18+ (nodejs.org)"
fi

echo "2) GitHub PAT available"
if [[ -n "${GITHUB_PAT:-}" ]]; then ok "\$GITHUB_PAT is set"
elif [[ -f .github-pat ]]; then ok "superassistant/.github-pat present"
elif [[ -f "$HOME/.config/perplexity-connector/github-pat.txt" ]]; then ok "~/.config/perplexity-connector/github-pat.txt present"
else bad "no PAT found — create one (README step 1) and store it (README step 3)"; fi

echo "3) start-proxy.sh can generate a valid config"
if DRY_RUN=1 GITHUB_PAT="${GITHUB_PAT:-doctor-dummy-pat}" ./start-proxy.sh >/dev/null 2>&1; then
  ok "config generation + JSON validation passed"
else
  bad "DRY_RUN=1 ./start-proxy.sh failed — run it manually to see the error"
fi
rm -f .generated-config.json

echo "4) Local proxy is answering"
URL="${PROXY_URL:-http://localhost:3006/mcp}"
HDR="$(mktemp)"; BODY="$(mktemp)"
if curl -s -m 5 -X POST "$URL" -H 'Content-Type: application/json' -H 'Accept: application/json, text/event-stream' \
     -d '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-03-26","capabilities":{},"clientInfo":{"name":"doctor","version":"0.1"}}}' \
     -D "$HDR" -o "$BODY"; then
  ok "proxy responds at $URL"
  sid="$(grep -i '^mcp-session-id:' "$HDR" | tr -d '\r' | awk '{print $2}')"
  extra=(); [[ -n "$sid" ]] && extra=(-H "mcp-session-id: $sid")
  curl -s -m 10 -X POST "$URL" -H 'Content-Type: application/json' -H 'Accept: application/json, text/event-stream' "${extra[@]}" \
       -d '{"jsonrpc":"2.0","method":"notifications/initialized"}' >/dev/null 2>&1
  tools="$(curl -s -m 10 -X POST "$URL" -H 'Content-Type: application/json' -H 'Accept: application/json, text/event-stream' "${extra[@]}" \
       -d '{"jsonrpc":"2.0","id":2,"method":"tools/list","params":{}}' | grep -o '"name":"[^"]*"' | sed 's/"name":"//;s/"//' | head -40 | tr '\n' ' ')"
  if [[ -n "$tools" ]]; then ok "tools visible through proxy: $tools"; else warn "initialize OK but tools/list empty — check the proxy terminal log (PAT scopes?)"; fi
else
  bad "nothing answering at $URL — start it: ./start-proxy.sh   (or set PROXY_URL=...)"
fi
rm -f "$HDR" "$BODY"

echo "5) Upstream GitHub MCP reachability (informational)"
if curl -s -m 8 -o /dev/null -X POST https://api.githubcopilot.com/mcp/ \
     -H 'Content-Type: application/json' -H 'Accept: application/json, text/event-stream' \
     -d '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-03-26","capabilities":{},"clientInfo":{"name":"doctor","version":"0.1"}}}'; then
  ok "api.githubcopilot.com reachable from this machine"
else
  warn "api.githubcopilot.com not reachable from here (VPN/firewall/offline — the proxy must be able to reach it when you use it)"
fi

echo
if [[ "$fail" -eq 0 ]]; then echo "RESULT: all critical checks passed — the setup is self-contained."; else echo "RESULT: fix the [FAIL] items above (README has a troubleshooting section)."; fi
exit "$fail"
