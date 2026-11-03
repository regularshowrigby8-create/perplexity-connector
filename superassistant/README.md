# Perplexity Free + GitHub, step by step (MCP SuperAssistant loophole)

Goal: use your **Perplexity Free** account in the browser to read **and write** your GitHub
repos, with $0 spent. Perplexity's own "+ Custom connector" is Pro+ only, so we inject MCP
tools into the web UI with the free **MCP SuperAssistant** extension + a local proxy that
forwards to GitHub's own hosted MCP server (`https://api.githubcopilot.com/mcp/`), which is
free for every GitHub user when authenticated with your own PAT.

> ⚠️ Gray area: the extension drives the page programmatically. Perplexity's ToS may treat
> automated access as misuse; use at your own discretion. Keep the PAT in a gitignored file
> only — never commit it.

## 60-second quickstart (beginner)

0. **Install 3 things:** Git (git-scm.com), Node.js 18+ (nodejs.org → download **LTS**), Google Chrome.
1. **Make a GitHub key (PAT):** github.com → your avatar → **Settings** → **Developer settings** → **Personal access tokens** → **Fine-grained tokens** → **Generate new token**. Name it `perplexity-mcp`, Repository access → your repos, Permissions → **Contents: Read and write**, **Pull requests: Read and write**, **Issues: Read and write** (Metadata is auto). Generate → **copy the `github_pat_...` value immediately (shown only once)**.
2. **Terminal** (Mac: Applications → Utilities → Terminal; Windows: **PowerShell**). Run:
   ```bash
   git clone -b arena/13ca0619-perplexity-connector https://github.com/regularshowrigby8-create/perplexity-connector.git
   cd perplexity-connector/superassistant
   # save your token from the CLIPBOARD (never typed into chat/history):
   ./set-token.sh          # Mac/Linux — or on Windows:  .\set-token.bat
   chmod +x start-proxy.sh && ./start-proxy.sh # keep this window open; wait for "Connected to server: github"
   ```
   (Windows PowerShell equivalent: `.\set-token.bat` then `.\start-proxy.bat`)
   **Windows (PowerShell) instead of the last line:** `.\start-proxy.bat` — it does the same thing via `start-proxy.ps1`.
   (On Windows, run the `./doctor.sh` self-check inside **Git Bash**, which came with Git for Windows.)
   In a second terminal, optionally self-check: `./doctor.sh`
3. **Chrome:** install the **MCP SuperAssistant** extension from the Chrome Web Store
   (https://chromewebstore.google.com/detail/kngiafgkdnlkgmefdafaibkibegkcaef).
4. **Connect:** open https://perplexity.ai and log in (Free is fine) → the extension adds a sidebar on the right → click the **Disconnected** status → paste `http://localhost:3006/mcp` → **Connect** → turn on **Auto-Execute** and **Auto-Submit**.
5. **First test (read-only):** in a new Perplexity thread type:
   *"Use the github-readonly MCP tools to list the files in regularshowrigby8-create/perplexity-connector and summarize the README."*
6. **When that works, writes:** *"Using the github MCP tools, create a branch, edit a file, push it, and open a pull request in regularshowrigby8-create/perplexity-connector."*

To make the proxy start automatically at login (so you never run step 2's last command by hand): `./install-autostart.sh`.

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
# the setup kit is on the arena branch (not main yet):
git clone -b arena/13ca0619-perplexity-connector https://github.com/regularshowrigby8-create/perplexity-connector.git
cd perplexity-connector/superassistant
# later: git pull   to get updates
```

## Step 3 — hand the PAT to the launcher (never committed)

Easiest (token taken from the **clipboard**, never typed into chat/history — it even
extracts the `github_pat_...` part if you copied extra text around it):

```bash
./set-token.sh          # Mac/Linux   (Windows: .\set-token.bat)
```

Fallbacks, any one of:

```bash
export GITHUB_PAT=github_pat_...                 # session-only
echo github_pat_... > .github-pat                # gitignored file in superassistant/
notepad .github-pat                              # Windows: paste token in Notepad, save
mkdir -p ~/.config/perplexity-connector && echo github_pat_... > ~/.config/perplexity-connector/github-pat.txt
```

## Changing / rotating the token (the easy way)

The PAT lives in exactly **one** place: `superassistant/.github-pat` (git-ignored, chmod 600).
It is never printed, never committed, never put in shell history or chat.

- **Set or replace:** copy the new token (Ctrl+C), run `.\set-token.bat` (Windows) or
  `./set-token.sh` (Mac/Linux), then restart the proxy (`.\start-proxy.bat` / `./start-proxy.sh`).
  No other file ever changes.
- The launcher pre-flights the token against `api.github.com` (prints only the HTTP status,
  never the token), so a bad/expired token fails fast.
- **Revoke old tokens** at https://github.com/settings/tokens (avatar → Settings → Developer
  settings → Personal access tokens → Fine-grained tokens → Delete).

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

## Runs without the agent — self-contained

Nothing in this setup depends on this chat or on any agent being online:

- **This repo clone** contains everything (template config, launcher, guide).
- **`./doctor.sh`** — self-check run anytime: Node version, PAT presence, config
  generation, live proxy endpoint + visible tool list, upstream reachability.
  Override the port with `PROXY_URL=http://localhost:3999/mcp ./doctor.sh`.
- **`./install-autostart.sh`** — auto-starts the proxy at login (macOS launchd agent /
  Linux systemd user unit), so you never have to remember to run `start-proxy.sh`.
  Undo with `./uninstall-autostart.sh`.
- **The moving parts live on infra that outlives any session**: the extension and proxy
  run on your machine, GitHub's MCP on GitHub's servers, and the optional
  `vercel-connector` on Vercel's servers (deployment stays up on its own).

```bash
./doctor.sh                  # diagnose anytime
./install-autostart.sh       # start proxy automatically at every login
./uninstall-autostart.sh     # remove autostart again
```

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
