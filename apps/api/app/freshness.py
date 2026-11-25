"""Freshness: turn every timestamp the web exposes into "how long ago".

The web is full of clocks, and most crawlers ignore them. This module reads all of
them and normalises to aware UTC, so a result can say *4 seconds ago* instead of
"undated link".

Imported from:
  * adbar/htmldate            — best-in-class publication-date extraction from HTML
    (meta tags, JSON-LD, <time>, URL patterns, sitemap hints)
  * scrapers/dateparser       — human and multilingual dates ("2 hours ago", "5. Mai")
  * dateutil                  — RFC 2822 / ISO 8601 fallbacks (email + feed dates)
  * jmoiron/humanize          — relative-time wording ("3 minutes ago")
  * Common Crawl / WARC       — 14-digit ``YYYYMMDDhhmmss`` timestamps
  * Internet Archive CDX      — the same 14-digit clock, plus ``addeddate``
  * IETF RFC 9110 §8.8.2      — ``Last-Modified`` beats ``Date`` for a document's age
  * RSS 2.0 / Atom            — ``pubDate`` / ``updated`` are the feed's own clock
  * WordPress core            — ``?feed=rss2`` search feeds expose second-level clocks

Rule of thumb, borrowed from htmldate's benchmark: a *published* date from page
metadata is trustworthy; a date guessed from a URL path is a hint, never a fact.
"""
from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone
from typing import Any, Iterable, Mapping

UTC = timezone.utc

# WARC / CDX: 20260301124559
_WARC = re.compile(r"^\s*(\d{4})(\d{2})(\d{2})(\d{2})?(\d{2})?(\d{2})?\s*$")
_ISO = re.compile(r"^\s*(\d{4})-(\d{2})-(\d{2})(?:[T ](\d{2}):(\d{2})(?::(\d{2}))?)?")
_META_DATE = re.compile(
    r"""<meta[^>]+(?:property|name|itemprop)=["']"""
    r"""((?:article|og|dc|dcterms|date|pub|publish)[\w:.\-]*(?:date|time)?[\w:.\-]*)"""
    r"""["'][^>]+content=["']([^"']{4,60})["']""", re.I)
_JSONLD_DATE = re.compile(
    r'"(datePublished|dateModified|uploadDate|published|updated|created)"\s*:\s*'
    r'"([^"]{4,60})"', re.I)
_TIME_TAG = re.compile(r"""<time[^>]+datetime=["']([^"']{4,60})["']""", re.I)

# Free text hints used only when no metadata clock exists.
_AGO = re.compile(r"(\d+)\s*(second|minute|hour|day|week|month|year)s?\s+ago", re.I)
_UNIT_SECONDS = {"second": 1, "minute": 60, "hour": 3600, "day": 86400,
                 "week": 604800, "month": 2592000, "year": 31536000}


def utcnow() -> datetime:
    return datetime.now(UTC)


def parse(value: Any, now: datetime | None = None) -> datetime | None:
    """Parse almost any timestamp the web hands us. Never raises."""
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        return value.astimezone(UTC) if value.tzinfo else value.replace(tzinfo=UTC)
    if isinstance(value, (int, float)):
        seconds = float(value)
        if seconds > 1e11:      # milliseconds
            seconds /= 1000.0
        try:
            return datetime.fromtimestamp(seconds, UTC)
        except (OverflowError, OSError, ValueError):
            return None
    text = str(value).strip()
    if not text:
        return None

    match = _WARC.match(text)
    if match and len(text.strip()) >= 8 and text.strip().isdigit():
        year, month, day, hour, minute, second = (
            int(part) if part else 0 for part in match.groups())
        try:
            return datetime(year, month, day, hour, minute, second, tzinfo=UTC)
        except ValueError:
            return None

    match = _ISO.match(text)
    if match:
        year, month, day = (int(match.group(i)) for i in (1, 2, 3))
        hour = int(match.group(4) or 0)
        minute = int(match.group(5) or 0)
        second = int(match.group(6) or 0)
        try:
            naive = datetime(year, month, day, hour, minute, second)
        except ValueError:
            return None
        if text.endswith(("Z", "z")) or "+" in text[10:] or text.count("-") > 3:
            try:
                from dateutil import parser as dateparser

                parsed = dateparser.parse(text, fuzzy=False)
                if parsed:
                    return parsed.astimezone(UTC) if parsed.tzinfo else parsed.replace(tzinfo=UTC)
            except Exception:
                pass
        return naive.replace(tzinfo=UTC)

    ago = _AGO.search(text)
    if ago:
        unit = ago.group(2).lower()
        delta = timedelta(seconds=int(ago.group(1)) * _UNIT_SECONDS[unit])
        return (now or utcnow()) - delta

    for parser in (_dateparser,):
        parsed = parser(text)
        if parsed is not None:
            return parsed
    return None


def _dateparser(text: str) -> datetime | None:
    try:
        from dateutil import parser as dateutil_parser

        parsed = dateutil_parser.parse(text, fuzzy=True)
        return parsed.astimezone(UTC) if parsed.tzinfo else parsed.replace(tzinfo=UTC)
    except Exception:
        pass
    try:
        from dateparser import parse as dp

        parsed = dp(text, settings={"RETURN_AS_TIMEZONE_AWARE": True})
        return parsed.astimezone(UTC) if parsed else None
    except Exception:
        return None


