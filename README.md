# Nighthawk

**One engine that finds what search engines bury.** A fusion crawler, 66 remote engines,
an 86-engine crawl arsenal and a local full-text vault — fused into a single ranked stream of
**hosted files, open calls, application packs, exposed listings and datasets**.

No API keys. No setup wizard. Nothing to configure before your first hunt.

```bash
./run.sh          # → http://localhost:3000
```

### Or just open the launcher

`index.html` is a single self-contained page — no build step, no dependencies. Double-click it,
or drop it on Vercel/Netlify/S3 as a static site, and point it at your engine under
**engine settings**. It probes `/api/v1/health` for live counts, links into every view, and shows
the launch commands with one-click copy.

```
python3 -m http.server 8080      # serve the page alone
# or, with the API running: http://localhost:8000/launch
```

---

## Why this exists

A normal SERP shows you ten pages that were built to rank. It hides the things that actually
carry information: the PDF in `/uploads/2019/03/`, the tender notice behind a portal search,
the spreadsheet in an open-data catalogue, the archived page the site deleted, the directory
listing nobody linked to.

Nighthawk attacks that gap from four directions at once:

| Layer | What it does | Examples |
|---|---|---|
| **Fusion crawler** | Own frontier. Harvests seeds, walks links, opens files, indexes text. | httpx · Crawlee · Scrapy · selectolax · trafilatura · pypdf |
| **Archive indexes** | Reads crawl databases directly, not a search front-end. | Common Crawl index · Wayback CDX · Internet Archive · Arquivo.pt |
| **Structured engines** | APIs that return deadlines, not blue links. | Grants.gov · ReliefWeb · EU SEDIA · OpenAlex · CKAN |
| **Portal universe** | 54 hand-picked opportunity/document/data portals, pre-queried. | Grants.gov · UNGM · TED · Data.gov · Zenodo |

## What makes the results different

- **Depth score (0–100).** Every hit is scored on how buried it is: archive-only, deep path,
  upload/download directories, unusual hosts, non-HTML extensions, directory listings.
  Sort by *most buried* to invert the usual popularity bias.
- **Deadline extraction.** Dates are pulled out of snippets and PDF text with context words
  ("closes", "apply by", "submission deadline"), rendered as *closes in 12d* and sortable.
  Closed calls are kept and labelled, not silently dropped.
- **Full-text vault.** Every PDF/XLSX/DOCX/CSV/ZIP the crawler touches is extracted and written
  into SQLite FTS5 + Whoosh + Tantivy, so you can search *inside* documents offline.
- **Consensus, not competition.** Duplicate URLs collapse to one canonical result that lists
  every engine which found it. Reciprocal-rank fusion decides the order.
- **Watchers.** Save a hunt; every run reports only URLs it has never seen before.

## The crawler (primary engine)

`/crawl` takes seeds, a domain or a query and then:

1. **Plans seeds** — SERP harvesters (DuckDuckGo, Mojeek, Marginalia, Bing, Brave, Startpage,
   Google or your own SearXNG), `robots.txt` sitemaps, Wayback CDX for the domain, or explicit URLs.
2. **Walks the frontier** — bounded depth, concurrency and byte caps; per-host politeness and
   crawl-delay; `robots.txt` honoured by default with a deliberate override for targets you own.
3. **Dispatches work** to whichever arsenal engines are actually installed (probed at request time).
4. **Extracts** files: PDF → `pypdf` → `pdfminer.six`; XLSX → `openpyxl`; DOCX → `python-docx`;
   ZIP → listing + text members; CSV/JSON/XML/SQL → decoded and chunked.
5. **Indexes** the text, then reports files *and* opportunity pages with their deadlines.

Try it with no internet at all: the app ships a **practice target** (`/demo/index.html`) —
five HTML pages, an "Index of /files" listing, three PDFs, a CSV, JSON, a ZIP and a
robots-disallowed page. One click on **Load practice target → Start** exercises the whole
pipeline: fetch → parse → extract → index → rank.

## The arsenal (86 engines)

Not a list of logos — each entry is probed and dispatched by role:

