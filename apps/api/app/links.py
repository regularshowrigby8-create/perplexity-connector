"""Find links that look like a link you already have.

You paste one URL — a form response page, a portal record, a file on a shared
drive — and this reads its *shape*: which segments are structure and which are
an opaque id. `https://docs.google.com/forms/d/e/1FAIpQLSe…/viewform` is
`/forms/d/e/{id}/viewform`, and every other form on that path is the same shape
with a different id.

Then it looks for that shape in two places:

  - the pages around the seed (a listing, an index, a page that embeds it)
  - the engine itself, by searching for the literal path prefix, because a page
    that contains one form usually ranks for others

Every candidate is reported with where it was found and why it matched, and the
optional phrase filter is matched against the link (and optionally the link text)
— never silently dropped: a link that fails the phrase is listed as `near`, so a
phrase that is too strict is visible instead of producing an empty page.
"""
from __future__ import annotations

import asyncio
import re
from typing import Any
from urllib.parse import urlsplit

import httpx
from pydantic import BaseModel, Field

from .config import settings

# Words that carry meaning in a path: `/viewform`, `/edit`, `/download`, `/files`
# are structure, not identifiers, so they are never blanked out of a template.
STRUCTURAL = {
    "viewform", "view", "edit", "forms", "form", "d", "e", "u", "file", "files",
    "download", "downloads", "index", "html", "htm", "php", "asp", "aspx", "jsp",
    "search", "results", "detail", "details", "item", "items", "record", "records",
    "doc", "docs", "document", "documents", "report", "reports", "api", "v1", "v2",
    "public", "private", "share", "shared", "open", "viewer", "preview", "embed",
    "pages", "page", "site", "sites", "app", "apps", "portal", "data", "dataset",
    "datasets", "files", "uploads", "assets", "static", "media", "download",
}
ID_TOKEN = "{id}"
ID_PATTERN = r"[A-Za-z0-9_\-]{6,}"
SEGMENT_SPLIT = re.compile(r"/+")


class LinkRequest(BaseModel):
    seed: str = Field(min_length=6, max_length=2000)
    phrase: str = Field(default="", max_length=300)
    # "both" by default: a phrase usually names what the link *says* ("round 4
    # solar"), and sometimes what it contains ("viewform"). Either counts.
    match_in: str = Field(default="both", pattern="^(url|text|both)$")
    depth: int = Field(default=2, ge=0, le=4)
    max_pages: int = Field(default=30, ge=1, le=200)
    max_links: int = Field(default=200, ge=1, le=1000)
    same_host: bool = True
    respect_robots: bool = True
    use_engines: bool = True
    delay: float = Field(default=0.1, ge=0.0, le=2.0)


def _is_opaque(segment: str) -> bool:
    if not segment or segment.lower() in STRUCTURAL:
        return False
    if len(segment) < 8:
        return False
    has_digit = any(char.isdigit() for char in segment)
    has_alpha = any(char.isalpha() for char in segment)
    if len(segment) >= 16:
        return True
    return has_digit and has_alpha


def template_of(url: str) -> dict[str, Any]:
    """The shape of a URL: structure kept, identifiers blanked."""
    parts = urlsplit(url)
    segments = [seg for seg in SEGMENT_SPLIT.split(parts.path) if seg]
    shaped: list[str] = []
    ids: list[str] = []
    for segment in segments:
        stem, dot, ext = segment.partition(".")
        if dot and ext and not _is_opaque(stem):
            shaped.append(segment)
            continue
        if _is_opaque(segment):
            shaped.append(ID_TOKEN)
            ids.append(segment)
        else:
            shaped.append(segment)
    path = "/" + "/".join(shaped) if shaped else ""
    if parts.path.endswith("/") and path:
        path += "/"
    template = f"{parts.scheme}://{parts.netloc}{path}"
    if parts.query:
        template += "?" + parts.query
    regex = "^" + re.escape(template).replace(re.escape(ID_TOKEN), ID_PATTERN) + "$"
    return {
        "template": template,
        "path_template": path,
        "ids": ids,
        "regex": regex,
        "is_opaque_seed": bool(ids),
        "host": parts.netloc,
        "scheme": parts.scheme or "https",
    }


def _phrase_hit(url: str, text: str, phrase: str, match_in: str) -> tuple[bool, list[str]]:
    if not phrase:
        return True, []
    needle = phrase.lower().strip()
    where: list[str] = []
    if match_in in ("url", "both") and needle in url.lower():
        where.append("url")
    if match_in in ("text", "both") and needle in (text or "").lower():
        where.append("text")
    return bool(where), where


ANCHOR_RE = re.compile(r"<a\b[^>]*href=[\"']([^\"']+)[\"'][^>]*>(.*?)</a>", re.I | re.S)
TAG_RE = re.compile(r"<[^>]+>")


def anchors(html: str, base: str) -> list[tuple[str, str]]:
    from urllib.parse import urljoin

    found: list[tuple[str, str]] = []
    for match in ANCHOR_RE.finditer(html or ""):
        href = match.group(1).strip()
        if not href or href.startswith(("#", "mailto:", "tel:", "javascript:")):
            continue
        url = urljoin(base, href)
        if not url.startswith(("http://", "https://")):
            continue
        text = TAG_RE.sub(" ", match.group(2))
        found.append((url, re.sub(r"\s+", " ", text).strip()[:180]))
    return found