# ------------------------------------------------------------------ sources of truth

def from_headers(headers: Mapping[str, str] | Iterable[tuple[str, str]]) -> datetime | None:
    """Last-Modified is the document's clock; Date is the response's clock."""
    items = headers.items() if isinstance(headers, Mapping) else headers
    bag: dict[str, str] = {str(k).lower(): str(v) for k, v in items}
    for key in ("last-modified", "date", "x-last-modified", "expires"):
        if bag.get(key):
            parsed = parse(bag[key])
            if parsed:
                return parsed
    return None


def from_html(html: str, url: str = "") -> tuple[datetime | None, datetime | None, str]:
    """Return (published, modified, source). Metadata only — never URL guessing."""
    if not html:
        return None, None, ""
    published: datetime | None = None
    modified: datetime | None = None
    source = ""

    for match in _META_DATE.finditer(html[:200_000]):
        key = match.group(1).lower()
        value = parse(match.group(2))
        if not value:
            continue
        if "modif" in key or "updated" in key:
            modified = modified or value
        else:
            published = published or value
            source = source or "meta"
    for match in _JSONLD_DATE.finditer(html[:200_000]):
        key = match.group(1).lower()
        value = parse(match.group(2))
        if not value:
            continue
        if key in ("datemodified", "updated"):
            modified = modified or value
        else:
            published = published or value
            source = "json-ld" if not source else source
    if published is None:
        match = _TIME_TAG.search(html[:200_000])
        if match:
            published = parse(match.group(1))
            source = "time-tag" if published else source

    if published is None and modified is None:
        guessed = _htmldate(html, url)
        if guessed:
            published, source = guessed, "htmldate"
    return published, modified, source


def _htmldate(html: str, url: str) -> datetime | None:
    try:
        from htmldate import find_date

        raw = find_date(html, url=url or None, original_date=True,
                        extensive_search=False, outputformat="%Y-%m-%dT%H:%M:%S")
        return parse(raw)
    except Exception:
        return None


def from_feed_entry(entry: Any) -> datetime | None:
    """RSS ``published_parsed`` / Atom ``updated_parsed`` (feedparser struct_time)."""
    for key in ("published_parsed", "updated_parsed", "created_parsed"):
        value = getattr(entry, key, None) if not isinstance(entry, dict) else entry.get(key)
        if value:
            try:
                return datetime(*value[:6], tzinfo=UTC)
            except (TypeError, ValueError):
                continue
    for key in ("published", "updated", "created"):
        value = getattr(entry, key, None) if not isinstance(entry, dict) else entry.get(key)
        parsed = parse(value)
        if parsed:
            return parsed
    return None


# ---------------------------------------------------------------------- relativity

def age_seconds(when: datetime | None, now: datetime | None = None) -> int | None:
    if when is None:
        return None
    reference = now or utcnow()
    try:
        return int((reference - when).total_seconds())
    except (TypeError, ValueError):
        return None


def human(seconds: int | None) -> str:
    """Human wording, second-granular for the first minute."""
    if seconds is None:
        return "undated"
    if seconds < 0:
        future = abs(seconds)
        if future < 60:
            return f"in {future}s"
        return f"in {human(future).replace(' ago', '')}"
    if seconds < 5:
        return "just now"
    if seconds < 60:
        return f"{seconds} seconds ago"
    if seconds < 120:
        return "a minute ago"
    if seconds < 3600:
        return f"{seconds // 60} minutes ago"
    if seconds < 7200:
        return "an hour ago"
    if seconds < 86400:
        return f"{seconds // 3600} hours ago"
    if seconds < 172800:
        return "yesterday"
    if seconds < 2592000:
        return f"{seconds // 86400} days ago"
    if seconds < 31536000:
        return f"{seconds // 2592000} months ago"
    return f"{seconds // 31536000} years ago"


def bucket(seconds: int | None) -> str:
    if seconds is None:
        return "undated"
    if seconds < 60:
        return "seconds"
    if seconds < 3600:
        return "minutes"
    if seconds < 86400:
        return "hours"
    if seconds < 604800:
        return "days"
    if seconds < 2592000:
        return "weeks"
    return "older"


def recency(seconds: int | None, half_life_hours: float = 36.0) -> float:
    """0..1 freshness curve: 1.0 = now, 0.5 at one half-life, ~0 beyond a season.

    Chosen over a step function so a five-second-old upload outranks a
    five-minute-old one, and a two-year-old PDF still has a non-zero value —
    Nighthawk never drops material for being old, it only orders it.
    """
    if seconds is None:
        return 0.0
    if seconds <= 0:
        return 1.0
    hours = seconds / 3600.0
    return round(0.5 ** (hours / max(half_life_hours, 0.5)), 6)


def describe(when: datetime | None, now: datetime | None = None) -> dict[str, Any]:
    seconds = age_seconds(when, now)
    return {
        "published_at": when.astimezone(UTC).isoformat() if when else None,
        "age_seconds": seconds,
        "age_human": human(seconds),
        "freshness": recency(seconds),
        "age_bucket": bucket(seconds),
    }


def freshest(values: Iterable[Any], now: datetime | None = None) -> datetime | None:
    stamps = [stamp for stamp in (parse(v, now) for v in values) if stamp]
    return max(stamps) if stamps else None
