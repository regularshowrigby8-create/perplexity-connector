# Nighthawk

**One engine that finds what search engines bury.** A fusion crawler, 119 remote engines,
an 86-engine crawl arsenal and a local full-text vault — fused into a single ranked stream of
**hosted files, open calls, application packs, exposed listings and datasets** — each result carrying
the **funder, amount, currency, location, closing date and real file type** where the web exposes them.

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

## The theme (unchanged)

> **Nighthawk does not rank by popularity, and it does not filter like one.**

It exists for the material a mainstream results page demotes or drops entirely: the PDF in
`/uploads/2019/03/`, the tender notice behind a portal search, the "Index of /" listing nobody
linked, the spreadsheet in a data dump, the page the site deleted. No freshness gate, no
"helpful content" scorer, no domain-authority penalty — old, ugly, unlinked and
machine-generated is the point.

Sort order is an **ordering, not a filter**. Switching to newest-first (or deadline, or depth)
changes what you see first; it never removes the buried, undated or archived results. The engine
states this in `/api/v1/health` under `policy`, so an integration can verify it rather than trust
the copy:

```json
"policy": {
  "purpose": "surface what typical engines filter out",
  "popularity_ranking": false,
  "freshness_gate": false,
  "authority_penalty": false,
  "buried_boost": true
}
```

---

## Newest first, to the second

`sort=newest` is the **default**. It is not a guess at what is fresh — every engine in the
freshness layer hands back the source's own publication timestamp, and the API normalises it to
`published_at`, `age_seconds`, `age_human`, `freshness` and `age_source`:

```
"age_human": "12 seconds ago"      "age_source": "published"
"age_human": "4 minutes ago"       "age_source": "published"
"age_human": "undated"             "age_source": null
```

When a page states no date at all, Nighthawk falls back to **its own clock** — the moment the
engine first saw that URL — and labels it `first_seen` in the badge, so "just now" never means
"we made up a date". Undated results are sorted last and **kept**; they are never dropped for
being old, and generated portal links (which have no upload time) are held outside the limit so
they cannot be pushed off the page by a wave of new items.

Sorting is stable and total: publication time → first-seen time → score → depth. The same rule
runs in the crawler, where `Last-Modified`, `<meta>`/JSON-LD dates, `<time>` tags and sitemap
`<lastmod>` values are all harvested, and in the vault, where a hunt's timestamps are stored so
the next hunt can still order them.

## Clean results, without throwing anything away

Two signals were added, and neither is a filter on age or popularity:

- **quality** (`quality.py`) repairs mojibake, detects language, and scores a page on
  stopword ratio, link density, keyword stuffing and boilerplate. Parked domains, login walls,
  error pages, spam and doorways score low; the score sorts them down and only true junk
  (parked/error/spam/empty) is removed — hidden-page false positives stay in.
- **freshness** (`freshness.py`) supplies the clock above, from WARC/CDX, ISO, RFC 2822, epoch
  and `"2 hours ago"` text, response headers, HTML metadata, feeds and sitemaps.

## The freshness layer (50 new engines)

Added to make the ordering truthful rather than decorative. Each one publishes a real timestamp
with every hit, so the top of the page is genuinely "seconds ago" when something *is* seconds old.

- **Real-time** — GDELT 2.0 · 20 institutional RSS feeds · Reddit (new + curated subs) ·
  Hacker News by date · Lobsters · Mastodon tag timelines · Bluesky latest · GitHub commits ·
  GitHub issues · GitLab activity · GitHub advisories · Wikipedia revisions · Stack Exchange new ·
  crates.io new · npm registry.
- **Open science** — arXiv by submission date · bioRxiv · medRxiv · Crossref (published) ·
  OpenAlex (by date) · Semantic Scholar bulk · Europe PMC · PubMed in-press · DOAJ new · DataCite ·
  Dryad · HAL · OpenAIRE Graph · OSF Preprints.
- **Open data** — Socrata catalog · Federal Register · USAspending new awards · data.gouv.fr ·
  data.europa.eu · CKAN (AU/IE/NZ) · ArcGIS Hub · ClinicalTrials.gov · SEC EDGAR current ·
  Zenodo most-recent · Hugging Face · Wikidata.
- **Opportunities** — Grants.gov (posted today) · TED (EU tenders) · UKRI Gateway to Research ·
  Find a Tender (UK OCDS) · World Bank procurement · CORDIS · FundsforNGOs · UNDP procurement.

