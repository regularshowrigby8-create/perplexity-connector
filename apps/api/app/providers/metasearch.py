"""Privacy metasearch engines and independent crawlers."""
from __future__ import annotations

from urllib.parse import quote_plus

from bs4 import BeautifulSoup

from .base import HuntContext, Provider, RawHit, clean, get_json


class _HtmlEngine(Provider):
    opt_in = True
    needs_network = True

    async def fetch_html(self, ctx: HuntContext, url: str) -> BeautifulSoup:
        resp = await ctx.client.get(url, headers={"Accept": "text/html"})
        resp.raise_for_status()
        return BeautifulSoup(resp.text, "html.parser")


class Whoogle(_HtmlEngine):
    id, name, family = "whoogle", "Whoogle", "metasearch"
    description = "Self-hosted privacy front-end for Google results."
    homepage = "https://github.com/benbusby/whoogle-search"
    requires = ("whoogle_url",)
    lenses = ("all", "files", "opportunities")

    async def hunt(self, ctx: HuntContext) -> list[RawHit]:
        base = self.key(ctx, "whoogle_url").rstrip("/")
        soup = await self.fetch_html(ctx, f"{base}/search?q={quote_plus(ctx.plan.query)}")
        out = []
        for block in soup.select("div.result, div.g")[:ctx.limit]:
            link = block.find("a", href=True)
            if not link:
                continue
            title = clean(link.get_text())
            snippet = clean(block.get_text(" "), 400)
            out.append(RawHit(url=link["href"], title=title or link["href"], snippet=snippet))
        return out


class LibreX(_HtmlEngine):
    id, name, family = "librex", "LibreX", "metasearch"
    description = "Lightweight metasearch front-end (Ahmia/Kagi-free stack)."
    homepage = "https://github.com/hnhx/librex"
    requires = ("librex_url",)
    lenses = ("all", "files")

    async def hunt(self, ctx: HuntContext) -> list[RawHit]:
        base = self.key(ctx, "librex_url").rstrip("/")
        soup = await self.fetch_html(ctx, f"{base}/search.php?q={quote_plus(ctx.plan.query)}")
        out = []
        for art in soup.select("article")[:ctx.limit]:
            link = art.find("a", href=True)
            if not link:
                continue
            out.append(RawHit(url=link["href"], title=clean(link.get_text()),
                              snippet=clean(art.get_text(" "), 400)))
        return out


class Forget(_HtmlEngine):
    id, name, family = "4get", "4get", "metasearch"
    description = "Multi-backend metasearch proxy with a clean JSON API."
    homepage = "https://github.com/4get-project/4get"
    requires = ("forget_url",)
    lenses = ("all", "files", "opportunities")

    async def hunt(self, ctx: HuntContext) -> list[RawHit]:
        base = self.key(ctx, "forget_url").rstrip("/")
        data = await get_json(ctx, f"{base}/api/v1/web", params={"s": ctx.plan.query, "n": ctx.limit})
        return [RawHit(url=item.get("url", ""), title=clean(item.get("title")),
                       snippet=clean(item.get("snippet")))
                for item in (data.get("web") or [])[:ctx.limit]]


class YaCy(_HtmlEngine):
    id, name, family = "yacy", "YaCy", "p2p"
    description = "Peer-to-peer distributed index; no central crawler."
    homepage = "https://yacy.net/"
    requires = ("yacy_url",)
    lenses = ("all", "files", "datasets")

    async def hunt(self, ctx: HuntContext) -> list[RawHit]:
        base = self.key(ctx, "yacy_url").rstrip("/")
        data = await get_json(ctx, f"{base}/yacysearch.json", params={
            "query": ctx.plan.query, "maximumRecords": ctx.limit, "resource": "global"})
        channels = (data.get("channels") or [{}])[0].get("items") or []
        return [RawHit(url=item.get("link", ""), title=clean(item.get("title")),
                       snippet=clean(item.get("description")))
                for item in channels[:ctx.limit]]


