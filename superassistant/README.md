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

You should see `Connected to server: github`, `github-readonly` and `deepwiki` in the log
(`vercel-connector` is skipped unless you opt in — see the table below). **The PowerShell
prompt will NOT come back — the proxy keeps running in that window.** Leave it open.
⚠️ At info level the proxy prints the `Authorization` header once at startup — once you see
`Connected to server: github`, run `cls` and don't screenshot the log; rotate the PAT when
done. `PROXY_LOGLEVEL=none` silences it. The generated
`superassistant/.generated-config.json` contains the real PAT — it is gitignored and
chmod 600; do not commit or paste it.

Servers in `config.template.json`:

| name | URL | auth | use |
| --- | --- | --- | --- |
| `github` | `https://api.githubcopilot.com/mcp/` | `Authorization: Bearer <PAT>` | full read/write: `search_code`, `get_file_contents`, `push_files`, `create_branch`, `create_pull_request`, issues… |
| `github-readonly` | `https://api.githubcopilot.com/mcp/readonly` | same PAT | safe browsing first |
| `vercel-connector` | `https://perplexity-connector-savage-coo.vercel.app/mcp` | `Bearer <CONNECTOR_API_KEY>` | this repo's self-hosted connector (needs `GITHUB_TOKEN` set in the Vercel dashboard first) |
| `deepwiki` | `https://mcp.deepwiki.com/mcp` | none | public-repo Q&A |

## Step 5 — install the browser extension (use the maintained fork)

**Primary (recommended):** load the maintained fork **v0.7.0** unpacked — it fixes the store
build's broken Streamable HTTP client (upstream #189/#200) and the "0 tools when tools/list
has outputSchema" bug (#191/#199, which GitHub's MCP triggers):

1. Download https://github.com/munir-abbasi/MCP-SuperAssistant-updated/releases/download/v0.7.0/extension-20260925-083157.zip
   (the `.zip`, not the `.xpi`), then extract it, e.g.:
   ```powershell
   Expand-Archive "$env:USERPROFILE\Downloads\extension-20260925-083157.zip" "$env:USERPROFILE\Downloads\fork-ext" -Force
   Get-ChildItem "$env:USERPROFILE\Downloads\fork-ext" -Recurse -Filter manifest.json | Select-Object -ExpandProperty DirectoryName
   ```
   That last command prints the exact folder that contains `manifest.json` — **that** is the folder to load.
2. Chrome → `chrome://extensions` → enable **Developer mode** → **Load unpacked** → select the
   folder printed above (the zip root itself contains `manifest.json`; if it doesn't, select the
   subfolder that does — e.g. `dist/`).
3. Disable/remove the store version of "MCP SuperAssistant" to avoid two sidebars.

