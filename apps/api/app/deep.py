"""Deep-link crawling: everything that only exists because you pasted the URL.

Some documents are not discoverable. They sit behind a portal's search form, in an
unlinked directory, on a page nothing points at, in a sitemap that never made it
into an index, or in an attachment whose only inbound link is a JavaScript handler.
A search engine cannot rank what it has never crawled — so the only way in is the
exact URL.

This module takes pasted links, crawls them deep, and then says *why* each hit
could not have been found any other way:

    pasted        one of your seeds — reachable only because you supplied it
    not-linked    nothing on the crawled pages links to it
    sitemap-only  the site listed it, but no page links to it
    archive-only  surfaced from an archive index, not from the live site
    query-url     a URL built from parameters (notice id, download id, page…)
    attachment    a file, not a page
    deep          buried several hops from the seed

No cap, no ranking gate, no removal — the deep report keeps what it finds.
"""
from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any, Callable
from urllib.parse import parse_qsl, urlsplit

from pydantic import BaseModel, Field

from . import exact, freshness
from .crawl import CrawlRequest, FusionCrawler

QUERY_SURFACE = re.compile(
    r"(id|notice|doc|document|file|download|attachment|view|page|pg|item|record|"
    r"detail|profile|post|article|apply|form|search|q|query|ref|key|token|hash)", re.I)
FILE_EXT = re.compile(r"\.(pdf|docx?|xlsx?|csv|tsv|pptx?|odt|ods|zip|tar|gz|7z|rar|json|xml|"
                      r"geojson|kml|sql|db|sqlite|bak|log|env|yml|yaml|txt|parquet|xlsm)$", re.I)

WEIGHTS = {"pasted": 4.0, "not-linked": 3.5, "sitemap-only": 3.0, "archive-only": 3.0,
           "query-url": 2.0, "attachment": 2.5, "deep": 1.5}

LEGEND = {
    "pasted": "you supplied this URL — nothing led here",
    "not-linked": "no crawled page links to this URL",
    "sitemap-only": "listed in the sitemap only; no page links to it",
    "archive-only": "surfaced from an archive index rather than the live site",
    "query-url": "built from query parameters (ids, downloads, portal searches)",
    "attachment": "a file, not a page — invisible to page-only indexes",
    "deep": "several hops from the seed",
}


class DeepRequest(BaseModel):
    seeds: list[str] = Field(min_length=1, max_length=60)
    query: str = ""
    depth: int = Field(default=4, ge=0, le=12)
    max_pages: int = Field(default=150, ge=0, le=3000)      # 0 = unlimited
    max_files: int = Field(default=250, ge=0, le=3000)
    same_host: bool = False
    use_archive: bool = True
    use_sitemaps: bool = True
    extract_files: bool = True
    keep_every_page: bool = True
    respect_robots: bool = False
    delay: float = Field(default=0.15, ge=0, le=5)
    concurrency: int = Field(default=10, ge=1, le=32)
    limit: int = Field(default=400, ge=0, le=3000)


def _normalise(seed: str) -> str | None:
    raw = (seed or "").strip()
    if not raw or raw.startswith("#"):
        return None
    if raw.startswith(("http://", "https://")):
        return raw
    if re.match(r"^[\w.-]+\.[a-z]{2,}(/|$)", raw, re.I):
        return "https://" + raw
    return None


def _host(url: str) -> str:
    try:
        return urlsplit(url).netloc.lower()
    except ValueError:
        return ""