class Mojeek(Provider):
    id, name, family, layer = "mojeek", "Mojeek", "independent", "remote"
    description = "Independent UK crawler with its own index (no Google/Bing)."
    homepage = "https://www.mojeek.com/"
    requires = ("mojeek_api_key",)
    lenses = ("all", "files", "opportunities")
    weight = 1.2

    async def hunt(self, ctx: HuntContext) -> list[RawHit]:
        data = await get_json(ctx, "https://www.mojeek.com/search", params={
            "q": ctx.plan.query, "fmt": "json", "t": min(ctx.limit, 20)},
            headers={"Authorization": f"Bearer {self.key(ctx, 'mojeek_api_key')}"})
        return [RawHit(url=r.get("url", ""), title=clean(r.get("title")),
                       snippet=clean(r.get("desc")))
                for r in (data.get("results") or [])[:ctx.limit]]


class Qwant(Provider):
    id, name, family, layer = "qwant", "Qwant", "independent", "remote"
    description = "European independent index (Bing-fed web results)."
    homepage = "https://www.qwant.com/"
    requires = ("qwant_api_key",)
    lenses = ("all", "files")

    async def hunt(self, ctx: HuntContext) -> list[RawHit]:
        data = await get_json(ctx, "https://api.qwant.com/v3/search/web", params={
            "q": ctx.plan.query, "count": min(ctx.limit, 20), "locale": "en_GB",
            "offset": 0, "device": "desktop", "safesearch": 0,
        }, headers={"Authorization": f"Bearer {self.key(ctx, 'qwant_api_key')}"})
        items = (((data.get("data") or {}).get("result") or {}).get("items")) or []
        return [RawHit(url=i.get("url", ""), title=clean(i.get("title")),
                       snippet=clean(i.get("desc")))
                for i in items[:ctx.limit]]


class MetaGer(Provider):
    id, name, family, layer = "metager", "MetaGer", "metasearch", "remote"
    description = "German non-profit metasearch with its own index."
    homepage = "https://metager.org/"
    requires = ("metager_api_key",)
    lenses = ("all", "files", "opportunities")

    async def hunt(self, ctx: HuntContext) -> list[RawHit]:
        data = await get_json(ctx, "https://api.metager.org/api/v1/meta/search", params={
            "q": ctx.plan.query, "key": self.key(ctx, "metager_api_key"),
            "count": min(ctx.limit, 20), "format": "json"})
        return [RawHit(url=r.get("link", ""), title=clean(r.get("title")),
                       snippet=clean(r.get("snippet")))
                for r in (data.get("results") or [])[:ctx.limit]]


class Wiby(_HtmlEngine):
    id, name, family = "wiby", "Wiby", "independent"
    description = "Hand-curated index of old-web, non-commercial pages."
    homepage = "https://wiby.me/"
    lenses = ("all", "files")

    async def hunt(self, ctx: HuntContext) -> list[RawHit]:
        soup = await self.fetch_html(ctx, f"https://wiby.me/?q={quote_plus(ctx.plan.query)}")
        out = []
        for block in soup.select("div#main div, div.result")[:ctx.limit]:
            link = block.find("a", href=True)
            if link and link["href"].startswith("http"):
                out.append(RawHit(url=link["href"], title=clean(link.get_text()),
                                  snippet=clean(block.get_text(" "), 300)))
        return out


class Marginalia(_HtmlEngine):
    id, name, family = "marginalia", "Marginalia", "independent"
    description = "Search for the small, old and forgotten web — text-first index."
    homepage = "https://search.marginalia.nu/"
    lenses = ("all", "files")

    async def hunt(self, ctx: HuntContext) -> list[RawHit]:
        url = f"https://old-search.marginalia.nu/search?query={quote_plus(ctx.plan.query)}"
        soup = await self.fetch_html(ctx, url)
        out = []
        for link in soup.select("a[href^=http]")[: ctx.limit * 3]:
            href = link.get("href", "")
            title = clean(link.get_text())
            if title and "marginalia" not in href:
                out.append(RawHit(url=href, title=title, snippet=""))
            if len(out) >= ctx.limit:
                break
        return out


class Gigablast(Provider):
    id, name, family, layer = "gigablast", "Gigablast", "independent", "remote"
    description = "Historic open-source crawler/index; service retired, code archived."
    homepage = "https://github.com/gigablast/open-source-search-engine"
    retired = True
    lenses = ("all",)

    async def hunt(self, ctx: HuntContext) -> list[RawHit]:
        return []
