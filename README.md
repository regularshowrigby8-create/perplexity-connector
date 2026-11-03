# perplexity-connector

A **free, self-hosted MCP connector** that you import into **Perplexity** so Perplexity can work with **your GitHub account directly** — search code, read files, browse issues/PRs, create branches, commit files (even straight to `main`), open/merge PRs, create issues and forks.

**No Perplexity API key and no Sonar billing involved.** The connector is a remote MCP server that calls the *GitHub* REST API with *your own GitHub token* (free), which is held server-side. Perplexity just calls the connector's tools. Deploy it free on **Vercel** (hobby tier) in minutes.

```
Perplexity ──MCP over HTTPS──▶ this connector (Vercel, free) ──REST──▶ api.github.com (your PAT, free)
```

## Import into Perplexity — three free options (no Perplexity API key / Sonar billing on any of them)

All options use the same Perplexity UI: sidebar **Plugins → Add custom → Connector → Add MCP connector → Remote** (if Plugins hasn't rolled out to your account yet, the old path still works: **Account settings / Customize → Connectors → + Custom connector (top right) → Remote**; old links redirect). Fill in **Name**, **MCP Server URL** (must be `https://`), under **Advanced** set **Authentication** (None / API Key / OAuth) and **Transport** (**Streamable HTTP**), tick the risk-acknowledgement checkbox (**Add stays greyed out until you tick it**) → **Add** → click the connector card to run the auth flow and enable it → turn it on under **Sources** in a thread. No `pplx-` key is involved, so nothing is billed to Perplexity.

### Why "+ Custom connector" is missing or locked (as of Nov 2026)

1. **Free plan → the option does not exist at all.** Custom (MCP) connectors are a paid-tier feature: **Pro, Max, Enterprise** only (Perplexity help center, quoted in third-party docs through Oct 2026). On Free, the Connectors/Plugins page shows only Perplexity's built-in catalog — the button is absent *by design*, not hidden. There is no public Pro free-trial; occasional programs (students → Education Pro, veterans, carrier partnerships) grant Pro.
2. **The menu moved in October 2026:** "Customize" became **Plugins**. Use **Plugins → Add custom → Connector → Add MCP connector → Remote**, or **Customize → Connectors** if Plugins isn't showing yet.
3. **Enterprise org:** an admin must enable **"Allow members to add custom connectors"** (off by default) under *Enterprise settings → Permissions → Connectors permissions*.
4. **Platform:** works on the **web app (perplexity.ai in a browser) and Mac desktop app**; **not in the iOS/Android apps** (they show only prebuilt connectors) and **not in the Comet browser**.
5. Perplexity also ships a **built-in GitHub connector** (Plugins → Discover → "GitHub" → Connect → authorize with your GitHub account) — also Pro/Max/Enterprise only.

**Free-plan workarounds (verified Nov 2026):** on Free there is **no** way to attach an MCP connector — custom connectors, the built-in GitHub connector, local MCP on the Mac app, and plugin import (plugins can bundle up to 15 remote MCP servers via `plugin.json` + `mcp.json` imported from a public GitHub repo) all require Perplexity Computer / Pro+ plans. What Free *can* do:

1. **Public repo via web search (unlimited standard searches on Free):** paste `https://github.com/<owner>/<repo>` (or file URLs) and ask Perplexity to read/summarize — works because github.com is indexed. For whole-repo context, generate a flattened digest at `gitingest.com` (swap `hub` → `ingest` in any github.com URL) and paste that into the chat — more reliable than raw file fetching.
2. **Upload the repo on Free:** ~3 file uploads/day, 25–40 MB each, up to 5 files per Space — upload a `.zip` of your repo into a Space (persistent) or a thread and chat with it there.
3. **Write path without a connector:** ask Perplexity Free to produce a unified diff / PR description, then apply it via the GitHub web UI ("Edit file" / "Create pull request") or locally with `gh`.
4. **Full MCP access free, outside Perplexity's UI:** use a free MCP client — e.g. claude.ai Free allows one custom connector — pointed at `https://api.githubcopilot.com/mcp/` with your GitHub PAT (API Key auth), or at this repo's self-hosted connector. Reverse direction: run `perplexity-web-mcp` locally with your free account's session cookies to expose Perplexity (free tier works) as MCP tools to your IDE.

**Community workarounds found on Reddit/X (Nov 2026):**

- **MCP SuperAssistant (the actual loophole):** free MIT Chrome/Firefox extension + local proxy (`npx -y @srbhptl39/mcp-superassistant-proxy@latest --config ./config.json`) that injects MCP tool execution into Perplexity's *web UI* — works with free accounts ("leverage your existing free or paid subscriptions"). Point its config at GitHub's hosted MCP via a local bridge: `{"mcpServers":{"github":{"command":"npx","args":["-y","mcp-remote","https://api.githubcopilot.com/mcp/","--header","Authorization: Bearer <PAT>"]}}}` (or at this repo's Vercel connector). The extension detects tool calls in Perplexity's answer, runs them through the proxy, and inserts results back into the chat. Caveats: needs the proxy running locally, Perplexity UI changes can break the adapter (use an actively-fixed fork, e.g. munir-abbasi/MCP-SuperAssistant-updated), Free runs Sonar only, and automated access is a ToS gray area.
- **DeepWiki trick (r/perplexity_ai, Feb 2026):** paste your repo URL into deepwiki.com → copy the generated `deepwiki.com/<owner>/<repo>` link → paste that link into Perplexity Free: it reads the whole repo via DeepWiki's indexed wiki. Works on Free because it is just a URL.
- **Session-cookie bridges:** `perplexity-web-api-mcp` (dhuettner fork v0.13, new `__Secure-pplx.session.<uuid>` cookie scheme + `x-pplx-account` header) and `perplexity-web-mcp` work on **Free** accounts for search/ask — but connector sources like `github_mcp_direct` require a connected (paid) account; Free accounts see no connector IDs.
- **Ruled out:** Perplexity API has **no free tier in 2026** (key generation requires prepaid credits; the $5/mo Pro API credit was removed Feb 2026), so the Agent API "connectors" (GitHub/Slack/Drive, announced @perplexitydevs Aug 2026) bill per call. GitHub Copilot Free (2,000 completions + 50 chat/mo, Copilot CLI, @workspace) is a genuinely free account that works directly on your repo in VS Code — but the Dec 2024 free `@perplexity_ai` Copilot extension promo is over (Free is auto-model only now). Comet (free) supports no custom connectors; `comet-mcp` only bridges its browsing.
- **Repo-context URL tricks:** gitingest.com (github URL with `hub`→`ingest`) for a flattened whole-repo digest to paste into any free chat; github.dev for browser editing; Sourcebot (self-hosted, free) indexes GitHub repos for cited Q&A.

### Option 1 — zero setup, full GitHub account access: GitHub's own hosted MCP server

GitHub hosts the official [`github-mcp-server`](https://github.com/github/github-mcp-server) remotely and, per GitHub's docs, it is **available to all GitHub users regardless of plan** (no Copilot subscription needed for the standard repos/issues/PRs/files tools; read-only variant at `/mcp/readonly`, toolset paths like `/mcp/x/repos`, `/mcp/x/all`).

- **Name:** `GitHub`
- **MCP Server URL:** `https://api.githubcopilot.com/mcp/`
- **Authentication:** `API Key` → paste a GitHub PAT (create a fine-grained one at github.com/settings/tokens, scoped to the repos you want; Perplexity sends the key as a `Authorization: Bearer` header, which is exactly what this server expects) — or choose `OAuth 2.0` and sign in with GitHub
- **Transport:** `Streamable HTTP`

You get the full official toolset — read **and** write on your account (private repos included, per PAT scopes): `search_code`, `get_file_contents`, `push_files`, `create_or_update_file`, `create_pull_request`, `create_issue`, `list_issues`, …

### Option 2 — fully self-controlled: this repo deployed on Vercel (free)

If you'd rather not route through GitHub's hosted endpoint (or need GHES / custom tools), deploy this repo (see "Deploy to Vercel" below). The connector is live at `https://perplexity-connector.vercel.app/mcp`:

- **Name:** `GitHub (self-hosted)`
- **MCP Server URL:** `https://<your-deployment>.vercel.app/mcp`
- **Authentication:** `API Key` → the `CONNECTOR_API_KEY` env var you set in Vercel
- **Transport:** `Streamable HTTP`

It needs a `GITHUB_TOKEN` env var in Vercel (your own PAT, pasted in the Vercel dashboard — never in chat/git) plus a redeploy; check `https://<your-deployment>.vercel.app/health` for `githubTokenConfigured: true`.

### Option 3 — zero setup, read-only, public repos only, no auth at all

- **DeepWiki MCP** — URL `https://mcp.deepwiki.com/mcp`, Authentication `None`. Tools: `ask_question`, `read_wiki_contents`, `read_wiki_structure` for any public repo indexed on DeepWiki.
- **GitMCP** — URL `https://gitmcp.io/docs` (any public repo) or `https://gitmcp.io/{owner}/{repo}`, Authentication `None`. Tools: `search_generic_code`, `search_generic_documentation`, `fetch_generic_documentation`, `fetch_url_content`.

(Read-only, public repos only; be aware of prompt-injection risk when feeding repo content to an LLM.)

### Example things to ask once a connector is enabled under Sources

- *"Search my GitHub repos for `perplexity-connector`, read its README and summarize it"*
- *"In `<owner>/<repo>`, create a branch `fix/thing`, commit a fix to `src/x.ts`, and open a PR into `main`"*
- *"List open issues in `<owner>/<repo>` and file a new one about the bug I describe"*

## Deploy to Vercel (free)

Via the Vercel dashboard or CLI:

```bash
git clone <this repo> && cd perplexity-connector
npm install
vercel login && vercel link          # or: Import Project in the dashboard, point at this git repo
vercel env add GITHUB_TOKEN production        # your GitHub PAT (see security below)
vercel env add CONNECTOR_API_KEY production   # any random string, e.g. $(openssl rand -hex(24))
vercel --prod
```

Then the MCP endpoint is `https://<project>.vercel.app/mcp` (pretty `/mcp` and `/health` routes are wired in `vercel.json`).

The server speaks **stateless Streamable HTTP with JSON responses**, which is exactly what serverless functions (Vercel) and Perplexity's connector form expect — no sticky sessions needed.

## Run locally

```bash
cp .env.example .env        # set GITHUB_TOKEN and CONNECTOR_API_KEY
npm install && npm run build
MCP_HTTP=1 PORT=3000 npm start          # → http://localhost:3000/mcp  (http://localhost:3000/health)
npm start                               # stdio mode for local MCP clients (Claude Desktop, mcp-remote, …)
BASE=http://127.0.0.1:3000 KEY=<CONNECTOR_API_KEY> npm run smoke   # read-only smoke test
```

## Environment variables

| Var | Required | Purpose |
| --- | --- | --- |
| `GITHUB_TOKEN` | yes | GitHub personal access token used **server-side** (alias `GITHUB_PERSONAL_ACCESS_TOKEN` also works). Never committed; never sent to Perplexity. |
| `CONNECTOR_API_KEY` | recommended | If set, MCP clients must send `Authorization: Bearer <key>`. Enter it in Perplexity under Authentication → API Key. If unset, the endpoint is open. |
| `GITHUB_READ_ONLY` | no | `true` → only read/search tools are registered (no writes at all). |
| `ENABLE_DESTRUCTIVE_TOOLS` | no | `true` → additionally registers `delete_repository` (off by default). |
| `GITHUB_API_URL` | no | Override for GitHub Enterprise Server / ghe.com, e.g. `https://ghe.company.com/api/v3`. |
| `PORT` / `MCP_HTTP` | no | Local HTTP mode. |

## Tools

Read (always on): `get_me`, `list_my_repositories`, `search_repositories`, `search_code`, `search_issues`, `search_commits`, `get_repository`, `list_contents`, `get_file_contents`, `list_branches`, `list_commits`, `list_issues`, `get_issue`, `list_pull_requests`, `get_pull_request`, `list_pull_request_files`

Write (unless `GITHUB_READ_ONLY=true`): `create_repository`, `create_fork` (import someone else's repo), `create_branch`, `create_or_update_file`, `delete_file`, `commit_files` (multi-file commit to any branch incl. `main` via the Git Data API), `create_pull_request`, `merge_pull_request`, `create_issue`, `update_issue`, `create_issue_comment`

Destructive (only with `ENABLE_DESTRUCTIVE_TOOLS=true`): `delete_repository`

## Security — read this before giving it wide access

- **Use a fine-grained PAT** (github.com → Settings → Developer settings → Personal access tokens → Fine-grained) and select **only the repositories** you want Perplexity to touch, with `Contents: read & write`, `Issues: read & write`, `Pull requests: read & write`, `Metadata: read`. Avoid "All repositories" unless you really mean it. A classic PAT with `repo` scope gives access to *everything* (incl. private repos) — that matches "all access to my account", but it's a big blast radius.
- The token lives only as a Vercel env var (encrypted at rest). Rotate it anytime in GitHub settings; update the Vercel env var to match.
- `CONNECTOR_API_KEY` keeps random internet clients from driving your GitHub token through the endpoint. Always set it.
- Perplexity asks for confirmation per tool call in the thread — keep that on.
- **Pushing to `main` / deleting files is real.** Prefer branches + PRs. Branch protection rules on GitHub still apply and can block direct pushes to `main` — that's a feature.
- `delete_repository` is disabled unless you explicitly opt in with `ENABLE_DESTRUCTIVE_TOOLS=true`.
- Rate limits with a token: 5,000 req/h core, 30 req/min for search endpoints. The tools surface GitHub's rate-limit errors with reset times.

## Troubleshooting

- `401 Unauthorized` from `/mcp` → wrong/missing API key; use Authentication → API Key in Perplexity with your `CONNECTOR_API_KEY`.
- `405` on GET `/mcp` → normal: this is a stateless server; all MCP traffic is `POST /mcp`.
- `GITHUB_TOKEN is not set` in a tool result → the Vercel env var is missing/misnamed; add it and redeploy (env changes need a new deployment).
- First request after idle is slow → Vercel cold start; retry.
- `search_code` returns 403/empty → code search needs an authenticated token with access; also newly pushed code takes a minute to be indexed.

## How it works

- `src/tools.ts` — MCP tool definitions on top of the GitHub REST API (`src/github.ts`).
- `src/http.ts` — Express app exposing `POST /mcp` using the MCP SDK's `StreamableHTTPServerTransport` in **stateless** mode (`sessionIdGenerator: undefined`, `enableJsonResponse: true`) — one fresh server+transport per request, so it runs on Vercel serverless functions. Optional bearer auth, open CORS, `/health`, `/` info.
- `src/index.ts` — stdio mode (default) or HTTP mode (`MCP_HTTP=1`/`PORT`) for local use.
- `api/mcp.ts`, `api/health.ts` — Vercel serverless entrypoints; `vercel.json` maps `/mcp` and `/health`.
- `test/smoke.mjs` (read-only) and `test/write.mjs` (mutating, uses a throwaway branch) — raw MCP-over-HTTP tests.
