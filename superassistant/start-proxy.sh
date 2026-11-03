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
if [[ -z "$PAT" && -f .github-pat ]]; then PAT="$(tr -d '[:space:]' < .github-pat | sed 's/^\xEF\xBB\xBF//')"; fi
if [[ -z "$PAT" && -f "$HOME/.config/perplexity-connector/github-pat.txt" ]]; then
  PAT="$(tr -d '[:space:]' < "$HOME/.config/perplexity-connector/github-pat.txt" | sed 's/^\xEF\xBB\xBF//')"
fi
if [[ -z "$PAT" ]]; then
  echo "ERROR: no GitHub PAT found. Provide one via any of:" >&2
  echo "  export GITHUB_PAT=github_pat_...                              # session only" >&2
  echo "  echo github_pat_... > superassistant/.github-pat               # gitignored file" >&2
  echo "  mkdir -p ~/.config/perplexity-connector && echo github_pat_... > ~/.config/perplexity-connector/github-pat.txt" >&2
  exit 1
fi
if [[ ! "$PAT" =~ ^github_pat_[A-Za-z0-9_]{30,}$ ]]; then
  echo "ERROR: '$PAT' is not a real fine-grained PAT (must start with github_pat_, long token, no '...' placeholders)." >&2
  exit 1
fi
# Pre-flight: ask GitHub if the token is valid (prints only the HTTP status, never the token)
if command -v curl >/dev/null 2>&1; then
  code="$(curl -s -o /dev/null -w '%{http_code}' -H "Authorization: Bearer $PAT" https://api.github.com/user || echo 000)"
  if [[ "$code" != "200" ]]; then
    echo "ERROR: api.github.com rejected this token (HTTP $code). Regenerate it (fine-grained; needs Metadata read + Contents read/write) and retry." >&2
    exit 1
  fi
  echo "GitHub token OK (HTTP $code)."
fi

# Documented in README.md (it is the public auth for your own Vercel connector).
KEY="${CONNECTOR_API_KEY:-ebc9973a4109f439485a7e562656eed428e9164733a90f8d}"

# Generate the config via gen-config.cjs (secrets via env vars, never CLI args).
GEN_GITHUB_PAT="$PAT" GEN_CONNECTOR_KEY="$KEY" node gen-config.cjs
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
