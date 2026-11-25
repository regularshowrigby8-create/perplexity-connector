"""The general web engines that answer without a key.

This module exists because of a measured failure, not a preference. A live run
of "diary of a wimpy kid pdf" on a machine with an open network asked 80
engines and got **no general web engine to answer at all** — every one of them
(Google CSE, Bing, Brave, Qwant, Mojeek, MetaGer) was key-gated. What was left
were scholarly, grant and registry APIs, which do not index books. The books
were on the open web the whole time: DuckDuckGo and Bing both put
`archive.org/download/.../book01.pdf` and Scribd at the top.

These three are scraped from their public HTML/RSS, so they need no account:
Bing's RSS output, DuckDuckGo's lite endpoint, and Mojeek's own index. Each one
is a real engine answering the query as typed — not an operator trick — so the
comparison with what a person sees in a browser stays honest.

They are best-effort by design: a markup change upstream makes a parser return
nothing, which the engine reports as an empty source rather than an error.
"""
from __future__ import annotations

import xml.etree.ElementTree as ElementTree
from typing import Any

from .base import HuntContext, Provider, RawHit, clean

UA = ("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) "
      "Chrome/124.0 Safari/537.36")

# The words a person actually typed, type word included: a general engine is
# good at "foo pdf" and its own ranking knows what to do with it.
def _query(ctx: HuntContext) -> str:
    return (getattr(ctx.plan, "query", "") or getattr(ctx.plan, "terms", "") or "").strip()


def _results(items: list[dict[str, Any]], limit: int, tag: str) -> list[RawHit]:
    out: list[RawHit] = []
    seen: set[str] = set()
    for item in items:
        url = str(item.get("url") or "").strip()
        if not url.startswith("http") or url in seen:
            continue
        seen.add(url)
        out.append(RawHit(
            url=url,
            title=clean(item.get("title") or url, 240),
            snippet=clean(item.get("snippet"), 320),
            published=item.get("published") or None,
            tags=("web", tag),
            meta={"engine": tag},
        ))
        if len(out) >= limit:
            break
    return out


# ---------------------------------------------------------------------- parsers
def parse_bing_rss(text: str) -> list[dict[str, Any]]:
    """Bing's RSS output: one <item> per result, no JavaScript, no key."""
    try:
        root = ElementTree.fromstring(text.strip())
    except ElementTree.ParseError:
        return []
    out: list[dict[str, Any]] = []
    for item in root.iter("item"):
        out.append({
            "title": (item.findtext("title") or "").strip(),
            "url": (item.findtext("link") or "").strip(),
            "snippet": (item.findtext("description") or "").strip(),
            "published": (item.findtext("pubDate") or "").strip(),
        })
    return out


def parse_ddg_lite(html: str) -> list[dict[str, Any]]:
    """DuckDuckGo's lite page.

    One table row per result: the link carries `result-link`, the snippet sits
    in `result-snippet`. Anything that does not match falls back to every
    outbound link in a row, because a markup change should cost precision, not
    the whole source.
    """
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(html, "html.parser")
    out: list[dict[str, Any]] = []
    links = soup.select("a.result-link")
    if not links:
        links = [a for a in soup.find_all("a", href=True)
                 if str(a.get("href", "")).startswith("http")
                 and "duckduckgo.com" not in a["href"]]
    for link in links:
        href = str(link.get("href") or "")
        if "uddg=" in href:                       # redirect wrapper: /l/?uddg=<url>
            from urllib.parse import parse_qs, unquote, urlsplit
            query = parse_qs(urlsplit(href).query).get("uddg")
            if query:
                href = unquote(query[0])
        row = link.find_parent("tr") or link.parent
        snippet = ""
        if row is not None:
            node = row.select_one(".result-snippet") or row.select_one("td.result-snippet")
            snippet = node.get_text(" ", strip=True) if node else row.get_text(" ", strip=True)
        out.append({"title": link.get_text(" ", strip=True), "url": href, "snippet": snippet[:320]})
    return out


def parse_mojeek(html: str) -> list[dict[str, Any]]:
    """Mojeek's own index, which is not a Bing or Google reseller."""
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(html, "html.parser")
    out: list[dict[str, Any]] = []
    for item in soup.select("ul.results-standard li, .results li"):
        link = item.select_one("a.title") or item.select_one("h2 a") or item.select_one("a[href^='http']")
        if not link:
            continue
        snippet = item.select_one("p.s") or item.select_one(".s")
        out.append({
            "title": link.get_text(" ", strip=True),
            "url": str(link.get("href") or ""),
            "snippet": snippet.get_text(" ", strip=True) if snippet else "",
        })
    return out


# -------------------------------------------------------------------- providers
class BingNews(Provider):
    id, name, family, layer = "bing-rss", "Bing (public RSS)", "general", "keyless"
    description = "Bing's own index through its public RSS output — no key, no JavaScript."
    lenses = ("all", "files", "opportunities", "exposed")
    homepage = "https://www.bing.com/"
    weight = 3.4
    rate_note = "public RSS; be gentle"

    async def hunt(self, ctx: HuntContext) -> list[RawHit]:
        query = _query(ctx)
        if not query:
            return []
        try:
            resp = await ctx.client.get("https://www.bing.com/search", params={
                "q": query, "format": "rss", "count": min(max(ctx.limit, 10), 30),
            }, headers={"User-Agent": UA})
            if resp.status_code >= 400:
                return []
            return _results(parse_bing_rss(resp.text), ctx.limit, "bing")
        except Exception:
            return []


class DuckDuckGoLite(Provider):
    id, name, family, layer = "ddg-lite", "DuckDuckGo (lite)", "general", "keyless"
    description = "DuckDuckGo's no-JavaScript page — its own index, no account needed."
    lenses = ("all", "files")
    homepage = "https://duckduckgo.com/"
    weight = 3.3
    rate_note = "public lite page; may rate-limit"

    async def hunt(self, ctx: HuntContext) -> list[RawHit]:
        query = _query(ctx)
        if not query:
            return []
        try:
            resp = await ctx.client.get("https://lite.duckduckgo.com/lite/", params={"q": query},
                                        headers={"User-Agent": UA})
            if resp.status_code >= 400:
                return []
            return _results(parse_ddg_lite(resp.text), ctx.limit, "duckduckgo")
        except Exception:
            return []


class MojeekHTML(Provider):
    id, name, family, layer = "mojeek-html", "Mojeek (public page)", "general", "keyless"
    description = "Mojeek's independent index through its public results page."
    lenses = ("all", "files")
    homepage = "https://www.mojeek.com/"
    weight = 2.6
    rate_note = "public page; be gentle"

    async def hunt(self, ctx: HuntContext) -> list[RawHit]:
        query = _query(ctx)
        if not query:
            return []
        try:
            resp = await ctx.client.get("https://www.mojeek.com/search", params={"q": query},
                                        headers={"User-Agent": UA})
            if resp.status_code >= 400:
                return []
            return _results(parse_mojeek(resp.text), ctx.limit, "mojeek")
        except Exception:
            return []


KEYLESS = [BingNews(), DuckDuckGoLite(), MojeekHTML()]
