# Perplexity Free + GitHub, step by step (MCP SuperAssistant loophole)

Goal: use your **Perplexity Free** account in the browser to read **and write** your GitHub
repos, with $0 spent. Perplexity's own "+ Custom connector" is Pro+ only, so we inject MCP
tools into the web UI with the free **MCP SuperAssistant** extension + a local proxy that
forwards to GitHub's own hosted MCP server (`https://api.githubcopilot.com/mcp/`), which is
free for every GitHub user when authenticated with your own PAT.

> ⚠️ Gray area: the extension drives the page programmatically. Perplexity's ToS may treat
> automated access as misuse; use at your own discretion. Keep the PAT in a gitignored file
> only — never commit it.

## What you need

- A browser with the extension store (Chrome/Edge/Brave or Firefox)
- Node.js 18+ (`node --version`)
- A Perplexity account (Free is fine) logged in at perplexity.ai in that browser
- A GitHub **fine-grained PAT** with access to your repos

## Step 1 — create the GitHub PAT (2 min)

1. Go to https://github.com/settings/tokens (fine-grained, "Generate new token (classic is NOT supported by the MCP server — use fine-grained)").
2. Repository access: **Only select repositories** → pick your repos (or All repositories).
3. Permissions:
   - **Contents: Read and write** (read files, push branches/commits)
   - **Pull requests: Read and write** (create PRs)
   - **Issues: Read and write**
   - **Metadata: Read-only** (added automatically)
   - **Workflows: Read and write** (only if you want to edit workflow files)
4. Generate, copy the `github_pat_...` value once. Treat it like a password.

## Step 2 — get this repo locally

```bash
git clone https://github.com/regularshowrigby8-create/perplexity-connector.git
cd perplexity-connector/superassistant
```

## Step 3 — hand the PAT to the launcher (never committed)

Any one of:

```bash
export GITHUB_PAT=github_pat_...                 # session-only
echo github_pat_... > .github-pat                # gitignored file in superassistant/
mkdir -p ~/.config/perplexity-connector && echo github_pat_... > ~/.config/perplexity-connector/github-pat.txt
```

## Step 4 — start the local proxy

```bash
chmod +x start-proxy.sh
DRY_RUN=1 ./start-proxy.sh        # optional: generate + validate config, secrets masked
./start-proxy.sh                  # starts proxy on http://localhost:3006, output at /mcp
# variants: ./start-proxy.sh sse   (connect to /sse)   ./start-proxy.sh ws  (connect to /message)
```

You should see `Connected to server: github` (and `github-readonly`, `vercel-connector`,
`deepwiki`) in the log. Leave this terminal running. The generated
`superassistant/.generated-config.json` contains the real PAT — it is gitignored and
chmod 600; do not commit or paste it.

Servers in `config.template.json`:

| name | URL | auth | use |
| --- | --- | --- | --- |
| `github` | `https://api.githubcopilot.com/mcp/` | `Authorization: Bearer <PAT>` | full read/write: `search_code`, `get_file_contents`, `push_files`, `create_branch`, `create_pull_request`, issues… |
| `github-readonly` | `https://api.githubcopilot.com/mcp/readonly` | same PAT | safe browsing first |
| `vercel-connector` | `https://perplexity-connector-savage-coo.vercel.app/mcp` | `Bearer <CONNECTOR_API_KEY>` | this repo's self-hosted connector (needs `GITHUB_TOKEN` set in the Vercel dashboard first) |
| `deepwiki` | `https://mcp.deepwiki.com/mcp` | none | public-repo Q&A |

## Step 5 — install the browser extension

1. Chrome Web Store → search **"MCP SuperAssistant"** → Add to Chrome
   (Firefox: addons.mozilla.org). MIT, free.
   Source: https://github.com/srbhptl39/MCP-SuperAssistant
   If the Perplexity adapter breaks after a Perplexity UI change, load a maintained fork
   instead, e.g. https://github.com/munir-abbasi/MCP-SuperAssistant-updated (load unpacked:
   chrome://extensions → Developer mode → Load unpacked → the `dist` folder of the release zip).
2. If the store listing is gone, download the release zip from the repo's Releases page and
   load it unpacked the same way.

## Step 6 — connect the extension to the proxy

1. Open https://perplexity.ai and log in (Free account is fine).
2. The extension adds a **sidebar** on the right of the page. Click the server status
   indicator (shows "Disconnected").
3. Enter the proxy URL matching the transport you started:
   - `./start-proxy.sh` (default) → `http://localhost:3006/mcp`
   - `./start-proxy.sh sse` → `http://localhost:3006/sse`
   - `./start-proxy.sh ws` → `ws://localhost:3006/message`
4. Click **Connect**. Status should turn green and list the tools from all four servers
   (e.g. `search_repositories`, `get_file_contents`, `create_or_update_file`, `push_files`,
   `create_pull_request`…).
5. In the extension settings, enable **Auto-Execute** and **Auto-Submit** so detected tool
   calls run without a manual click each time.

## Step 7 — talk to your repo from Perplexity Free

In a new Perplexity thread, be explicit (Free runs Sonar, which sometimes needs a nudge to
emit tool calls):

> "You have MCP tools available in the SuperAssistant sidebar (servers: github,
> github-readonly). Use the github-readonly tools to list the files in
> regularshowrigby8-create/perplexity-connector and summarize the README."

Then for writes, switch to the full server:

> "Using the `github` MCP tools: create a branch `feature/x` in
> regularshowrigby8-create/perplexity-connector, update README.md with …, and push it."

The flow: Perplexity emits a tool call → the extension detects it → the local proxy runs it
against `api.githubcopilot.com/mcp` with your PAT → the result is inserted back into the
chat → Perplexity continues. Everything happens inside the normal Perplexity Free UI.

## Troubleshooting

- **Status stays "Disconnected"**: make sure `start-proxy.sh` is still running (terminal
  open), then chrome://extensions → reload the extension, and re-enter the URL.
- **"Connected" but no tools / errors**: check the proxy terminal — if a server failed to
  connect, the PAT may be wrong/expired or lack scopes; re-check Step 1. `deepwiki` needs no
  auth and is a good canary.
- **Tool calls not detected**: prompt explicitly ("call the tool named `get_file_contents`
  with …"), and enable Auto-Execute/Auto-Submit.
- **401 from GitHub MCP**: fine-grained PAT expired or missing `Contents`/`Metadata` scopes.
- **CORS errors in console**: the proxy enables CORS by default; always connect via the
  proxy URL, never the remote URL directly from the extension.
- **perplexity.ai UI changed and the sidebar vanished**: use the updated fork (Step 5).
- **Token hygiene**: `git status` must never show `.generated-config.json` or `.github-pat`
  (both gitignored). Rotate the PAT at github.com/settings/tokens if you ever pasted it
  anywhere public.

## Alternative target: this repo's Vercel connector

`vercel-connector` in the template points at the live deployment
`https://perplexity-connector-savage-coo.vercel.app/mcp`. For it to act on GitHub, first set
`GITHUB_TOKEN` (your PAT) in the Vercel project dashboard → Settings → Environment
Variables, then Redeploy; until then `/health` reports `githubTokenConfigured: false`.
Prefer `github`/`github-readonly` (GitHub's own hosted MCP) — no hosting needed at all.
