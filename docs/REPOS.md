# What Nighthawk imported, and what it changed

This is not a bibliography. Every row below is machinery that runs on the request path, or a
parameter set copied from a real project into our own implementation. The **Effect** column says
what behaves differently because of it — if a row cannot answer that, it does not belong here.

Two kinds of import:

* **wired** — the library is imported and called; we pass its output downstream.
* **ported** — we re-implemented the algorithm/threshold inside `apps/api/app/*.py`, crediting the
  source. (Clean-room code, not copied source; the parameters and rules are theirs.)

Verify a claim with `grep -rn "<name>" apps/api/app` — the module column names the file.

---

## 1. The crawl frontier

| Repo | Taken | Lands in | Effect |
|---|---|---|---|
| [apify/crawlee](https://github.com/apify/crawlee) | request-queue + autoscaled-concurrency idea, retry/session pool | `crawl.py::FusionCrawler.run` | frontier is a heap of scored requests, batch width = `2 × concurrency`; a failing host is retried, not fatal — **wired (architecture)** |
| [scrapy/frontera](https://github.com/scrapy/frontera) | score-ordered frontier, per-domain politeness slots | `crawl.py::run`, `_gate` | URLs are popped by priority, not FIFO; one slow host cannot starve the queue — **ported** |
| [projectdiscovery/katana](https://github.com/projectdiscovery/katana) | known-file extension probing, headless-first fetch order | `priority.py::PRIORITY_EXTENSIONS` (24 extensions) | document links are fetched before generic pages — **ported** |
| [opsdisk/metagoofil](https://github.com/opsdisk/metagoofil) | the 8-file-type document list (`pdf,doc,xls,ppt,odp,ods,docx,xlsx,pptx`) | `priority.py`, `crawl.py::FILE_MAP` | these types get +6.0 priority and are always fetched even when `file_types` is empty — **ported** |
| [internetarchive/heritrix3](https://github.com/internetarchive/heritrix3) | scope rules: same-host, depth cap, reject-by-regex | `crawl.py::_same_host_ok`, `NOISE` | off-host links are recorded but not walked, so a crawl stays on target — **ported** |
| [searxng/searxng](https://github.com/searxng/searxng) | 358-entry engine settings model, per-engine timeout/isolation | `registry.py`, `providers/base.py` | one dead engine never fails a hunt; every provider reports `ok / empty / error / needs_key` — **ported** |
| [StractOrg/stract](https://github.com/StractOrg/stract) | `site:` / `inurl:` / `filetype:` operator parsing | `plays.py` | operators are compiled into crawl seeds as well as SERP queries — **ported** |
| [MarginaliaSearch/MarginaliaSearch](https://github.com/MarginaliaSearch/MarginaliaSearch) | independent-index query shape (non-commercial bias) | `providers/metasearch.py::Marginalia` | results from an index that does not rank by ad value — **wired (API)** |
| [benbusby/whoogle-search](https://github.com/benbusby/whoogle-search) | self-hosted metasearch query shape (no tracking, `!bang` support) | `providers/metasearch.py::Whoogle` | the same query through an unpersonalised proxy — **wired (API)** |
| [searxng/searxng](https://github.com/searxng/searxng) | instance-level `/search?format=json` contract | `providers/metasearch.py` (LibreX, 4get, MetaGer) | four more independent indexes behind one schema — **wired (API)** |
| [yacy/yacy_search_server](https://github.com/yacy/yacy_search_server) | `/yacysearch.json` contract | `providers/metasearch.py::Yacy` | one more non-corporate index in the fusion — **wired (API, needs a peer URL)** |
| [rashadphz/farfalle](https://github.com/rashadphz/farfalle) | multi-backend fan-out + fusion shape | `orchestrator.py::hunt` | all engines queried concurrently, results fused by RRF — **ported** |
| [gigablast](https://github.com/gigablast/open-source-search-engine) | "deep index" ranking signal | `extract.py::depth_score` | deep paths/archive-only results outrank front-page links — **ported** |
| [diskoverdata/diskover-community](https://github.com/diskoverdata/diskover-community) | filesystem-inventory semantics (type, size, owner) | `models.py::Hit`, `vault` table | every hit is a record with size/mime/type, not a link — **ported** |

## 2. Politeness and URL truth

| Repo | Taken | Lands in | Effect |
|---|---|---|---|
| [scrapy/protego](https://github.com/scrapy/protego) | full robots.txt parser (wildcards, `$` anchors, longest-match) | `crawl.py::_robots_for` | `Disallow: /*.pdf$` is honoured; `crawl-delay` becomes a per-host floor — **wired** |
| [google/robotstxt](https://github.com/google/robotstxt) | longest-match/most-specific-group semantics | same | the rule we implement matches Google's documented behaviour, not `urllib`'s naive prefix check — **ported** |
| [scrapy/scrapy](https://github.com/scrapy/scrapy) (`RobotFileParser` wrapper) | user-agent identity + fallback path | `crawl.py::settings.user_agent` | robots is always evaluated for *our* UA, never a spoofed browser — **wired (stdlib fallback)** |
| [seomoz/reppy](https://github.com/seomoz/reppy) | robots caching per host, crawl-delay reuse | `crawl.py::self.robots` | one robots fetch per host per crawl — **ported** |
| [adbar/courlan](https://github.com/adbar/courlan) | URL cleaning edge cases (IDN, semicolon paths, double-encoding) | `urlnorm.py::_courlan_fallback` | malformed URLs are repaired instead of dropped — **wired** |
| [ClearURLs/rules](https://github.com/ClearURLs/rules) | tracking-parameter families (`utm_*`, `fbclid`, `gclid`, `msclkid`, …) | `urlnorm.py::TRACKING` (~90 params) | the same document from a newsletter and from a search box dedupes to one hit — **ported** |
| [scrapy/w3lib](https://github.com/scrapy/w3lib) | url-safe quoting, HTML entity handling | `urlnorm.py`, `textkit.py` | URLs with unicode paths canonicalise instead of exploding — **wired (dependency)** |
| [john-kurkowski/tldextract](https://github.com/john-kurkowski/tldextract) | public-suffix resolution, offline snapshot | `urlnorm.py::registrable` | `co.za`, `ac.uk`, `github.io` are treated as one site for diversity and near-dup passes — **wired** |

## 3. Deduplication (exact, then near)

| Repo | Taken | Lands in | Effect |
|---|---|---|---|
| [ekzhu/datasketch](https://github.com/ekzhu/datasketch) | MinHash `num_perm=128`, LSH banding, `_hash_range = 1<<32` | `near_dup.py::cluster` | near-identical pages collapse before ranking — **wired** |
| [seomoz/simhash-py](https://github.com/seomoz/simhash-py) | 64-bit simhash, hamming ≤ 3 fallback | `near_dup.py::_simhash` | works even when LSH banding misses a pair — **ported** |
| [1e0ng/simhash](https://github.com/1e0ng/simhash) | 4-word shingles → weighted hash | same | the fingerprint is content, not markup — **ported** |
| [rapidfuzz/RapidFuzz](https://github.com/rapidfuzz/RapidFuzz) | `token_set_ratio ≥ 92` same-site second pass | `near_dup.py` | a 0.867-Jaccard pair that LSH missed is still folded — **wired** |
| [dedupeio/dedupe](https://github.com/dedupeio/dedupe) | blocking keys before pairwise comparison | `near_dup.py` (site blocking) | O(n²) becomes per-site; a hunt with 40 hits clusters in ~5 ms — **ported** |
| [adbar/trafilatura](https://github.com/adbar/trafilatura) | `MIN_DUPLICATE_LENGTH = 50` duplicate gate | `near_dup.py` | stub pages are never treated as duplicates of real documents — **ported** |

**Rule added on top:** when a cluster collapses, the survivor is the *most specific* member — the
record with a funder, an amount, a deadline and a schema type — and it inherits the missing fields
from its siblings (`near_dup.py::_specificity`). A bare PDF never beats the page that names the
money.

## 4. Text extraction

| Repo | Taken | Lands in | Effect |
|---|---|---|---|
| [adbar/trafilatura](https://github.com/adbar/trafilatura) | main-content extraction + metadata | `textkit.py::extract_text` | nav/footer noise never reaches the index — **wired** |
| [buriy/python-readability](https://github.com/buriy/python-readability) | article scoring fallback | `textkit.py` | works on pages trafilatura refuses — **wired** |
| [miso-belica/jusText](https://github.com/miso-belica/jusText) | length-based boilerplate classification | `textkit.py` | short-link pages still yield readable text — **wired** |
| [misja/python-boilerpipe](https://github.com/misja/python-boilerpipe) | density-based block classification | `textkit.py` | tables and definition lists survive extraction — **wired** |
| [jmriebold/BoilerPy3](https://github.com/jmriebold/BoilerPy3) | `ArticleExtractor` alternative | `textkit.py` | four extractors vote; the longest coherent text wins — **wired** |
| [codelucas/newspaper](https://github.com/codelucas/newspaper) | `article.text` + publish date | `textkit.py` | publication dates improve the `newest` sort — **wired** |
| [dalab/web2text](https://github.com/dalab/web2text) | block-level segmentation idea | `textkit.py` (fallback chain) | heading/list structure is preserved for keyphrase extraction — **ported** |
| [behindthefirewalls/Parsero](https://github.com/behindthefirewalls/Parsero) | text-to-content ratio thresholds | `textkit.py::_looks_like_content` | "index of /" listings are kept as text rather than discarded — **ported** |
| [rushter/selectolax](https://github.com/rushter/selectolax) | lexbor parse for links | `textkit.py::parse_links_rich` | anchor text, `rel` and listing context per link, in one pass — **wired** |
| [scrapy/parsel](https://github.com/scrapy/parsel) | selector API for structured fields | `textkit.py` | fallback selector engine when lexbor is missing — **wired** |
| [Alir3z4/html2text](https://github.com/Alir3z4/html2text) | markdown rendering | `textkit.py` | `.md` export of extracted pages — **wired** |
| [kurtmckee/feedparser](https://github.com/kurtmckee/feedparser) | RSS/Atom normalisation | `providers/web.py` (feed layer) | feed items become crawl seeds with dates — **wired** |

## 5. Files: what they really are

| Repo | Taken | Lands in | Effect |
|---|---|---|---|
| [h2non/filetype.py](https://github.com/h2non/filetype.py) | magic-byte signature table | `magic.py::sniff` | a `.pdf` that is really a ZIP (or a login wall) is re-labelled before indexing — **ported** |
| [PyMuPDF](https://github.com/pymupdf/PyMuPDF) | PDF text + first-page title fallback | `magic.py::pdf_title` | a scanned tender keeps its real title instead of `document.pdf` — **wired** |
| [py-pdf/pypdf](https://github.com/py-pdf/pypdf) | PDF text engine | `textkit.py::file_text` | deadline text inside a PDF is indexed — **wired** |
| [pdfminer/pdfminer.six](https://github.com/pdfminer/pdfminer.six) | layout-preserving fallback | `textkit.py::file_text` | multi-column PDFs do not interleave — **wired** |
| [Apache Tika](https://github.com/apache/tika) | "sniff → choose parser" architecture | `textkit.py::file_text` | one dispatch table for 20+ formats — **ported** |
| [python-openxml/python-docx](https://github.com/python-openxml/python-docx) | `.docx` text | `textkit.py::file_text` | application forms are searchable — **wired** |
| [theorchard/openpyxl](https://github.com/theorchard/openpyxl) | `.xlsx` cell text | `textkit.py::file_text` | budget tables become text — **wired** |
| [webrecorder/warcio](https://github.com/webrecorder/warcio) | WARC iteration | `providers/archives.py` | archived PDFs are read straight out of WARC records — **wired** |
| [libarchive](https://github.com/libarchive/libarchive) | archive listing (`bsdtar`) | `arsenal.py` | a ZIP listing reveals further documents — **wired** |
| [tesseract-ocr/tesseract](https://github.com/tesseract-ocr/tesseract) | OCR probe for scanned PDFs | `arsenal.py::ENGINES` | scanned documents are reported as OCR-able instead of silently empty — **registered** |

## 6. Structured fields — the specificity layer

| Repo | Taken | Lands in | Effect |
|---|---|---|---|
| [scrapinghub/extruct](https://github.com/scrapinghub/extruct) | JSON-LD / microdata / RDFa walk | `schemaorg.py::extract` | a page's `Grant`/`JobPosting` becomes a typed record — **wired** |
| [schema.org](https://github.com/schemaorg/schemaorg) | vocabulary: `Grant`, `MonetaryGrant`, `JobPosting`, `Dataset`, `Offer` | `schemaorg.py::OPPORTUNITY_TYPES` | type decides which deadline/amount keys are read — **ported** |
| [Google Jobs structured-posting contract](https://developers.google.com/search/docs/appearance/structured-data/job-posting) | `validThrough` + `hiringOrganization` pairing | `schemaorg.py::DEADLINE_KEYS` | a deadline is trusted only when a published field says so — **ported** |
| [w3c/json-ld](https://github.com/w3c/json-ld-api) | tolerant JSON-LD parsing (trailing commas, `@graph`) | `schemaorg.py::jsonld_blocks` | markup that extruct rejects still yields a record — **ported** |
| — (our rule) | prose fallback: `funded by …`, `USD 250,000`, `Duty station: …` | `schemaorg.py::guess_fields` | pages with **no** markup still arrive with funder/amount/currency/location — **new** |

`guess_fields` is the single biggest specificity change: it converts "a page that mentions a grant"
into `Ford Foundation · USD 90,000 · Nairobi, Kenya · 2026-02-28`.

## 7. Query understanding

| Repo | Taken | Lands in | Effect |
|---|---|---|---|
| [u-prashant/RAKE](https://github.com/u-prashant/RAKE) | the whole package — `rake.py`, `SmartStoplist.txt`, LICENSE — vendored unmodified under `apps/api/app/vendor/rake_keyword/` | `understand.py::read` | every search is read before a source is asked: the subject phrase is the highest-RAKE-scoring run of words in the query, and the answer says what it understood — **wired (vendored source, py3, stdlib only)** |
| [LIAAD/yake](https://github.com/LIAAD/yake) | YAKE parameters (`n=3`, `dedupLim=0.85`, `top=12`) | `keyterms.py::keyphrases` | every hit carries 4–6 extracted keyphrases — **wired** |
| [boudinfl/pke](https://github.com/boudinfl/pke) | TF-IDF/TextRank family as the fallback | `keyterms.py` | phrases still appear when YAKE is absent — **ported** |
| [swisscom/ai-research-keyphrase-extraction](https://github.com/swisscom/ai-research-keyphrase-extraction) | embedded-keyphrase elimination idea | `keyterms.py::_dedupe_subphrases` | `climate grant` is not listed next to `grant` — **ported** |
| [searxng/searxng](https://github.com/searxng/searxng) | synonym expansion per category | `keyterms.py::THESAURUS`, `expand_terms` | a hunt for "grant" also queries "call for proposals", "tender", "fellowship" — **ported** |
| [explosion/spaCy](https://github.com/explosion/spaCy) | (rejected) heavy NLP dependency | — | we kept YAKE + regex: no model download, works offline — **decision** |
| [aneesha/RAKE](https://github.com/aneesha/RAKE) | (rejected) Python 2 source; only its `SmartStoplist.txt` lineage is reused | `vendor/rake_keyword/resources` | the same stop list, through the Python 3 fork above — **decision** |
| [MaartenGr/KeyBERT](https://github.com/MaartenGr/KeyBERT) · [csurfer/rake-nltk](https://github.com/csurfer/rake-nltk) | (rejected) torch + sentence-transformers, NLTK corpora | — | a free 512 MB instance cannot download a model at boot; RAKE needs nothing — **decision** |

## 8. Change detection

| Repo | Taken | Lands in | Effect |
|---|---|---|---|
| [dgtlmoon/changedetection.io](https://github.com/dgtlmoon/changedetection.io) | per-URL content hash stored per watch, diff on each run | `change.py`, `api.py::run_hunt` | a watcher reports "changed", not just "new" — **ported** |
| [python/cpython](https://github.com/python/cpython) `difflib` | `SequenceMatcher` opcodes for word-level deltas | `change.py::word_diff` | `28 February 90,000` → `30 April 120,000` is shown as an exact edit — **wired** |

The vault only accepts a *richer* record over an existing one (`local_index.py::payload_richness`),
so a re-hunt can never downgrade a structured record to a plain snippet.

## 9. Opportunity and archive data

| Repo / service | Taken | Lands in | Effect |
|---|---|---|---|
| [Grants.gov](https://github.com/HHS/grants.gov-api) | opportunity search + `closeDate`/`awardFloor` | `providers/opportunities.py::GrantsGov` | real deadlines and award floors — **wired** |
| [NIH RePORTER](https://github.com/NIH-NEI-Software/reporter-api) | `AwardAmount`, `AgencyIcAdmin`, project period | `providers/opportunities.py::NihReporter` | funded projects with amounts, not calls — **wired** |
| [NSF Awards API](https://github.com/RTIInternational/nsf-awards) | `fundsObligatedAmt`, start/expiry | `providers/opportunities.py::NsfAwards` | award records with money — **wired** |
| [USAspending](https://github.com/fedspendingtransparency/usaspending-api) | award search by keyword + time period | `providers/opportunities.py::UsaSpending` | federal awards as opportunities — **wired** |
| [EU Funding & Tenders / SEDIA](https://github.com/opengovpartnership/eu-funding-tenders) | topic search, `deadlineDate` | `providers/opportunities.py::EuFunding` | EU calls with closing dates — **wired** |
| [ReliefWeb API](https://github.com/reliefweb/reliefweb-api) | jobs + reports + `closing_date` | `providers/opportunities.py::ReliefWebJobs` | humanitarian roles with deadlines — **wired** |
| [Common Crawl index](https://github.com/commoncrawl/cc-index-table) | CDX-style index queries | `providers/archives.py` | buried pages from sites that no longer exist — **wired** |
| [internetarchive/wayback](https://github.com/internetarchive/wayback) | CDX API + availability | `providers/archives.py`, `providers/archives.py` | deleted PDFs are still retrievable — **wired** |
| [OpenAlex](https://github.com/ourresearch/openalex-api) / [arXiv](https://github.com/lukasschwab/arxiv.py) / [DOAJ](https://github.com/DOAJ/doaj) / [PubMed E-utilities](https://github.com/biocommons/eutils) | per-source query shapes | `providers/scholar.py` | papers, preprints and datasets in the same stream — **wired** |

## 10. Engines registered in the arsenal (86)

`apps/api/app/arsenal.py` declares 86 engines with a real probe (Python import, `PATH` binary, or
service URL). They are not decoration: `arsenal_ready` in `/api/v1/health` is the count that
actually resolved in this environment, and the crawler dispatches to whatever is present.

Selected repos represented there, by role:

* **Frameworks / fetchers** — [crawlee](https://github.com/apify/crawlee), [scrapy](https://github.com/scrapy/scrapy), [crawlab](https://github.com/crawlab-team/crawlab), [gerapy](https://github.com/Gerapy/Gerapy), [scrapyd](https://github.com/scrapy/scrapyd), [bda-research/node-crawler](https://github.com/bda-research/node-crawler), [simplecrawler](https://github.com/simplecrawler/simplecrawler), [siteone-crawler](https://github.com/janreges/siteone-crawler), [matthewmueller/x-ray](https://github.com/matthewmueller/x-ray), [gocolly/colly](https://github.com/gocolly/colly), [Apache Nutch](https://github.com/apache/nutch), [StormCrawler](https://github.com/apache/incubator-stormcrawler)
* **Browsers** — [playwright](https://github.com/microsoft/playwright), [puppeteer](https://github.com/puppeteer/puppeteer), [selenium](https://github.com/SeleniumHQ/selenium), [pyppeteer](https://github.com/pyppeteer/pyppeteer), [splinter](https://github.com/cobrateam/splinter), [requests-html](https://github.com/psf/requests-html), [brozzler](https://github.com/internetarchive/brozzler), [browsertrix-crawler](https://github.com/webrecorder/browsertrix-crawler), [splash](https://github.com/scrapinghub/splash)
* **Archival fetchers** — [heritrix3](https://github.com/internetarchive/heritrix3), [warcprox](https://github.com/internetarchive/warcprox), [wpull](https://github.com/ArchiveTeam/wpull), [warcio](https://github.com/webrecorder/warcio), [waybackpy](https://github.com/akamhy/waybackpy), [gau](https://github.com/lc/gau), [waymore](https://github.com/xnl-h4ck3r/waymore)
* **Content discovery CLIs** — [katana](https://github.com/projectdiscovery/katana), [hakrawler](https://github.com/hakluke/hakrawler), [gospider](https://github.com/jaeles-project/gospider), [Photon](https://github.com/s0md3v/Photon), [LinkFinder](https://github.com/GerbenJavado/LinkFinder), [xnLinkFinder](https://github.com/xnl-h4ck3r/xnLinkFinder), [Arjun](https://github.com/s0md3v/Arjun), [ParamSpider](https://github.com/devanshbatham/ParamSpider), [unfurl](https://github.com/tomnomnom/unfurl)
* **Directory / file discovery** — [ffuf](https://github.com/ffuf/ffuf), [feroxbuster](https://github.com/epi052/feroxbuster), [gobuster](https://github.com/OJ/gobuster), [dirsearch](https://github.com/maurosoria/dirsearch), [dirb](https://github.com/v0re/dirb), [httrack](https://github.com/xroche/httrack), [wget](https://git.savannah.gnu.org/cgit/wget.git), [curl](https://github.com/curl/curl), [aria2](https://github.com/aria2/aria2)
* **Asset / host mapping** — [subfinder](https://github.com/projectdiscovery/subfinder), [OWASP Amass](https://github.com/owasp-amass/amass), [assetfinder](https://github.com/tomnomnom/assetfinder), [dnsx](https://github.com/projectdiscovery/dnsx), [theHarvester](https://github.com/laramies/theHarvester)
* **Parsers** — [lxml](https://github.com/lxml/lxml), [BeautifulSoup](https://github.com/wention/BeautifulSoup4), [selectolax](https://github.com/rushter/selectolax), [pyquery](https://github.com/gawel/pyquery), [cheerio](https://github.com/cheeriojs/cheerio), [jsdom](https://github.com/jsdom/jsdom), [extruct](https://github.com/scrapinghub/extruct), [w3lib](https://github.com/scrapy/w3lib), [tldextract](https://github.com/john-kurkowski/tldextract), [charset-normalizer](https://github.com/Ousret/charset_normalizer)

---

## Count

| Group | Repos / projects |
|---|---|
| 1. Frontier | 13 |
| 2. Politeness & URL truth | 8 |
| 3. Deduplication | 6 |
| 4. Text extraction | 12 |
| 5. Files | 10 |
| 6. Structured fields | 5 |
| 7. Query understanding | 8 |
| 8. Change detection | 2 |
| 9. Opportunity & archive data | 9 |
| 10. Registered arsenal engines | 50 (of 86 entries) |
| **Distinct projects** | **123** (53 wired or ported into the request path, 1 of them vendored source) |

## What this bought, in numbers

Measured on the built-in practice target (`scripts/selftest.py`, no network):

| Before | After |
|---|---|
| 4 near-duplicate records kept | folded into 1, the richest one |
| files identified by extension only | magic bytes re-label codecs; a fake `.pdf` is caught |
| deadlines only | funder, amount, currency, location, schema type, size, keyphrases |
| 1 crawl order (BFS) | priority heap: documents first, login walls last |
| `climate grants kenya` → generic links | `Climate Resilience Grant 2026 · Ford Foundation · USD 90,000 · Nairobi, Kenya · 2026-02-28` |
| watchers report only new URLs | new URLs **and** changed documents, with word-level diffs |
