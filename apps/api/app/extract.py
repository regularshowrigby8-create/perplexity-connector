"""URL forensics, file fingerprinting, deadline extraction and obscurity scoring."""
from __future__ import annotations

import re
import urllib.parse
from datetime import date, datetime, timezone
from typing import Iterable

from dateutil import parser as dateparser

from .models import Deadline

# --------------------------------------------------------------------------- files

FILE_MAP: dict[str, tuple[str, str]] = {
    # ext: (kind, mime)
    "pdf": ("document", "application/pdf"),
    "doc": ("document", "application/msword"),
    "docx": ("document", "application/vnd.openxmlformats-officedocument.wordprocessingml.document"),
    "odt": ("document", "application/vnd.oasis.opendocument.text"),
    "rtf": ("document", "application/rtf"),
    "txt": ("document", "text/plain"),
    "md": ("document", "text/markdown"),
    "xls": ("spreadsheet", "application/vnd.ms-excel"),
    "xlsx": ("spreadsheet", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"),
    "ods": ("spreadsheet", "application/vnd.oasis.opendocument.spreadsheet"),
    "csv": ("dataset", "text/csv"),
    "tsv": ("dataset", "text/tab-separated-values"),
    "ppt": ("presentation", "application/vnd.ms-powerpoint"),
    "pptx": ("presentation", "application/vnd.openxmlformats-officedocument.presentationml.presentation"),
    "json": ("data", "application/json"),
    "geojson": ("dataset", "application/geo+json"),
    "xml": ("data", "application/xml"),
    "yaml": ("config", "application/yaml"),
    "yml": ("config", "application/yaml"),
    "sql": ("database", "application/sql"),
    "db": ("database", "application/octet-stream"),
    "sqlite": ("database", "application/vnd.sqlite3"),
    "sqlite3": ("database", "application/vnd.sqlite3"),
    "mdb": ("database", "application/x-msaccess"),
    "zip": ("archive", "application/zip"),
    "tar": ("archive", "application/x-tar"),
    "gz": ("archive", "application/gzip"),
    "tgz": ("archive", "application/gzip"),
    "7z": ("archive", "application/x-7z-compressed"),
    "rar": ("archive", "application/vnd.rar"),
    "bak": ("backup", "application/octet-stream"),
    "backup": ("backup", "application/octet-stream"),
    "old": ("backup", "application/octet-stream"),
    "log": ("log", "text/plain"),
    "env": ("config", "text/plain"),
    "ini": ("config", "text/plain"),
    "conf": ("config", "text/plain"),
    "cfg": ("config", "text/plain"),
    "toml": ("config", "text/plain"),
    "pem": ("key", "application/x-pem-file"),
    "key": ("key", "application/octet-stream"),
    "ovpn": ("config", "application/x-openvpn-profile"),
    "sh": ("script", "application/x-sh"),
    "py": ("script", "text/x-python"),
    "js": ("script", "text/javascript"),
    "php": ("script", "application/x-httpd-php"),
    "rss": ("feed", "application/rss+xml"),
    "atom": ("feed", "application/atom+xml"),
    "kml": ("dataset", "application/vnd.google-earth.kml+xml"),
    "epub": ("document", "application/epub+zip"),
    "mp4": ("video", "video/mp4"),
    "webm": ("video", "video/webm"),
    "mp3": ("audio", "audio/mpeg"),
    "png": ("image", "image/png"),
    "jpg": ("image", "image/jpeg"),
    "jpeg": ("image", "image/jpeg"),
    "gif": ("image", "image/gif"),
    "svg": ("image", "image/svg+xml"),
    "webp": ("image", "image/webp"),
}

FILE_TYPES = [
    "pdf", "docx", "doc", "xlsx", "xls", "csv", "pptx", "ppt", "json", "xml",
    "zip", "sql", "env", "bak", "log", "txt", "md", "sqlite", "db", "geojson", "rss",
]

_PILLAR_EXT = {
    "pdf", "doc", "docx", "xls", "xlsx", "csv", "ppt", "pptx", "odt", "ods",
    "zip", "7z", "tar", "gz", "sql", "sqlite", "db", "bak", "env", "log",
}

TRACKING = re.compile(
    r"^(utm_[a-z]+|fbclid|gclid|dclid|msclkid|mc_cid|mc_eid|ref|ref_src|referrer|"
    r"source|spm|igshid|yclid|_ga|_gl|pk_campaign|pk_kwd|ck_subscriber_id)$",
    re.I,
)


def path_ext(url: str) -> str | None:
    try:
        path = urllib.parse.urlsplit(url).path
    except ValueError:
        return None
    name = path.rsplit("/", 1)[-1]
    if "." not in name:
        return None
    ext = name.rsplit(".", 1)[-1].lower()
    if ext and len(ext) <= 8 and ext.isalnum():
        return ext
    return None


def fingerprint(url: str) -> tuple[str | None, str, str, str | None]:
    """Return (ext, kind, mime, domain)."""
    ext = path_ext(url)
    domain = safe_domain(url)
    if ext and ext in FILE_MAP:
        kind, mime = FILE_MAP[ext]
        return ext, kind, mime, domain
    return ext, "page", "text/html", domain


def safe_domain(url: str) -> str:
    try:
        host = urllib.parse.urlsplit(url).hostname or ""
        return host.lower().removeprefix("www.")
    except ValueError:
        return ""


def canonical_url(url: str) -> str:
    """Dedupe key: strip trackers, normalise scheme/host, sort params, drop fragments."""
    try:
        parts = urllib.parse.urlsplit(url.strip())
    except ValueError:
        return url.strip()
    if not parts.scheme:
        parts = urllib.parse.urlsplit("https://" + url.strip())
    host = (parts.hostname or "").lower().removeprefix("www.")
    port = parts.port
    scheme = "https" if parts.scheme in ("http", "https") else parts.scheme
    netloc = host if not port or port in (80, 443) else f"{host}:{port}"
    query = [(k, v) for k, v in urllib.parse.parse_qsl(parts.query, keep_blank_values=True)
             if not TRACKING.match(k)]
    query.sort()
    path = re.sub(r"/{2,}", "/", parts.path or "/")
    if path != "/":
        path = path.rstrip("/")
    qs = urllib.parse.urlencode(query)
    return urllib.parse.urlunsplit((scheme, netloc, path, qs, ""))


def pretty_name(url: str) -> str:
    """Human title from a file URL: last segment, de-slugged."""
    try:
        path = urllib.parse.urlsplit(url).path
    except ValueError:
        path = url
    name = urllib.parse.unquote(path.rstrip("/").rsplit("/", 1)[-1]) or safe_domain(url)
    name = re.sub(r"\.(pdf|docx?|xlsx?|pptx?|csv|json|xml|zip|sql|env|bak|log|txt|md|sqlite3?|db)$", "", name, flags=re.I)
    name = re.sub(r"[_+]+", " ", name)
    name = re.sub(r"[-.]+", " ", name)
    name = re.sub(r"\s{2,}", " ", name).strip()
    if name.isdigit():
        return f"Unnamed file on {safe_domain(url)}"
    return name[:180] or safe_domain(url)


def human_size(n: int | str | None) -> str | None:
    try:
        size = int(n)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None
    if size <= 0:
        return None
    for unit in ("B", "KB", "MB", "GB"):
        if size < 1024 or unit == "GB":
            return f"{size:.0f} {unit}" if unit == "B" else f"{size:.1f} {unit}"
        size /= 1024
    return None


# ----------------------------------------------------------------------- deadlines

_MONTH = r"(?:jan|feb|mar|apr|may|jun|jul|aug|sep|sept|oct|nov|dec)[a-z]*"
DATE_PATTERNS = [
    re.compile(rf"\b(\d{{1,2}}\s+{_MONTH}\.?\s+\d{{4}})\b", re.I),
    re.compile(rf"\b({_MONTH}\.?\s+\d{{1,2}},?\s+\d{{4}})\b", re.I),
    re.compile(r"\b(\d{4}-\d{2}-\d{2})\b"),
    re.compile(r"\b(\d{1,2}/\d{1,2}/\d{2,4})\b"),
    re.compile(rf"\b(\d{{1,2}}\s+{_MONTH})\b", re.I),
]
DEADLINE_WORDS = re.compile(
    r"(deadline|closes?|closing|apply by|applications? (?:close|due|open)|submissions? (?:close|due|until)|"
    r"due (?:date|by)|open until|no later than|cut[- ]?off|last date|expires?|end date|until)",
    re.I,
)


def _urgency(days: int) -> str:
    if days < 0:
        return "closed"
    if days == 0:
        return "today"
    if days <= 14:
        return "soon"
    if days <= 60:
        return "upcoming"
    return "later"


def _parse_date(raw: str, default_year: int) -> date | None:
    text = raw.replace(".", " ").strip()
    try:
        dt = dateparser.parse(text, fuzzy=True, default=datetime(default_year, 1, 1))
    except (ValueError, OverflowError, TypeError):
        return None
    if dt is None:
        return None
    return dt.date()


def find_deadline(text: str, explicit: str | None = None, today: date | None = None) -> Deadline | None:
    """Pull the most plausible closing date out of a snippet or structured field."""
    today = today or datetime.now(timezone.utc).date()
    if explicit:
        when = _parse_date(str(explicit)[:40], today.year)
        if when:
            days = (when - today).days
            return Deadline(date=when.isoformat(), days_left=days, phrase=str(explicit)[:80],
                            urgency=_urgency(days))  # type: ignore[arg-type]
    if not text:
        return None
    best: Deadline | None = None
    for sentence in re.split(r"(?<=[.;!?])\s+|\n", text):
        if not DEADLINE_WORDS.search(sentence):
            continue
        for pat in DATE_PATTERNS:
            for match in pat.finditer(sentence):
                when = _parse_date(match.group(1), today.year)
                if not when:
                    continue
                days = (when - today).days
                if days < -400 or days > 540:
                    continue
                cand = Deadline(date=when.isoformat(), days_left=days,
                                phrase=sentence.strip()[:140], urgency=_urgency(days))  # type: ignore[arg-type]
                if best is None or abs(cand.days_left) < abs(best.days_left):
                    best = cand
    return best


# ------------------------------------------------------------------------- depth

MAINSTREAM = {
    "google.com", "youtube.com", "facebook.com", "wikipedia.org", "twitter.com", "x.com",
    "instagram.com", "linkedin.com", "reddit.com", "amazon.com", "apple.com", "microsoft.com",
    "bing.com", "yahoo.com", "pinterest.com", "medium.com", "quora.com", "tiktok.com",
    "netflix.com", "spotify.com", "github.com", "stackoverflow.com", "nytimes.com", "bbc.co.uk",
    "cnn.com", "forbes.com", "wordpress.com", "blogspot.com", "tumblr.com", "scribd.com",
}

DEEP_WORDS = re.compile(
    r"(upload|uploads|files?|docs?|documents?|downloads?|archive|backup|backups|private|"
    r"internal|data|dataset|export|dump|attachments?|media|assets|public|static|storage|"
    r"wp-content|sites/default/files|system/files)",
    re.I,
)

OPPORTUNITY_WORDS = re.compile(
    r"(grant|funding|fund|tender|procurement|rfp|rfi|call for (proposals?|applications?|entries|papers?)|"
    r"fellowship|scholarship|bursary|accelerator|incubator|residency|prize|award|competition|"
    r"hackathon|bounty|contract|vacanc|job|recruit|internship|apply|application|submission|"
    r"eligib|awardee|opportunit|open call|expression of interest|eoi)",
    re.I,
)


def opportunity_tags(text: str) -> list[str]:
    tags: list[str] = []
    mapping = {
        "grant": r"\bgrant",
        "tender": r"\btender|procurement|\brfp\b|\brfi\b|contract notice",
        "fellowship": r"fellowship|residency",
        "scholarship": r"scholarship|bursary|tuition",
        "accelerator": r"accelerator|incubator|cohort",
        "job": r"vacanc|job|recruit|hiring|internship|position",
        "call": r"call for|open call|expression of interest",
        "prize": r"prize|award|competition|challenge",
        "bounty": r"bounty|bug bounty|reward",
        "deadline": r"deadline|closes|apply by|due",
    }
    for tag, pat in mapping.items():
        if re.search(pat, text, re.I):
            tags.append(tag)
    return tags


def depth_score(url: str, ext: str | None, archive: bool, text: str = "") -> int:
    """How far below the surface this result lives. 0 = front page, 100 = buried."""
    score = 0
    domain = safe_domain(url)
    try:
        parts = urllib.parse.urlsplit(url)
    except ValueError:
        return 0
    path = parts.path

    if archive:
        score += 30
    if ext and ext in FILE_MAP:
        score += 15
        if ext in _PILLAR_EXT:
            score += 12
        if ext in {"sql", "db", "sqlite", "bak", "env", "log", "pem", "key"}:
            score += 14
    if DEEP_WORDS.search(path):
        score += 8
    segments = [s for s in path.split("/") if s]
    score += min(len(segments) * 3, 15)
    if parts.query and re.search(r"(id|file|doc|download|attach|token|key)=", parts.query, re.I):
        score += 6
    if domain in MAINSTREAM or any(domain.endswith("." + m) for m in MAINSTREAM):
        score -= 12
    else:
        score += 8
    tld = domain.rsplit(".", 1)[-1] if "." in domain else ""
    if tld in {"gov", "mil", "int"} or tld.startswith("gov.") or ".gov." in domain:
        score += 6
    elif tld in {"edu", "ac", "or", "org", "io", "int"} or ".edu" in domain:
        score += 3
    host = parts.hostname or ""
    if host and not host.startswith(("www.", "m.")):
        score += 4
    if re.search(r"(index of|parent directory|directory listing)", text, re.I):
        score += 14
    if re.search(r"(confidential|internal use|not for distribution|draft|embargoed)", text, re.I):
        score += 8
    return max(0, min(100, score))


def tokens(text: str) -> list[str]:
    return [t for t in re.split(r"[^a-z0-9]+", text.lower()) if len(t) > 1]


def truncate(text: str, n: int = 280) -> str:
    text = re.sub(r"\s+", " ", (text or "")).strip()
    return text if len(text) <= n else text[: n - 1].rstrip() + "…"


def dedupe_words(parts: Iterable[str]) -> str:
    seen, out = set(), []
    for part in parts:
        p = (part or "").strip()
        if p and p.lower() not in seen:
            seen.add(p.lower())
            out.append(p)
    return " — ".join(out)
