# Engine reference

Generated from the live registry: **69 remote engines**, **86 arsenal engines** (29 resolved here), **54 portals**, plus the fusion crawler.

Regenerate with `.venv/bin/python scripts/gen_engines_doc.py`.

## Remote engines

| # | Engine | Layer | Family | Lenses | Credentials | Status |
|---|---|---|---|---|---|---|
| 1 | SearXNG | remote | metasearch | all, files, opportunities, applications, datasets, exposed | searxng_url | needs_key |
| 2 | Brave Search | remote | web | all, files, opportunities, applications | brave_api_key | needs_key |
| 3 | Tavily | remote | web | all, files, opportunities | tavily_api_key | needs_key |
| 4 | Exa | remote | web | all, files, datasets | exa_api_key | needs_key |
| 5 | Serper | remote | serp | all, files, opportunities, applications | serper_api_key | needs_key |
| 6 | SerpApi | remote | serp | all, files, opportunities, applications | serpapi_api_key | needs_key |
| 7 | SearchApi | remote | serp | all, opportunities, files | searchapi_api_key | needs_key |
| 8 | Google Programmable Search | remote | serp | all, files, opportunities | google_cse_key, google_cse_cx | needs_key |
| 9 | Perplexity | remote | ai | all, opportunities, files | perplexity_api_key | needs_key |
| 10 | You.com | remote | web | all, files | you_api_key | needs_key |
| 11 | Bing | remote | serp | all, files | serpapi_api_key | needs_key |
| 12 | Yahoo | remote | serp | all | serpapi_api_key | needs_key |
| 13 | Ecosia | remote | serp | all | serpapi_api_key | needs_key |
| 14 | Startpage | remote | serp | all | serpapi_api_key | needs_key |
| 15 | Yandex | remote | serp | all | serpapi_api_key | needs_key |
| 16 | Google Scholar | remote | serp | all, files | serpapi_api_key | needs_key |
| 17 | Google News | remote | serp | all, opportunities | serpapi_api_key | needs_key |
| 18 | Mojeek | remote | independent | all, files, opportunities | mojeek_api_key | needs_key |
| 19 | Qwant | remote | independent | all, files | qwant_api_key | needs_key |
| 20 | MetaGer | remote | metasearch | all, files, opportunities | metager_api_key | needs_key |
| 21 | Whoogle | remote | metasearch | all, files, opportunities | whoogle_url | needs_key |
| 22 | LibreX | remote | metasearch | all, files | librex_url | needs_key |
| 23 | 4get | remote | metasearch | all, files, opportunities | forget_url | needs_key |
| 24 | YaCy | remote | p2p | all, files, datasets | yacy_url | needs_key |
| 25 | Wiby | remote | independent | all, files | — | ready |
| 26 | Marginalia | remote | independent | all, files | — | ready |
| 27 | Gigablast | remote | independent | all | — | retired |
| 28 | Common Crawl Index | archive | archive | files, datasets, opportunities, applications, exposed, all | — | ready |
| 29 | Wayback CDX | archive | archive | files, datasets, opportunities, applications, exposed, all | — | ready |
| 30 | Internet Archive | archive | archive | files, datasets, all | — | ready |
| 31 | Arquivo.pt | archive | archive | files, all, opportunities | — | ready |
| 32 | Grants.gov | remote | opportunity | opportunities, applications, all | — | ready |
| 33 | ReliefWeb Jobs | remote | opportunity | opportunities, all | — | ready |
| 34 | ReliefWeb Reports | remote | document | files, opportunities, datasets, all | — | ready |
| 35 | EU Funding & Tenders | remote | opportunity | opportunities, applications, all | — | ready |
| 36 | NIH RePORTER | remote | opportunity | opportunities, datasets, all | — | ready |
| 37 | NSF Awards | remote | opportunity | opportunities, datasets | — | ready |
| 38 | USAspending | remote | opportunity | opportunities, datasets | — | ready |
| 39 | OpenAlex | remote | scholar | files, datasets, all | — | ready |
| 40 | Crossref | remote | scholar | files, all | — | ready |
| 41 | arXiv | remote | scholar | files, datasets, all | — | ready |
| 42 | DOAJ | remote | scholar | files, all | — | ready |
| 43 | PubMed | remote | scholar | files, all | — | ready |
| 44 | Semantic Scholar | remote | scholar | files, all | — | ready |
| 45 | CORE | remote | scholar | files, datasets | core_api_key | needs_key |
| 46 | Wikipedia | remote | reference | all, opportunities | — | ready |
| 47 | Wikidata | remote | reference | all, opportunities, datasets | — | ready |
| 48 | Open Library | remote | reference | all, files | — | ready |
| 49 | Zenodo | remote | dataset | datasets, files, all | — | ready |
| 50 | Figshare | remote | dataset | datasets, files | — | ready |
| 51 | Data.gov | remote | dataset | datasets, files, all | — | ready |
| 52 | Data.gov.uk | remote | dataset | datasets, files, all | — | ready |
| 53 | EU Open Data | remote | dataset | datasets, files, all | — | ready |
| 54 | Data.gov.au | remote | dataset | datasets, files, all | — | ready |
| 55 | Open Canada | remote | dataset | datasets, files, all | — | ready |
| 56 | World Bank Documents | remote | document | files, datasets, opportunities | — | ready |
| 57 | World Bank Data | remote | dataset | datasets | — | ready |
| 58 | Hugging Face Datasets | remote | dataset | datasets, files | — | ready |
| 59 | CKAN Portal | remote | dataset | datasets, files, all | — | ready |
| 60 | GitHub | remote | code | all, exposed, datasets | — | ready |
| 61 | GitLab | remote | code | all, exposed, datasets | — | ready |
| 62 | Hacker News | remote | community | all, opportunities | — | ready |
| 63 | Stack Exchange | remote | community | all | — | ready |
| 64 | npm Registry | remote | code | all, exposed | — | ready |
| 65 | crates.io | remote | code | all, exposed | — | ready |
| 66 | Nighthawk Vault | core | local | all, files, opportunities, applications, datasets, exposed | — | local |
| 67 | Vault Deep Text | core | local | all, files, opportunities, datasets | — | local |
| 68 | Portal Universe | portal | launcher | all, opportunities, files, applications, datasets, exposed | — | ready |
| 69 | Dork Hand-off | portal | launcher | all, exposed, files, opportunities | — | ready |

