# Architecture

```
                       ┌─────────────────────────────┐
   query ─────────────▶│  query intelligence (plays) │
                       └──────────────┬──────────────┘
                                      │
        ┌─────────────────────────────┼──────────────────────────────┐
        ▼                             ▼                              ▼
┌───────────────┐           ┌──────────────────┐          ┌──────────────────┐
│ Fusion crawler│           │  Remote engines  │          │  Portal universe │
│ seeds→frontier│           │ 66 adapters      │          │ 54 deep links    │
│ fetch→parse   │           │ RRF weights      │          │ lens ranked      │
│ extract→index │           │ per-engine timeout│         │                  │
└──────┬────────┘           └────────┬─────────┘          └────────┬─────────┘
       │                             │                             │
       └──────────────┬──────────────┴──────────────┬──────────────┘
                      ▼                             ▼
             ┌──────────────────┐          ┌────────────────────┐
             │ normalise + score│          │  SSE event stream  │
             │ dedupe canonical │          │  meta → results*   │
             │ merge sources    │          │  → done            │
             └────────┬─────────┘          └────────────────────┘
                      ▼
             ┌──────────────────┐
             │ local vault      │  SQLite FTS5 · Whoosh · Tantivy
             │ + BM25 rerank    │  metadata + extracted full text
             └──────────────────┘
```

## 1. Query intelligence

`plays.py` parses operators (`site:`, `filetype:`, `inurl:`, `intitle:`) out of plain language,
infers the lens from intent words ("grant", "apply", "backup"), and emits operator-grade plays:

```
funding calls:  <terms> ("call for proposals" OR grant OR fellowship OR RFP ...)
live deadlines: <terms> ("deadline" OR "closes" OR "apply by") (filetype:pdf OR filetype:docx)
deep paths:     <terms> (filetype:pdf ...) (inurl:upload OR inurl:files OR inurl:archive)
```

Plays are used three ways: as dorks for the hand-off provider, as hints for API providers,
and as the archive regex targets in the crawler.

## 2. Fan-out and isolation

Every provider runs in its own task with `asyncio.wait_for(provider_timeout)`. A provider can
time out, 500, or return garbage — it becomes `{status: "error"}` in the response and the hunt
continues. Per-provider result caps are enforced before fusion.

## 3. Fusion and ranking

For each provider result at rank `r`:

```
score = provider.weight × 1000 / (40 + r)         # reciprocal rank fusion
score ×= file-type boost        (1.35 for files/datasets with an extension)
score ×= opportunity boost      (1.30 when the lens and tags agree)
score ×= deadline boost         (1.45 ≤7d, 1.20 ≤30d, 1.05 ≤90d, 0.85 closed)
score ×= freshness boost        (1.08 current year)
score ×= depth boost            (1 + depth/100 × 0.40)
score ×= portal/dork dampener   (0.45 / 0.35 — visible, never dominant)
```

Depth is its own 0–100 model: archive-only (+30), file extension (+15, +12 pillar, +14 sensitive),
deep-path words (+8), path segments (≤15), parameter hints (+6), mainstream-domain penalty (−12),
non-mainstream bonus (+8), gov/int bonus (+6), unusual subdomain (+4), "index of" (+14),
"confidential/internal/draft" (+8).

Duplicate URLs are canonicalised first: lowercase host, strip `www`, default ports, fragments,
tracking params, trailing slashes, sorted query string. Survivors merge their engine lists,
tags, best snippet and nearest deadline.

## 4. Streaming protocol

`POST /api/v1/hunt/stream` returns `text/event-stream`:

| event | payload |
|---|---|
| `meta` | plan, resolved archive domains, provider ids |
| `results` | `{provider, hits[]}` — preview batch, `final: false` |
| `provider` | `{id, status, count, ms, message}` |
| `done` | the complete fused `HuntResponse` |

