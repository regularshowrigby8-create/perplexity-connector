"""The Crawler Arsenal: 60+ independent crawl / parse / extract engines.

Nothing here is simulated. Each entry is a real project with a real probe:
Python engines are imported, native binaries are looked up on PATH. The fusion
crawler then dispatches to whatever is present and records which engine produced
each artefact. Missing engines are reported honestly instead of failing silently.
"""
from __future__ import annotations

import importlib.util
import shutil
from dataclasses import dataclass, field
from functools import lru_cache


@dataclass(frozen=True)
class EngineSpec:
    id: str
    name: str
    role: str            # seeder | fetcher | parser | extractor | files | cli | proxy | browser
    language: str
    homepage: str
    license: str = ""
    probe: str = ""      # python module or binary name
    kind: str = "python"  # python | binary | node | java | service
    command: str = ""    # for CLI engines: template with {target} {out}
    note: str = ""
    tiers: tuple[str, ...] = ("crawl",)


ENGINES: tuple[EngineSpec, ...] = (
    # ---------------------------------------------------------------- frameworks
    EngineSpec("crawlee", "Crawlee", "fetcher", "TypeScript/Python", "https://crawlee.dev/", "Apache-2.0", "crawlee"),
    EngineSpec("scrapy", "Scrapy", "fetcher", "Python", "https://scrapy.org/", "BSD-3", "scrapy"),
    EngineSpec("playwright", "Playwright", "browser", "TS/Python", "https://playwright.dev/", "Apache-2.0", "playwright", kind="python"),
    EngineSpec("puppeteer", "Puppeteer", "browser", "Node", "https://pptr.dev/", "Apache-2.0", "puppeteer", kind="node"),
    EngineSpec("selenium", "Selenium", "browser", "Multi", "https://www.selenium.dev/", "Apache-2.0", "selenium"),
    EngineSpec("pyppeteer", "Pyppeteer", "browser", "Python", "https://github.com/pyppeteer/pyppeteer", "MIT", "pyppeteer"),
    EngineSpec("splinter", "Splinter", "browser", "Python", "https://splinter.readthedocs.io/", "BSD-3", "splinter"),
    EngineSpec("mechanicalsoup", "MechanicalSoup", "fetcher", "Python", "https://mechanicalsoup.readthedocs.io/", "MIT", "mechanicalsoup"),
    EngineSpec("requests-html", "Requests-HTML", "browser", "Python", "https://requests-html.kennethreitz.org/", "MIT", "requests_html"),
    EngineSpec("aiohttp", "aiohttp", "fetcher", "Python", "https://docs.aiohttp.org/", "Apache-2.0", "aiohttp"),
    EngineSpec("httpx", "HTTPX", "fetcher", "Python", "https://www.python-httpx.org/", "BSD-3", "httpx"),
    EngineSpec("hrequests", "hrequests", "fetcher", "Python", "https://github.com/daijro/hrequests", "MIT", "hrequests"),
    EngineSpec("cloudscraper", "Cloudscraper", "fetcher", "Python", "https://github.com/VeNoMouS/cloudscraper", "MIT", "cloudscraper"),
    EngineSpec("colly", "Colly", "fetcher", "Go", "https://go-colly.org/", "Apache-2.0", "", kind="binary"),
    EngineSpec("nutch", "Apache Nutch", "fetcher", "Java", "https://nutch.apache.org/", "Apache-2.0", "nutch", kind="binary"),
    EngineSpec("heritrix", "Heritrix", "fetcher", "Java", "https://github.com/internetarchive/heritrix3", "Apache-2.0", "heritrix", kind="binary"),
    EngineSpec("stormcrawler", "StormCrawler", "fetcher", "Java", "https://stormcrawler.apache.org/", "Apache-2.0", "", kind="java"),
    EngineSpec("brozzler", "Brozzler", "browser", "Python", "https://github.com/internetarchive/brozzler", "Apache-2.0", "brozzler"),
    EngineSpec("browsertrix", "Browsertrix Crawler", "browser", "Node", "https://github.com/webrecorder/browsertrix-crawler", "AGPL-3.0", "browsertrix-crawler", kind="binary"),
    EngineSpec("warcprox", "Warcprox", "proxy", "Python", "https://github.com/internetarchive/warcprox", "GPL-3.0", "warcprox"),
    EngineSpec("splash", "Splash", "browser", "Python", "https://github.com/scrapinghub/splash", "BSD-3", "", kind="service", note="needs Splash server"),
    EngineSpec("apify", "Apify SDK", "fetcher", "Node", "https://apify.com/", "Apache-2.0", "apify", kind="node"),
    EngineSpec("gerapy", "Gerapy", "fetcher", "Python", "https://github.com/Gerapy/Gerapy", "MIT", "gerapy"),
    EngineSpec("crawlab", "Crawlab", "fetcher", "Go", "https://github.com/crawlab-team/crawlab", "BSD-3", "crawlab", kind="binary"),
    EngineSpec("scrapyd", "Scrapyd", "fetcher", "Python", "https://github.com/scrapy/scrapyd", "BSD-3", "scrapyd"),
    EngineSpec("node-crawler", "node-crawler", "fetcher", "Node", "https://github.com/bda-research/node-crawler", "MIT", "", kind="node"),
    EngineSpec("simplecrawler", "SimpleCrawler", "fetcher", "Node", "https://github.com/simplecrawler/simplecrawler", "BSD-2", "", kind="node"),
    EngineSpec("website-scraper", "website-scraper", "fetcher", "Node", "https://github.com/website-scraper/node-website-scraper", "MIT", "", kind="node"),
    EngineSpec("xray", "X-Ray", "fetcher", "Node", "https://github.com/matthewmueller/x-ray", "MIT", "", kind="node"),
    EngineSpec("jsdom", "jsdom", "parser", "Node", "https://github.com/jsdom/jsdom", "MIT", "", kind="node"),
    EngineSpec("cheerio", "Cheerio", "parser", "Node", "https://cheerio.js.org/", "MIT", "", kind="node"),

    # ---------------------------------------------------------------- CLI raiders
    EngineSpec("katana", "Katana", "cli", "Go", "https://github.com/projectdiscovery/katana", "MIT", "katana",
               command="katana -u {target} -silent -nc -jc -d 3 -timeout 8"),
    EngineSpec("hakrawler", "Hakrawler", "cli", "Go", "https://github.com/hakluke/hakrawler", "MIT", "hakrawler",
               command="hakrawler -url {target} -depth 3 -plain"),
    EngineSpec("gospider", "GoSpider", "cli", "Go", "https://github.com/jaeles-project/gospider", "MIT", "gospider",
               command="gospider -s {target} -d 3 -t 5 -q"),
    EngineSpec("photon", "Photon", "cli", "Python", "https://github.com/s0md3v/Photon", "GPL-3.0", "photon",
               command="python3 -m photon -u {target} -o {out} -t 10"),
    EngineSpec("gau", "gau (GetAllUrls)", "seeder", "Go", "https://github.com/lc/gau", "MIT", "gau",
               command="gau --subs {host} --threads 5"),
    EngineSpec("waymore", "waymore", "seeder", "Python", "https://github.com/xnl-h4ck3r/waymore", "GPL-3.0", "waymore",
               command="waymore -i {host} -mode U -oU {out}"),
    EngineSpec("waybackpy", "waybackpy", "seeder", "Python", "https://github.com/akamhy/waybackpy", "MIT", "waybackpy"),
    EngineSpec("ffuf", "ffuf", "cli", "Go", "https://github.com/ffuf/ffuf", "Apache-2.0", "ffuf",
               command="ffuf -u {target}/FUZZ -w {wordlist} -mc 200,301,302,403 -s", note="needs wordlist"),
    EngineSpec("feroxbuster", "feroxbuster", "cli", "Rust", "https://github.com/epi052/feroxbuster", "MIT", "feroxbuster",
               command="feroxbuster -u {target} --depth 2 --quiet --no-state", note="needs wordlist"),
    EngineSpec("gobuster", "Gobuster", "cli", "Go", "https://github.com/OJ/gobuster", "Apache-2.0", "gobuster",
               command="gobuster dir -u {target} -w {wordlist} -q", note="needs wordlist"),
    EngineSpec("dirsearch", "dirsearch", "cli", "Python", "https://github.com/maurosoria/dirsearch", "GPL-2.0", "dirsearch",
               command="dirsearch -u {target} -q --format=plain"),
    EngineSpec("dirb", "DIRB", "cli", "C", "https://github.com/v0re/dirb", "GPL-2.0", "dirb",
               command="dirb {target} -S -r"),
    EngineSpec("wget", "GNU Wget", "cli", "C", "https://www.gnu.org/software/wget/", "GPL-3.0", "wget",
               command="wget --spider -r -nd -l 2 -nv {target}"),
    EngineSpec("curl", "curl", "cli", "C", "https://curl.se/", "MIT", "curl",
               command="curl -sSL --max-time 10 {target}"),
    EngineSpec("aria2c", "aria2", "cli", "C++", "https://aria2.github.io/", "GPL-2.0", "aria2c",
               command="aria2c -x4 -j4 --dry-run=true {target}"),
    EngineSpec("httrack", "HTTrack", "cli", "C", "https://www.httrack.com/", "GPL-3.0", "httrack",
               command="httrack {target} -O {out} -r3 -%v"),
    EngineSpec("wpull", "wpull", "cli", "Python", "https://github.com/ArchiveTeam/wpull", "GPL-3.0", "wpull",
               command="wpull {target} --no-robots --output {out}"),
    EngineSpec("subfinder", "subfinder", "seeder", "Go", "https://github.com/projectdiscovery/subfinder", "MIT", "subfinder",
               command="subfinder -d {host} -silent"),
    EngineSpec("amass", "Amass", "seeder", "Go", "https://github.com/owasp-amass/amass", "Apache-2.0", "amass",
               command="amass enum -passive -d {host} -silent"),
    EngineSpec("assetfinder", "assetfinder", "seeder", "Go", "https://github.com/tomnomnom/assetfinder", "MIT", "assetfinder",
               command="assetfinder --subs-only {host}"),
    EngineSpec("dnsx", "dnsx", "seeder", "Go", "https://github.com/projectdiscovery/dnsx", "MIT", "dnsx",
               command="dnsx -silent -a -resp -d {host}"),
    EngineSpec("theharvester", "theHarvester", "seeder", "Python", "https://github.com/laramies/theHarvester", "GPL-2.0", "theHarvester",
               command="theHarvester -d {host} -b duckduckgo,bing -l 200", note="needs API keys upstream"),
    EngineSpec("linkfinder", "LinkFinder", "cli", "Python", "https://github.com/GerbenJavado/LinkFinder", "MIT", "linkfinder",
               command="python3 linkfinder.py -i {target} -o cli -d"),
    EngineSpec("xnlinkfinder", "xnLinkFinder", "cli", "Python", "https://github.com/xnl-h4ck3r/xnLinkFinder", "GPL-3.0", "xnLinkFinder",
               command="xnLinkFinder -i {target} -sf {host} -o {out}"),
    EngineSpec("arjun", "Arjun", "cli", "Python", "https://github.com/s0md3v/Arjun", "GPL-3.0", "arjun",
               command="arjun -u {target} -oT {out} -q"),
    EngineSpec("paramspider", "ParamSpider", "cli", "Python", "https://github.com/devanshbatham/ParamSpider", "MIT", "paramspider",
               command="paramspider -d {host} --quiet -o {out}"),
    EngineSpec("unfurl", "unfurl", "seeder", "Go", "https://github.com/tomnomnom/unfurl", "MIT", "unfurl",
               command="unfurl domains < {target}"),
    EngineSpec("gospider-sitemap", "sitemap-generator", "seeder", "Node", "https://github.com/lgraubner/sitemap-generator", "MIT", "", kind="node"),
    EngineSpec("wget2", "Wget2", "cli", "C", "https://gitlab.com/gnuwget/wget2", "GPL-3.0", "wget2",
               command="wget2 --spider -r -l 2 {target}"),

    # ---------------------------------------------------------------- extractors
    EngineSpec("trafilatura", "Trafilatura", "extractor", "Python", "https://trafilatura.readthedocs.io/", "Apache-2.0", "trafilatura"),
    EngineSpec("readability", "Readability-lxml", "extractor", "Python", "https://github.com/buriy/python-readability", "Apache-2.0", "readability"),
    EngineSpec("justext", "JusText", "extractor", "Python", "https://github.com/miso-belica/jusText", "BSD-2", "justext"),
    EngineSpec("newspaper", "Newspaper3k", "extractor", "Python", "https://github.com/codelucas/newspaper", "MIT", "newspaper"),
    EngineSpec("boilerpy3", "BoilerPy3", "extractor", "Python", "https://github.com/jmriebold/BoilerPy3", "MIT", "boilerpy3"),
    EngineSpec("html2text", "html2text", "extractor", "Python", "https://github.com/Alir3z4/html2text", "GPL-3.0", "html2text"),
    EngineSpec("bs4", "BeautifulSoup", "parser", "Python", "https://www.crummy.com/software/BeautifulSoup/", "MIT", "bs4"),
    EngineSpec("lxml", "lxml", "parser", "Python", "https://lxml.de/", "BSD-3", "lxml"),
    EngineSpec("parsel", "Parsel", "parser", "Python", "https://github.com/scrapy/parsel", "BSD-3", "parsel"),
    EngineSpec("selectolax", "Selectolax", "parser", "Python", "https://github.com/rushter/selectolax", "MIT", "selectolax"),
    EngineSpec("pyquery", "pyquery", "parser", "Python", "https://pythonhosted.org/pyquery/", "BSD-3", "pyquery"),
    EngineSpec("extruct", "Extruct", "extractor", "Python", "https://github.com/scrapinghub/extruct", "BSD-3", "extruct"),
    EngineSpec("feedparser", "feedparser", "extractor", "Python", "https://github.com/kurtmckee/feedparser", "BSD-2", "feedparser"),
    EngineSpec("w3lib", "w3lib", "parser", "Python", "https://github.com/scrapy/w3lib", "BSD-3", "w3lib"),
    EngineSpec("tldextract", "tldextract", "parser", "Python", "https://github.com/john-kurkowski/tldextract", "BSD-3", "tldextract"),
    EngineSpec("chardet", "charset-normalizer", "parser", "Python", "https://github.com/Ousret/charset_normalizer", "MIT", "charset_normalizer"),
    EngineSpec("pypdf", "pypdf", "files", "Python", "https://pypdf.readthedocs.io/", "BSD-3", "pypdf"),
    EngineSpec("pdfminer", "pdfminer.six", "files", "Python", "https://github.com/pdfminer/pdfminer.six", "MIT", "pdfminer"),
    EngineSpec("pdftotext", "pdftotext (Poppler)", "files", "C++", "https://poppler.freedesktop.org/", "GPL-2.0", "pdftotext",
               kind="binary", command="pdftotext -layout {target} -"),
    EngineSpec("tesseract", "Tesseract OCR", "files", "C++", "https://github.com/tesseract-ocr/tesseract", "Apache-2.0", "tesseract",
               kind="binary", command="tesseract {target} -"),
    EngineSpec("ocrmypdf", "OCRmyPDF", "files", "Python", "https://github.com/ocrmypdf/OCRmyPDF", "MPL-2.0", "ocrmypdf"),
    EngineSpec("tika", "Apache Tika", "files", "Java", "https://tika.apache.org/", "Apache-2.0", "", kind="service",
               note="needs Tika server on :9998"),
    EngineSpec("warcio", "warcio", "files", "Python", "https://github.com/webrecorder/warcio", "Apache-2.0", "warcio"),
    EngineSpec("libarchive", "libarchive", "files", "C", "https://libarchive.org/", "BSD-2", "bsdtar", kind="binary",
               command="bsdtar -tf {target}"),
    EngineSpec("openpyxl", "openpyxl", "files", "Python", "https://openpyxl.readthedocs.io/", "MIT", "openpyxl",
               note="XLSX text extraction"),
    EngineSpec("python-docx", "python-docx", "files", "Python", "https://python-docx.readthedocs.io/", "MIT", "docx",
               note="DOCX text extraction"),
)

