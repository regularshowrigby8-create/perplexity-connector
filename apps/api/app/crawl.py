"""Nighthawk Fusion Crawler — the primary engine.

No API gatekeeper, no result ceiling, no moderation layer. It plans its own seeds
(SERP harvest, sitemaps, archives, explicit URLs), walks the frontier politely,
dispatches fetching/parsing/extraction to whichever arsenal engines are installed,
then extracts and indexes every file it finds so the vault becomes searchable
from the inside.
"""
from __future__ import annotations

import asyncio
import re
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable
from urllib.parse import urljoin, urlsplit

import httpx
from pydantic import BaseModel, Field

from . import local_index
from .arsenal import available_ids
from .config import settings
from .extract import (canonical_url, depth_score, fingerprint, find_deadline,
                      opportunity_tags, pretty_name, safe_domain, truncate)
from .models import Hit
from .textkit import extract_text, file_text, meta_extract, parse_links

Emit = Callable[[dict], Awaitable[None]]
READY = available_ids()

FILE_EXT_RE = re.compile(
    r"\.(pdf|docx?|xlsx?|pptx?|odt|ods|rtf|csv|tsv|json|jsonl|xml|geojson|kml|zip|7z|tar|gz|"
    r"tgz|rar|sql|sqlite3?|db|mdb|bak|backup|old|log|env|ini|conf|cfg|toml|pem|key|yml|yaml|"
    r"txt|md|epub|rss|atom|shp|parquet|avro|ipynb)(?:$|\?)", re.I)

# ------------------------------------------------------------------ request model


class CrawlRequest(BaseModel):
    query: str = ""
    seeds: list[str] = Field(default_factory=list)
    depth: int = Field(default=2, ge=0, le=6)
    max_pages: int = Field(default=40, ge=1, le=800)
    max_files: int = Field(default=80, ge=1, le=800)
    concurrency: int = Field(default=8, ge=1, le=32)
    respect_robots: bool = True
    same_host: bool = True
    serp_engines: list[str] = Field(default_factory=lambda: ["duckduckgo", "mojeek", "marginalia", "bing"])
    use_sitemaps: bool = True
    use_archive: bool = False
    file_types: list[str] = Field(default_factory=list)
    extract_files: bool = True
    fetch_engine: str = "httpx"
    max_bytes: int = Field(default=6_000_000, ge=100_000, le=30_000_000)
    delay: float = Field(default=0.35, ge=0, le=5)
    label: str = "ad-hoc"


SERP_TARGETS: dict[str, dict[str, str]] = {
    "duckduckgo": {"url": "https://lite.duckduckgo.com/lite/", "note": "HTML lite"},
    "mojeek": {"url": "https://www.mojeek.com/search", "note": "independent index"},
    "marginalia": {"url": "https://old-search.marginalia.nu/search", "note": "small web"},
    "bing": {"url": "https://www.bing.com/search", "note": "HTML results"},
    "brave": {"url": "https://search.brave.com/search", "note": "HTML results"},
    "startpage": {"url": "https://www.startpage.com/sp/search", "note": "proxy front-end"},
    "google": {"url": "https://www.google.com/search", "note": "may challenge automated clients"},
}


def normalize_seed(raw: str) -> str | None:
    raw = (raw or "").strip()
    if not raw:
        return None
    if raw.startswith(("http://", "https://")):
        return raw
    host = raw.split("/")[0]
    scheme = "http" if host.startswith(("127.0.0.1", "localhost")) or ":" in host else "https"
    return f"{scheme}://{raw}"


# --------------------------------------------------------------------- the crawler


@dataclass
class CrawlStats:
    pages: int = 0
    files: int = 0
    links: int = 0
    blocked: int = 0
    errors: int = 0
    bytes: int = 0
    docs_indexed: int = 0
    opportunities: int = 0
    started: float = field(default_factory=time.time)
    engines: dict[str, int] = field(default_factory=dict)

    def bump(self, engine: str, n: int = 1) -> None:
        self.engines[engine] = self.engines.get(engine, 0) + n

    def as_dict(self) -> dict[str, Any]:
        return {
            "pages": self.pages, "files": self.files, "links": self.links,
            "blocked_by_robots": self.blocked, "errors": self.errors,
            "opportunities": self.opportunities,
            "bytes": self.bytes, "docs_indexed": self.docs_indexed,
            "engines": self.engines,
            "took_ms": int((time.time() - self.started) * 1000),
        }


