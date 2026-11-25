"""The buried-file layer: web archives and crawl indexes.

Mainstream engines drop PDFs, spreadsheets, dumps and dead pages. These adapters
read the crawl indexes directly, so they still find what Google forgot.
"""
from __future__ import annotations

import re
import time
from typing import Any
from urllib.parse import quote

from .base import HuntContext, Provider, RawHit, clean, get_json

EXT_RE = r"\.(?:pdf|docx?|xlsx?|pptx?|odt|ods|csv|tsv|zip|7z|tar|gz|json|xml|geojson|sql|sqlite3?|db|bak|env|log|txt|md|kml)$"
FILE_RE = re.compile(EXT_RE, re.I)


def _score_row(url: str, terms: list[str]) -> int:
    low = url.lower()
    hits = sum(1 for t in terms if len(t) > 2 and t in low)
    return hits


class CommonCrawl(Provider):
    id, name, family, layer = "commoncrawl", "Common Crawl Index", "archive", "archive"
    description = "Raw crawl index (petabytes). Lists files engines never surface."
    lenses = ("files", "datasets", "opportunities", "applications", "exposed", "all")
    homepage = "https://index.commoncrawl.org/"
    weight = 1.6
    _coll: tuple[str, float] | None = None

    async def collection(self, ctx: HuntContext) -> str:
        if CommonCrawl._coll and time.time() - CommonCrawl._coll[1] < 21600:
            return CommonCrawl._coll[0]
        try:
            data = await get_json(ctx, "https://index.commoncrawl.org/collinfo.json")
            cid = data[0]["id"]
        except Exception:
            cid = "CC-MAIN-2025-30"
        CommonCrawl._coll = (cid, time.time())
        return cid

    async def hunt(self, ctx: HuntContext) -> list[RawHit]:
        coll = await self.collection(ctx)
        out: list[RawHit] = []
        terms = [t for t in ctx.plan.terms.lower().split() if len(t) > 3][:4]
        for domain in ctx.domains[:4]:
            params = {
                "url": f"{domain}/*", "output": "json", "collapse": "urlkey",
                "filter": f"~url:{EXT_RE}", "limit": min(ctx.limit * 8, 160),
            }
            try:
                resp = await ctx.client.get(
                    f"https://index.commoncrawl.org/{coll}-index", params=params)
                if resp.status_code >= 400:
                    continue
                for line in resp.text.splitlines()[: params["limit"]]:
                    try:
                        row = __import__("json").loads(line)
                    except Exception:
                        continue
                    url = row.get("url") or ""
                    if not FILE_RE.search(url):
                        continue
                    keep = _score_row(url, terms)
                    out.append(RawHit(
                        url=url, title="", archive=True, kind="document",
                        snippet=f"Archived {row.get('mime') or 'file'} · crawl {coll}",
                        published=str(row.get("timestamp") or "")[:8],
                        tags=("crawl-index", "commoncrawl") + (("term-match",) if keep else ()),
                        meta={"mime": row.get("mime"), "status": row.get("status"),
                              "term_hits": keep},
                    ))
            except Exception:
                continue
        return out


