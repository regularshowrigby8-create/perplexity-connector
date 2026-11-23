"""Commercial + self-hosted web search APIs (bring-your-own key, never stored)."""
from __future__ import annotations

from typing import Any

from .base import HuntContext, Provider, RawHit, clean, get_json, post_json


class SearxNG(Provider):
    id, name, family, layer = "searxng", "SearXNG", "metasearch", "remote"
    description = "Self-hosted metasearch: one endpoint, 70+ upstream engines."
    lenses = ("all", "files", "opportunities", "applications", "datasets", "exposed")
    homepage = "https://github.com/searxng/searxng"
    requires = ("searxng_url",)
    weight = 1.5

    async def hunt(self, ctx: HuntContext) -> list[RawHit]:
        base = self.key(ctx, "searxng_url").rstrip("/")
        data = await get_json(ctx, f"{base}/search", params={
            "q": ctx.plan.query, "format": "json", "safesearch": 0,
            "categories": "general", "pageno": 1,
        })
        out = []
        for item in (data.get("results") or [])[:ctx.limit]:
            out.append(RawHit(
                url=item.get("url", ""), title=clean(item.get("title")),
                snippet=clean(item.get("content")),
                tags=("searxng", *(item.get("engines") or [])),
                published=item.get("publishedDate"),
            ))
        return out


class Brave(Provider):
    id, name, family, layer = "brave", "Brave Search", "web", "remote"
    description = "Independent 30B-page index with its own crawler."
    lenses = ("all", "files", "opportunities", "applications")
    homepage = "https://brave.com/search/api/"
    requires = ("brave_api_key",)
    weight = 1.4

    async def hunt(self, ctx: HuntContext) -> list[RawHit]:
        data = await get_json(
            ctx, "https://api.search.brave.com/res/v1/web/search",
            params={"q": ctx.plan.query, "count": min(ctx.limit, 20), "safesearch": "off"},
            headers={"X-Subscription-Token": self.key(ctx, "brave_api_key"),
                     "Accept": "application/json"},
        )
        out = []
        for item in ((data.get("web") or {}).get("results") or [])[:ctx.limit]:
            out.append(RawHit(
                url=item.get("url", ""), title=clean(item.get("title")),
                snippet=clean(item.get("description")),
                published=item.get("age"),
                meta={"thumbnail": ((item.get("thumbnail") or {}).get("src"))},
            ))
        return out


class Tavily(Provider):
    id, name, family, layer = "tavily", "Tavily", "web", "remote"
    description = "Agent-oriented search API with extracted page content."
    lenses = ("all", "files", "opportunities")
    homepage = "https://tavily.com/"
    requires = ("tavily_api_key",)
    weight = 1.3

    async def hunt(self, ctx: HuntContext) -> list[RawHit]:
        data = await post_json(ctx, "https://api.tavily.com/search", json={
            "api_key": self.key(ctx, "tavily_api_key"),
            "query": ctx.plan.query, "max_results": min(ctx.limit, 20),
            "search_depth": "advanced", "include_answer": False,
        })
        return [RawHit(url=r.get("url", ""), title=clean(r.get("title")),
                       snippet=clean(r.get("content")), published=r.get("published_date"))
                for r in (data.get("results") or [])[:ctx.limit]]


class Exa(Provider):
    id, name, family, layer = "exa", "Exa", "web", "remote"
    description = "Neural/embedding search over a live crawl."
    lenses = ("all", "files", "datasets")
    homepage = "https://exa.ai/"
    requires = ("exa_api_key",)
    weight = 1.25

    async def hunt(self, ctx: HuntContext) -> list[RawHit]:
        data = await post_json(ctx, "https://api.exa.ai/search", json={
            "query": ctx.plan.query, "numResults": min(ctx.limit, 25),
            "contents": {"text": {"maxCharacters": 400}},
        }, headers={"x-api-key": self.key(ctx, "exa_api_key")})
        return [RawHit(url=r.get("url", ""), title=clean(r.get("title")),
                       snippet=clean(r.get("text")), published=r.get("publishedDate"))
                for r in (data.get("results") or [])[:ctx.limit]]


class Serper(Provider):
    id, name, family, layer = "serper", "Serper", "serp", "remote"
    description = "Google SERP results as JSON."
    lenses = ("all", "files", "opportunities", "applications")
    homepage = "https://serper.dev/"
    requires = ("serper_api_key",)
    weight = 1.4

    async def hunt(self, ctx: HuntContext) -> list[RawHit]:
        data = await post_json(ctx, "https://google.serper.dev/search", json={
            "q": ctx.plan.query, "num": min(ctx.limit, 20),
        }, headers={"X-API-KEY": self.key(ctx, "serper_api_key")})
        out = []
        for item in (data.get("organic") or [])[:ctx.limit]:
            out.append(RawHit(url=item.get("link", ""), title=clean(item.get("title")),
                              snippet=clean(item.get("snippet")), published=item.get("date")))
        return out


