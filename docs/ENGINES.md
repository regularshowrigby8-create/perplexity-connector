# Engine reference

Generated from the live registry: **66 remote engines**, **86 arsenal engines**, **54 portals**, plus the fusion crawler.


## Remote engines

| # | Engine | Layer | Lenses | Credentials | Status |
|---|---|---|---|---|---|
| 1 | SearXNG | remote | all, files, opportunities, applications, datasets, exposed | searxng_url | needs_key |
| 2 | Brave Search | remote | all, files, opportunities, applications | brave_api_key | needs_key |
| 3 | Tavily | remote | all, files, opportunities | tavily_api_key | needs_key |
| 4 | Exa | remote | all, files, datasets | exa_api_key | needs_key |
| 5 | Serper | remote | all, files, opportunities, applications | serper_api_key | needs_key |
| 6 | SerpApi | remote | all, files, opportunities, applications | serpapi_api_key | needs_key |
| 7 | SearchApi | remote | all, opportunities, files | searchapi_api_key | needs_key |
| 8 | Google Programmable Search | remote | all, files, opportunities | google_cse_key, google_cse_cx | needs_key |
| 9 | Perplexity | remote | all, opportunities, files | perplexity_api_key | needs_key |
| 10 | You.com | remote | all, files | you_api_key | needs_key |
| 11 | Bing | remote | all, files | serpapi_api_key | needs_key |
| 12 | Yahoo | remote | all | serpapi_api_key | needs_key |
| 13 | Ecosia | remote | all | serpapi_api_key | needs_key |
| 14 | Startpage | remote | all | serpapi_api_key | needs_key |
| 15 | Yandex | remote | all | serpapi_api_key | needs_key |
| 16 | Google Scholar | remote | all, files | serpapi_api_key | needs_key |
| 17 | Google News | remote | all, opportunities | serpapi_api_key | needs_key |
| 18 | Mojeek | remote | all, files, opportunities | mojeek_api_key | needs_key |
| 19 | Qwant | remote | all, files | qwant_api_key | needs_key |
| 20 | MetaGer | remote | all, files, opportunities | metager_api_key | needs_key |
| 21 | Whoogle | remote | all, files, opportunities | whoogle_url | needs_key |
| 22 | LibreX | remote | all, files | librex_url | needs_key |
| 23 | 4get | remote | all, files, opportunities | forget_url | needs_key |
| 24 | YaCy | remote | all, files, datasets | yacy_url | needs_key |
| 25 | Wiby | remote | all, files | none | ready |
| 26 | Marginalia | remote | all, files | none | ready |
| 27 | Gigablast | remote | all | none | retired |
| 28 | Common Crawl Index | archive | files, datasets, opportunities, applications, exposed, all | none | ready |
| 29 | Wayback CDX | archive | files, datasets, opportunities, applications, exposed, all | none | ready |
| 30 | Internet Archive | archive | files, datasets, all | none | ready |
| 31 | Arquivo.pt | archive | files, all, opportunities | none | ready |
| 32 | Grants.gov | remote | opportunities, applications, all | none | ready |
| 33 | ReliefWeb Jobs | remote | opportunities, all | none | ready |
| 34 | ReliefWeb Reports | remote | files, opportunities, datasets, all | none | ready |
| 35 | EU Funding & Tenders | remote | opportunities, applications, all | none | ready |
| 36 | OpenAlex | remote | files, datasets, all | none | ready |
| 37 | Crossref | remote | files, all | none | ready |
| 38 | arXiv | remote | files, datasets, all | none | ready |
| 39 | DOAJ | remote | files, all | none | ready |
| 40 | PubMed | remote | files, all | none | ready |
| 41 | Semantic Scholar | remote | files, all | none | ready |
| 42 | CORE | remote | files, datasets | core_api_key | needs_key |
| 43 | Wikipedia | remote | all, opportunities | none | ready |
| 44 | Wikidata | remote | all, opportunities, datasets | none | ready |
| 45 | Open Library | remote | all, files | none | ready |
| 46 | Zenodo | remote | datasets, files, all | none | ready |
| 47 | Figshare | remote | datasets, files | none | ready |
| 48 | Data.gov | remote | datasets, files, all | none | ready |
| 49 | Data.gov.uk | remote | datasets, files, all | none | ready |
| 50 | EU Open Data | remote | datasets, files, all | none | ready |
| 51 | Data.gov.au | remote | datasets, files, all | none | ready |
| 52 | Open Canada | remote | datasets, files, all | none | ready |
| 53 | World Bank Documents | remote | files, datasets, opportunities | none | ready |
| 54 | World Bank Data | remote | datasets | none | ready |
| 55 | Hugging Face Datasets | remote | datasets, files | none | ready |
| 56 | CKAN Portal | remote | datasets, files, all | none | ready |
| 57 | GitHub | remote | all, exposed, datasets | none | ready |
| 58 | GitLab | remote | all, exposed, datasets | none | ready |
| 59 | Hacker News | remote | all, opportunities | none | ready |
| 60 | Stack Exchange | remote | all | none | ready |
| 61 | npm Registry | remote | all, exposed | none | ready |
| 62 | crates.io | remote | all, exposed | none | ready |
| 63 | Nighthawk Vault | core | all, files, opportunities, applications, datasets, exposed | none | local |
| 64 | Vault Deep Text | core | all, files, opportunities, datasets | none | local |
| 65 | Portal Universe | portal | all, opportunities, files, applications, datasets, exposed | none | ready |
| 66 | Dork Hand-off | portal | all, exposed, files, opportunities | none | ready |

