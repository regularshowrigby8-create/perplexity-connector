#!/usr/bin/env bash
# start-proxy.sh — launch the MCP SuperAssistant proxy pre-configured for GitHub.
#
# Secrets are resolved in this order (the PAT is NEVER committed: the generated
# config is gitignored and chmod 600):
#   1. $GITHUB_PAT environment variable
#   2. superassistant/.github-pat            (gitignored file, one line)
#   3. ~/.config/perplexity-connector/github-pat.txt
# CONNECTOR_API_KEY (for the vercel-connector server) comes from
# $CONNECTOR_API_KEY or falls back to the key documented in the repo README.
#
# Usage:
#   ./start-proxy.sh                 # streamableHttp output on :3006/mcp
#   ./start-proxy.sh sse             # SSE output on :3006/sse
#   ./start-proxy.sh ws              # WebSocket output on :3006/message
#   DRY_RUN=1 ./start-proxy.sh       # only generate + validate the config, print it masked
set -euo pipefail
cd "$(dirname "$0")"

TEMPLATE="config.template.json"
OUT=".generated-config.json"

PAT="${GITHUB_PAT:-}"
if [[ -z "$PAT" && -f .github-pat ]]; then PAT="$(tr -d '[:space:]' < .github-pat)"; fi
if [[ -z "$PAT" && -f "$HOME/.config/perplexity-connector/github-pat.txt" ]]; then
  PAT="$(tr -d '[:space:]' < "$HOME/.config/perplexity-connector/github-pat.txt")"
fi
if [[ -z "$PAT" ]]; then
  echo "ERROR: no GitHub PAT found. Provide one via any of:" >&2
  echo "  export GITHUB_PAT=github_pat_...                              # session only" >&2
  echo "  echo github_pat_... > superassistant/.github-pat               # gitignored file" >&2
  echo "  mkdir -p ~/.config/perplexity-connector && echo github_pat_... > ~/.config/perplexity-connector/github-pat.txt" >&2
  exit 1
fi

# Documented in README.md (it is the public auth for your own Vercel connector).
KEY="${CONNECTOR_API_KEY:-ebc9973a4109f439485a7e562656eed428e9164733a90f8d}"

node -e '
  const fs = require("fs");
  const tpl = fs.readFileSync(process.argv[1], "utf8");
  const out = tpl
    .split("__GITHUB_PAT__").join(process.argv[2])
    .split("__CONNECTOR_API_KEY__").join(process.argv[3]);
  JSON.parse(out); // validate before writing
  fs.writeFileSync(process.argv[4], out);
' "$TEMPLATE" "$PAT" "$KEY" "$OUT"
chmod 600 "$OUT"

if [[ "${DRY_RUN:-0}" == "1" ]]; then
  echo "OK: $OUT generated and valid JSON. Contents (secrets masked):"
  node -e 'const c=require(process.argv[1]); for (const [k,v] of Object.entries(c.mcpServers)) { if (v.headers) v.headers = Object.fromEntries(Object.entries(v.headers).map(([h,val])=>[h, val.replace(/Bearer .+/, "Bearer ***")])); console.log(k, JSON.stringify(v)); }' "$PWD/$OUT"
  exit 0
fi

TRANSPORT="${1:-streamableHttp}"
case "$TRANSPORT" in
  streamableHttp) EP="/mcp" ;;
  sse)            EP="/sse" ;;
  ws)             EP="/message" ;;
  *) echo "Unknown transport: $TRANSPORT (use streamableHttp|sse|ws)" >&2; exit 1 ;;
esac

echo "Starting MCP SuperAssistant proxy on http://localhost:3006 (transport: $TRANSPORT)"
echo "In the browser extension, connect the sidebar to: http://localhost:3006$EP"
exec npx -y @srbhptl39/mcp-superassistant-proxy@latest --config "$OUT" --outputTransport "$TRANSPORT" --port 3006