class SerpApi(Provider):
    id, name, family, layer = "serpapi", "SerpApi", "serp", "remote"
    description = "Structured results from Google, Bing, Yahoo, Yandex and more."
    lenses = ("all", "files", "opportunities", "applications")
    homepage = "https://serpapi.com/"
    requires = ("serpapi_api_key",)
    engine = "google"
    weight = 1.3

    async def hunt(self, ctx: HuntContext) -> list[RawHit]:
        data = await get_json(ctx, "https://serpapi.com/search.json", params={
            "engine": self.engine, "q": ctx.plan.query,
            "api_key": self.key(ctx, "serpapi_api_key"),
            "num": min(ctx.limit, 20),
        })
        out = []
        for item in (data.get("organic_results") or [])[:ctx.limit]:
            out.append(RawHit(url=item.get("link", ""), title=clean(item.get("title")),
                              snippet=clean(item.get("snippet")), published=item.get("date")))
        return out


class SearchApi(Provider):
    id, name, family, layer = "searchapi", "SearchApi", "serp", "remote"
    description = "SERP + maps + news via one REST surface."
    lenses = ("all", "opportunities", "files")
    homepage = "https://www.searchapi.io/"
    requires = ("searchapi_api_key",)
    weight = 1.15

    async def hunt(self, ctx: HuntContext) -> list[RawHit]:
        data = await get_json(ctx, "https://www.searchapi.io/api/v1/search", params={
            "engine": "google", "q": ctx.plan.query,
            "api_key": self.key(ctx, "searchapi_api_key"), "num": min(ctx.limit, 20),
        })
        return [RawHit(url=r.get("link", ""), title=clean(r.get("title")),
                       snippet=clean(r.get("snippet")), published=r.get("date"))
                for r in (data.get("organic_results") or [])[:ctx.limit]]


class GoogleCSE(Provider):
    id, name, family, layer = "google_cse", "Google Programmable Search", "serp", "remote"
    description = "Google Custom Search JSON API (sunset announced for 2027)."
    lenses = ("all", "files", "opportunities")
    homepage = "https://programmablesearchengine.google.com/"
    requires = ("google_cse_key", "google_cse_cx")
    weight = 1.25

    async def hunt(self, ctx: HuntContext) -> list[RawHit]:
        data = await get_json(ctx, "https://www.googleapis.com/customsearch/v1", params={
            "key": self.key(ctx, "google_cse_key"), "cx": self.key(ctx, "google_cse_cx"),
            "q": ctx.plan.query, "num": min(ctx.limit, 10),
        })
        return [RawHit(url=r.get("link", ""), title=clean(r.get("title")),
                       snippet=clean(r.get("snippet")))
                for r in (data.get("items") or [])[:ctx.limit]]


class Perplexity(Provider):
    id, name, family, layer = "perplexity", "Perplexity", "ai", "remote"
    description = "Answer engine with citations — surfaces documents, then cites them."
    lenses = ("all", "opportunities", "files")
    homepage = "https://docs.perplexity.ai/"
    requires = ("perplexity_api_key",)
    weight = 1.1

    async def hunt(self, ctx: HuntContext) -> list[RawHit]:
        prompt = (f"List the most relevant {ctx.lens} documents, files and open calls for: "
                  f"{ctx.plan.query}. Prefer direct PDFs, portals and primary sources. Be terse.")
        data = await post_json(ctx, "https://api.perplexity.ai/chat/completions", json={
            "model": "sonar", "messages": [{"role": "user", "content": prompt}],
        }, headers={"Authorization": f"Bearer {self.key(ctx, 'perplexity_api_key')}"})
        text = clean(((data.get("choices") or [{}])[0].get("message") or {}).get("content"), 600)
        out = []
        for url in (data.get("citations") or [])[:ctx.limit]:
            out.append(RawHit(url=url, title=url.rsplit("/", 1)[-1] or url,
                              snippet=text, tags=("synthesis",)))
        return out


class YouCom(Provider):
    id, name, family, layer = "you", "You.com", "web", "remote"
    description = "You.com search index with snippets."
    lenses = ("all", "files")
    homepage = "https://you.com/"
    requires = ("you_api_key",)
    weight = 1.15

    async def hunt(self, ctx: HuntContext) -> list[RawHit]:
        data = await get_json(ctx, "https://api.ydc-index.io/search",
                              params={"query": ctx.plan.query},
                              headers={"X-API-Key": self.key(ctx, "you_api_key")})
        out = []
        for hit in (data.get("hits") or [])[:ctx.limit]:
            out.append(RawHit(url=hit.get("url", ""), title=clean(hit.get("title")),
                              snippet=clean(" ".join(hit.get("snippets") or [])),
                              published=hit.get("page_age")))
        return out


def _serpapi_variant(engine: str, name: str, pid: str, lenses: tuple[str, ...] = ("all",)) -> type[SerpApi]:
    return type(f"SerpApi_{engine}", (SerpApi,), {
        "id": pid, "name": name, "engine": engine, "lenses": lenses, "weight": 0.9,
        "description": f"{name} results through the SerpApi gateway.",
    })


SerpApiBing = _serpapi_variant("bing", "Bing", "bing", ("all", "files"))
SerpApiYahoo = _serpapi_variant("yahoo", "Yahoo", "yahoo")
SerpApiEcosia = _serpapi_variant("ecosia", "Ecosia", "ecosia")
SerpApiStartpage = _serpapi_variant("startpage", "Startpage", "startpage")
SerpApiYandex = _serpapi_variant("yandex", "Yandex", "yandex")
SerpApiScholar = _serpapi_variant("google_scholar", "Google Scholar", "google_scholar", ("all", "files"))
SerpApiNews = _serpapi_variant("google_news", "Google News", "google_news", ("all", "opportunities"))