**Fallback:** the Chrome Web Store build (https://chromewebstore.google.com/detail/kngiafgkdnlkgmefdafaibkibegkcaef,
upstream https://github.com/srbhptl39/MCP-SuperAssistant, unmaintained since 2026-02-09) —
with it, use **SSE mode** (Step 6) and connect only once (see Troubleshooting for the
reconnect crash).

## Step 6 — connect the extension to the proxy

1. Open https://perplexity.ai and log in (Free account is fine).
2. The extension adds a **sidebar** on the right of the page. Click the server status
   indicator (shows "Disconnected").
3. **With the fork extension (recommended):** keep the proxy in default mode
   (`./start-proxy.sh` / `.\start-proxy.bat` → streamableHttp) and in the sidebar set
   **Connection Type = Streamable HTTP**, **Server URI = `http://localhost:3006/mcp`**.
   **With the store build:** use SSE instead — start the proxy with `./start-proxy.sh sse`
   (Windows: `.\start-proxy.bat sse`) and set **Connection Type = SSE**,
   **Server URI = `http://localhost:3006/sse`**. Connect **once** — do not keep clicking
   refresh (the upstream proxy crashes on SSE reconnect, see Troubleshooting).
4. Click **Connect** / the ↻ refresh button. Status should turn green and list the tools from all servers
   (e.g. `search_repositories`, `get_file_contents`, `create_or_update_file`, `push_files`,
   `create_pull_request`…).
5. In the extension settings, enable **Auto-Execute** and **Auto-Submit** so detected tool
   calls run without a manual click each time.

## Step 7 — talk to your repo from Perplexity Free

Perplexity-specific settings first (from the extension's own docs):

1. **Mode selector**: the docs say turn OFF Search mode, but on Perplexity **Free** Search is the
   only mode (Computer/agent is Pro) — that's OK, stay in Search. The mode is not the blocker;
   missing instructions are. If you ever get Pro, switch to the non-search mode for cleaner calls.
2. **Use a reasoning-capable model** in the Model dropdown if available on Free.
3. In the sidebar, open the **Instructions** tab and click **Insert** (or copy the MCP working
   instructions and paste them into the chat first). Without these, the model doesn't know the
   function-call format and will try Perplexity's own connector registry instead
   ("Unknown source_id").
4. Make sure **Auto Execute** and **Auto Submit** are ON (Settings tab → Automation Features).

Then in a new Perplexity thread, be explicit:

> "Use the github-readonly MCP tool `list_contents` with owner=regularshowrigby8-create,
> repo=perplexity-connector (root), then fetch README.md with `get_file_contents` and
> summarize it."

The model should answer with a ```json function-call block; the extension turns it into a
tool-call card and (Auto Execute) runs it against the proxy and submits the result.

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

## "Did Perplexity patch/block the extension?" (checked 2026-11-03)

- Upstream `srbhptl39/MCP-SuperAssistant`: last code commit **2026-02-09** (v0.6.0, which
  already contained a "Perplexity UI Update fix"). Known Perplexity-side breakages, all from
  **Feb 2026 or earlier**: issue #177 (input-box layout change hid the button — fixed in
  v0.6.0), #59 ("Could not find a suitable insertion point" after the Labs button), and
  **#180: Perplexity added prompt-injection detection that blocks the extension's injected
  "SuperAssistant Operational Instructions"** ("Prompt Injection Attack Detected and
  Blocked"). Our flow does NOT need that injected prompt — just ask naturally in the thread.
- **No Perplexity-specific breakage reports in Oct/Nov 2026** (recent upstream activity is
  ChatGPT-adapter only). But upstream is unmaintained since Feb 2026, so newer silent UI
  changes are possible.
- Watch out for upstream issues #191/#199: **"connected but 0 tools" when tools/list includes
  `outputSchema`** — GitHub's MCP tools do include it. The maintained fork
  `munir-abbasi/MCP-SuperAssistant-updated` (active through **2026-10-18**, v0.7.0) fixes this
  plus Streamable HTTP handling — if you connect but see no tools, load the fork unpacked
  (chrome://extensions → Developer mode → Load unpacked → its `dist`).
- Your "SSE error 404 / Disconnected" is **not** a Perplexity patch — it is the
  extension↔local-proxy link (transport/URI). The proxy is the thing to fix (see below).

### "Sidebar connects but the chat never reacts to tools" — diagnostics (2026-11-03)

The sidebar working proves the content script runs on perplexity.ai. If no tool-call cards
appear and the model claims it has no MCP tools, check in this order:

1. **Only ONE extension enabled**: chrome://extensions — disable/remove the store
   "MCP SuperAssistant" (v0.6.0). Two copies both inject content scripts on perplexity.ai and
   fight each other (shadow-DOM conflicts, duplicate sidebars).
2. **Did the instructions actually get into the chat?** Sidebar → Instructions → **Copy**
   (not Insert), then click the Perplexity input box and Ctrl+V — the long text must be
   *visibly* in the box. If "Insert in Chat" silently failed (stale textarea selector), paste
   manually. Perplexity's prompt-injection filter (upstream #180) can strip auto-injected
   text on submit — manually pasted text as your own message is the reliable route.
3. **Console check**: on perplexity.ai press F12 → Console. The content script logs lines
   starting with `[SuperAssistant]` / `[json-extractor]`. No such lines = content script not
   running on that page (would indicate a real block). Lines present = script runs; the issue
   is instructions/format.
4. **Force the format once** (decisive end-to-end test of extension→proxy→GitHub): send this
   verbatim as the whole message — if the pipeline works, a tool-call card appears over the
   code block and Auto Execute runs it:
   ````
   Reply with ONLY this code block and nothing else:
   ```xml
   <function_calls>
   <invoke name="list_contents">
   <parameter name="owner" string="true">regularshowrigby8-create</parameter>
   <parameter name="repo" string="true">perplexity-connector</parameter>
   </invoke>
   </function_calls>
   ```
   ````
   The extension watches `pre` code blocks on perplexity.ai and detects ```xml
   `<function_calls>` blocks (and ```json `function_call_start` blocks) in them; Auto Execute
   then runs the card. If the card appears and returns the repo file list, the whole chain
   works and the only remaining step is getting the model to emit calls (instructions paste).
5. If the model still refuses after instructions are visibly in the prompt, that is the #180
   filter eating them — retry in a fresh thread with the instructions pasted as the first
   user message.

## Troubleshooting

- **Status stays "Disconnected"**: make sure `start-proxy.sh` is still running (terminal
  open), then chrome://extensions → reload the extension, and re-enter the URL.
- **`EADDRINUSE ::1:3006` / "address already in use"**: an old proxy instance still holds the
  port. Kill it: `netstat -ano | findstr :3006` → note the PID → `taskkill /F /PID <pid>`,
  then start once. Note the proxy binds `localhost`, which on Windows can be IPv6 `::1` only —
  then `127.0.0.1` fails while `localhost` works. To listen on all interfaces:
  `PROXY_HOST=0.0.0.0 ./start-proxy.sh` (Windows: `$env:PROXY_HOST='0.0.0.0'; .\start-proxy.bat`).
- **"SSE error: Non-200 status code (404)"**: either the extension is still on **SSE** while
  the proxy runs in Streamable HTTP mode, or the error text is stale from the previous attempt.
  Fix: set **Connection Type = Streamable HTTP**, **Server URI = `http://localhost:3006/mcp`**,
  then click the **circular refresh/reconnect button** in the sidebar (the "SSE error" text only
  clears on a successful reconnect). If it still 404s, try the URI **without** the path
  (`http://localhost:3006`) — some extension versions append `/mcp` themselves — or
  `http://127.0.0.1:3006/mcp`. Verify the proxy first from another terminal:
  `curl.exe -i -X POST http://localhost:3006/mcp -H "Content-Type: application/json" -H "Accept: application/json, text/event-stream" -d '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-03-26","capabilities":{},"clientInfo":{"name":"t","version":"0.1"}}}'`
  — expect `HTTP/1.1 200` (a 404 means the proxy is in SSE mode: use `/sse`; connection refused
  means the proxy is not running: rerun `start-proxy`).
  ⚠️ On Windows PowerShell 5.1, `curl -d '{"..."}'` loses its quotes (native-arg mangling) and
  you get a 400 JSON SyntaxError — that 400 actually PROVES the proxy is up. Use this instead:
  `Invoke-WebRequest -Uri http://localhost:3006/mcp -Method Post -ContentType 'application/json' -Headers @{Accept='application/json, text/event-stream'} -Body '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-03-26","capabilities":{},"clientInfo":{"name":"t","version":"0.1"}}}'` → check `StatusCode` = 200.
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