class FusionCrawler:
    def __init__(self, req: CrawlRequest, emit: Emit | None = None) -> None:
        self.req = req
        self.emit = emit or (lambda event: asyncio.sleep(0))
        self.stats = CrawlStats()
        self.client = httpx.AsyncClient(
            timeout=httpx.Timeout(settings.provider_timeout, connect=settings.connect_timeout),
            follow_redirects=True,
            headers={"User-Agent": settings.user_agent, "Accept-Language": "en"},
            limits=httpx.Limits(max_connections=32, max_keepalive_connections=16),
        )
        self.visited: set[str] = set()
        self.files: dict[str, Hit] = {}
        self.page_hits: dict[str, Hit] = {}
        self.robots: dict[str, Any] = {}
        self.gates: dict[str, float] = {}
        self.pages_lock = asyncio.Lock()
        self.allowed_hosts: set[str] = set()

    # ------------------------------------------------------------------ utilities
    async def _send(self, kind: str, **payload: Any) -> None:
        await self.emit({"type": kind, **payload})

    def _same_host_ok(self, url: str) -> bool:
        if not self.req.same_host:
            return True
        host = safe_domain(url)
        return not self.allowed_hosts or host in self.allowed_hosts

    async def _gate(self, url: str) -> None:
        host = urlsplit(url).netloc
        wait_until = self.gates.get(host, 0)
        now = time.monotonic()
        if wait_until > now:
            await asyncio.sleep(min(wait_until - now, 3.0))
        delay = self.req.delay
        parser = self.robots.get(host)
        if parser is not None:
            try:
                crawl_delay = parser.crawl_delay(settings.user_agent)
                if crawl_delay:
                    delay = max(delay, min(float(crawl_delay), 3.0))
            except Exception:
                pass
        self.gates[host] = time.monotonic() + delay

    async def _robots_for(self, url: str) -> Any:
        host = urlsplit(url).netloc
        if host in self.robots:
            return self.robots[host]
        parser = None
        try:
            from urllib.robotparser import RobotFileParser

            origin = f"{urlsplit(url).scheme}://{host}"
            resp = await self.client.get(f"{origin}/robots.txt", timeout=6.0)
            if resp.status_code == 200 and resp.text:
                parser = RobotFileParser()
                parser.parse(resp.text.splitlines())
                await self._send("robots", host=host, rules=len(resp.text.splitlines()),
                                 sitemaps=[line.split(":", 1)[1].strip()
                                           for line in resp.text.splitlines()
                                           if line.lower().startswith("sitemap:")])
        except Exception:
            parser = None
        self.robots[host] = parser
        return parser

    async def _allowed(self, url: str) -> bool:
        if not self.req.respect_robots:
            return True
        parser = await self._robots_for(url)
        if parser is None:
            return True
        try:
            return parser.can_fetch(settings.user_agent, url)
        except Exception:
            return True

    # ---------------------------------------------------------------------- fetch
    async def _fetch(self, url: str) -> tuple[int, str, bytes, str]:
        engine = self.req.fetch_engine
        if engine == "aiohttp" and "aiohttp" in READY:
            try:
                import aiohttp

                timeout = aiohttp.ClientTimeout(total=settings.provider_timeout)
                async with aiohttp.ClientSession(
                        timeout=timeout, headers={"User-Agent": settings.user_agent}) as session:
                    async with session.get(url) as resp:
                        body = await resp.content.read(self.req.max_bytes)
                        ctype = resp.headers.get("content-type", "")
                        return resp.status, ctype, body, "aiohttp"
            except Exception:
                pass
        if engine in ("cloudscraper", "hrequests", "mechanicalsoup") and engine.replace("-", "_") in READY:
            try:
                return await asyncio.to_thread(self._sync_fetch, url, engine)
            except Exception:
                pass
        if engine == "crawlee" and "crawlee" in READY:
            try:
                from crawlee.http_clients import HttpxHttpClient

                client = HttpxHttpClient()
                response = await client.send_request(url, headers={"User-Agent": settings.user_agent})
                body = response.read()[: self.req.max_bytes]
                ctype = (response.headers.get("content-type") or [""])[0]
                return response.status_code, ctype, body, "crawlee"
            except Exception:
                pass
        # default + universal fallback
        async with self.client.stream("GET", url) as resp:
            chunks: list[bytes] = []
            size = 0
            async for chunk in resp.aiter_bytes():
                chunks.append(chunk)
                size += len(chunk)
                if size >= self.req.max_bytes:
                    break
            return resp.status_code, resp.headers.get("content-type", ""), b"".join(chunks), "httpx"

    def _sync_fetch(self, url: str, engine: str) -> tuple[int, str, bytes, str]:
        if engine == "cloudscraper":
            import cloudscraper

            resp = cloudscraper.create_scraper().get(url, timeout=settings.provider_timeout)
            return resp.status_code, resp.headers.get("content-type", ""), resp.content[: self.req.max_bytes], "cloudscraper"
        if engine == "hrequests":
            import hrequests

            resp = hrequests.get(url, timeout=settings.provider_timeout)
            return resp.status_code, resp.headers.get("content-type", ""), resp.content[: self.req.max_bytes], "hrequests"
        import mechanicalsoup

        browser = mechanicalsoup.StatefulBrowser()
        resp = browser.open(url, timeout=settings.provider_timeout)
        html = str(resp.soup).encode()
        return resp.status_code, resp.headers.get("content-type", ""), html[: self.req.max_bytes], "mechanicalsoup"

    async def _head(self, url: str) -> dict[str, Any]:
        try:
            resp = await self.client.head(url, timeout=5.0)
            return {"size": resp.headers.get("content-length"),
                    "mime": resp.headers.get("content-type", "").split(";")[0],
                    "modified": resp.headers.get("last-modified")}
        except Exception:
            return {}

    # --------------------------------------------------------------------- seeds
    async def _serp(self, engine: str, query: str, limit: int = 12) -> list[str]:
        target = SERP_TARGETS.get(engine)
        if engine == "searxng" and settings.searxng_url:
            try:
                resp = await self.client.get(f"{settings.searxng_url.rstrip('/')}/search",
                                             params={"q": query, "format": "json"}, timeout=10)
                data = resp.json()
                return [r.get("url", "") for r in (data.get("results") or [])[:limit] if r.get("url")]
            except Exception as exc:
                raise RuntimeError(str(exc)[:120]) from exc
        if not target:
            raise RuntimeError("unknown engine")
        resp = await self.client.get(target["url"], params={"q": query}, timeout=10.0,
                                     headers={"Accept": "text/html,application/xhtml+xml"})
        resp.raise_for_status()
        html = resp.text
        urls: list[str] = []
        if engine == "duckduckgo":
            urls = re.findall(r'class="result-link"[^>]*href="([^"]+)"', html)
            if not urls:
                urls = re.findall(r'href="(https?://[^"]+)"[^>]*class="result-link"', html)
        elif engine == "mojeek":
            urls = re.findall(r'<a class="ob"[^>]*href="([^"]+)"', html)
            if not urls:
                urls = re.findall(r'<a[^>]+class="title"[^>]+href="([^"]+)"', html)
        elif engine == "marginalia":
            urls = re.findall(r'<a[^>]+href="(https?://[^"]+)"[^>]*class="[^"]*title', html)
            if not urls:
                urls = re.findall(r'<a[^>]+href="(https?://[^"]+)"', html)
        elif engine == "bing":
            urls = re.findall(r'<h2><a href="([^"]+)"', html)
        elif engine == "brave":
            urls = re.findall(r'<a[^>]+href="(https?://[^"]+)"[^>]+data-testid="result-title', html)
        elif engine == "startpage":
            urls = re.findall(r'<a[^>]+href="(https?://[^"]+)"[^>]+class="[^"]*result-link', html)
        else:
            urls = re.findall(r'/url\?q=(https?://[^&"]+)', html)
        out: list[str] = []
        for url in urls:
            if "duckduckgo.com" in url or "bing.com" in url or "mojeek.com" in url:
                continue
            out.append(url.split("&amp;")[0])
            if len(out) >= limit:
                break
        return out

    async def _sitemap_seeds(self, origin: str, cap: int = 120) -> list[str]:
        urls: list[str] = []
        candidates: list[str] = []
        try:
            resp = await self.client.get(f"{origin}/robots.txt", timeout=6.0)
            if resp.status_code == 200:
                for line in resp.text.splitlines():
                    if line.lower().startswith("sitemap:"):
                        candidates.append(line.split(":", 1)[1].strip())
        except Exception:
            pass
        candidates += [f"{origin}/sitemap.xml", f"{origin}/sitemap_index.xml"]
        seen: set[str] = set()
        for sm_url in candidates[:4]:
            if sm_url in seen:
                continue
            seen.add(sm_url)
            try:
                resp = await self.client.get(sm_url, timeout=8.0)
                if resp.status_code >= 400:
                    continue
                locs = re.findall(r"<loc>\s*([^<\s]+)\s*</loc>", resp.text, re.I)
                if "<sitemapindex" in resp.text.lower():
                    for sub in locs[:3]:
                        try:
                            sub_resp = await self.client.get(sub, timeout=8.0)
                            urls += re.findall(r"<loc>\s*([^<\s]+)\s*</loc>", sub_resp.text, re.I)
                        except Exception:
                            continue
                else:
                    urls += locs
                await self._send("sitemap", url=sm_url, urls=len(urls))
                if len(urls) >= cap:
                    break
            except Exception:
                continue
        return urls[:cap]

    async def resolve_seeds(self) -> list[tuple[str, str]]:
        seeds: list[tuple[str, str]] = []
        seen: set[str] = set()

        def add(url: str | None, source: str) -> None:
            norm = normalize_seed(url or "")
            if not norm:
                return
            canon = canonical_url(norm)
            if canon in seen:
                return
            seen.add(canon)
            seeds.append((norm, source))

        for raw in self.req.seeds:
            add(raw, "explicit")

        query = self.req.query.strip()
        site = None
        m = re.search(r"\bsite:([^\s]+)", query, re.I)
        if m:
            site = m.group(1)
            add(site, "site-operator")
        elif re.fullmatch(r"(?:https?://)[^\s]+", query) or re.fullmatch(r"[\w.-]+\.[a-z]{2,}(?:/\S*)?", query):
            site = query
            add(query, "query-as-url")

        if query and not site:
            for engine in self.req.serp_engines[:6]:
                try:
                    found = await self._serp(engine, query)
                    for url in found:
                        add(url, f"serp:{engine}")
                    await self._send("serp", engine=engine, found=len(found), status="ok")
                except Exception as exc:
                    self.stats.errors += 1
                    await self._send("serp", engine=engine, found=0, status="error",
                                     message=str(exc)[:180])
            self.req.serp_engines  # keep order

        if self.req.use_sitemaps:
            origins = {f"{urlsplit(u).scheme}://{urlsplit(u).netloc}" for u, _ in seeds}
            for origin in list(origins)[:3]:
                for url in await self._sitemap_seeds(origin):
                    add(url, "sitemap")

        if self.req.use_archive and site:
            try:
                resp = await self.client.get("https://web.archive.org/cdx/search/cdx", params=[
                    ("url", f"{site}/*"), ("output", "json"), ("collapse", "urlkey"),
                    ("fl", "original"), ("filter", "statuscode:200"), ("limit", "150")], timeout=12)
                rows = resp.json()
                for row in rows[1:]:
                    add(row[0], "wayback-cdx")
            except Exception:
                await self._send("serp", engine="wayback", found=0, status="error",
                                 message="CDX unavailable")

        for url, _ in seeds[:12]:
            self.allowed_hosts.add(safe_domain(url))
        await self._send("seeds", total=len(seeds),
                         list=[{"url": u, "source": s} for u, s in seeds[:30]])
        return seeds

    # --------------------------------------------------------------------- files
    async def _register_file(self, url: str, referrer: str | None, depth: int) -> Hit | None:
        canon = canonical_url(url)
        if canon in self.files:
            return None
        if len(self.files) >= self.req.max_files:
            return None
        ext, kind, mime, domain = fingerprint(url)
        if ext is None and kind == "page":
            return None
        if self.req.file_types and (ext or "") not in self.req.file_types:
            return None
        head = await self._head(url)
        size = head.get("size")
        if str(head.get("mime") or "").startswith(("text/html",)) and ext:
            return None
        text, text_engine = "", ""
        if self.req.extract_files:
            try:
                if head.get("size") and int(head["size"]) > self.req.max_bytes:
                    raise ValueError("too large")
                status, _ctype, body, fetch_engine = await self._fetch(url)
                if status >= 400:
                    return None
                if body:
                    self.stats.bytes += len(body)
                    text, text_engine = await asyncio.to_thread(file_text, body, url, head.get("mime"))
                    if text:
                        local_index.index_document(canon, url, pretty_name(url), text, text_engine)
                        self.stats.docs_indexed += 1
                        self.stats.bump(text_engine)
            except Exception:
                pass
        deadline = find_deadline(text[:4000]) if text else None
        snippet_bits = [f"{(ext or 'file').upper()} · {pretty_name(url)}"]
        if size:
            from .extract import human_size

            snippet_bits.append(human_size(size) or "")
        if head.get("modified"):
            snippet_bits.append(f"modified {head['modified']}")
        if text:
            snippet_bits.append(truncate(text, 320))
        hit = Hit(
            url=url, title=pretty_name(url), snippet=" · ".join(b for b in snippet_bits if b),
            provider="crawler", provider_name="Fusion Crawler", kind=kind or "document",
            file_ext=ext, mime=head.get("mime") or mime, domain=domain,
            deadline=deadline, tags=("crawled", ext or "file") + (("text-indexed",) if text else ()),
            archive=False, meta={"referrer": referrer, "size": size, "text_engine": text_engine,
                                 "chars": len(text)},
        )
        hit.depth = depth_score(url, ext, False, text[:2000])
        hit.score = 40 + hit.depth * 0.5
        self.files[canon] = hit
        self.stats.files += 1
        await self._send("file", hit=hit.model_dump())
        return hit

    # ---------------------------------------------------------------------- visit
    async def _visit(self, url: str, depth: int) -> list[tuple[str, int]]:
        canon = canonical_url(url)
        if canon in self.visited:
            return []
        self.visited.add(canon)
        if not self._same_host_ok(url):
            return []
        if not await self._allowed(url):
            self.stats.blocked += 1
            await self._send("blocked", url=url, reason="robots.txt")
            return []
        await self._gate(url)
        try:
            status, ctype, body, fetch_engine = await self._fetch(url)
        except Exception as exc:
            self.stats.errors += 1
            await self._send("error", url=url, message=str(exc)[:160])
            return []
        self.stats.bump(fetch_engine)
        if status >= 400:
            await self._send("error", url=url, message=f"HTTP {status}")
            return []
        self.stats.bytes += len(body)
        is_html = "html" in ctype.lower() or (not ctype and b"<html" in body[:600].lower())
        if not is_html:
            await self._register_file(url, None, depth)
            return []

        self.stats.pages += 1
        html = body.decode("utf-8", "replace")
        links, link_engine = await asyncio.to_thread(parse_links, html, url)
        text, text_engine = await asyncio.to_thread(extract_text, html, url)
        meta = await asyncio.to_thread(meta_extract, html)
        title = meta.get("title") or ""
        if not title:
            m = re.search(r"<title[^>]*>(.*?)</title>", html, re.I | re.S)
            title = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", m.group(1))).strip()[:200] if m else url
        self.stats.links += len(links)
        self.stats.bump(link_engine)
        self.stats.bump(text_engine)

        listing = bool(re.search(
            r"(<title[^>]*>\s*index of|<h1[^>]*>\s*index of|parent directory\s*</|directory listing)",
            html[:6000], re.I))
        if listing:
            await self._send("listing", url=url, title=title)

        if text and len(text) > 120:
            local_index.index_document(canon, url, title, text, text_engine)
            self.stats.docs_indexed += 1

        deadline = find_deadline(text[:6000]) if text else None
        opps = opportunity_tags(f"{title} {text[:3000]}")
        if (deadline or len(opps) >= 2) and canon not in self.page_hits:
            self.stats.opportunities += 1
            page_hit = Hit(
                url=url, title=title or url,
                snippet=truncate(text, 340),
                provider="crawler", provider_name="Fusion Crawler",
                kind="opportunity" if deadline else "page",
                file_ext=None, mime="text/html", domain=safe_domain(url),
                deadline=deadline, tags=tuple(dict.fromkeys(["crawled", "page", *opps])),
                meta={"text_engine": text_engine, "chars": len(text)},
            )
            page_hit.depth = depth_score(url, None, False, text[:2000])
            page_hit.score = 35 + page_hit.depth * 0.5
            self.page_hits[canon] = page_hit
            await self._send("pagehit", hit=page_hit.model_dump())

        await self._send("page", url=url, title=title, status=status, depth=depth,
                         links=len(links), text_chars=len(text), link_engine=link_engine,
                         text_engine=text_engine, engine=fetch_engine, listing=listing)

        next_wave: list[tuple[str, int]] = []
        for link in links:
            if FILE_EXT_RE.search(link):
                await self._register_file(link, url, depth + 1)
                continue
            if depth + 1 <= self.req.depth and link not in self.visited and self._same_host_ok(link):
                if len(self.visited) + len(next_wave) < self.req.max_pages * 6:
                    next_wave.append((link, depth + 1))
        return next_wave

    # ------------------------------------------------------------------------ run
    async def run(self) -> dict[str, Any]:
        started = time.time()
        await self._send("status", message="planning seeds", request=self.req.model_dump(
            exclude={"seeds"}) | {"seed_count": len(self.req.seeds)})
        seeds = await self.resolve_seeds()
        if not seeds:
            await self._send("status", message="no seeds — supply a URL, a domain or a query")
            await self.client.aclose()
            return {"stats": self.stats.as_dict(), "files": [], "seeds": []}

        frontier: deque[tuple[str, int]] = deque((url, 0) for url, _ in seeds)
        pages_seen = 0
        while frontier and pages_seen < self.req.max_pages:
            width = min(len(frontier), max(2, self.req.concurrency * 2))
            batch = [frontier.popleft() for _ in range(width)]
            pages_seen += len(batch)
            results = await asyncio.gather(*[self._visit(u, d) for u, d in batch],
                                           return_exceptions=True)
            for result in results:
                if isinstance(result, list):
                    for item in result:
                        if len(frontier) < self.req.max_pages * 6:
                            frontier.append(item)
            await self._send("progress", pages=self.stats.pages, files=self.stats.files,
                             queued=len(frontier), docs=self.stats.docs_indexed)

        await self._send("status", message="closing connections")
        await self.client.aclose()
        stats = self.stats.as_dict()
        stats["walls_ms"] = int((time.time() - started) * 1000)
        hits = sorted(self.files.values(), key=lambda h: (-h.depth, -h.score))
        pages = sorted(self.page_hits.values(), key=lambda h: (-h.depth, -h.score))
        everything = [*hits, *pages]
        await self._send("done", stats=stats,
                         files=[h.model_dump() for h in everything[:400]],
                         seeds=[{"url": u, "source": s} for u, s in seeds[:50]])
        return {"stats": stats, "files": [h.model_dump() for h in everything], "seeds": seeds}
