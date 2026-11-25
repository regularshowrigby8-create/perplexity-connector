"""One hop out from an index result — the pages the index never handed over.

This is the piece that was missing when the engine was compared with Google,
Bing, DuckDuckGo and Brave on the same query. They all answered "diary of a
wimpy kid pdf" with *pages that hold the file*: an archive.org item, a Scribd
document, a flipbook viewer. An API index gives you the URL and a snippet and
stops there; it will not tell you that the item page links to nine chapter PDFs,
or that the viewer has a download button, or when the page was actually
published.

So after the engines answer, the engine does what a Crawlee-style crawler does —
seed, fetch, extract — but bounded: a handful of the best pages, a couple of
seconds, one hop. It reads the page itself, pulls the file links, the dates from
the page's own metadata and the server's Last-Modified header, and hands those
back as results of their own.

Relevance is not given up for this. A link only comes back if a word from the
query appears in the link text or the URL, if its extension is one the query is
after (or none was asked for), and if it is not already in the answer. Pages
that are slow, refuse, or are not HTML are skipped and counted — never silently.
"""
from __future__ import annotations

import asyncio
import time
from typing import Any, Iterable
from urllib.parse import urljoin

from .extract import path_ext, safe_domain
from .providers.base import HuntContext, Provider, RawHit, clean

FILE_EXTS = {"pdf", "epub", "mobi", "djvu", "doc", "docx", "xls", "xlsx", "csv",
             "ppt", "pptx", "txt", "zip", "rar", "apk", "gz", "json"}
# Where a page says when it was published. The engine believe pages over
# snippets: a `datePublished` in the page's own markup beats a search engine's
# guess by a wide margin.
DATE_META = ("article:published_time", "datepublished", "date", "pubdate", "publishdate",
             "dc.date", "dc.date.issued", "sailthru.date", "parsely-pub-date", "og:updated_time")
PAGE_TIMEOUT = 1.2
OFFER_HINTS = ("download", "/details/", "/doc/", "/document/", "/view/", "flipbook",
               "issuu", "yumpu", "fliphtml5", "scribd", "pubhtml5")


class Discover(Provider):
    """Not a fan-out engine: it is handed the answer so far and crawls out of it."""

    id, name, family, layer = "hop", "One hop out", "crawl", "crawl"
    description = ("After the indexes answer, open the best pages and take the files and "
                   "dates inside them — seeded, fetched and parsed here, no key.")
    lenses = ("all", "files", "opportunities", "datasets", "exposed", "applications")
    homepage = "/crawl"
    weight = 2.0
    rate_note = "one hop, a few pages, polite"


HOP = Discover()


def _wanted_exts(types: Iterable[str] | None) -> set[str]:
    asked = {t.lower() for t in (types or []) if t}
    if not asked:
        return set(FILE_EXTS)
    # "pdf" also means the sibling formats a person actually wants; anything
    # else stays exactly what was asked for.
    if "pdf" in asked:
        return asked | {"pdf", "epub", "mobi", "djvu"}
    return asked & FILE_EXTS


def _relevant(text: str, url: str, terms: list[str]) -> bool:
    if not terms:
        return True
    hay = f"{text} {url}".lower()
    return any(term in hay for term in terms)


def page_date(soup: Any, headers: dict[str, str] | None = None) -> str | None:
    """The page's own statement of when it was published, or the server's."""
    for key in DATE_META:
        node = soup.find("meta", attrs={"property": key}) or soup.find("meta", attrs={"name": key})
        if node and node.get("content"):
            value = str(node["content"]).strip()
            if value:
                return value
    for node in soup.find_all("time"):
        value = node.get("datetime") or node.get_text(" ", strip=True)
        if value and any(ch.isdigit() for ch in value) and len(value) >= 8:
            return str(value).strip()
    if headers:
        for key in ("last-modified", "date"):
            if headers.get(key):
                return headers[key]
    return None