## Arsenal engines

| # | Engine | Role | Language | Probe | State |
|---|---|---|---|---|---|
| 1 | [Crawlee](https://crawlee.dev/) | fetcher | TypeScript/Python | `crawlee` | ready |
| 2 | [Scrapy](https://scrapy.org/) | fetcher | Python | `scrapy` | ready |
| 3 | [Playwright](https://playwright.dev/) | browser | TS/Python | `playwright` | missing |
| 4 | [Puppeteer](https://pptr.dev/) | browser | Node | `puppeteer` | missing |
| 5 | [Selenium](https://www.selenium.dev/) | browser | Multi | `selenium` | missing |
| 6 | [Pyppeteer](https://github.com/pyppeteer/pyppeteer) | browser | Python | `pyppeteer` | missing |
| 7 | [Splinter](https://splinter.readthedocs.io/) | browser | Python | `splinter` | missing |
| 8 | [MechanicalSoup](https://mechanicalsoup.readthedocs.io/) | fetcher | Python | `mechanicalsoup` | ready |
| 9 | [Requests-HTML](https://requests-html.kennethreitz.org/) | browser | Python | `requests_html` | missing |
| 10 | [aiohttp](https://docs.aiohttp.org/) | fetcher | Python | `aiohttp` | ready |
| 11 | [HTTPX](https://www.python-httpx.org/) | fetcher | Python | `httpx` | ready |
| 12 | [hrequests](https://github.com/daijro/hrequests) | fetcher | Python | `hrequests` | ready |
| 13 | [Cloudscraper](https://github.com/VeNoMouS/cloudscraper) | fetcher | Python | `cloudscraper` | ready |
| 14 | [Colly](https://go-colly.org/) | fetcher | Go | `—` | missing |
| 15 | [Apache Nutch](https://nutch.apache.org/) | fetcher | Java | `nutch` | missing |
| 16 | [Heritrix](https://github.com/internetarchive/heritrix3) | fetcher | Java | `heritrix` | missing |
| 17 | [StormCrawler](https://stormcrawler.apache.org/) | fetcher | Java | `—` | missing |
| 18 | [Brozzler](https://github.com/internetarchive/brozzler) | browser | Python | `brozzler` | missing |
| 19 | [Browsertrix Crawler](https://github.com/webrecorder/browsertrix-crawler) | browser | Node | `browsertrix-crawler` | missing |
| 20 | [Warcprox](https://github.com/internetarchive/warcprox) | proxy | Python | `warcprox` | missing |
| 21 | [Splash](https://github.com/scrapinghub/splash) | browser | Python | `—` | missing |
| 22 | [Apify SDK](https://apify.com/) | fetcher | Node | `apify` | missing |
| 23 | [Gerapy](https://github.com/Gerapy/Gerapy) | fetcher | Python | `gerapy` | missing |
| 24 | [Crawlab](https://github.com/crawlab-team/crawlab) | fetcher | Go | `crawlab` | missing |
| 25 | [Scrapyd](https://github.com/scrapy/scrapyd) | fetcher | Python | `scrapyd` | missing |
| 26 | [node-crawler](https://github.com/bda-research/node-crawler) | fetcher | Node | `—` | missing |
| 27 | [SimpleCrawler](https://github.com/simplecrawler/simplecrawler) | fetcher | Node | `—` | missing |
| 28 | [website-scraper](https://github.com/website-scraper/node-website-scraper) | fetcher | Node | `—` | missing |
| 29 | [X-Ray](https://github.com/matthewmueller/x-ray) | fetcher | Node | `—` | missing |
| 30 | [jsdom](https://github.com/jsdom/jsdom) | parser | Node | `—` | missing |
| 31 | [Cheerio](https://cheerio.js.org/) | parser | Node | `—` | missing |
| 32 | [Katana](https://github.com/projectdiscovery/katana) | cli | Go | `katana` | missing |
| 33 | [Hakrawler](https://github.com/hakluke/hakrawler) | cli | Go | `hakrawler` | missing |
| 34 | [GoSpider](https://github.com/jaeles-project/gospider) | cli | Go | `gospider` | missing |
| 35 | [Photon](https://github.com/s0md3v/Photon) | cli | Python | `photon` | missing |
| 36 | [gau (GetAllUrls)](https://github.com/lc/gau) | seeder | Go | `gau` | missing |
| 37 | [waymore](https://github.com/xnl-h4ck3r/waymore) | seeder | Python | `waymore` | missing |
| 38 | [waybackpy](https://github.com/akamhy/waybackpy) | seeder | Python | `waybackpy` | ready |
| 39 | [ffuf](https://github.com/ffuf/ffuf) | cli | Go | `ffuf` | missing |
| 40 | [feroxbuster](https://github.com/epi052/feroxbuster) | cli | Rust | `feroxbuster` | missing |
| 41 | [Gobuster](https://github.com/OJ/gobuster) | cli | Go | `gobuster` | missing |
| 42 | [dirsearch](https://github.com/maurosoria/dirsearch) | cli | Python | `dirsearch` | missing |
| 43 | [DIRB](https://github.com/v0re/dirb) | cli | C | `dirb` | missing |
| 44 | [GNU Wget](https://www.gnu.org/software/wget/) | cli | C | `wget` | missing |
| 45 | [curl](https://curl.se/) | cli | C | `curl` | missing |
| 46 | [aria2](https://aria2.github.io/) | cli | C++ | `aria2c` | missing |
| 47 | [HTTrack](https://www.httrack.com/) | cli | C | `httrack` | missing |
| 48 | [wpull](https://github.com/ArchiveTeam/wpull) | cli | Python | `wpull` | missing |
| 49 | [subfinder](https://github.com/projectdiscovery/subfinder) | seeder | Go | `subfinder` | missing |
| 50 | [Amass](https://github.com/owasp-amass/amass) | seeder | Go | `amass` | missing |
| 51 | [assetfinder](https://github.com/tomnomnom/assetfinder) | seeder | Go | `assetfinder` | missing |
| 52 | [dnsx](https://github.com/projectdiscovery/dnsx) | seeder | Go | `dnsx` | missing |
| 53 | [theHarvester](https://github.com/laramies/theHarvester) | seeder | Python | `theHarvester` | missing |
| 54 | [LinkFinder](https://github.com/GerbenJavado/LinkFinder) | cli | Python | `linkfinder` | missing |
| 55 | [xnLinkFinder](https://github.com/xnl-h4ck3r/xnLinkFinder) | cli | Python | `xnLinkFinder` | missing |
| 56 | [Arjun](https://github.com/s0md3v/Arjun) | cli | Python | `arjun` | missing |
| 57 | [ParamSpider](https://github.com/devanshbatham/ParamSpider) | cli | Python | `paramspider` | missing |
| 58 | [unfurl](https://github.com/tomnomnom/unfurl) | seeder | Go | `unfurl` | missing |
| 59 | [sitemap-generator](https://github.com/lgraubner/sitemap-generator) | seeder | Node | `—` | missing |
| 60 | [Wget2](https://gitlab.com/gnuwget/wget2) | cli | C | `wget2` | missing |
| 61 | [Trafilatura](https://trafilatura.readthedocs.io/) | extractor | Python | `trafilatura` | ready |
| 62 | [Readability-lxml](https://github.com/buriy/python-readability) | extractor | Python | `readability` | ready |
| 63 | [JusText](https://github.com/miso-belica/jusText) | extractor | Python | `justext` | ready |
| 64 | [Newspaper3k](https://github.com/codelucas/newspaper) | extractor | Python | `newspaper` | ready |
| 65 | [BoilerPy3](https://github.com/jmriebold/BoilerPy3) | extractor | Python | `boilerpy3` | ready |
| 66 | [html2text](https://github.com/Alir3z4/html2text) | extractor | Python | `html2text` | ready |
| 67 | [BeautifulSoup](https://www.crummy.com/software/BeautifulSoup/) | parser | Python | `bs4` | ready |
| 68 | [lxml](https://lxml.de/) | parser | Python | `lxml` | ready |
| 69 | [Parsel](https://github.com/scrapy/parsel) | parser | Python | `parsel` | ready |
| 70 | [Selectolax](https://github.com/rushter/selectolax) | parser | Python | `selectolax` | ready |
| 71 | [pyquery](https://pythonhosted.org/pyquery/) | parser | Python | `pyquery` | ready |
| 72 | [Extruct](https://github.com/scrapinghub/extruct) | extractor | Python | `extruct` | ready |
| 73 | [feedparser](https://github.com/kurtmckee/feedparser) | extractor | Python | `feedparser` | ready |
| 74 | [w3lib](https://github.com/scrapy/w3lib) | parser | Python | `w3lib` | ready |
| 75 | [tldextract](https://github.com/john-kurkowski/tldextract) | parser | Python | `tldextract` | ready |
| 76 | [charset-normalizer](https://github.com/Ousret/charset_normalizer) | parser | Python | `charset_normalizer` | ready |
| 77 | [pypdf](https://pypdf.readthedocs.io/) | files | Python | `pypdf` | ready |
| 78 | [pdfminer.six](https://github.com/pdfminer/pdfminer.six) | files | Python | `pdfminer` | ready |
| 79 | [pdftotext (Poppler)](https://poppler.freedesktop.org/) | files | C++ | `pdftotext` | missing |
| 80 | [Tesseract OCR](https://github.com/tesseract-ocr/tesseract) | files | C++ | `tesseract` | missing |
| 81 | [OCRmyPDF](https://github.com/ocrmypdf/OCRmyPDF) | files | Python | `ocrmypdf` | missing |
| 82 | [Apache Tika](https://tika.apache.org/) | files | Java | `—` | missing |
| 83 | [warcio](https://github.com/webrecorder/warcio) | files | Python | `warcio` | ready |
| 84 | [libarchive](https://libarchive.org/) | files | C | `bsdtar` | missing |
| 85 | [openpyxl](https://openpyxl.readthedocs.io/) | files | Python | `openpyxl` | ready |
| 86 | [python-docx](https://python-docx.readthedocs.io/) | files | Python | `docx` | ready |

## Portals

54 hand-picked opportunity portals are searched as links, so a hit on a portal page still carries the portal's own deadline.

- **Grants.gov** — grants.gov · opportunities, applications
- **EU Funding & Tenders** — ec.europa.eu · opportunities, applications
- **TED — Tenders Electronic Daily** — ted.europa.eu · opportunities
- **UNGM — UN Global Marketplace** — ungm.org · opportunities
- **ReliefWeb** — reliefweb.int · opportunities, files
- **UNjobs** — unjobs.org · opportunities
- **UNDP Procurement** — undp.org · opportunities
- **World Bank Procurement** — worldbank.org · opportunities, files
- **SAM.gov** — sam.gov · opportunities
- **Find a Tender (UK)** — find-tender.service.gov.uk · opportunities
- **eTenders South Africa** — etenders.gov.za · opportunities
- **CORDIS** — cordis.europa.eu · opportunities, datasets, files
- **NSF Funding** — nsf.gov · opportunities
- **NIH Grants** — grants.nih.gov · opportunities
- **UKRI Opportunities** — ukri.org · opportunities
- **Wellcome Funding** — wellcome.org · opportunities
- **IDRC Funding** — idrc-crdi.ca · opportunities
- **Gates Foundation Grants** — gatesfoundation.org · opportunities
- **FundsforNGOs** — fundsforngos.org · opportunities
- **Opportunity Desk** — opportunitydesk.org · opportunities, applications
- **Scholars4Dev** — scholars4dev.com · opportunities, applications
- **Idealist** — idealist.org · opportunities
- **Devex** — devex.com · opportunities
- **UN Careers** — careers.un.org · opportunities
- **African Development Bank** — afdb.org · opportunities, files
- **FCDO International Funding** — gov.uk · opportunities, files
- **Echoing Green** — echoinggreen.org · opportunities, applications
- **Y Combinator** — ycombinator.com · opportunities, applications
- **World Bank Documents** — documents.worldbank.org · files, datasets, opportunities
- **World Bank Open Knowledge** — openknowledge.worldbank.org · files, datasets
- **UN Digital Library** — digitallibrary.un.org · files, opportunities
- **WHO IRIS** — iris.who.int · files, datasets
- **FAO Documents** — fao.org · files, datasets
- **OECD** — oecd.org · files, datasets
- **IMF Publications** — imf.org · files, datasets
- **ILO** — ilo.org · files, opportunities
- **UNHCR** — unhcr.org · files, opportunities
- **Open Knowledge Repository** — openknowledge.worldbank.org · files, datasets
- **BASE** — base-search.net · files, datasets
- **CORE** — core.ac.uk · files, datasets
- **OpenAIRE** — openaire.eu · files, datasets
- **Data.gov** — catalog.data.gov · datasets, files
- **Data.gov.uk** — data.gov.uk · datasets, files
- **EU Open Data Portal** — data.europa.eu · datasets, files
- **Data.gov.au** — data.gov.au · datasets, files
- **Open Canada** — open.canada.ca · datasets, files
- **Hugging Face Datasets** — huggingface.co · datasets, files
- **Zenodo** — zenodo.org · datasets, files
- **Figshare** — figshare.com · datasets, files
- **Dryad** — datadryad.org · datasets, files
- **Common App** — commonapp.org · applications
- **DAAD Scholarships** — daad.de · applications, opportunities
- **Erasmus+** — erasmus-plus.ec.europa.eu · applications, opportunities
- **Voluntary Service / ESC** — europa.eu · applications, opportunities