## Crawl arsenal

| # | Engine | Role | Language | License | Probe |
|---|---|---|---|---|---|
| 1 | Crawlee | fetcher | TypeScript/Python | Apache-2.0 | installed |
| 2 | Scrapy | fetcher | Python | BSD-3 | installed |
| 3 | Playwright | browser | TS/Python | Apache-2.0 | missing |
| 4 | Puppeteer | browser | Node | Apache-2.0 | missing |
| 5 | Selenium | browser | Multi | Apache-2.0 | missing |
| 6 | Pyppeteer | browser | Python | MIT | missing |
| 7 | Splinter | browser | Python | BSD-3 | missing |
| 8 | MechanicalSoup | fetcher | Python | MIT | installed |
| 9 | Requests-HTML | browser | Python | MIT | missing |
| 10 | aiohttp | fetcher | Python | Apache-2.0 | installed |
| 11 | HTTPX | fetcher | Python | BSD-3 | installed |
| 12 | hrequests | fetcher | Python | MIT | installed |
| 13 | Cloudscraper | fetcher | Python | MIT | installed |
| 14 | Colly | fetcher | Go | Apache-2.0 | missing |
| 15 | Apache Nutch | fetcher | Java | Apache-2.0 | missing |
| 16 | Heritrix | fetcher | Java | Apache-2.0 | missing |
| 17 | StormCrawler | fetcher | Java | Apache-2.0 | missing |
| 18 | Brozzler | browser | Python | Apache-2.0 | missing |
| 19 | Browsertrix Crawler | browser | Node | AGPL-3.0 | missing |
| 20 | Warcprox | proxy | Python | GPL-3.0 | missing |
| 21 | Splash | browser | Python | BSD-3 | missing |
| 22 | Apify SDK | fetcher | Node | Apache-2.0 | missing |
| 23 | Gerapy | fetcher | Python | MIT | missing |
| 24 | Crawlab | fetcher | Go | BSD-3 | missing |
| 25 | Scrapyd | fetcher | Python | BSD-3 | missing |
| 26 | node-crawler | fetcher | Node | MIT | missing |
| 27 | SimpleCrawler | fetcher | Node | BSD-2 | missing |
| 28 | website-scraper | fetcher | Node | MIT | missing |
| 29 | X-Ray | fetcher | Node | MIT | missing |
| 30 | jsdom | parser | Node | MIT | missing |
| 31 | Cheerio | parser | Node | MIT | missing |
| 32 | Katana | cli | Go | MIT | missing |
| 33 | Hakrawler | cli | Go | MIT | missing |
| 34 | GoSpider | cli | Go | MIT | missing |
| 35 | Photon | cli | Python | GPL-3.0 | missing |
| 36 | gau (GetAllUrls) | seeder | Go | MIT | missing |
| 37 | waymore | seeder | Python | GPL-3.0 | missing |
| 38 | waybackpy | seeder | Python | MIT | installed |
| 39 | ffuf | cli | Go | Apache-2.0 | missing |
| 40 | feroxbuster | cli | Rust | MIT | missing |
| 41 | Gobuster | cli | Go | Apache-2.0 | missing |
| 42 | dirsearch | cli | Python | GPL-2.0 | missing |
| 43 | DIRB | cli | C | GPL-2.0 | missing |
| 44 | GNU Wget | cli | C | GPL-3.0 | missing |
| 45 | curl | cli | C | MIT | missing |
| 46 | aria2 | cli | C++ | GPL-2.0 | missing |
| 47 | HTTrack | cli | C | GPL-3.0 | missing |
| 48 | wpull | cli | Python | GPL-3.0 | missing |
| 49 | subfinder | seeder | Go | MIT | missing |
| 50 | Amass | seeder | Go | Apache-2.0 | missing |
| 51 | assetfinder | seeder | Go | MIT | missing |
| 52 | dnsx | seeder | Go | MIT | missing |
| 53 | theHarvester | seeder | Python | GPL-2.0 | missing |
| 54 | LinkFinder | cli | Python | MIT | missing |
| 55 | xnLinkFinder | cli | Python | GPL-3.0 | missing |
| 56 | Arjun | cli | Python | GPL-3.0 | missing |
| 57 | ParamSpider | cli | Python | MIT | missing |
| 58 | unfurl | seeder | Go | MIT | missing |
| 59 | sitemap-generator | seeder | Node | MIT | missing |
| 60 | Wget2 | cli | C | GPL-3.0 | missing |
| 61 | Trafilatura | extractor | Python | Apache-2.0 | installed |
| 62 | Readability-lxml | extractor | Python | Apache-2.0 | installed |
| 63 | JusText | extractor | Python | BSD-2 | installed |
| 64 | Newspaper3k | extractor | Python | MIT | installed |
| 65 | BoilerPy3 | extractor | Python | MIT | installed |
| 66 | html2text | extractor | Python | GPL-3.0 | installed |
| 67 | BeautifulSoup | parser | Python | MIT | installed |
| 68 | lxml | parser | Python | BSD-3 | installed |
| 69 | Parsel | parser | Python | BSD-3 | installed |
| 70 | Selectolax | parser | Python | MIT | installed |
| 71 | pyquery | parser | Python | BSD-3 | installed |
| 72 | Extruct | extractor | Python | BSD-3 | installed |
| 73 | feedparser | extractor | Python | BSD-2 | installed |
| 74 | w3lib | parser | Python | BSD-3 | installed |
| 75 | tldextract | parser | Python | BSD-3 | installed |
| 76 | charset-normalizer | parser | Python | MIT | installed |
| 77 | pypdf | files | Python | BSD-3 | installed |
| 78 | pdfminer.six | files | Python | MIT | installed |
| 79 | pdftotext (Poppler) | files | C++ | GPL-2.0 | missing |
| 80 | Tesseract OCR | files | C++ | Apache-2.0 | missing |
| 81 | OCRmyPDF | files | Python | MPL-2.0 | missing |
| 82 | Apache Tika | files | Java | Apache-2.0 | missing |
| 83 | warcio | files | Python | Apache-2.0 | installed |
| 84 | libarchive | files | C | BSD-2 | missing |
| 85 | openpyxl | files | Python | MIT | installed |
| 86 | python-docx | files | Python | MIT | installed |