class Wayback(Provider):
    id, name, family, layer = "wayback", "Wayback CDX", "archive", "archive"
    description = "27 years of URL history — including files deleted from the live web."
    lenses = ("files", "datasets", "opportunities", "applications", "exposed", "all")
    homepage = "https://web.archive.org/"
    weight = 1.55

    async def hunt(self, ctx: HuntContext) -> list[RawHit]:
        out: list[RawHit] = []
        terms = [t for t in ctx.plan.terms.lower().split() if len(t) > 3][:4]
        for domain in ctx.domains[:4]:
            params = [
                ("url", f"{domain}/*"), ("output", "json"),
                ("fl", "timestamp,original,mimetype,statuscode,length"),
                ("collapse", "urlkey"), ("filter", "statuscode:200"),
                ("filter", f"~original:{EXT_RE}"), ("limit", str(min(ctx.limit * 8, 200))),
                ("from", "2015"),
            ]
            try:
                resp = await ctx.client.get("https://web.archive.org/cdx/search/cdx", params=params)
                if resp.status_code >= 400:
                    continue
                rows = resp.json()
            except Exception:
                continue
            if not isinstance(rows, list) or len(rows) < 2:
                continue
            header = rows[0]
            for row in rows[1:]:
                rec = dict(zip(header, row))
                url = rec.get("original") or ""
                if not FILE_RE.search(url):
                    continue
                stamp = str(rec.get("timestamp") or "")
                out.append(RawHit(
                    url=url, title="", archive=True,
                    snippet=f"Archived {rec.get('mimetype') or 'file'} · {rec.get('length') or '?'} bytes",
                    published=f"{stamp[:4]}-{stamp[4:6]}-{stamp[6:8]}" if len(stamp) >= 8 else None,
                    tags=("wayback", "deleted-or-buried") + (("term-match",)
                           if _score_row(url, terms) else ()),
                    meta={"timestamp": stamp, "mime": rec.get("mimetype"),
                          "snapshot": f"https://web.archive.org/web/{stamp}/{url}"},
                ))
        return out


class InternetArchive(Provider):
    id, name, family, layer = "internetarchive", "Internet Archive", "archive", "archive"
    description = "Digital library: texts, datasets, audio, software, ephemera."
    lenses = ("files", "datasets", "all")
    homepage = "https://archive.org/"
    weight = 1.2

    async def hunt(self, ctx: HuntContext) -> list[RawHit]:
        params = [
            ("q", f'({ctx.plan.terms}) AND (mediatype:texts OR mediatype:data OR mediatype:software)'),
            ("fl[]", "identifier"), ("fl[]", "title"), ("fl[]", "mediatype"),
            ("fl[]", "date"), ("fl[]", "description"), ("rows", str(min(ctx.limit, 25))),
            ("page", "1"), ("output", "json"), ("sort[]", "downloads desc"),
        ]
        data = await get_json(ctx, "https://archive.org/advancedsearch.php", params=params)
        docs = ((data.get("response") or {}).get("docs")) or []

        def one(value) -> str:
            # archive.org gives the same field as a string on one item and a
            # list on the next; a list used to crash the whole engine
            if isinstance(value, list):
                return " ".join(str(item) for item in value if item)
            return "" if value is None else str(value)

        out: list[RawHit] = []
        for doc in docs[:ctx.limit]:
            if not isinstance(doc, dict):
                continue
            identifier = one(doc.get("identifier"))
            if not identifier:
                continue
            out.append(RawHit(
                url=f"https://archive.org/details/{identifier}",
                title=clean(one(doc.get("title"))) or identifier,
                snippet=clean(one(doc.get("description"))),
                kind="document", published=one(doc.get("date")) or None, archive=True,
                tags=("internet-archive", one(doc.get("mediatype"))),
                meta={"mediatype": one(doc.get("mediatype"))},
            ))
        return out


class ArquivoPT(Provider):
    id, name, family, layer = "arquivo", "Arquivo.pt", "archive", "archive"
    description = "Portuguese web archive with full-text search over 50M pages."
    lenses = ("files", "all", "opportunities")
    homepage = "https://arquivo.pt/"
    weight = 0.9

    async def hunt(self, ctx: HuntContext) -> list[RawHit]:
        data = await get_json(ctx, "https://arquivo.pt/textsearch", params={
            "q": ctx.plan.terms, "maxItems": min(ctx.limit, 20)})
        out = []
        for item in (data.get("response_items") or [])[:ctx.limit]:
            out.append(RawHit(
                url=item.get("linkToArchive") or item.get("originalURL") or "",
                title=clean(item.get("title")), snippet=clean(item.get("snippet")),
                archive=True, published=str(item.get("tstamp") or "")[:8],
                tags=("arquivo.pt",), meta={"original": item.get("originalURL")},
            ))
        return out
