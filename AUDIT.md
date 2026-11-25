# A session with my own search engine

I was asked to stop building for a minute, act like a person with a normal question, use only
the page, and then say honestly whether this thing is better than Google or pleasant to use
every day. This is that session, what it found, and what I changed because of it.

**Short answer: no, it is not better than Google, and it should stop implying it is.**
It is better at exactly one job — finding a *document, form, notice or dataset* that contains
specific words, with a real date — and only when the network is open. Everything else, Google
does faster and better. Details, including the things I could not test here, are below.

---

## How the session was run

- The real `index.html` was loaded in a real DOM (jsdom), served from the real API, and the
  harness typed into `#q`, pressed the button, and read the screen. Nothing called the API
  directly; every result below came through the page's own code, its own streaming fetch and
  its own rendering.
- Seven searches, the way a person would do them: a normal need, the same need again, a
  navigational lookup, a file-type search, a typo, a query that cannot exist, and a pasted link.
- I ran the session five times: once on the build as it was, once after each fix, and once at
  the end. The numbers in the tables are "before → after", first run → last run.

### The one thing that makes this an unfair test — and I am not going to hide it

This machine has **no general internet**. Outbound connections are whitelisted: GitHub works,
DuckDuckGo and Bing do not. So 73 of the 80 engines could not be reached, and the ones that
could are the release feeds (npm, PyPI, GitHub) plus the local vault.

That means: **the interface, the timing and the behaviour were tested for real; the coverage
was not.** Every "no results" below is a statement about this sandbox, not about the web. The
honest test of coverage has to run on the deployed instance, which does have an open network.
There is a copy-paste script for that at the end.

---

## What the screen actually did

| # | What I typed | Rows before → after | First row | Whole answer |
|---|---|---|---|---|
| 1 | `climate resilience grant application form kenya` | 43 → 28 | 0.49 → 0.97 s | 2.1 → 2.7 s |
| 2 | the same search again | 43 → 28 | 0.12 s | 0.85 s |
| 3 | `facebook` | 17 → 16 | 0.60 s | 1.8 s |
| 4 | `pdf water point maintenance tender` | 2 → 0 | 0.61 s → — | 1.5 → 3.9 s |
| 5 | `climate resilence grant apllication form for costal towns` | 60 → 26 | 0.36 s | 1.6 s |
| 6 | `zzqqxx nonexistent topic 88` | 27 → 24 | 0.36 s | 1.3 s |
| 7 | a pasted https:// link | 0 | — | 3.1 s |

**Speeds.** Repeat is genuinely instant (0.12 s to a full answer). A fresh answer lands in
1.3–2.7 s, with the first row inside half a second. Google is about 0.4 s. That gap is real and
it comes from asking 80 sources at once instead of one index; it is the price of the design, not
a bug. The worst case was 3.9 s, on a search where almost every engine timed out.

**Search 1 and 5, before the fixes — the experience a real person would have had.** The top two
results were `surtgis 1.9.0` (a geospatial Python package) and `@aws-sdk/client-sso-oidc` (an AWS
auth library). Neither mentions climate, grants or Kenya. They were on top because they were
**published seconds ago** and the engine puts fresh things first inside each band — and because a
release feed answers "what is new" no matter what was asked. A person would have closed the tab.

**Search 4** returned two PDFs — both from the practice site that ships inside the engine, served
from `127.0.0.1`. In production that is the app's own host. They were fake documents presented as
found documents.

**Search 6** returned 27 results for a string that appears nowhere on earth. They were the npm
firehose again, unfiltered.

---

## Verdict

### Is it better than Google?

**No.** Being blunt about why, job by job:

| What people actually use search for | Who wins | Why |
|---|---|---|
| "facebook", "my bank login", "weather tomorrow" | **Google, completely** | Nighthawk returns npm packages whose names contain the word. It has no entity answers, no knowledge panel, no instant answers. |
| a fact, a definition, "how do I…" | **Google** | No answer box, no snippets tuned for that. Nighthawk gives documents that contain the words. |
| images, news, video, maps | **Google** | Not built, not pretended. |
| "find the application form / tender notice / dataset with these exact words, recent" | **Nighthawk, when the network is open** | Google buries PDFs and portal notices under SEO pages; Nighthawk searches for the words and the file type, dates everything, and shows what it set aside instead of hiding it. |
| "what appeared in the last hour about X" | **Nighthawk, with a caveat** | It has feeds Google does not index quickly — but those feeds are also where the noise came from. |
| "I have a link, read the whole site" | **Nighthawk** | Google cannot do this at all. |

So: **not a Google replacement. A second engine for one kind of search, plus a document reader.**
The page should say that in one line, and now it does.

### Is it efficient for everyday use?

