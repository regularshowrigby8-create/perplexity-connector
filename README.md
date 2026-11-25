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
  "buried_boost": true,
  "match_default": "exact",
  "constraints": {
    "result_removal": false, "result_cap": false,
    "dedup": "reported, not applied", "junk": "labelled, sorted last",
    "noise": "labelled, kept", "diversity_penalty": false,
    "query_expansion": false, "stemming": false, "synonyms": false
  }
}
```

---

## The engine reads the question first

Before a single source is asked, `understand.py` turns the query into a structure: what kind of thing
is wanted, what the subject phrase is, which place or organisation was named, which file type was
asked for, which years were mentioned, what was excluded, and whether the request can be honoured
inside the window at all.

"A machine part that understands the search" is not a prompt: it is a taxonomy (`KINDS`), a gazetteer
of places, a rule for names ("World Bank" is one name, not "Bank"), a reader for quoted phrases and
`-exclusions`, and **RAKE** for the phrase extraction. RAKE is a real codebase, vendored unmodified in
`apps/api/app/vendor/rake_keyword/` — MIT, from [`u-prashant/RAKE`](https://github.com/u-prashant/RAKE),
with the upstream `rake.py`, its `SmartStoplist.txt` and its LICENSE kept intact next to a NOTICE that
records the URL and the reason it is here. It needs no model file, no download and no network: it
scores phrases from word degree and frequency, which is the only kind of keyword engine that belongs
on a free instance.

What it does with the reading:

| reading | effect |
|---|---|
| kind (`form`, `tender`, `dataset`, `document`, `legal`, `code`, `media`, `job`, `place`) | a **+6** ordering nudge towards that artefact, and a suggested lens — never a filter |
| subject phrases | shown back to you ("about 'water points maintenance tender'") |
| places and names | shown back, and used by the existing intent layer |
| file words (`pdf`, `csv`, `apk`…) | become the one type filter the engine has |
| quoted phrases, `-exclusions` | separated out and honoured by the verbatim matcher |
| a year outside the window | a warning in the answer and on the page, before you read any results |

The words matched against a result are still the words you typed — the reading steers *where to look*
and *how to phrase the answer*, never *what counts as a match*.

```bash
curl -s localhost:8000/api/v1/hunt -H 'content-type: application/json' \
  -d '{"q":"climate resilience grant application form for coastal towns in Kenya","limit":5}' \
  | python -m json.tool | head -30