def reasons_for(url: str, meta: dict[str, Any], seeds: set[str]) -> list[str]:
    """Why this URL is only reachable by having the link."""
    found: list[str] = []
    split = urlsplit(url)
    if url in seeds or url.rstrip("/") in seeds:
        found.append("pasted")
    inbound = int(meta.get("inbound") or 0)
    via = str(meta.get("via") or "")
    if via in ("sitemap", "wayback-cdx", "archive") and inbound == 0:
        found.append("sitemap-only" if via == "sitemap" else "archive-only")
    elif inbound == 0:
        found.append("not-linked")
    if split.query:
        params = {key.lower() for key, _value in parse_qsl(split.query, keep_blank_values=True)}
        if params & {"id", "notice", "doc", "document", "file", "download", "view", "page",
                     "item", "record", "detail", "post", "article", "apply", "form", "q"} or \
                any(QUERY_SURFACE.fullmatch(p) for p in params):
            found.append("query-url")
    if FILE_EXT.search(split.path):
        found.append("attachment")
    try:
        if int(meta.get("crawl_depth") or 0) >= 3:
            found.append("deep")
    except (TypeError, ValueError):
        pass
    return found


async def deep_crawl(req: DeepRequest,
                     emit: Callable[[dict], Any] | None = None) -> dict[str, Any]:
    seeds = [url for url in (_normalise(seed) for seed in req.seeds) if url]
    if not seeds:
        return {"error": "no usable links — paste absolute URLs or bare domains",
                "hits": [], "stats": {}, "seeds": [], "legend": LEGEND}

    crawl_req = CrawlRequest(
        seeds=seeds,
        query=req.query,
        depth=req.depth,
        max_pages=req.max_pages or 1_000_000,
        max_files=req.max_files or 1_000_000,
        concurrency=req.concurrency,
        respect_robots=req.respect_robots,
        same_host=req.same_host,
        serp_engines=[],                 # paste-driven: no search engines, no discovery help
        use_sitemaps=req.use_sitemaps,
        use_archive=req.use_archive,
        extract_files=req.extract_files,
        keep_pages=req.keep_every_page,
        delay=req.delay,
        label="deep",
    )
    crawler = FusionCrawler(crawl_req, emit)
    result = await crawler.run()

    phrase = exact.Phrase.parse(req.query) if req.query.strip() else None
    from .models import Hit

    hits: list[Hit] = []
    for payload in result.get("files", []):
        try:
            hit = Hit.model_validate(payload)
        except Exception:
            continue
        meta = hit.meta or {}
        reasons = reasons_for(hit.url, meta, set(seeds))
        meta["deep_reasons"] = reasons
        meta["deep_score"] = round(sum(WEIGHTS.get(r, 1.0) for r in reasons), 2)
        hit.meta = meta
        hit.tags = sorted({*(hit.tags or []), *(f"deep:{r}" for r in reasons)})
        if phrase:
            exact.annotate(hit, phrase)
        hits.append(hit)

    # best evidence first, then verbatim, then newest
    hits.sort(key=lambda h: (
        -float((h.meta or {}).get("deep_score") or 0.0),
        0 if h.exact else 1,
        h.age_seconds if h.age_seconds is not None else 10 ** 9,
    ))
    if req.limit:
        hits = hits[: req.limit]

    counts = {key: sum(1 for h in hits if key in ((h.meta or {}).get("deep_reasons") or []))
              for key in WEIGHTS}
    stats = dict(result.get("stats") or {})
    stats.update({
        "deep_only": sum(1 for h in hits if not h.meta.get("inbound")),
        "attachments": counts.get("attachment", 0),
        "pasted": counts.get("pasted", 0),
        "not_linked": counts.get("not-linked", 0),
        "query_urls": counts.get("query-url", 0),
        "verbatim": sum(1 for h in hits if h.exact),
        "kept": len(hits),
        "as_of": datetime.now(timezone.utc).isoformat(),
        "unrestricted": True,
    })
    return {
        "query": req.query,
        "seeds": [{"url": url, "host": _host(url)} for url in seeds],
        "hits": [hit.model_dump() for hit in hits],
        "stats": stats,
        "counts": counts,
        "legend": LEGEND,
        "policy": {"result_removal": False, "result_cap": bool(req.limit),
                   "robots": "advisory" if not req.respect_robots else "enforced"},
    }