def file_links(html: str, base_url: str, terms: list[str], types: list[str] | None,
               cap: int = 6) -> list[dict[str, Any]]:
    """The links on a page that are the thing the query asked for.

    Pure on purpose: given the same HTML it returns the same links, so the
    behaviour can be checked without a network.
    """
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(html, "html.parser")
    wanted = _wanted_exts(types)
    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    dated = page_date(soup)
    for anchor in soup.find_all("a", href=True):
        href = urljoin(base_url, str(anchor["href"]).strip())
        if not href.startswith("http") or href in seen:
            continue
        ext = path_ext(href)
        text = anchor.get_text(" ", strip=True)
        offers = any(hint in href.lower() for hint in OFFER_HINTS) or \
            any(word in text.lower() for word in ("download", "pdf", "epub", "read online"))
        if ext not in wanted and not (offers and ext is None):
            continue
        if not _relevant(f"{text} {href.rsplit('/', 1)[-1]}", href, terms):
            continue
        seen.add(href)
        out.append({
            "url": href,
            "title": clean(text or href.rsplit("/", 1)[-1], 200),
            "snippet": clean(f"found one hop out from {safe_domain(base_url)}", 200),
            # the page's own date travels with what it offers: an item page dated
            # 2007 links to a 2007 file, and saying so beats leaving it undated
            "published": dated,
            "ext": ext,
        })
        if len(out) >= cap:
            break
    return out


def seeds_from(hits: list[Any], cap: int = 6) -> list[Any]:
    """The pages worth opening: HTML, on the open web, best-scoring first."""
    picked: list[Any] = []
    seen_domains: dict[str, int] = {}
    for hit in hits:
        url = getattr(hit, "url", "") or ""
        if not url.startswith("http"):
            continue
        if (getattr(hit, "file_ext", None) or "") not in ("", "html", "htm", "shtml"):
            continue
        domain = getattr(hit, "domain", "") or safe_domain(url)
        # two pages per host at most: one host should not own the hop
        if seen_domains.get(domain, 0) >= 2:
            continue
        seen_domains[domain] = seen_domains.get(domain, 0) + 1
        picked.append(hit)
        if len(picked) >= cap:
            break
    return picked


async def hop(hits: list[Any], client: Any, *, terms: list[str], types: list[str] | None,
              budget_s: float = 1.6, seed_cap: int = 6, cap_per_page: int = 4
              ) -> tuple[list[RawHit], dict[str, Any]]:
    """Fetch the seeds, read each page once, return what is inside them."""
    started = time.perf_counter()
    seeds = seeds_from(hits, cap=seed_cap)
    stats: dict[str, Any] = {"hop": "one hop out", "seeds": len(seeds), "pages_read": 0,
                             "skipped": 0, "budget_ms": int(budget_s * 1000), "found": 0,
                             "note": ""}
    if not seeds:
        stats["note"] = "nothing to open"
        return [], stats
    known = {getattr(h, "url", "") for h in hits}
    deadline = started + max(0.2, budget_s)

    async def one(seed: Any) -> list[RawHit]:
        left = deadline - time.perf_counter()
        if left <= 0:
            stats["skipped"] += 1
            return []
        try:
            # A page gets a second, not the answer's whole latency: a hop that is
            # slow is a hop that is skipped and counted.
            resp = await client.get(getattr(seed, "url", ""),
                                    timeout=min(PAGE_TIMEOUT, max(0.3, left)),
                                    headers={"Accept": "text/html,application/xhtml+xml"})
            if resp.status_code >= 400:
                stats["skipped"] += 1
                return []
            if "html" not in (resp.headers.get("content-type") or "html").lower():
                stats["skipped"] += 1
                return []
            stats["pages_read"] += 1
            links = file_links(resp.text, str(seed.url), terms, types, cap=cap_per_page)
        except Exception:
            stats["skipped"] += 1
            return []
        out: list[RawHit] = []
        for link in links:
            if link["url"] in known:
                continue
            known.add(link["url"])
            out.append(RawHit(url=link["url"], title=link["title"], snippet=link["snippet"],
                              published=link["published"], tags=("hidden", "one-hop"),
                              meta={"from": getattr(seed, "domain", ""), "hop": 1}))
        return out

    results = await asyncio.gather(*(one(seed) for seed in seeds))
    found = [raw for batch in results for raw in batch]
    stats["found"] = len(found)
    stats["ms"] = int((time.perf_counter() - started) * 1000)
    if stats["skipped"]:
        stats["note"] = f"{stats['skipped']} page(s) skipped (slow, refused or not a page)"
    return found, stats