# "understanding": {
#   "kind": "form", "kind_label": "a form or application",
#   "phrases": ["climate resilience grant application", "coastal towns", "kenya"],
#   "places": ["kenya"], "suggested_lens": "applications",
#   "summary": "A form or application, about \u201cclimate resilience grant application\u201d \u2014 in Kenya",
#   "engine": "rules + RAKE (vendored)"
# }
```

On the page it is one quiet line under the search: **Understood · A form or application, about
"climate resilience grant application" — in Kenya · nothing older than 730 days**, with any conflict
underneath it in amber.

## Verbatim results, and no restrictions on them

The query is matched **word for word**. No stemming, no synonyms, no query expansion, no fuzzy
similarity, no "related concepts" — `climate grant` matches `climate grant`, not `climatic grants`
and not `grant for the climate`.

`match=exact` is the default. Each result reports the literal outcome:

```json
{ "exact": true,  "occurrences": 2, "match_where": "snippet", "proximity": 0 }
{ "exact": false, "proximity": 1,  "match_where": "title" }      // "climate resilience grant"
{ "exact": false, "proximity": null }                            // no in-order match at all
```

`proximity` is measured in words: `0` means contiguous, `1` means one word sat inside the smallest
window that still contains every query word in order. Word order is part of the match — reversed
keywords are not a hit. Offsets come back in `match_span`, so the matched words can be marked in
the snippet instead of approximating where they are.

**Nothing is done to the result set.** `unrestricted` defaults to true, and under it the engine:

| would-be constraint | what happens instead |
|---|---|
| near-duplicate folding | `copies`/`copies_reported` reported, every copy kept |
| spam / parked / error removal | hit flagged `junk`, sorted last, kept |
| URL noise (`login`, `/tag/`, `.js`) | hit flagged `noise`, kept |
| diversity penalty on one host | not applied |
| result cap | only your own `limit` — `0` means everything found |
| truncation | `stats.truncated` says if *you* capped it |

`only_exact=true` is the one filter that exists, it is opt-in, and it only ever narrows to results
that contain the phrase word for word. The `/api/v1/health` policy block publishes all of this
(`constraints: {result_removal: false, result_cap: false, dedup: "reported, not applied", …}`)
so an integration can assert it rather than trust the copy.

## Deep links — results you can only get by pasting the URL

Some material has no discovery path: a portal's `notice.cfm?notice_id=48213`, an annex nothing links
to, a sitemap entry that never made it into an index, an attachment behind a JavaScript handler, the
page the site deleted. No engine can rank what it never crawled, so the only way in is the exact link.

`POST /api/v1/deep` takes those links, crawls **from** them (`depth` 4, other hosts, sitemaps,
archives, every page kept, no search engine involved) and reports, per result, why nothing else
could have found it:

| reason | meaning |
|---|---|
| `pasted` | one of your seeds — you supplied the only route in |
| `not-linked` | no crawled page links to it (inbound 0) |
| `sitemap-only` | the site listed it; no page links to it |
| `archive-only` | surfaced from an archive index, not the live site |
| `query-url` | built from parameters (ids, downloads, portal searches) |
| `attachment` | a file, not a page |
| `deep` | three or more hops from the seed |

Each hit is still matched **verbatim** against your phrase, still carries its publication clock, and is
still never removed — the report is the same policy as the hunt, applied to links you chose.
`/api/v1/deep/stream` emits the same report as SSE with every page, file and block in between.

The launcher (`index.html`, also `/launch`) has the panel: paste links, pick depth, run, and watch the
reasons arrive. The offline practice target includes a page that is linked from nowhere
(`demo/annex/off-cycle-notice.html`) so the feature can be proven without the internet — the self-test
asserts that a normal crawl cannot find it and a pasted deep crawl can.

## Similar links — one link in, the rest of that shape out

Forms, notice portals and government document systems rarely publish an index. Each item lives at its
own link with one changing segment — an id, a slug, a code:

```
https://docs.google.com/forms/d/e/1FAIpQLSeUgRo9ZXDqQIE3U4J2uGECV3SApcHs5M95tBlbaflCeSp52w/viewform
                                    └────────────── the only part that changes ──────────────┘
```

Paste any one of them into **Similar links**, and Nighthawk works out the *shape* of the link
(everything fixed stays fixed, the varying part becomes `{id}`), then crawls out from your seed to find
every other link built the same way. The panel shows the shape it matched, so you can see exactly what
it looked for:

```
https://docs.google.com/forms/d/e/{id}/viewform
```

The second box takes a **phrase or word that must appear in the link** — in the URL itself or in the
link text on the page it was found (`match_in: "both"` by default). Matches are listed first. The ones
the phrase ruled out are not thrown away: they stay underneath under *didn't match*, with the reason,
because a link that has the right shape is still the right link — you just asked for a narrower view.

`POST /api/v1/links` does the same thing without the page:

```json
{
  "seed": "https://docs.google.com/forms/d/e/1FAIpQLSe…/viewform",
  "phrase": "climate",
  "match_in": "both",
  "depth": 2,
  "max_pages": 30,
  "max_links": 300,
  "same_host": true,
  "use_engines": true,
  "respect_robots": true
}
```

Each returned link carries where it was seen (`found_on`), whether your phrase matched the URL, the
text, both, or neither (`phrase_where`), and the crawl's counts: pages read, links seen, links with the
same shape, kept, rejected. `notes` explains in words what the shape was; `errors` lists pages that
refused to load rather than pretending they were empty.

The offline practice target has the case built in: `demo/forms/` links to four sibling forms
(`/demo/forms/{id}/view.html`) with different round names, so the self-test can prove that a pasted
seed finds its siblings, that `solar` keeps exactly one of them and reports the other three as
rejected, and that an impossible phrase matches nothing while still listing the shape.

## Speed — the answer is on a clock

A search used to wait for **every** engine, so the slowest of 125 set the latency: an 11-second
provider timeout meant an 11-second wait, and a page that looked frozen. Two things changed.

**A budget, not a race.** `hunt` now waits `hunt_budget_ms` (default **2500 ms**, env
`NH_HUNT_BUDGET_MS`) and then answers with what has arrived. Engines still working are cancelled and
reported as `slow` by name, with the reason — never dropped and never hidden:

```json
{"stats": {"took_ms": 2210, "budget_ms": 2500, "slow_providers": 9, "cached": false},
 "providers": [..., {"id": "wayback", "status": "slow", "ms": 2500,
                     "message": "still working when the 2500 ms budget ran out"}]}
