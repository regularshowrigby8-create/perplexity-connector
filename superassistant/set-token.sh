#!/usr/bin/env bash
# set-token.sh - save your GitHub PAT to .github-pat WITHOUT it appearing in chat/history.
# macOS: reads the clipboard (pbpaste). Linux: xclip/wl-paste if available, else hidden prompt.
# Usage: copy the token, then run:  ./set-token.sh
set -euo pipefail
cd "$(dirname "$0")"
t=""
if command -v pbpaste >/dev/null 2>&1; then t="$(pbpaste)"
elif command -v xclip >/dev/null 2>&1; then t="$(xclip -selection clipboard -o)"
elif command -v wl-paste >/dev/null 2>&1; then t="$(wl-paste)"
else
  printf 'Paste the PAT (input hidden), then press Enter: '
  read -rs t; echo
fi
# extract the token even if the clipboard holds surrounding text
t="$(printf '%s' "$t" | grep -o 'github_pat_[A-Za-z0-9_]\{30,\}' | head -1 || true)"
[ -z "$t" ] && t="${GITHUB_PAT:-}"
t="$(printf '%s' "$t" | tr -d '[:space:]' | sed 's/^\xEF\xBB\xBF//')"
if [[ ! "$t" =~ ^github_pat_[A-Za-z0-9_]{30,}$ ]]; then
  echo "ERROR: no fine-grained PAT (github_pat_...) found on the clipboard." >&2
  echo "Copy the token (or any text containing it) and rerun, OR edit the file directly:" >&2
  echo "  nano .github-pat   -> paste the token -> save" >&2
  exit 1
fi
printf '%s' "$t" > .github-pat
chmod 600 .github-pat
echo "OK: PAT saved to .github-pat (git-ignored). Token never printed."
echo "Use it: ./start-proxy.sh    (restart the proxy after changing the token)"
echo "Rotate later: revoke old at github.com/settings/tokens -> new token -> copy -> ./set-token.sh"