Offline proof that each one parses and dates its hits: `python3 scripts/check_sources.py`
(50/50 engines, plus the ordering contract).

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

## Specificity, not just recall

Breadth is cheap. What makes a result usable is the fields inside it. Nighthawk imports the
machinery that produces them:

| Layer | Module | What it does |
|---|---|---|
| URL truth | `urlnorm.py` | RFC-3986 path cleaning, ~90 tracking/session params stripped, default-document removal, IDNA + `www` folding, registrable-domain resolution (courlan / tldextract rules) |
| Near-duplicate collapse | `near_dup.py` | MinHash + LSH (`num_perm=128`), token-set second pass, 64-bit simhash fallback; the **richest** record survives and inherits the others' fields |
| Real file type | `magic.py` | magic-byte sniffing (PDF/OOXML/OLE2/RAR/7z/gzip/SQLite/images/audio/mp4), ZIP re-labelling, PDF title fallback |
| Structured fields | `schemaorg.py` | JSON-LD / microdata / RDFa → typed records, plus a prose fallback (`funded by …`, `USD 250,000`, `Duty station: …`) |
| Keyphrases | `keyterms.py` | YAKE (`n=3`, `dedupLim=0.85`) + lens thesaurus expansion |
| Crawl priority | `priority.py` | heap frontier: documents and opportunity words first, login walls and carts last |
| Change detection | `change.py` | per-URL content hash, word-level diffs for watchers |

See **[docs/REPOS.md](docs/REPOS.md)** for the full import map — 120 projects, which of them run
on the request path, and the parameter that came from each.

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

## The remote engines (119)

`SearXNG · Brave · Tavily · Exa · Serper · SerpApi (+Bing, Yahoo, Ecosia, Startpage, Yandex,
Scholar, News) · SearchApi · Google CSE · Perplexity · You.com · Mojeek · Qwant · MetaGer ·
Whoogle · LibreX · 4get · YaCy · Wiby · Marginalia · Gigablast (retired) · Common Crawl ·
Wayback · Internet Archive · Arquivo.pt · Grants.gov · NIH RePORTER · NSF Awards · USAspending ·
ReliefWeb (jobs + reports) · EU SEDIA ·
OpenAlex · Crossref · arXiv · DOAJ · PubMed · Semantic Scholar · CORE · Wikipedia · Wikidata ·
Open Library · Zenodo · Figshare · Data.gov (+UK, EU, AU, CA) · World Bank documents + data ·
Hugging Face · GitHub · GitLab · Hacker News · Stack Exchange · npm · crates.io ·
Nighthawk Vault + Vault Deep Text · Portal Universe · Dork Hand-off`

Plus the freshness layer listed above: GDELT, institutional RSS, Reddit, Bluesky, Mastodon,
GitHub commits/issues/advisories, GitLab, Wikipedia, Lobsters, Stack Exchange, npm, crates.io,
arXiv/bioRxiv/medRxiv/Crossref/OpenAlex/Semantic Scholar/Europe PMC/PubMed/DOAJ/DataCite/Dryad/
HAL/OpenAIRE/OSF, Socrata/Federal Register/USAspending/data.gouv.fr/data.europa.eu/CKAN/ArcGIS/
ClinicalTrials/SEC EDGAR/Zenodo/Wikidata, Grants.gov live/TED/UKRI/Find a Tender/World Bank
procurement/CORDIS/FundsforNGOs/UNDP.

Open engines run with **zero configuration**. Keyed engines appear as `needs_key` in `/arsenal`
and can be enabled with an environment variable *or* a per-request key that is never stored.

## API

```
POST /api/v1/hunt            federated search (JSON, newest-first by default)
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
  registry.py      the 119 remote engines
  orchestrator.py  fan-out, fusion, ranking, streaming
  local_index.py   SQLite FTS5 / Whoosh / Tantivy / BM25 vault
  portals.py       54 portals + archive targeting
  plays.py         natural language → dorks
  fixtures.py      the offline practice target
apps/web/          Next.js 15 interface (hunt, crawl, arsenal, vault, watchers)
docs/              architecture, engine reference, deployment, and REPOS.md (what was imported)
scripts/selftest.py  end-to-end proof: crawl the fixture, then search inside it
```
