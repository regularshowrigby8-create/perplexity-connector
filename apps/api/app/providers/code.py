"""Code, package and developer-community engines."""
from __future__ import annotations

from .base import HuntContext, Provider, RawHit, clean, get_json


class GitHub(Provider):
    id, name, family, layer = "github", "GitHub", "code", "remote"
    description = "Repositories, including configs, datasets and tooling."
    lenses = ("all", "exposed", "datasets")
    homepage = "https://github.com/"
    weight = 1.15

    async def hunt(self, ctx: HuntContext) -> list[RawHit]:
        data = await get_json(ctx, "https://api.github.com/search/repositories", params={
            "q": ctx.plan.terms, "per_page": min(ctx.limit, 15), "sort": "stars"},
            headers={"Accept": "application/vnd.github+json"})
        return [RawHit(url=item.get("html_url", ""), title=clean(item.get("full_name")),
                       snippet=clean(item.get("description")), kind="repository",
                       published=(item.get("updated_at") or "")[:10] or None,
                       tags=tuple(item.get("topics") or [])[:4] + ("github",),
                       meta={"stars": item.get("stargazers_count")})
                for item in (data.get("items") or [])[:ctx.limit]]


class GitLab(Provider):
    id, name, family, layer = "gitlab", "GitLab", "code", "remote"
    description = "GitLab.com project search; self-hosted instances supported."
    lenses = ("all", "exposed", "datasets")
    homepage = "https://gitlab.com/"
    weight = 0.85

    async def hunt(self, ctx: HuntContext) -> list[RawHit]:
        data = await get_json(ctx, "https://gitlab.com/api/v4/projects", params={
            "search": ctx.plan.terms, "per_page": min(ctx.limit, 15), "order_by": "last_activity_at"})
        return [RawHit(url=item.get("web_url", ""), title=clean(item.get("name_with_namespace")),
                       snippet=clean(item.get("description")), kind="repository",
                       published=(item.get("last_activity_at") or "")[:10] or None,
                       tags=("gitlab",))
                for item in (data or [])[:ctx.limit]]


class HackerNews(Provider):
    id, name, family, layer = "hackernews", "Hacker News", "community", "remote"
    description = "Founder/engineer chatter, launches and hiring threads."
    lenses = ("all", "opportunities")
    homepage = "https://news.ycombinator.com/"

    async def hunt(self, ctx: HuntContext) -> list[RawHit]:
        data = await get_json(ctx, "https://hn.algolia.com/api/v1/search", params={
            "query": ctx.plan.terms, "hitsPerPage": min(ctx.limit, 20), "tags": "story"})
        out = []
        for item in (data.get("hits") or [])[:ctx.limit]:
            url = item.get("url") or f"https://news.ycombinator.com/item?id={item.get('objectID')}"
            out.append(RawHit(url=url, title=clean(item.get("title")),
                              snippet=clean(item.get("story_text") or
                                            f"{item.get('points') or 0} points · {item.get('num_comments') or 0} comments"),
                              published=item.get("created_at"), tags=("hn",)))
        return out


class StackExchange(Provider):
    id, name, family, layer = "stackexchange", "Stack Exchange", "community", "remote"
    description = "Q&A across 180 Stack Exchange sites."
    lenses = ("all",)
    homepage = "https://stackexchange.com/"

    async def hunt(self, ctx: HuntContext) -> list[RawHit]:
        data = await get_json(ctx, "https://api.stackexchange.com/2.3/search/advanced", params={
            "order": "desc", "sort": "relevance", "q": ctx.plan.terms,
            "site": "stackoverflow", "pagesize": min(ctx.limit, 15), "filter": "default"})
        return [RawHit(url=item.get("link", ""), title=clean(item.get("title")),
                       snippet=clean(item.get("body")), kind="question",
                       tags=tuple(item.get("tags") or [])[:4] + ("stackoverflow",))
                for item in (data.get("items") or [])[:ctx.limit]]


class Npm(Provider):
    id, name, family, layer = "npm", "npm Registry", "code", "remote"
    description = "JavaScript packages and their tarballs."
    lenses = ("all", "exposed")
    homepage = "https://www.npmjs.com/"

    async def hunt(self, ctx: HuntContext) -> list[RawHit]:
        data = await get_json(ctx, "https://registry.npmjs.org/-/v1/search", params={
            "text": ctx.plan.terms, "size": min(ctx.limit, 12)})
        out = []
        for item in (data.get("objects") or [])[:ctx.limit]:
            pkg = item.get("package") or {}
            out.append(RawHit(url=(pkg.get("links") or {}).get("npm") or "",
                              title=clean(pkg.get("name")),
                              snippet=clean(pkg.get("description")), kind="package",
                              published=(pkg.get("date") or "")[:10] or None,
                              tags=("npm", pkg.get("version") or "")))
        return [h for h in out if h.url]


class Crates(Provider):
    id, name, family, layer = "crates", "crates.io", "code", "remote"
    description = "Rust crate registry."
    lenses = ("all", "exposed")
    homepage = "https://crates.io/"

    async def hunt(self, ctx: HuntContext) -> list[RawHit]:
        data = await get_json(ctx, "https://crates.io/api/v1/crates", params={
            "q": ctx.plan.terms, "per_page": min(ctx.limit, 12)})
        return [RawHit(url=c.get("repository") or f"https://crates.io/crates/{c.get('name')}",
                       title=clean(c.get("name")), snippet=clean(c.get("description")),
                       kind="package", published=(c.get("updated_at") or "")[:10] or None,
                       tags=("rust",), meta={"downloads": c.get("downloads")})
                for c in (data.get("crates") or [])[:ctx.limit]]
