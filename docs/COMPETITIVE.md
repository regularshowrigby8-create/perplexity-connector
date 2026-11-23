# Landscape check — does this already exist?

Scanned on 2026-11-23 via the GitHub REST search API (`search/repositories`) and the
Vercel/Netlify ecosystem (site-search libraries, templates, hosted products). Star counts are
as returned by the API on that date.

## Verdict

**No equivalent project found — on GitHub, Vercel or Netlify.**

The space splits into four well-occupied quadrants, and Nighthawk sits in the empty middle:
nobody ships an engine that *crawls itself* **and** reads archive indexes **and** extracts the
hosted files **and** ranks by obscurity **and** extracts deadlines from opportunity pages.

| Project | Stars | Quadrant | Own crawler | Archive indexes | File text | Deadlines | Depth rank | Local vault | Vercel/Netlify |
|---|---|---|---|---|---|---|---|---|---|
| [searxng/searxng](https://github.com/searxng/searxng) | 39.8k | metasearch | — | — | — | — | — | — | no (needs server) |
| [ItzCrazyKns/Vane](https://github.com/ItzCrazyKns/Vane) (ex-Perplexica) | 38.3k | AI answer engine | — | — | partial | — | — | — | yes (Next.js) |
| [miurla/morphic](https://github.com/miurla/morphic) | 9.4k | AI answer engine | — | — | — | — | — | — | yes (Next.js) |
| [yacy/yacy_search_server](https://github.com/yacy/yacy_search_server) | 4.1k | own index / P2P | yes | — | — | — | — | — | no (Java) |
| [rashadphz/farfalle](https://github.com/rashadphz/farfalle) | 3.5k | AI answer engine | — | — | — | — | — | — | yes-ish |
| [StractOrg/stract](https://github.com/StractOrg/stract) | 2.4k | own index (Rust) | yes | — | — | — | — | — | no |
| [MarginaliaSearch](https://github.com/MarginaliaSearch/MarginaliaSearch) | 2.2k | curated small web | yes | — | — | — | partial (small-web bias) | — | no |
| [mwmbl/mwmbl](https://github.com/mwmbl/mwmbl) | 1.9k | distributed open index | yes | — | — | — | — | — | no |
| [gigablast/open-source-search-engine](https://github.com/gigablast/open-source-search-engine) | 1.6k | archived engine code | yes | — | — | — | — | — | no |
| [opsdisk/metagoofil](https://github.com/opsdisk/metagoofil) | 610 | file recon CLI | — | — | filenames only | — | — | — | no |
| [odcrawler-frontend](https://github.com/Chaphasilor/odcrawler-frontend) | 53 | open-directory search | — | — | — | — | — | — | no |
| **Nighthawk** (this repo) | — | **fusion discovery** | **yes** | **yes** | **yes** | **yes** | **yes** | **yes** | UI yes / API needs a host |

## What each neighbour does, and why it is not this

- **SearXNG** is the strongest adjacency: one query, 70+ upstream engines, privacy-preserving.
  But it is a *proxy in front of other people's indexes*. It does not crawl, cannot open a PDF,
  has no concept of a deadline, and returns the same popularity-ordered web everyone else does.
  Nighthawk can *use* SearXNG as one engine among 66.
- **Vane / Perplexica, Morphic, Farfalle** are answer engines: an LLM summarises web snippets.
  They are the projects people deploy on Vercel. Excellent at prose, blind to `/uploads/2019/03/`
  and to a tender PDF that never ranked. None of them keeps an index you can search offline.
- **YaCy, Mwmbl, Stract, Marginalia** are genuine independent-search-engine projects with their
  own crawlers and indexes — the closest in *spirit*. All four are search-*result* engines:
  page titles and snippets. None extracts and indexes non-HTML payloads, none has an
  opportunity/deadline model, none exposes a crawl arsenal or an archive-index reader.
- **Metagoofil** does file discovery by asking a search engine for `filetype:` — i.e. it depends
  on exactly the index that buries the file. Nighthawk reads Common Crawl and Wayback CDX directly
  and then fetches the payload itself.
- **ODCrawler** targets open directory listings ("Index of /"), which Nighthawk detects too — but
  it is a 53-star Vue frontend with no file extraction, ranking model or opportunity layer.
- **Diskover** is a wonderful file search engine — for *your own storage*, not the web.

## Vercel / Netlify

Nothing resembling this exists there. What lives in that ecosystem is:

- **site-local search** — [Pagefind](https://pagefind.app/), Algolia, the
  [Netlify search-index plugin](https://github.com/swyxio/netlify-plugin-search-index): crawl
  *your own* static site at build time and search it in the browser.
- **metadata scrapers** — e.g. [vercel-metafy](https://github.com/xiaoluoboding/vercel-metafy),
  a single serverless function that fetches one URL's OpenGraph tags.
- **AI answer apps** — Vane/Morphic-style Next.js apps that call a paid search API.

None of them discovers files, reads archives, or tracks opportunities.

Also worth stating plainly: Vercel/Netlify are a **poor runtime for this engine**. A BFS crawl with
per-host politeness, PDF extraction and a persistent FTS index does not fit serverless execution
limits or an ephemeral filesystem. That is why Nighthawk ships `docker compose` + `./run.sh` for a
VPS, and keeps the Next.js UI deployable to Vercel separately (point `API_URL` at the crawler host).

## Gap Nighthawk occupies

1. **Crawler as the primary engine**, not a wrapper around someone else's SERP.
2. **Archive-first discovery** — Common Crawl + Wayback CDX to reach what was de-indexed or never
   indexed, with regex filters on file extensions and URL slugs.
3. **Payload-level indexing** — PDF/XLSX/DOCX/ZIP text extracted into SQLite FTS5 + Whoosh +
   Tantivy so you can search *inside* what you found.
4. **Opportunity semantics** — deadline extraction with urgency, "closes in 12d" sorting, watcher
   diffs that only report newly appearing calls.
5. **Obscurity ranking** — a depth score that inverts popularity bias, with "most buried first".
6. **Arsenal transparency** — 86 crawl engines probed and dispatched by role, honest about what is
   installed, no fake integrations.

## Reusable ideas worth borrowing (and not reinventing)

- SearXNG's per-engine settings and `!bang` routing → future engine-level preferences.
- Stract's optics-based ranking DSL → an alternative ranker behind the fusion layer.
- Mwmbl's distributed crawl coordination → multi-node frontier for large scans.
- ODCrawler's directory-listing parser → extra heuristics for `Index of /` pages.
- Metagoofil's file-type recon recipes → more seeds for the files lens.

## How to reproduce this scan

```bash
gh api -X GET search/repositories -f q="metasearch engine" -f sort=stars -f per_page=10 \
  --jq '.items[] | "\(.stargazers_count)\t\(.full_name)"'
gh api -X GET search/repositories -f q="topic:vercel search engine" -f sort=stars
gh api -X GET search/repositories -f q="common crawl search" -f sort=stars
```

Queries run: `metasearch engine`, `search engine self-hosted`, `google dork scanner`,
`crawler search engine`, `common crawl search`, `wayback machine search ui`,
`open directory search engine`, `unified search api aggregator`, `tender aggregator`,
`grant finder open source`, `topic:vercel search engine`, `topic:netlify search`.
