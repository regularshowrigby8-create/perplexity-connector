"""Query intelligence: turn plain language into operator-grade discovery plays."""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from urllib.parse import urlsplit

FILE_GROUPS: dict[str, tuple[str, ...]] = {
    "docs": ("pdf", "doc", "docx", "odt", "rtf", "txt", "md"),
    "sheets": ("xls", "xlsx", "csv", "ods", "tsv"),
    "slides": ("ppt", "pptx"),
    "data": ("json", "xml", "csv", "geojson", "kml", "rss"),
    "archives": ("zip", "tar", "gz", "7z", "rar"),
    "databases": ("sql", "db", "sqlite", "sqlite3", "mdb", "bak"),
    "configs": ("env", "yml", "yaml", "ini", "conf", "toml", "log"),
}

LENS_FILE_TYPES = {
    "files": ("pdf", "docx", "xlsx", "csv", "pptx", "zip", "json", "xml"),
    "datasets": ("csv", "json", "xlsx", "geojson", "xml", "zip"),
    "opportunities": ("pdf", "docx", "xlsx"),
    "applications": ("pdf", "docx"),
    "exposed": ("env", "bak", "sql", "db", "log", "json", "zip", "yml"),
    "all": ("pdf", "docx", "xlsx", "csv"),
}

OPPORTUNITY_TERMS = (
    '"call for proposals"', '"call for applications"', '"request for proposals"', "grant",
    "tender", "fellowship", "scholarship", "accelerator", '"open call"', "RFP",
    '"expression of interest"', "procurement", "bounty", '"applications open"',
)
APPLICATION_TERMS = (
    '"application form"', '"apply now"', '"applications close"', '"application deadline"',
    '"call for applications"', '"admissions"', '"apply by"', '"online application"',
)
EXPOSED_TERMS = (
    'intitle:"index of"', '"parent directory"', 'inurl:backup', 'inurl:.env',
    '"wp-config"', 'inurl:"/files/"', '"swagger"', 'inurl:api/v1', 'inurl:"/uploads/"',
)
DATASET_TERMS = ('dataset', '"open data"', 'CSV', '"download data"', '"data portal"')

INTENT_PATTERNS: list[tuple[str, str]] = [
    (r"\b(grant|funding|fund|financ|sponsor|subsidy|capital)\w*", "opportunities"),
    (r"\b(tender|procure|rfp|contract notice|bid)\w*", "opportunities"),
    (r"\b(fellowship|scholarship|bursary|residency|accelerator|incubator|cohort)\w*", "opportunities"),
    (r"\b(job|vacan|hiring|internship|position|career)\w*", "opportunities"),
    (r"\b(apply|application|admission|enrol|nominat)\w*", "applications"),
    (r"\b(pdf|docx?|xlsx?|csv|spreadsheet|dataset|report|document|paper|file)\w*", "files"),
    (r"\b(dataset|open data|database|statistic)\w*", "datasets"),
    (r"\b(index of|exposed|leak|backup|\.env|config|dump|directory listing)\b", "exposed"),
]

OPERATOR_RE = re.compile(r"\b(site|filetype|inurl|intitle|intext|ext|after|before):\s*([^\s]+)", re.I)


@dataclass
class Play:
    id: str
    label: str
    dork: str
    lens: str
    file_types: tuple[str, ...] = ()


@dataclass
class Plan:
    query: str
    terms: str
    lens: str
    site: str | None
    file_types: list[str]
    operators: dict[str, str]
    plays: list[Play] = field(default_factory=list)
    suggested_lens: str | None = None


def _strip_operators(text: str) -> tuple[str, dict[str, str]]:
    ops: dict[str, str] = {}

    def grab(m: re.Match[str]) -> str:
        ops[m.group(1).lower()] = m.group(2)
        return " "

    cleaned = OPERATOR_RE.sub(grab, text)
    return re.sub(r"\s{2,}", " ", cleaned).strip(), ops


def infer_lens(text: str) -> str | None:
    scores: dict[str, int] = {}
    low = text.lower()
    for pattern, lens in INTENT_PATTERNS:
        hits = len(re.findall(pattern, low))
        if hits:
            scores[lens] = scores.get(lens, 0) + hits
    if not scores:
        return None
    return max(scores.items(), key=lambda kv: kv[1])[0]