The UI renders preview batches immediately and replaces them with the fused list on `done`.
Crawl streams emit `status`, `seeds`, `serp`, `sitemap`, `robots`, `page`, `listing`, `file`,
`pagehit`, `blocked`, `error`, `progress`, `done`.

## 5. Crawl contract

Priority-first. The frontier is a heap keyed by `priority.url_priority()` — documents and
opportunity vocabulary float up, login walls, carts and pagination sink — and each wave pops
`2 × concurrency` requests. Each URL: canonicalise → same-host check → robots check (protego:
wildcards, `$` anchors, crawl-delay) → host gate → fetch (engine-selected, byte-capped) →
content-type dispatch.

- HTML → `parse_links_rich` (selectolax lexbor → bs4), `schemaorg.extract` (JSON-LD → microdata →
  RDFa) with a prose fallback (`guess_fields`) and `extract_text`
  (trafilatura → readability → justext → newspaper3k → boilerpy3 → html2text → bs4).
- Files → HEAD for size/mime → bounded GET → `magic.sniff` (magic bytes re-label the extension and
  MIME) → `file_text` (pypdf → pdfminer, openpyxl, python-docx,
  zipfile, text decode) → `index_document` → emit a `Hit`.
- Pages with a deadline or ≥2 opportunity tags are emitted as page hits.

Nothing is written outside `data/`; the SQLite connection is per-operation with WAL enabled.

## 6. Vault

Three local indexes, one query surface:

- **SQLite FTS5** over `vault` (URL/title/snippet) and `docs` (full text), porter stemming,
  `bm25()` ordering.
- **Whoosh** — a RAM index of the current candidate set for BM25F re-scoring.
- **Tantivy** — mirrored documents for fast offline retrieval.

`search_docs` returns snippet fragments with match markers, which the UI renders as highlights, and
hydrates structured fields from the vault record (`_payload_meta`) so the full-text engine can
return a complete opportunity, not just a snippet.

## 7. Specificity pipeline

Recall is the easy half. Before ranking, every result passes through:

1. `urlnorm.canonicalize` — RFC-3986 path cleanup, ~90 tracking/session parameters, default
   documents, IDNA and `www` folding; `registrable()` for site identity.
2. `schemaorg` — typed records from JSON-LD/microdata/RDFa, then `guess_fields` for prose
   (`funded by …`, `USD 250,000`, `Duty station: …`).
3. `magic` — file truth from bytes, not extensions; PDF titles extracted when the name is useless.
4. `near_dup.cluster` — MinHash+LSH (`num_perm=128`), token-set ≥92 pass, simhash ≤3 fallback;
   the **richest** member survives and inherits the others' fields.
5. `orchestrator.build_hit` — specificity boosts (named funder + amount, schema type, complete
   record), term coverage, diversity demotion.
6. `local_index.payload_richness` — the vault only accepts a *richer* record over an existing one,
   so a re-hunt can never downgrade a structured result to a plain snippet.

`docs/REPOS.md` maps each of these to the project whose algorithm or parameter set it came from.

## 8. Ranking policy (the part that does not change)

The engine surfaces what typical engines filter out. Concretely, that means these are **never**
applied as filters: publication recency, domain authority, inbound-link count, "helpful content"
scoring, content-type snobbery (HTML over PDF/XLS/SQL), or "ugliness" (directory listings, plain
Apache indexes, machine-generated pages).

What exists instead is ordering: `relevance` (default), `newest`, `deadline`, `depth`. Every sort
keeps the full candidate set — a hit with no timestamp sorts last under `newest`, it is never
dropped. `/api/v1/health` publishes this as a machine-readable `policy` block so downstream tools
can assert it, and the UI carries a persistent banner saying the same thing.

## 9. Security posture

- Keys, when supplied, live in the request body only; they are never persisted or logged.
- No arbitrary URL proxying — the browser talks to one origin and the server only fetches targets
  you asked it to crawl.
- `robots.txt`, politeness and rate limiting default on; the override is explicit and labelled.
- Crawl caps (pages, files, bytes, seconds) bound every run.
