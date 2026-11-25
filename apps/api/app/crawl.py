"""Nighthawk Fusion Crawler — the primary engine.

No API gatekeeper, no result ceiling, no moderation layer. It plans its own seeds
(SERP harvest, sitemaps, archives, explicit URLs), walks the frontier politely,
dispatches fetching/parsing/extraction to whichever arsenal engines are installed,
then extracts and indexes every file it finds so the vault becomes searchable
from the inside.
"""
from __future__ import annotations

import asyncio
import heapq
import re
import time
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable
from urllib.parse import urljoin, urlsplit

import httpx
from pydantic import BaseModel, Field

from . import local_index, recency
from .arsenal import available_ids
from .config import settings
from .extract import (FILE_MAP, canonical_url, depth_score, fingerprint, find_deadline,
                      human_size, opportunity_tags, pretty_name, safe_domain, truncate)
from .magic import pdf_title, sniff
from .priority import score as url_priority
from . import freshness
from .keyterms import keyphrases
from .schemaorg import extract as schema_extract, guess_fields
from .models import Hit
from .textkit import extract_text, file_text, meta_extract, parse_links_rich

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
    keep_pages: bool = False        # keep every crawled page as a result (deep mode)
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
    cut_older: int = 0
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
            "cut_older": self.cut_older,
            "window_days": recency.Window.current().days,
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
        self._pdf_titles: dict[str, str] = {}
        self.lastmod: dict[str, str] = {}
        # provenance for the deep report: who links here, and how we found it
        self.inbound: dict[str, int] = {}
        self.via: dict[str, str] = {}
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

    def _crawl_delay(self, host: str) -> float:
        parser = self.robots.get(host)
        if isinstance(parser, tuple) and parser[0] == "protego":
            try:
                delay = parser[1].crawl_delay(settings.user_agent)
                return float(delay) if delay else 0.0
            except Exception:
                return 0.0
        return 0.0

    async def _gate(self, url: str) -> None:
        host = urlsplit(url).netloc
        wait_until = self.gates.get(host, 0)
        now = time.monotonic()
        if wait_until > now:
            await asyncio.sleep(min(wait_until - now, 3.0))
        delay = max(self.req.delay, min(self._crawl_delay(host), 3.0))
        self.gates[host] = time.monotonic() + delay

    async def _robots_for(self, url: str) -> Any:
        host = urlsplit(url).netloc
        if host in self.robots:
            return self.robots[host]
        parser = None
        try:
            origin = f"{urlsplit(url).scheme}://{host}"
            resp = await self.client.get(f"{origin}/robots.txt", timeout=6.0)
            if resp.status_code == 200 and resp.text:
                # protego (scrapy's own parser): wildcards, `$` anchors and the
                # longest-match rule, which urllib's parser gets wrong.
                try:
                    from protego import Protego

                    robot = Protego.parse(resp.text)
                    parser = ("protego", robot)
                except Exception:
                    from urllib.robotparser import RobotFileParser

                    fallback = RobotFileParser()
                    fallback.parse(resp.text.splitlines())
                    parser = ("stdlib", fallback)
                await self._send("robots", host=host, rules=len(resp.text.splitlines()),
                                 sitemaps=list(robot.sitemaps) if isinstance(parser, tuple)
                                 and parser[0] == "protego" else [])
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
            if isinstance(parser, tuple):
                kind, robot = parser
                if kind == "protego":
                    return bool(robot.can_fetch(url, settings.user_agent))
                return bool(robot.can_fetch(settings.user_agent, url))
        except Exception:
            return True
        return True

    # ---------------------------------------------------------------------- fetch
    async def _fetch_meta(self, url: str) -> tuple[int, str, bytes, str, dict[str, str]]:
        """Fetch and keep the response headers — they carry the document's clock."""
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
                        return resp.status, ctype, body, "aiohttp", dict(resp.headers)
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
                flat = {k: (v[0] if isinstance(v, list) and v else str(v))
                        for k, v in dict(getattr(response, "headers", {}) or {}).items()}
                ctype = flat.get("content-type") or flat.get("Content-Type") or ""
                return response.status_code, ctype, body, "crawlee", flat
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
            return (resp.status_code, resp.headers.get("content-type", ""), b"".join(chunks),
                    "httpx", dict(resp.headers))

    async def _fetch(self, url: str) -> tuple[int, str, bytes, str]:
        status, ctype, body, engine, _headers = await self._fetch_meta(url)
        return status, ctype, body, engine

    def _sync_fetch(self, url: str, engine: str) -> tuple[int, str, bytes, str, dict[str, str]]:
        if engine == "cloudscraper":
            import cloudscraper

            resp = cloudscraper.create_scraper().get(url, timeout=settings.provider_timeout)
            return (resp.status_code, resp.headers.get("content-type", ""),
                    resp.content[: self.req.max_bytes], "cloudscraper", dict(resp.headers))
        if engine == "hrequests":
            import hrequests

            resp = hrequests.get(url, timeout=settings.provider_timeout)
            return (resp.status_code, resp.headers.get("content-type", ""),
                    resp.content[: self.req.max_bytes], "hrequests", dict(resp.headers))
        import mechanicalsoup

        browser = mechanicalsoup.StatefulBrowser()
        resp = browser.open(url, timeout=settings.provider_timeout)
        html = str(resp.soup).encode()
        return (resp.status_code, resp.headers.get("content-type", ""),
                html[: self.req.max_bytes], "mechanicalsoup", dict(resp.headers))

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

    def _note_inbound(self, url: str) -> None:
        canon = canonical_url(url)
        self.inbound[canon] = self.inbound.get(canon, 0) + 1

    def _remember_lastmod(self, xml: str) -> None:
        """Keep ``<url><loc>…</loc><lastmod>…</lastmod></url>`` pairs.

        Sitemaps are the only place a site tells you, in bulk, when each page
        changed. That clock is what makes a focused crawl able to lead with the
        newest documents instead of the most-linked ones.
        """
        for match in re.finditer(
                r"<url>.*?<loc>\s*([^<\s]+)\s*</loc>.*?<lastmod>\s*([^<\s]+)\s*</lastmod>",
                xml, re.I | re.S):
            url, stamp = match.group(1), match.group(2)
            if freshness.parse(stamp):
                self.lastmod[canonical_url(url)] = stamp

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
                self._remember_lastmod(resp.text)
                if "<sitemapindex" in resp.text.lower():
                    for sub in locs[:3]:
                        try:
                            sub_resp = await self.client.get(sub, timeout=8.0)
                            sub_locs = re.findall(r"<loc>\s*([^<\s]+)\s*</loc>", sub_resp.text, re.I)
                            urls += sub_locs
                            self._remember_lastmod(sub_resp.text)
                        except Exception:
                            continue
                else:
                    urls += locs
                await self._send("sitemap", url=sm_url, urls=len(urls))
                if len(urls) >= cap:
                    break
            except Exception:
                continue
        def recency_key(url: str) -> float:
            stamp = freshness.parse(self.lastmod.get(canonical_url(url)))
            return -(stamp.timestamp() if stamp else 0.0)

        urls = list(dict.fromkeys(urls))
        urls.sort(key=recency_key)      # sitemap with lastmod → freshest seeds first
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

        for url, source in seeds:
            self.via.setdefault(canonical_url(url), source)
        for url, _ in seeds[:12]:
            self.allowed_hosts.add(safe_domain(url))
        await self._send("seeds", total=len(seeds),
                         list=[{"url": u, "source": s} for u, s in seeds[:30]])
        return seeds

    # --------------------------------------------------------------------- files
    def _in_window(self, hit: Hit) -> bool:
        """The same recency window a search uses, applied to what a crawl keeps.

        An undated page is kept (the site may simply not publish a clock); a page
        that says it is from 2014 is not, however it was reached.
        """
        if recency.Window.current().keeps(hit):
            return True
        self.stats.cut_older += 1
        return False

    async def _register_file(self, url: str, referrer: str | None, depth: int,
                             headers: dict[str, str] | None = None) -> Hit | None:
        canon = canonical_url(url)
        if canon in self.files:
            return None
        if len(self.files) >= self.req.max_files:
            return None
        ext, kind, mime, domain = fingerprint(url)
        if kind == "page" or ext in ("html", "htm", "php", "asp", "aspx", "jsp", "shtml"):
            return None  # pages belong to page_hits, not the file list
        if self.req.file_types and (ext or "") not in self.req.file_types:
            return None

        head = await self._head(url)
        size = head.get("size")
        if str(head.get("mime") or "").startswith("text/html") and ext:
            return None  # an .pdf that answers text/html is a login wall, not a document

        text, text_engine, sniffed, body_len = "", "", None, 0
        if self.req.extract_files:
            try:
                if head.get("size") and int(head["size"]) > self.req.max_bytes:
                    raise ValueError("too large")
                status, _ctype, body, _engine = await self._fetch(url)
                if status >= 400:
                    return None
                if body:
                    body_len = len(body)
                    self.stats.bytes += len(body)
                    sniffed_ext, sniffed_mime = await asyncio.to_thread(sniff, body)
                    if sniffed_ext and sniffed_ext != "html":
                        if sniffed_ext != ext:
                            sniffed = f"{ext or 'none'}→{sniffed_ext}"
                        ext = sniffed_ext
                        kind, mime = FILE_MAP.get(ext, (kind, sniffed_mime or mime))
                        domain = safe_domain(url)
                    text, text_engine = await asyncio.to_thread(
                        file_text, body, url, head.get("mime") or mime)
                    if text:
                        local_index.index_document(canon, url, pretty_name(url), text, text_engine)
                        self.stats.docs_indexed += 1
                        self.stats.bump(text_engine)
                    if ext == "pdf":
                        guessed = await asyncio.to_thread(pdf_title, body)
                        if guessed and domain not in pretty_name(url):
                            self._pdf_titles[canon] = guessed
            except Exception:
                pass

        size = size or (body_len or None)
        published = (freshness.from_headers(headers or {})
                     or freshness.parse(head.get("modified"))
                     or freshness.parse(self.lastmod.get(canonical_url(url))))
        deadline = find_deadline(text[:4000]) if text else None
        title = self._pdf_titles.get(canon) or pretty_name(url)
        snippet_bits = [f"{(ext or 'file').upper()} · {title}"]
        if size:
            snippet_bits.append(human_size(size) or "")
        if sniffed:
            snippet_bits.append(f"magic says {sniffed}")
        if text:
            snippet_bits.append(truncate(text, 320))
        hit = Hit(
            url=url, title=title, snippet=" · ".join(b for b in snippet_bits if b),
            provider="crawler", provider_name="Fusion Crawler", kind=kind or "document",
            file_ext=ext, mime=head.get("mime") or mime, domain=domain,
            deadline=deadline, tags=("crawled", ext or "file") + (("text-indexed",) if text else ()),
            archive=False, meta={"referrer": referrer, "size": size, "text_engine": text_engine,
                                 "chars": len(text), "sniffed": sniffed,
                                 "via": self.via.get(canonical_url(url), "link"),
                                 "inbound": self.inbound.get(canonical_url(url), 0),
                                 "crawl_depth": depth},
        )
        hit.size = int(size) if size and str(size).isdigit() else None
        hit.sniffed = sniffed
        hit.mime = head.get("mime") or mime
        hit.schema_type = None  # files carry no schema.org type of their own
        _stamp = freshness.describe(published or freshness.utcnow())
        hit.published_at = _stamp["published_at"]
        hit.age_seconds = _stamp["age_seconds"]
        hit.age_human = _stamp["age_human"]
        hit.freshness = _stamp["freshness"]
        hit.age_source = "published" if published else "first_seen"
        hit.first_seen = freshness.utcnow().isoformat()
        if text:
            try:
                hit.keyphrases = await asyncio.to_thread(keyphrases, text, 5)
            except Exception:
                hit.keyphrases = []
        hit.depth = depth_score(url, ext, False, text[:2000])
        hit.score = 40 + hit.depth * 0.5
        if not self._in_window(hit):
            return None
        self.files[canon] = hit
        self.stats.files += 1
        if sniffed:
            self.stats.bump("magic-sniff")
        await self._send("file", hit=hit.model_dump())
        return hit

    # ---------------------------------------------------------------------- visit
    async def _visit(self, url: str, depth: int, anchor: str = "") -> list[tuple]:
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
            status, ctype, body, fetch_engine, headers = await self._fetch_meta(url)
        except Exception as exc:
            self.stats.errors += 1
            await self._send("error", url=url, message=str(exc)[:160])
            return []
        self.stats.bump(fetch_engine)
        if status >= 400:
            self.stats.errors += 1        # an HTTP failure is an error too, and
            await self._send("error", url=url, message=f"HTTP {status}")   # the
            return []                      # report has to say so, not just the log
        self.stats.bytes += len(body)
        is_html = "html" in ctype.lower() or (not ctype and b"<html" in body[:600].lower())
        if not is_html:
            await self._register_file(url, None, depth, headers=headers)
            return []

        self.stats.pages += 1
        html = body.decode("utf-8", "replace")
        links = await asyncio.to_thread(parse_links_rich, html, url)
        text, text_engine = await asyncio.to_thread(extract_text, html, url)
        meta = await asyncio.to_thread(meta_extract, html)
        published, modified, clock_source = await asyncio.to_thread(
            freshness.from_html, html, url)
        if published is None:
            published = freshness.from_headers(headers)
            clock_source = clock_source or ("headers" if published else "")
        if published is None:
            lastmod = self.lastmod.get(canonical_url(url))
            if lastmod:
                published = freshness.parse(lastmod)
                clock_source = "sitemap" if published else ""
        records = await asyncio.to_thread(schema_extract, html, url)
        best = next((r for r in records if r["category"] == "opportunity"), None)
        title = meta.get("title") or ""
        if not title:
            m = re.search(r"<title[^>]*>(.*?)</title>", html, re.I | re.S)
            title = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", m.group(1))).strip()[:200] if m else url

        self.stats.links += len(links)
        self.stats.bump("selectolax")
        self.stats.bump(text_engine)
        if records:
            self.stats.bump("schema.org")

        listing = bool(re.search(
            r"(<title[^>]*>\s*index of|<h1[^>]*>\s*index of|parent directory\s*</|directory listing)",
            html[:6000], re.I))
        if listing:
            await self._send("listing", url=url, title=title)

        if text and len(text) > 120:
            local_index.index_document(canon, url, title, text, text_engine)
            self.stats.docs_indexed += 1

        guessed = await asyncio.to_thread(guess_fields, text[:6000]) if text else {}
        if guessed:
            best = {**guessed, **(best or {})}   # JSON-LD wins over prose
        deadline = find_deadline(text[:6000]) if text else None
        explicit_deadline = None
        if best and best.get("deadline"):
            explicit_deadline = find_deadline("", explicit=best["deadline"])
        if explicit_deadline:
            deadline = explicit_deadline
        opps = opportunity_tags(f"{title} {text[:3000]}")
        structured = bool(best)
        if (self.req.keep_pages or deadline or len(opps) >= 2 or structured) and canon not in self.page_hits:
            self.stats.opportunities += 1
            page_hit = Hit(
                url=url, title=title or url,
                snippet=truncate(text, 340),
                provider="crawler", provider_name="Fusion Crawler",
                kind="opportunity" if (deadline or structured or len(opps) >= 2) else "page",
                file_ext=None, mime="text/html", domain=safe_domain(url),
                deadline=deadline,
                funder=(best or {}).get("organization") or None,
                amount=(best or {}).get("amount") or None,
                currency=(best or {}).get("currency") or None,
                location=(best or {}).get("location") or None,
                structured=(str(best["type"]).title() if best and best.get("type") else None),
                tags=tuple(dict.fromkeys(
                    ["crawled", "page", *(opps)]
                    + ([best["type"]] if best and best.get("type") else [])
                    + ([best["keywords"].split(",")[0].strip()] if best and best.get("keywords") else []))),
                meta={"text_engine": text_engine, "chars": len(text),
                      "via": self.via.get(canon, "link"),
                      "inbound": self.inbound.get(canon, 0),
                      "crawl_depth": depth, "listing": listing,
                      "structured": records[:3],
                      "organization": (best or {}).get("organization"),
                      "amount": (best or {}).get("amount"),
                      "currency": (best or {}).get("currency")},
            )
            page_hit.schema_type = page_hit.structured
            _stamp = freshness.describe(published or freshness.utcnow())
            page_hit.published_at = _stamp["published_at"]
            page_hit.age_seconds = _stamp["age_seconds"]
            page_hit.age_human = _stamp["age_human"]
            page_hit.freshness = _stamp["freshness"]
            page_hit.age_source = "published" if published else "first_seen"
            page_hit.first_seen = freshness.utcnow().isoformat()
            page_hit.meta["published_source"] = clock_source
            page_hit.depth = depth_score(url, None, False, text[:2000])
            page_hit.score = 35 + page_hit.depth * 0.5 + (12 if structured else 0)
            if self._in_window(page_hit):
                self.page_hits[canon] = page_hit
                await self._send("pagehit", hit=page_hit.model_dump())

        if records:
            await self._send("structured", url=url, count=len(records),
                             types=sorted({r["type"] for r in records})[:6])

        await self._send("page", url=url, title=title, status=status, depth=depth,
                         links=len(links), text_chars=len(text), link_engine="selectolax",
                         text_engine=text_engine, engine=fetch_engine, listing=listing,
                         structured=len(records))

        frontier: list[tuple] = []
        terms = [t for t in self.req.query.lower().split() if len(t) > 3][:5]
        for link in links:
            target = link["url"]
            self._note_inbound(target)
            if FILE_EXT_RE.search(target):
                await self._register_file(target, url, depth + 1)
                continue
            if depth + 1 > self.req.depth or target in self.visited:
                continue
            if not self._same_host_ok(target):
                continue
            priority = url_priority(target, link.get("anchor", ""), terms, depth + 1,
                                    from_sitemap=False, same_host=True)
            frontier.append((priority, target, depth + 1, link.get("anchor", "")))
        return frontier

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

        terms = [t for t in (self.req.query or "").lower().split() if len(t) > 3][:5]
        heap: list[tuple] = []
        seq = 0
        for url, source in seeds:
            priority = url_priority(url, "", terms, 0, from_sitemap=(source == "sitemap"))
            heapq.heappush(heap, (-priority, seq, url, 0, ""))
            seq += 1

        pages_seen = 0
        while heap and pages_seen < self.req.max_pages:
            width = min(len(heap), max(2, self.req.concurrency * 2))
            batch = [heapq.heappop(heap) for _ in range(width)]
            pages_seen += len(batch)
            results = await asyncio.gather(
                *[self._visit(item[2], item[3], item[4]) for item in batch],
                return_exceptions=True)
            for result in results:
                if isinstance(result, BaseException):
                    self.stats.errors += 1
                    await self._send("error", url="", message=f"{type(result).__name__}: {result}"[:160])
                    continue
                if not isinstance(result, list):
                    continue
                for entry in result:
                    if len(heap) < self.req.max_pages * 8:
                        heapq.heappush(heap, (-entry[0], seq, entry[1], entry[2], entry[3]))
                        seq += 1
            await self._send("progress", pages=self.stats.pages, files=self.stats.files,
                             queued=len(heap), docs=self.stats.docs_indexed,
                             opportunities=self.stats.opportunities)

        await self._send("status", message="closing connections")
        await self.client.aclose()
        stats = self.stats.as_dict()
        stats["walls_ms"] = int((time.time() - started) * 1000)
        hits = sorted(self.files.values(), key=lambda h: (-h.depth, -h.score))
        pages = sorted(self.page_hits.values(), key=lambda h: (-h.depth, -h.score))
        everything = [*hits, *pages]
        try:
            local_index.upsert_hits(everything)   # crawl discoveries join the vault
        except Exception:
            pass
        await self._send("done", stats=stats,
                         files=[h.model_dump() for h in everything[:400]],
                         seeds=[{"url": u, "source": s} for u, s in seeds[:50]])
        return {"stats": stats, "files": [h.model_dump() for h in everything], "seeds": seeds}