**Not yet, but closer than it was this morning.** What is genuinely good: repeat answers are
instant, the answer arrives while you watch instead of behind a spinner, a typed file type is
obeyed, dates are real, the window is enforced, and nothing is silently dropped — it is counted
and shown. What still gets in the way: 1–3 s per fresh answer, no typo correction, a strict
file-type filter that can leave the page empty, and no recall of its own — it borrows other
people's indexes, so its answers are only as good as which endpoints answer today.

---

## What the session broke, and what I changed

Seven real defects, in the order I hit them. Each is fixed on this branch and covered by a test.

1. **"Search this portal yourself" links won every ranking.** Rows titled
   *"EU Funding & Tenders — climate resilience grant application form kenya"* are not documents;
   they are links into that portal's own search box. Their title is the query word for word, so
   they scored top. **Fix:** launchers are held out of the ranking in *every* sort order and put
   at the end, labelled *"opens that site's own search"*. `orchestrator.py`.
2. **One shared word counted as a match.** A React form library matched the word "form" and
   ranked above a grant application form. **Fix:** a result must contain at least a third of the
   words that were typed, and never fewer than two (unless the query is one word). Results below
   that line are **kept, counted and sorted last**, tagged *"none of your words"* — not deleted.
   `orchestrator.judge_words`.
3. **The demo site leaked into real answers.** Practice documents served from this machine's
   `/demo/` path appeared as search results. **Fix:** that path is left out of a real answer and
   reported ("6 practice-site results left out"); tests opt back in with `include_practice`.
   `orchestrator.is_practice_site`.
4. **A pasted link kept the previous search's "Understood" line.** **Fix:** a crawl now says
   *"Reading · only the site you pointed at — pages it dates older than 730 days are left out,
   undated pages are kept"*.
5. **An empty answer was a blank page.** Search 4 returned zero rows with no explanation.
   **Fix:** an empty answer now says what happened in sentences — how many sources answered, how
   many could not be reached, what the type filter set aside, what the window cut — and offers two
   buttons: *"Search without the file-type word"* and *"Allow gaps between my words"* (an opt-in
   looser pass; exact matches still lead, and the note says gaps were allowed).
6. **"Cached" on a first search.** When the streaming request fell back to a plain POST, the
   answer was labelled a repeat. **Fix:** the fallback no longer claims a cache hit, and the
   wording is now *"instant — answered from what we already had"*.
7. **A crawl that failed said only "1 errors".** **Fix:** it now shows the first real problem
   (*"TLS/SSL connection has been closed"*), which is the difference between "the site is broken"
   and "this machine has no internet".

Also changed: the note under the answer is plainer (*"1.8 s to answer"* instead of
*"verbatim match · nothing removed · 1262 ms · cached"*), the zero-value ticks are gone, and the
version tag reads **v1.9**.

---

## What is still wrong (not fixed, deliberately)

Ranked by what would annoy a real person most. None of these is hidden from the page.

1. **No typo correction.** *"climate resilence grant apllication form"* matches almost nothing,
   because the engine matches the words you typed and never rewrites them. Google silently fixes
   it. The page now offers the looser pass as a button instead of doing it behind your back — a
   deliberate choice, and arguably the wrong one for everyday use.
2. **Latency.** 1.3–2.7 s typical, 3.9 s worst, against Google's ~0.4 s. Caused by fanning out to
   80 sources and waiting for a budget. Could be cut by answering sooner with fewer sources, at
   the cost of coverage.
3. **Recall is borrowed.** No index of its own beyond what it has crawled: if the free endpoints
   are rate-limited or blocked, the answer is thin and the page can only say so.
4. **A type word is a hard filter.** `pdf <something>` returns 0 if no PDF exists, where Google
   would show web pages and a PDF tab. The page explains and offers the one-click way out.
5. **No entity answers, images, news, maps, or knowledge panels.** Out of scope; the page should
   not pretend otherwise.

---

## Run the same session against the live instance

The only honest coverage test needs an open network. From any machine:

```bash
# 1. the deployed engine is awake (Render free sleeps after ~15 min)
curl -s https://nighthawk-4mvl.onrender.com/api/v1/health | head -c 300

# 2. the same normal need, as a person would type it
curl -s https://nighthawk-4mvl.onrender.com/api/v1/hunt \
  -H 'content-type: application/json' \
  -d '{"q":"climate resilience grant application form kenya","limit":0,"fresh":true}' \
  | python3 -c 'import json,sys; d=json.load(sys.stdin); s=d["stats"]; \
print(s["took_ms"],"ms ·",len(d["hits"]),"rows ·",s["providers_ok"],"sources ok ·",s["providers_failed"],"down"); \
[print("  -",h["title"][:70],"|",h["domain"],"|",h.get("age_human")) for h in d["hits"][:8]]'
```

What to look for: `providers_ok` (how many of the 80 answered), whether the first eight rows are
*documents* rather than launchers or release feeds, and whether `cut_older` / `undated_kept` are
counted rather than silent. If those eight rows are what you would have wanted, the engine is
doing its job; if they are not, the ranking is the next thing to work on — not the design.