```

The trade is stated plainly: an engine that needs four seconds does not appear in that answer. Ask
again — it will.

**A cache that is actually used.** The page used to send `fresh: true` on every search, which skipped
the cache entirely. It no longer does: the same question inside `cache_ttl` (**60 s**) comes back in
milliseconds with `cached: true`, and the answer offers **ask again** when you want a real fresh pass.

**The page says what it is doing.** Pressing Search paints *searching every working source* straight
away, then *still gathering* if a slow source is being waited on, then the rows. A hung engine can no
longer make the page look broken.

Measured here against the full engine list:

| | before | after |
|---|---|---|
| first search, 6 engines hanging 30 s | never returns (30 s+) | **2.6 s**, six reported `slow` |
| repeat of the same search | 1.4–3.5 s every time | **13 ms** (`cached`) |
| the page on click | nothing until the last engine answered | a line at once, **first results at ~0.9 s**, complete at 1.6 s |

## Results arrive while the search is still running

Waiting for the budget and *then* painting the page still means a blank screen for two seconds. The
launcher no longer does that: it reads `/api/v1/hunt/stream` and paints each frame as it lands.

```
POST /api/v1/hunt/stream   {"q": "…", "sort": "accuracy", "limit": 0}

data: {"type":"results","final":false,"provider":"mojeek","answered":40,
       "total":12,"hits":[…]}          ← every source that answers updates the list