class _Robots:
    """A small, cached robots reader — the crawler's politeness, reused."""

    def __init__(self, client: httpx.AsyncClient, respect: bool) -> None:
        self.client = client
        self.respect = respect
        self._cache: dict[str, Any] = {}

    async def allowed(self, url: str) -> bool:
        if not self.respect:
            return True
        parts = urlsplit(url)
        origin = f"{parts.scheme}://{parts.netloc}"
        if origin not in self._cache:
            try:
                resp = await self.client.get(origin + "/robots.txt", timeout=6.0)
                rules = resp.text if resp.status_code == 200 else ""
            except Exception:
                rules = ""
            from urllib.robotparser import RobotFileParser

            parser = RobotFileParser()
            parser.parse(rules.splitlines() if rules else [])
            self._cache[origin] = parser
        parser = self._cache[origin]
        try:
            return parser.can_fetch(settings.user_agent, url)
        except Exception:
            return True


async def find_links(req: LinkRequest) -> dict[str, Any]:
    shape = template_of(req.seed)
    pattern = re.compile(shape["regex"])
    parts = urlsplit(req.seed)
    seed_host = parts.netloc.lower()
    phrase = req.phrase.strip()

    candidates: dict[str, dict[str, Any]] = {}
    pages: dict[str, int] = {}
    visited: set[str] = set()
    errors: list[str] = []
    anchors_seen = 0

    def note(url: str, text: str, found_on: str) -> None:
        nonlocal anchors_seen
        anchors_seen += 1
        by_template = bool(pattern.search(url))
        ok, where = _phrase_hit(url, text, phrase, req.match_in)
        row = candidates.get(url)
        if row is None:
            candidates[url] = {
                "url": url, "text": text, "found_on": [found_on],
                "by_template": by_template, "phrase_ok": ok, "phrase_where": where,
            }
            return
        if found_on not in row["found_on"]:
            row["found_on"].append(found_on)
        if not row["text"] and text:
            row["text"] = text

    async with httpx.AsyncClient(
        timeout=httpx.Timeout(settings.request_timeout, connect=settings.connect_timeout),
        follow_redirects=True,
        headers={"User-Agent": settings.user_agent, "Accept": "text/html,*/*"},
        limits=httpx.Limits(max_connections=8, max_keepalive_connections=4),
    ) as client:
        robots = _Robots(client, req.respect_robots)

        # ---- 1. the seed, then its neighbourhood, breadth first
        frontier: list[tuple[str, int]] = [(req.seed, 0)]
        while frontier and len(pages) < req.max_pages:
            url, depth = frontier.pop(0)
            if url in visited:
                continue
            visited.add(url)
            if not await robots.allowed(url):
                errors.append(f"robots: {url}")
                continue
            try:
                resp = await client.get(url)
            except Exception as exc:  # transport, TLS, DNS — reported, never fatal
                errors.append(f"{type(exc).__name__}: {url}")
                continue
            if resp.status_code >= 400 or "html" not in resp.headers.get("content-type", "html"):
                errors.append(f"HTTP {resp.status_code}: {url}")
                continue
            pages[url] = resp.status_code
            for link, text in anchors(resp.text, str(resp.url)):
                note(link, text, url)
                if depth < req.depth:
                    host = urlsplit(link).netloc.lower()
                    if (not req.same_host or host == seed_host) and link not in visited:
                        frontier.append((link, depth + 1))
            if req.delay:
                await asyncio.sleep(req.delay)

        # ---- 2. the engine, asked for the literal prefix: pages that hold one
        # form usually rank for others, and their links carry the same shape.
        if req.use_engines and len(candidates) < req.max_links:
            prefix = shape["path_template"].replace(ID_TOKEN, "").strip("/")
            query = f'"{parts.netloc}/{prefix}"' if prefix else f'"{parts.netloc}"'
            try:
                from .models import HuntRequest
                from .orchestrator import hunt

                result = await hunt(HuntRequest(q=query, limit=60, match="loose", fresh=True),
                                    use_cache=True)
                for hit in result.hits:
                    note(hit.url, hit.title or "", "engine:" + hit.provider_name)
                    if pattern.search(hit.url):
                        for link, text in anchors(
                                f'<a href="{hit.url}">{hit.title or ""}</a>', hit.url):
                            note(link, text, "engine")
                errors.extend(f"engine {p['name']}: {p.get('message') or p['status']}"
                              for p in result.providers if p.get("status") == "error")
            except Exception as exc:
                errors.append(f"engine: {type(exc).__name__}")

    shaped = [row for row in candidates.values() if row["by_template"] and row["phrase_ok"]]
    near = [row for row in candidates.values() if row["by_template"] and not row["phrase_ok"]]
    shaped.sort(key=lambda row: (row["url"] != req.seed, -len(row["found_on"]), row["url"]))
    near.sort(key=lambda row: row["url"])
    shaped = shaped[: req.max_links]

    return {
        "seed": req.seed,
        "template": shape["template"],
        "regex": shape["regex"],
        "ids": shape["ids"],
        "opaque_seed": shape["is_opaque_seed"],
        "phrase": phrase,
        "match_in": req.match_in,
        "links": shaped,
        "near": near[:100],
        "stats": {
            "pages_fetched": len(pages),
            "anchors_seen": anchors_seen,
            "candidates": len(candidates),
            "same_shape": sum(1 for row in candidates.values() if row["by_template"]),
            "phrase_matched": len(shaped),
            "phrase_rejected": len(near),
            "returned": len(shaped),
            "errors": len(errors),
        },
        "errors": errors[:40],
        "notes": [
            "A link is a candidate when its path has the same shape as the seed's, "
            "with any identifier in place of the seed's id.",
            "Links that share the shape but not the phrase are listed under 'near' — "
            "the phrase rejects them, the engine does not.",
        ],
    }