## Portal universe

| # | Portal | Lenses | Domains |
|---|---|---|---|
| 1 | Grants.gov | opportunities, applications | grants.gov |
| 2 | EU Funding & Tenders | opportunities, applications | ec.europa.eu |
| 3 | TED — Tenders Electronic Daily | opportunities | ted.europa.eu |
| 4 | UNGM — UN Global Marketplace | opportunities | ungm.org |
| 5 | ReliefWeb | opportunities, files | reliefweb.int |
| 6 | UNjobs | opportunities | unjobs.org |
| 7 | UNDP Procurement | opportunities | undp.org |
| 8 | World Bank Procurement | opportunities, files | worldbank.org |
| 9 | SAM.gov | opportunities | sam.gov |
| 10 | Find a Tender (UK) | opportunities | find-tender.service.gov.uk |
| 11 | eTenders South Africa | opportunities | etenders.gov.za |
| 12 | CORDIS | opportunities, datasets, files | cordis.europa.eu |
| 13 | NSF Funding | opportunities | nsf.gov |
| 14 | NIH Grants | opportunities | grants.nih.gov |
| 15 | UKRI Opportunities | opportunities | ukri.org |
| 16 | Wellcome Funding | opportunities | wellcome.org |
| 17 | IDRC Funding | opportunities | idrc-crdi.ca |
| 18 | Gates Foundation Grants | opportunities | gatesfoundation.org |
| 19 | FundsforNGOs | opportunities | fundsforngos.org |
| 20 | Opportunity Desk | opportunities, applications | opportunitydesk.org |
| 21 | Scholars4Dev | opportunities, applications | scholars4dev.com |
| 22 | Idealist | opportunities | idealist.org |
| 23 | Devex | opportunities | devex.com |
| 24 | UN Careers | opportunities | careers.un.org |
| 25 | African Development Bank | opportunities, files | afdb.org |
| 26 | FCDO International Funding | opportunities, files | gov.uk |
| 27 | Echoing Green | opportunities, applications | echoinggreen.org |
| 28 | Y Combinator | opportunities, applications | ycombinator.com |
| 29 | World Bank Documents | files, datasets, opportunities | documents.worldbank.org, documents1.worldbank.org |
| 30 | World Bank Open Knowledge | files, datasets | openknowledge.worldbank.org |
| 31 | UN Digital Library | files, opportunities | digitallibrary.un.org, documents.un.org |
| 32 | WHO IRIS | files, datasets | iris.who.int |
| 33 | FAO Documents | files, datasets | fao.org |
| 34 | OECD | files, datasets | oecd.org |
| 35 | IMF Publications | files, datasets | imf.org |
| 36 | ILO | files, opportunities | ilo.org |
| 37 | UNHCR | files, opportunities | unhcr.org |
| 38 | Open Knowledge Repository | files, datasets | openknowledge.worldbank.org |
| 39 | BASE | files, datasets | base-search.net |
| 40 | CORE | files, datasets | core.ac.uk |
| 41 | OpenAIRE | files, datasets | openaire.eu |
| 42 | Data.gov | datasets, files | catalog.data.gov, data.gov |
| 43 | Data.gov.uk | datasets, files | data.gov.uk |
| 44 | EU Open Data Portal | datasets, files | data.europa.eu |
| 45 | Data.gov.au | datasets, files | data.gov.au |
| 46 | Open Canada | datasets, files | open.canada.ca |
| 47 | Hugging Face Datasets | datasets, files | huggingface.co |
| 48 | Zenodo | datasets, files | zenodo.org |
| 49 | Figshare | datasets, files | figshare.com |
| 50 | Dryad | datasets, files | datadryad.org |
| 51 | Common App | applications | commonapp.org |
| 52 | DAAD Scholarships | applications, opportunities | daad.de |
| 53 | Erasmus+ | applications, opportunities | erasmus-plus.ec.europa.eu |
| 54 | Voluntary Service / ESC | applications, opportunities | europa.eu |