…
data: {"type":"results","final":true,"answered":94,"total":65,"hits":[…]}   ← the clock ran out
data: {"type":"done","hits":[…],"stats":{…}}                                 ← the settled answer
```

Each frame carries **the whole list as it stands**, already ordered, so a late source slots into its
right place instead of being appended to the bottom. Frames are emitted whenever the answer actually
changes (throttled to ~12 a second) plus a heartbeat every half second, so a client can tell "nothing
new yet" from "nothing happening". The same filters the finished answer applies — the typed file type,
`only_exact` — are applied to the frames too: a live result is never something the final answer is
about to drop.

### Accuracy first, upload date second

`sort: "accuracy"` is what the page asks for:

| band | meaning |
|---|---|
| 1 | the phrase, word for word, in the title, snippet or URL |
| 2 | the words are there but not adjacent — ordered by how many extra words sit between them |
| 3 | no verbatim match reported |

Inside a band the **newest upload wins**, banded the same way the newest-first order always was: dated
in the past (newest first), then future-dated (a broken clock, never allowed to jump the queue), then
undated. Junk-labelled results stay last. An exact match from 2019 therefore outranks a fresh page that
does not contain the phrase — which is the point of ordering by accuracy before date.

The page falls back to a plain `POST /api/v1/hunt` if a proxy buffers SSE, so nothing depends on
streaming being available.


**The answer is not held up by its own bookkeeping.** Two things used to run inside the response
after the last source answered: the near-duplicate report (MinHash over *every* row) and writing every
hit into the vault. On a small instance those cost more than the search itself — it is how a 2.5-second
budget still produced an 11-second answer. Now:

| | |
|---|---|
| duplicate report | compares the top `cluster_cap` rows (400) instead of the whole set, and says so in `stats.copies_scanned` |
| vault write | off the response path (`run_in_executor`), so later searches still see the hits without the current one waiting |
| what is left | `stats.post_ms` — the tail after the last source, normally tens of milliseconds |
| stragglers | cancelled engines get 0.3 s to unwind, then the answer goes out anyway |

## Typing a file type means that file type

`apk` used to be read as the word "apk": you got papers about water that happened to contain those
three letters. The query is now read for its *shape* before anything is crawled
(`apps/api/app/intent.py`):

| you type | the engine does |
|---|---|
| `apk` | browses APKs — the matched word is not required to appear in the text |
| `minecraft apk` | searches "minecraft", returns **only** APK-family files |
| `climate grant pdf` | searches "climate grant", returns **only** PDFs |
| `budget csv mediafire` | searches "budget", returns CSVs, and aims the crawl at MediaFire |
| `water` | no type word, no filter — exactly as before |

Families are generous on purpose: `zip` covers zip/rar/7z/tar, `video` covers mp4/mkv/avi/webm, and
an APKPure or F-Droid page counts as an APK even though its URL has no extension.

This is the **only filter in the engine**, it is applied because it was typed, and the response says
exactly what it did: `intent.types`, `intent.hosts`, `intent.removed_by_type`. No type word in the
query means `removed_by_type: 0` and the old "nothing removed" rule stands untouched.

A host word (`mediafire`, `mega`, `drive`, `dropbox`, `apkmirror`, `archive.org`, `sourceforge` …) is a
**pointer, not a filter**: it dispatches the file-host engines (`mediafire`, `apkpure`, `apkmirror`,
`fdroid`, `archivefiles`, `sourceforge`) and lifts those results to the front. A host we cannot reach
returns nothing and says so — it never turns into "no results".

## Nothing older than two years — the window is the search

Every answer is bounded to the **last 730 days**. A result whose own clock says it is older than
that is not returned: not sorted last, not greyed out, not "see more" — cut, before ranking, dedupe
and limits ever see it. `recency.py` holds the rule and `Window.current()` is the only place the
number lives.

| what the page says | what happens |
|---|---|
| published seconds, minutes, days or months ago | **kept**, and it is where the answer starts |
| published up to two years ago | **kept** — the far end of the window |
| published 2014 | **cut**, and counted in `cut_older` |
| dated 18 months in the future | **cut** as a broken clock, counted in `cut_future` |
| dated 3 weeks ahead (a tender opening, a scheduled notice) | **kept**, sorted after real dates |
| no date anywhere on the page or in its headers | **kept**, counted in `undated_kept` |

The last row is the deliberate one. A page with no clock — an `/uploads/2019/03/annex.pdf` whose only
date is in its path, a portal entry behind a form, an old-style `.doc` with no metadata — is not
evidence of age. We saw it today. It is kept, and counted separately so you can see how much of the
answer is undated rather than dated.

The window applies to **every way in**, not just the front page:

- **a search** — applied once to the merged set, so the live streamed frames and the final answer
  both obey it (live: `stats.window_days 730 · cut_older 4 · undated_kept 18`)
- **the vault** — `search_vault` now carries a real `published` column (added by an in-place
  migration, with a one-off full-text rebuild for vaults written by older releases), so a 2011 annex
  found last month is judged on its date, not on when we found it
- **a pasted link** — the crawl and deep layers use the same gate; an undated page on a site you named
  is still kept, a page the site dates 2014 is not

Nothing about the cut is silent: the answer carries `cut_older`, `cut_future` and `undated_kept`, the
page shows them as ticks ("12 cut as too old"), and a query that names a year outside the window says
so out loud — "2016 is outside the 730-day window the engine enforces, so this search can only return
2024 onwards" — instead of quietly returning nothing.

## Newest first, to the second

### A clock that lies

Future-dated records used to sort *above* everything, because their age is negative — which is how a
document stamped "in 10 months" ended up over results that were 16 seconds old. Newest-first now has
three bands: dated in the past (newest first, to the second), dated up to a few months ahead (a
scheduled notice, sorted after every real date), then undated. Anything dated further ahead than 120
days is a broken clock and is cut by the window above — a date that cannot be true is not a reason to
show a page.

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

## Paste a link and it starts reading

Typing a URL used to be a mistake: it went to the search engines as a *phrase*, matched nothing, and the
page said **0 results**. Now a pasted link is recognised on submit and sent to the crawler instead.

The crawl is streamed, page by page (`POST /api/v1/crawl/stream`): every page that is read is announced,
every page or file that is kept is painted immediately, and the list fills in on screen while the crawl
is still running.

```
page      http://example.org/         ← read
pagehit   http://example.org/         ← kept, painted at 0.1 s
page      http://example.org/about    ← read next
file      http://example.org/x.pdf
done      {stats, files, seeds}
```

Measured on the fixture site: **first result at 0.11 s**, complete at 2.6 s.

### When a site gives nothing back

A crawl that finds nothing now explains itself instead of shrugging. The page names the page count, then
the four things that actually cause it — `robots.txt`, an HTTP error in place of the page (403/404/429 or
a login wall), content drawn by JavaScript so the HTML is empty, or a link with no HTML to follow — plus
the literal lines the crawler met (`what it met: … — HTTP 403`). It also offers the way out: paste exact
links (deep crawl) or run the crawl again.

`stats.errors` counts HTTP failures as well as transport failures, so that explanation is never a guess.

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

## Live crawl — start it once and it keeps going

Every other mode here is a request: ask, get an answer, done. **Live crawl** is the one that keeps
working. You give it a site once and a background worker walks it round after round — new pages get
fetched, changed pages get read again, and everything lands in the same local index a normal crawl
writes to. Closing the page does not stop it; it lives on the server.

```
POST /api/v1/continuous
{
  "seeds": ["https://example.org"],
  "delay": 20,             // seconds of real pause between rounds
  "pages_per_round": 25,
  "same_host": true,
  "respect_robots": true
}
```

The response is the live status, and `GET /api/v1/continuous` gives the same thing any time:

```json
{
  "running": true,
  "origins": ["https://example.org"],
  "rounds": 14,
  "pages": 312,
  "files": 27,
  "documents": 288,
  "current": "https://example.org/reports/2024",
  "next_in_s": 11,
  "delay_s": 20,
  "pages_per_round": 25,
  "errors": [],
  "notes": ["Each round is a real crawl of one site, using the same engines a one-off crawl uses.", "..."]
}
```

What it honestly is, and is not:

| | |
|---|---|
| **a round** | one real `FusionCrawler` pass over one site — same engines, same robots checks, same extractors as a one-off crawl |
| **rotation** | add several sites and each round takes the next one, so none is starved (`POST /api/v1/continuous/seeds`) |
| **the pause** | `delay` seconds between rounds, default 20. A crawler that hammers a host is a denial of service, not a feature |
| **stop** | answers immediately: the worker checks its flag every couple of seconds and cancels a round in flight |
| **restarts** | state is per-process and in memory. Restart the service, or let a free host sleep, and it stops — that is stated in `notes`, not hidden |

The page has a panel for it (menu → **Live crawl**): start, watch rounds/pages/index size tick over,
add a site, stop.

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
POST /api/v1/hunt            federated search (verbatim, newest-first, nothing removed)
POST /api/v1/hunt/stream     same, as Server-Sent Events
POST /api/v1/deep            crawl pasted exact links + why each hit is deep-only
POST /api/v1/deep/stream     same, as SSE
POST /api/v1/links           one link in, every link of the same shape out
POST /api/v1/continuous      start (or reconfigure) the background crawler
GET  /api/v1/continuous      what it is doing: rounds, pages, index size, next round
POST /api/v1/continuous/seeds  add another site while it is running
POST /api/v1/continuous/stop   stop it
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

## Deploying the launcher on a static host (Netlify / Vercel)

`index.html` is a static page; the crawler is a Python service. Netlify can serve the page but not
run `/api/*`, which is exactly why a freshly-dropped deployment says **"No engine answered"** — the
page is fine, it just has nothing to talk to. Put an engine behind it (see *Running it somewhere
that is not your machine*), in one of three ways:

1. **Proxy (best).** The repo ships `netlify.toml` and `vercel.json` with an `/api/*` proxy. Edit the
   one `to`/`destination` URL to point at a running engine, redeploy, and the launcher finds it as
   "this origin" — same behaviour as self-hosting.
2. **Bake it into the page.** Set `<meta name="nighthawk-engine" content="https://your-engine">`
   before deploying.
3. **Point it per visit.** Add `?api=https://your-engine` to the page URL, or paste the URL into
   **engine settings** (stored in `localStorage`).

The probe tries, in order: `?api=` → the meta tag → the saved setting → this origin → the
`8000-<sandbox>` preview convention → `localhost` (only when the page itself is local). The banner
lists every URL it tried, so "offline" is never a mystery.

## Running it somewhere that is not your machine

The crawler is a long-running Python service, so it needs a host that runs processes, not a host
that serves files. The image is built so that **one container is the whole product**: `GET /` returns
the launcher, `/api/v1/*` is the engine, on one origin — no proxy rewrite, no engine URL to paste,
no "offline" banner.

| Where | What runs there | What you do |
|---|---|---|
| **Render** | page + crawler, one Docker service — **free plan** (sleeps when idle, vault resets) | New → Blueprint → this repo + this branch → Apply (`render.yaml`) |
| **Fly.io** | same image, one machine, `jnb` region by default | `fly launch --copy-config --no-deploy`, `fly volumes create nighthawk_data -s 1`, `fly deploy` (`fly.toml`) — pay-as-you-go, needs a card |
| **Railway** | same image, `$PORT` respected | New Project → Deploy from repo (`railway.json`) — trial credit, then paid |
| **Any VPS** | both, on `http://host:8000/` | `docker compose up -d --build` |
| **Netlify / Vercel** | **the page only** — no Python, no crawler | deploy, then give it an engine (below) |
| **This sandbox preview** | both, until the session ends | open the `:8000` or `:3000` preview |

**Free was the requirement, so read the trade-offs before picking a row.** Render's free plan runs this
image at no cost but sleeps when idle and has no disk, which means the page may take ~30 s to wake and
the vault forgets its documents between runs. Everything else on the list is either a card-required
service or a machine you already pay for. Any host that can run a Docker container — Koyeb's free
instance, a free Hugging Face Space, a Raspberry Pi under your desk — works with the same image and
the same single-origin result; only the YAML differs.

One click for the Render path (it reads `render.yaml` straight out of the repo):

<https://render.com/deploy?repo=https://github.com/regularshowrigby8-create/perplexity-connector>

The same image, by hand, in full:

```bash
docker build -f Dockerfile.api -t nighthawk .
docker run -d -p 8000:8000 -v nighthawk-data:/data nighthawk
# http://127.0.0.1:8000/      → the launcher
# http://127.0.0.1:8000/api/v1/health → the engine the page is talking to
```

Mount `/data` (or set `NH_DATA_DIR`) or the vault resets whenever the container is replaced.

`docker compose up -d --build` still runs the two-service layout (api `:8000`, web `:3000`) for the
Next.js app; `./run.sh` does the same on a VPS with Python 3.11+ and Node 20+. The only persistent
state is `data/` (SQLite vault, watchlist, extraction cache).

### What the page does by itself

The launcher is not a menu of links into the Next.js app — it **runs the hunt and the crawl in
place**. `Hunt` POSTs `/api/v1/hunt` and renders the rows (verbatim badge, word distance, copies
reported, junk/noise labelled, newest first); `Crawl` does the same through `/api/v1/crawl` when the
box holds a URL; `Deep crawl` and `Similar links` have panels of their own. Vault, Watchers and Arsenal
open the engine's own JSON in a new tab.

That matters on a one-container deployment, where `/hunt` and `/vault` — pages of the Next.js app —
do not exist at all. Before this, clicking **Hunt** on `nighthawk-*.onrender.com` returned
`{"detail":"Not Found"}`; now the same click lists results without leaving the page.

The page opens as a search box and a sentence. Everything else — Crawl a site, Similar links,
Live crawl, Pasted links, Status, Settings, the sample site, the deploy commands — sits in one **Menu**
in the top bar, one panel at a time, and each panel has a *back to search* line. Filters and the engine
URL are two small links under the box, folded away until you want them. Type chips are inside filters.

The look follows the same rule: a serif heading face, one warm accent, **one surface** — the panel, the
field, the chips and the rows are one blended grey with hairlines instead of a stack of boxes, and result
metadata (`verbatim`, `in title`, `paper`) is quiet uppercase text rather than grey pills. Results read as
a list, not a deck of cards. No gradients, no card wall, no pitch banner, no numbers strip on the front
page. Google is simple because the thing you came to do is
in front of you and the rest is one click away; that is the whole idea here.

If the page is the half you already deployed to Netlify or Vercel, give that deployment an engine
with the proxy / meta / `?api=` options in *Deploying the launcher on a static host* above. The
engine itself has to live on one of the rows in the table that can run Python.

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
  understand.py    reads the query first: kind, phrases, places, names, file words, years
  recency.py       the 730-day window every answer lives inside (and what it cut)
  vendor/          imported code, unmodified, with its LICENSE and a NOTICE
  local_index.py   SQLite FTS5 / Whoosh / Tantivy / BM25 vault
  portals.py       54 portals + archive targeting
  plays.py         natural language → dorks
  fixtures.py      the offline practice target
apps/web/          Next.js 15 interface (hunt, crawl, arsenal, vault, watchers)
docs/              architecture, engine reference, deployment, and REPOS.md (what was imported)
scripts/selftest.py  end-to-end proof: crawl the fixture, then search inside it, then
                     derive a link shape and find its siblings
```