BY_ID = {e.id: e for e in ENGINES}


@lru_cache(maxsize=1)
def probe_all() -> tuple[dict, ...]:
    out: list[dict] = []
    for spec in ENGINES:
        available = False
        detail = ""
        if spec.kind == "python":
            if spec.probe:
                try:
                    available = importlib.util.find_spec(spec.probe) is not None
                except (ImportError, ValueError):
                    available = False
                detail = "module imported" if available else "not installed"
        elif spec.kind in ("binary", "node", "java"):
            path = shutil.which(spec.probe) if spec.probe else None
            available = bool(path)
            detail = path or "not on PATH"
        else:
            available = False
            detail = spec.note or "external service"
        out.append({
            "id": spec.id, "name": spec.name, "role": spec.role, "language": spec.language,
            "homepage": spec.homepage, "license": spec.license, "kind": spec.kind,
            "available": available, "detail": detail, "note": spec.note,
            "command": spec.command,
        })
    return tuple(out)


def available_ids() -> set[str]:
    return {row["id"] for row in probe_all() if row["available"]}


def summary() -> dict:
    rows = probe_all()
    roles: dict[str, int] = {}
    ready: dict[str, int] = {}
    for row in rows:
        roles[row["role"]] = roles.get(row["role"], 0) + 1
        if row["available"]:
            ready[row["role"]] = ready.get(row["role"], 0) + 1
    return {
        "total": len(rows),
        "available": sum(1 for r in rows if r["available"]),
        "by_role": [{"role": k, "total": v, "available": ready.get(k, 0)}
                    for k, v in sorted(roles.items())],
    }