def _site_from_text(text: str) -> str | None:
    if re.search(r"https?://", text):
        try:
            host = urlsplit(text if text.startswith("http") else "https://" + text).hostname
            if host and "." in host:
                return host.removeprefix("www.")
        except ValueError:
            return None
    return None


def _or(terms: tuple[str, ...]) -> str:
    return "(" + " OR ".join(terms) + ")"


def _filetype_or(exts: tuple[str, ...]) -> str:
    return "(" + " OR ".join(f"filetype:{e}" for e in exts) + ")"


def build_plan(raw_query: str, lens: str = "all", site: str | None = None,
               file_types: list[str] | None = None, limit_site: bool = True) -> Plan:
    query, ops = _strip_operators(raw_query.strip())
    site = site or ops.get("site") or _site_from_text(query)
    suggested = infer_lens(query) if lens == "all" else None
    effective = lens if lens != "all" else (suggested or "all")

    exts = [e.lower().lstrip(".") for e in (file_types or []) if e]
    if not exts:
        if "filetype" in ops:
            exts = [ops["filetype"].lower().lstrip(".")]
        else:
            exts = list(LENS_FILE_TYPES.get(effective, LENS_FILE_TYPES["all"]))

    base = query
    if site and site.lower() not in query.lower():
        base = f"{query} site:{site}".strip()

    plays: list[Play] = []

    def add(pid: str, label: str, dork: str, play_lens: str, ftypes: tuple[str, ...] = ()) -> None:
        if dork and all(p.id != pid for p in plays):
            plays.append(Play(pid, label, dork, play_lens, ftypes))

    if effective in ("files", "datasets", "all"):
        add("files-core", "Document sweep", f"{base} {_filetype_or(tuple(exts[:8]))}", effective, tuple(exts[:8]))
        add("files-deep", "Deep paths (uploads, archives, assets)",
            f'{base} {_filetype_or(tuple(exts[:4]))} (inurl:upload OR inurl:files OR inurl:documents OR inurl:download OR inurl:archive)',
            effective, tuple(exts[:4]))
    if effective == "datasets":
        add("datasets-open", "Open-data tables", f'{base} {_or(DATASET_TERMS)} {_filetype_or(("csv", "xlsx", "json", "geojson"))}', "datasets")
        add("datasets-catalog", "Catalogue entries", f'{base} (inurl:catalog OR inurl:dataset OR inurl:data-portal) ("download" OR "resources")', "datasets")
    if effective in ("opportunities", "all"):
        add("opps-calls", "Funding calls & open applications",
            f'{base} {_or(OPPORTUNITY_TERMS)}', "opportunities")
        add("opps-deadline", "Live deadlines",
            f'{base} ("deadline" OR "closes" OR "apply by" OR "applications close") {_filetype_or(("pdf", "docx"))}', "opportunities")
    if effective in ("applications", "all"):
        add("apps-forms", "Application forms & portals",
            f'{base} {_or(APPLICATION_TERMS)}', "applications")
        add("apps-pack", "Application packs",
            f'{base} ("guidelines" OR "eligibility" OR "terms of reference") {_filetype_or(("pdf", "docx"))}', "applications")
    if effective == "exposed":
        add("exposed-index", "Open directory listings", f'{base} {_or(EXPOSED_TERMS[:2])}', "exposed")
        add("exposed-files", "Exposed archives & configs",
            f'{base} {_filetype_or(("env", "bak", "sql", "zip", "log", "yml"))} (inurl:backup OR inurl:dump OR inurl:old OR inurl:private)', "exposed")
    if not plays:
        add("general", "General web sweep", base, effective)

    if limit_site and site:
        for play in plays:
            if "site:" not in play.dork:
                play.dork = f"{play.dork} site:{site}"

    return Plan(query=query, terms=query, lens=effective, site=site, file_types=exts,
                operators=ops, plays=plays, suggested_lens=suggested)


def dork_launch_links(dork: str) -> list[tuple[str, str]]:
    from urllib.parse import quote_plus

    q = quote_plus(dork)
    return [
        ("Google", f"https://www.google.com/search?q={q}"),
        ("Bing", f"https://www.bing.com/search?q={q}"),
        ("DuckDuckGo", f"https://duckduckgo.com/?q={q}"),
        ("Brave", f"https://search.brave.com/search?q={q}"),
        ("Yandex", f"https://yandex.com/search/?text={q}"),
        ("Mojeek", f"https://www.mojeek.com/search?q={q}"),
    ]