- **fetchers** httpx · aiohttp · Crawlee · Scrapy · MechanicalSoup · Cloudscraper · hrequests
- **parsers** selectolax · parsel · lxml · BeautifulSoup · pyquery · w3lib · tldextract
- **extractors** trafilatura · readability-lxml · JusText · newspaper3k · BoilerPy3 · html2text · extruct · feedparser
- **files** pypdf · pdfminer.six · openpyxl · python-docx · warcio · zipfile · OCR/tika hooks
- **browsers** Playwright · Puppeteer · Selenium · Brozzler · Browsertrix · Splash
- **CLI raiders** katana · hakrawler · gospider · gau · waymore · ffuf · feroxbuster · gobuster ·
  dirsearch · httrack · wget · curl · subfinder · amass · dnsx · linkfinder · arjun · paramspider
- **frameworks** Nutch · Heritrix · StormCrawler · Colly · wpull · warcprox

Missing tiers are reported honestly in `/arsenal` and skipped at runtime. Drop a binary on `PATH`
or `pip install` a Python engine and it lights up — no code change, no restart of the registry logic.

## The remote engines (66)

`SearXNG · Brave · Tavily · Exa · Serper · SerpApi (+Bing, Yahoo, Ecosia, Startpage, Yandex,
Scholar, News) · SearchApi · Google CSE · Perplexity · You.com · Mojeek · Qwant · MetaGer ·
Whoogle · LibreX · 4get · YaCy · Wiby · Marginalia · Gigablast (retired) · Common Crawl ·
Wayback · Internet Archive · Arquivo.pt · Grants.gov · ReliefWeb (jobs + reports) · EU SEDIA ·
OpenAlex · Crossref · arXiv · DOAJ · PubMed · Semantic Scholar · CORE · Wikipedia · Wikidata ·
Open Library · Zenodo · Figshare · Data.gov (+UK, EU, AU, CA) · World Bank documents + data ·
Hugging Face · GitHub · GitLab · Hacker News · Stack Exchange · npm · crates.io ·
Nighthawk Vault + Vault Deep Text · Portal Universe · Dork Hand-off`

Open engines run with **zero configuration**. Keyed engines appear as `needs_key` in `/arsenal`
and can be enabled with an environment variable *or* a per-request key that is never stored.

## API

```
POST /api/v1/hunt            federated search (JSON)
POST /api/v1/hunt/stream     same, as Server-Sent Events
POST /api/v1/crawl           run the crawler to completion
POST /api/v1/crawl/stream    live crawl events (page, file, pagehit, blocked, done)
GET  /api/v1/engines         remote engines + status
GET  /api/v1/arsenal         all 86 crawl engines + probe results
GET  /api/v1/portals         the portal universe
GET  /api/v1/vault?q=        local metadata + full-text search
GET/POST/DELETE /api/v1/hunts + /hunts/{id}/run   watchers with diffing
GET/POST/DELETE /api/v1/saved                    saved items
POST /api/v1/plan            natural language → operator dorks
GET  /api/docs               OpenAPI
```

Everything is proxied through the Next.js app, so the browser only ever talks to one origin.

## Deploy

```bash
docker compose up -d --build     # api :8000, web :3000, volumes for data/
```

Or `./run.sh` on a VPS with Python 3.11+ and Node 20+. The only persistent state is `data/`
(SQLite vault, watchlist, extraction cache).

## Responsible use

The crawler is unrestricted by design — no result ceilings, no provider gatekeepers — but it is
not a licence to do whatever you like. `robots.txt` is enforced unless you explicitly turn it off,
per-host politeness is on, and the SERP harvesters are rate-limited. Point it at domains you own,
domains that permit crawling, or public-interest work you have cleared. It does not bypass
authentication, solve challenges, or touch anything behind a login.

## Layout

```
apps/api/app/
  crawl.py         fusion crawler: seeds → frontier → files → vault
  arsenal.py       the 86-engine manifest + probes
  textkit.py       parser/extractor dispatch
  registry.py      the 66 remote engines
  orchestrator.py  fan-out, fusion, ranking, streaming
  local_index.py   SQLite FTS5 / Whoosh / Tantivy / BM25 vault
  portals.py       54 portals + archive targeting
  plays.py         natural language → dorks
  fixtures.py      the offline practice target
apps/web/          Next.js 15 interface (hunt, crawl, arsenal, vault, watchers)
docs/              architecture, engine reference, deployment
scripts/selftest.py  end-to-end proof: crawl the fixture, then search inside it
```
