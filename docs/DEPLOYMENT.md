# Deployment

## Local, one command

```bash
./run.sh
```

Creates `.venv`, installs the Python arsenal, installs the web app, starts the API on `:8000`
and the interface on `:3000`. `data/` is created automatically (SQLite vault + demo target).

## Docker Compose

```bash
docker compose up -d --build
# interface → http://localhost:3000
# api       → http://localhost:8000/api/docs
```

Volumes: `nh-data` holds the vault, watchlist and extraction cache. The API is only reachable
from the web container unless you publish it.

## Environment (all optional)

| Variable | Default | Meaning |
|---|---|---|
| `NH_RATE_LIMIT_PER_MIN` | `90` | per-IP request budget |
| `NH_PROVIDER_TIMEOUT` | `11` | seconds per engine |
| `NH_CACHE_TTL` | `300` | hunt cache seconds |
| `NH_REQUEST_TIMEOUT` | `9` | per-request HTTP timeout |
| `NH_MAX_DOMAINS_PER_HUNT` | `6` | archive targets per hunt |
| `NH_USER_AGENT` | `Nighthawk/1.0 …` | crawler identity (set a real contact) |
| `NH_SEARXNG_URL` | — | your SearXNG instance, unlocks a full metasearch layer |
| `NH_BRAVE_API_KEY` | — | Brave Search API |
| `NH_TAVILY_API_KEY` / `NH_EXA_API_KEY` | — | agent search APIs |
| `NH_GITHUB_TOKEN` | — | raises GitHub rate limits |
| `API_URL` | `http://127.0.0.1:8000` | where the web app proxies to |

## Binary tiers (optional, big wins)

```bash
go install github.com/projectdiscovery/katana/cmd/katana@latest
go install github.com/lc/gau/v2/cmd/gau@latest
sudo apt install poppler-utils tesseract-ocr httrack wget2
```

Restart is not required; `/arsenal` probes on request.

## Operational notes

- One SQLite file, WAL mode. Back it up by copying `data/nighthawk.db*`.
- The demo target is mounted at `/demo` and is safe to delete after first boot.
- Behind a reverse proxy, forward `X-Forwarded-For` so rate limiting sees real clients.
- If you crawl at volume, set `NH_USER_AGENT` with a contact URL and keep `delay` at 0.5s+.
