"""Real-time layer: the engines that can hand back something published *seconds* ago.

Breadth is not the point of this file. Every engine here answers one question —
"what appeared since the last time you looked?" — and every hit carries a real
publication clock so the newest-first ordering has something true to sort on.
"""
from __future__ import annotations

import asyncio
import re
from datetime import datetime, timedelta, timezone
from urllib.parse import quote, quote_plus

from .base import HuntContext, Provider, RawHit, clean, get_json

BROWSER_UA = ("Mozilla/5.0 (compatible; Nighthawk/1.0; +https://github.com/"
              "regularshowrigby8-create/perplexity-connector)")


def _iso(value) -> str | None:
    """Any feed/API timestamp → ISO-8601 with a Z, or None."""
    if value in (None, ""):
        return None
    if isinstance(value, (int, float)):
        seconds = float(value)
        if seconds > 1e11:          # milliseconds
            seconds /= 1000.0
        try:
            return datetime.fromtimestamp(seconds, tz=timezone.utc).isoformat()
        except (OverflowError, OSError, ValueError):
            return None
    text = str(value).strip()
    if re.fullmatch(r"\d{10,13}", text):
        return _iso(int(text))
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", text):
        return f"{text}T00:00:00Z"
    if re.fullmatch(r"\d{14}", text):                       # WARC / GDELT seendate
        return (f"{text[0:4]}-{text[4:6]}-{text[6:8]}T"
                f"{text[8:10]}:{text[10:12]}:{text[12:14]}Z")
    if text.endswith("Z") and "T" in text:
        return text
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
        return parsed.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
    except ValueError:
        pass
    from ..freshness import parse as _parse          # RFC 2822, "2026 Nov 25", "3 days ago"

    parsed = _parse(text)
    return parsed.isoformat() if parsed else None


def _terms(ctx: HuntContext, n: int = 6) -> str:
    return " ".join(ctx.plan.terms.split()[:n]) or "news"


def _strip_tags(html: str, limit: int = 300) -> str:
    return clean(re.sub(r"<[^>]+>", " ", html or ""), limit)


class GDelt(Provider):
    id, name, family, layer = "gdelt", "GDELT 2.0", "realtime", "remote"
    description = "Global news firehose, 65 languages, updated every 15 minutes."
    lenses = ("all", "files", "opportunities")
    homepage = "https://api.gdeltproject.org/api/v2/doc/doc"
    weight = 1.35
    rate_note = "no key; 1 request/second courtesy limit"

    async def hunt(self, ctx: HuntContext) -> list[RawHit]:
        data = await get_json(ctx, "https://api.gdeltproject.org/api/v2/doc/doc", params={
            "query": f"{_terms(ctx)} sourcelang:english", "mode": "artlist",
            "format": "json", "sort": "datedesc", "maxrecords": min(ctx.limit, 25)})
        out: list[RawHit] = []
        for article in (data.get("articles") or [])[:ctx.limit]:
            url = article.get("url")
            if not url:
                continue
            out.append(RawHit(
                url=url, title=clean(article.get("title")) or url,
                snippet=clean(f"{article.get('domain', '')} · {article.get('sourcecountry', '')}"),
                kind="page", published=_iso(article.get("seendate")),
                tags=("news",), meta={"domain": article.get("domain"),
                                      "language": article.get("language")}))
        return out


class RedditNew(Provider):
    id, name, family, layer = "reddit-new", "Reddit (new)", "realtime", "remote"
    description = "Every subreddit, sorted by creation time — seconds after posting."
    lenses = ("all", "opportunities")
    homepage = "https://www.reddit.com/search/?sort=new"
    weight = 1.05
    rate_note = "public JSON; ~60 requests/hour per IP"

    async def hunt(self, ctx: HuntContext) -> list[RawHit]:
        resp = await ctx.client.get("https://www.reddit.com/search.json", params={
            "q": ctx.plan.terms, "sort": "new", "t": "week",
            "limit": min(ctx.limit, 25), "raw_json": 1},
            headers={"User-Agent": BROWSER_UA, "Accept": "application/json"})
        resp.raise_for_status()
        children = ((resp.json().get("data") or {}).get("children")) or []
        out: list[RawHit] = []
        for child in children:
            post = child.get("data") or {}
            link = post.get("url_overridden_by_dest") or (
                f"https://www.reddit.com{post.get('permalink', '')}")
            if not link:
                continue
            out.append(RawHit(
                url=link, title=clean(post.get("title")) or link,
                snippet=_strip_tags(post.get("selftext") or post.get("subreddit_name_prefixed") or ""),
                kind="page", published=_iso(post.get("created_utc")),
                tags=("reddit", post.get("subreddit", "")),
                meta={"score": post.get("score"), "comments": post.get("num_comments"),
                      "subreddit": post.get("subreddit")}))
        return out


class RedditSubreddit(Provider):
    id, name, family, layer = "reddit-subs", "Reddit (curated subs)", "realtime", "remote"
    description = "Grant, tender, data and research subreddits, newest post first."
    lenses = ("all", "opportunities", "datasets")
    homepage = "https://www.reddit.com/r/grantwriting/new/"
    weight = 1.0
    rate_note = "one request per subreddit; newest listing"
    SUBREDDITS = ("grantwriting", "Nonprofit", "opendata", "datasets", "academicresearch")

    async def hunt(self, ctx: HuntContext) -> list[RawHit]:
        async def one(sub: str) -> list[RawHit]:
            try:
                resp = await ctx.client.get(f"https://www.reddit.com/r/{sub}/new.json",
                                            params={"limit": 12, "raw_json": 1},
                                            headers={"User-Agent": BROWSER_UA})
                if resp.status_code >= 400:
                    return []
                children = ((resp.json().get("data") or {}).get("children")) or []
            except Exception:
                return []
            hits = []
            for child in children:
                post = child.get("data") or {}
                link = post.get("url_overridden_by_dest") or (
                    f"https://www.reddit.com{post.get('permalink', '')}")
                if not link:
                    continue
                hits.append(RawHit(url=link, title=clean(post.get("title")) or link,
                                   snippet=_strip_tags(post.get("selftext") or ""),
                                   kind="page", published=_iso(post.get("created_utc")),
                                   tags=("reddit", sub),
                                   meta={"subreddit": sub, "score": post.get("score")}))
            return hits

        batches = await asyncio.gather(*(one(sub) for sub in self.SUBREDDITS),
                                       return_exceptions=True)
        out: list[RawHit] = []
        for batch in batches:
            if isinstance(batch, list):
                out.extend(batch)
        return out[:ctx.limit]


class HackerNewsNew(Provider):
    id, name, family, layer = "hn-new", "Hacker News (by date)", "realtime", "remote"
    description = "Algolia mirror sorted by creation time, not by points."
    lenses = ("all", "datasets")
    homepage = "https://hn.algolia.com/api"
    weight = 1.1
    rate_note = "10k requests/hour"

    async def hunt(self, ctx: HuntContext) -> list[RawHit]:
        data = await get_json(ctx, "https://hn.algolia.com/api/v1/search_by_date", params={
            "query": ctx.plan.terms, "tags": "story", "hitsPerPage": min(ctx.limit, 25)})
        out: list[RawHit] = []
        for hit in (data.get("hits") or [])[:ctx.limit]:
            link = hit.get("url") or f"https://news.ycombinator.com/item?id={hit.get('objectID')}"
            out.append(RawHit(
                url=link, title=clean(hit.get("title") or hit.get("story_title")) or link,
                snippet=clean(f"HN · {hit.get('author', '')} · {hit.get('points') or 0} points"),
                kind="page", published=_iso(hit.get("created_at")),
                tags=("hn",), meta={"points": hit.get("points"),
                                    "comments": hit.get("num_comments")}))
        return out


class Lobsters(Provider):
    id, name, family, layer = "lobsters", "Lobsters", "realtime", "remote"
    description = "Small, link-heavy tech community with a true newest ordering."
    lenses = ("all", "datasets")
    homepage = "https://lobste.rs/"
    weight = 0.95
    rate_note = "public JSON"

    async def hunt(self, ctx: HuntContext) -> list[RawHit]:
        resp = await ctx.client.get("https://lobste.rs/search.json", params={
            "q": ctx.plan.terms, "what": "stories", "order": "newest"},
            headers={"User-Agent": BROWSER_UA, "Accept": "application/json"})
        resp.raise_for_status()
        out: list[RawHit] = []
        for story in (resp.json() or [])[:ctx.limit]:
            url = story.get("url") or story.get("short_id_url")
            if not url:
                continue
            out.append(RawHit(url=url, title=clean(story.get("title")) or url,
                              snippet=clean(" ".join(story.get("tags") or [])),
                              kind="page", published=_iso(story.get("created_at")),
                              tags=("lobsters",), meta={"score": story.get("score")}))
        return out


class MastodonTag(Provider):
    id, name, family, layer = "mastodon", "Mastodon (tag timeline)", "realtime", "remote"
    description = "Fediverse public tag timelines — no account, no ranking."
    lenses = ("all",)
    homepage = "https://mastodon.social/explore"
    weight = 0.85
    rate_note = "public timeline endpoint"
    INSTANCES = ("https://mastodon.social", "https://fosstodon.org")

    async def hunt(self, ctx: HuntContext) -> list[RawHit]:
        tag = (ctx.plan.terms.split() or ["news"])[0].strip(":").lower()
        tag = re.sub(r"[^a-z0-9_]", "", tag) or "news"

        async def one(base: str) -> list[RawHit]:
            try:
                resp = await ctx.client.get(f"{base}/api/v1/timelines/tag/{tag}",
                                            params={"limit": 20},
                                            headers={"User-Agent": BROWSER_UA})
                if resp.status_code >= 400:
                    return []
                posts = resp.json()
            except Exception:
                return []
            hits = []
            for post in posts or []:
                account = (post.get("account") or {}).get("acct") or ""
                if not post.get("url"):
                    continue
                hits.append(RawHit(url=post["url"],
                                   title=clean(f"@{account}: {_strip_tags(post.get('content', ''), 90)}")
                                   or post["url"],
                                   snippet=_strip_tags(post.get("content", "")),
                                   kind="page", published=_iso(post.get("created_at")),
                                   tags=("mastodon", f"#{tag}"),
                                   meta={"instance": base, "boosts": post.get("reblogs_count")}))
            return hits

        batches = await asyncio.gather(*(one(base) for base in self.INSTANCES),
                                       return_exceptions=True)
        out: list[RawHit] = []
        for batch in batches:
            if isinstance(batch, list):
                out.extend(batch)
        return out[:ctx.limit]


class BlueskySearch(Provider):
    id, name, family, layer = "bluesky", "Bluesky (latest)", "realtime", "remote"
    description = "AT-protocol public search, sorted latest — unauthenticated."
    lenses = ("all",)
    homepage = "https://bsky.app/search"
    weight = 0.9
    rate_note = "public AppView; no auth"

    async def hunt(self, ctx: HuntContext) -> list[RawHit]:
        data = await get_json(ctx, "https://public.api.bsky.app/xrpc/app.bsky.feed.searchPosts",
                              params={"q": ctx.plan.terms, "limit": min(ctx.limit, 25),
                                      "sort": "latest"})
        out: list[RawHit] = []
        for post in (data.get("posts") or [])[:ctx.limit]:
            author = (post.get("author") or {}).get("handle") or ""
            rkey = (post.get("uri") or "").rsplit("/", 1)[-1]
            if not (author and rkey):
                continue
            record = post.get("record") or {}
            out.append(RawHit(
                url=f"https://bsky.app/profile/{author}/post/{rkey}",
                title=clean(f"@{author}: {record.get('text', '')[:90]}"),
                snippet=_strip_tags(record.get("text", "")),
                kind="page", published=_iso(record.get("createdAt")),
                tags=("bluesky",), meta={"likes": post.get("likeCount"),
                                         "reposts": post.get("repostCount")}))
        return out


class RSSFirehose(Provider):
    """One provider, many institutional feeds — all of them publish a real date."""
    id, name, family, layer = "rss-firehose", "Institutional RSS (20 feeds)", "realtime", "remote"
    description = ("Grant, tender, data and research feeds from UN, WHO, NIH, NSF, "
                   "gov.uk, Federal Register, PyPI and arXiv — read newest first.")
    lenses = ("all", "files", "opportunities", "datasets")
    homepage = "https://www.grants.gov/"
    weight = 1.15
    rate_note = "per-feed politeness; failures are skipped, never fatal"
    FEEDS = (
        ("Grants.gov new opportunities", "https://www.grants.gov/rss/GG_NewOppByCategory.xml"),
        ("ReliefWeb updates", "https://reliefweb.int/updates/rss.xml"),
        ("UN News", "https://news.un.org/feed/subscribe/en/news/all/rss.xml"),
        ("WHO news", "https://www.who.int/rss-feeds/news-english.xml"),
        ("NIH news releases", "https://www.nih.gov/news-events/news-releases/rss.xml"),
        ("NSF news", "https://www.nsf.gov/rss/rss_www_news.xml"),
        ("gov.uk news", "https://www.gov.uk/search/news-and-communications.atom"),
        ("gov.uk research", "https://www.gov.uk/search/research-and-statistics.atom"),
        ("Federal Register", "https://www.federalregister.gov/documents/search.rss?order=newest"),
        ("PyPI releases", "https://pypi.org/rss/updates.xml"),
        ("arXiv cs.AI", "https://arxiv.org/rss/cs.AI"),
        ("arXiv cs.CL", "https://arxiv.org/rss/cs.CL"),
        ("arXiv econ", "https://arxiv.org/rss/econ.GN"),
        ("State Dept releases", "https://www.state.gov/rss-feed/press-releases/feed/"),
        ("World Bank news", "https://www.worldbank.org/en/news/all?format=rss"),
        ("IMF news", "https://www.imf.org/en/News/RSS"),
        ("Nature", "https://www.nature.com/nature.rss"),
        ("FundsforNGOs", "https://www.fundsforngos.org/feed/"),
        ("GitHub blog", "https://github.blog/feed/"),
        ("OECD newsroom", "https://www.oecd.org/en/about/news.html?feed=rss"),
    )

    async def _one(self, ctx: HuntContext, name: str, url: str) -> list[RawHit]:
        try:
            resp = await ctx.client.get(url, headers={"User-Agent": BROWSER_UA},
                                        timeout=12.0, follow_redirects=True)
            if resp.status_code >= 400:
                return []
            payload = resp.text
        except Exception:
            return []
        try:
            import feedparser

            parsed = feedparser.parse(payload)
            entries = parsed.entries or []
        except Exception:
            entries = []
        # Most of these feeds are global firehoses (PyPI releases, arXiv listings,
        # Nature). They are the fastest clocks on the internet and completely
        # unselective, so each entry must earn its place against the query.
        words = [w for w in re.split(r"\W+", ctx.plan.terms.lower()) if len(w) > 3]
        out: list[RawHit] = []
        for entry in entries[:12]:
            link = entry.get("link") or (entry.get("links") or [{}])[0].get("href")
            if not link:
                continue
            stamp = (entry.get("published") or entry.get("updated")
                     or entry.get("created"))
            if not stamp:
                struct = (entry.get("published_parsed") or entry.get("updated_parsed"))
                if struct:
                    stamp = datetime(*struct[:6], tzinfo=timezone.utc).isoformat()
            summary = entry.get("summary") or entry.get("description") or ""
            title_text = entry.get("title") or ""
            if words:
                haystack = f"{title_text} {summary}".lower()
                if not any(word in haystack for word in words):
                    continue
            out.append(RawHit(
                url=link, title=clean(title_text) or link,
                snippet=_strip_tags(summary, 320), kind="page",
                published=_iso(stamp), tags=("feed", name),
                meta={"feed": name, "feed_url": url}))
        return out

    async def hunt(self, ctx: HuntContext) -> list[RawHit]:
        batches = await asyncio.gather(
            *(self._one(ctx, name, url) for name, url in self.FEEDS),
            return_exceptions=True)
        out: list[RawHit] = []
        for batch in batches:
            if isinstance(batch, list):
                out.extend(batch)
        out.sort(key=lambda h: str(h.published or ""), reverse=True)
        return out[: max(ctx.limit * 2, 20)]


class GitHubCommits(Provider):
    id, name, family, layer = "github-commits", "GitHub commits (newest)", "realtime", "remote"
    description = "Commit search sorted by committer date — code that landed minutes ago."
    lenses = ("all", "datasets")
    homepage = "https://github.com/search?type=commits"
    weight = 1.0
    rate_note = "search API; 10 requests/minute unauthenticated"

    async def hunt(self, ctx: HuntContext) -> list[RawHit]:
        since = (datetime.now(timezone.utc) - timedelta(days=30)).date().isoformat()
        resp = await ctx.client.get("https://api.github.com/search/commits", params={
            "q": f"{_terms(ctx)} committer-date:>={since}", "sort": "committer-date",
            "order": "desc", "per_page": min(ctx.limit, 25)},
            headers={"Accept": "application/vnd.github+json"})
        resp.raise_for_status()
        out: list[RawHit] = []
        for item in ((resp.json() or {}).get("items") or [])[:ctx.limit]:
            commit = item.get("commit") or {}
            message = ((commit.get("message") or "").splitlines() or [""])[0]
            out.append(RawHit(
                url=item.get("html_url") or "", title=clean(message)[:140] or item.get("html_url", ""),
                snippet=clean(f"{(item.get('repository') or {}).get('full_name', '')} · commit"),
                kind="commit", published=_iso((commit.get("committer") or {}).get("date")),
                tags=("code",), meta={"repo": (item.get("repository") or {}).get("full_name")}))
        return [hit for hit in out if hit.url]


class GitHubIssues(Provider):
    id, name, family, layer = "github-issues", "GitHub issues (newest)", "realtime", "remote"
    description = "Issues and discussions opened in the last month, newest first."
    lenses = ("all", "opportunities", "datasets")
    homepage = "https://github.com/issues"
    weight = 0.9
    rate_note = "search API; 10 requests/minute unauthenticated"

    async def hunt(self, ctx: HuntContext) -> list[RawHit]:
        since = (datetime.now(timezone.utc) - timedelta(days=30)).date().isoformat()
        resp = await ctx.client.get("https://api.github.com/search/issues", params={
            "q": f"{_terms(ctx)} created:>={since}", "sort": "created", "order": "desc",
            "per_page": min(ctx.limit, 25)},
            headers={"Accept": "application/vnd.github+json"})
        resp.raise_for_status()
        out: list[RawHit] = []
        for item in ((resp.json() or {}).get("items") or [])[:ctx.limit]:
            out.append(RawHit(
                url=item.get("html_url") or "", title=clean(item.get("title")) or "",
                snippet=clean(item.get("body") or "")[:320], kind="page",
                published=_iso(item.get("created_at")), tags=("issue",),
                meta={"repo": (item.get("repository_url") or "").rsplit("/", 2)[-2:],
                      "state": item.get("state")}))
        return [hit for hit in out if hit.url]


class WikipediaRevisions(Provider):
    id, name, family, layer = "wikipedia-rev", "Wikipedia (last revision)", "realtime", "remote"
    description = "Matching articles with the timestamp of their most recent edit."
    lenses = ("all",)
    homepage = "https://en.wikipedia.org/wiki/Special:RecentChanges"
    weight = 0.7
    rate_note = "MediaWiki API, 200 requests/second sustained"

    async def hunt(self, ctx: HuntContext) -> list[RawHit]:
        resp = await ctx.client.get("https://en.wikipedia.org/w/api.php", params={
            "action": "query", "generator": "search", "gsrsearch": ctx.plan.terms,
            "gsrlimit": min(ctx.limit, 20), "prop": "revisions|info",
            "rvprop": "timestamp", "rvlimit": 1, "inprop": "url", "format": "json",
            "formatVersion": 2})
        resp.raise_for_status()
        pages = ((resp.json() or {}).get("query") or {}).get("pages") or []
        out: list[RawHit] = []
        for page in pages:
            revisions = page.get("revisions") or []
            stamp = revisions[0].get("timestamp") if revisions else None
            url = page.get("fullurl")
            if not url:
                continue
            out.append(RawHit(url=url, title=clean(page.get("title")) or url,
                              snippet="last edited " + (stamp or "unknown"),
                              kind="page", published=_iso(stamp),
                              tags=("reference",), meta={"pageid": page.get("pageid")}))
        return out


class StackExchangeNew(Provider):
    id, name, family, layer = "se-new", "Stack Exchange (newest)", "realtime", "remote"
    description = "Newest questions across Stack Overflow and the data/science sites."
    lenses = ("all", "datasets")
    homepage = "https://api.stackexchange.com/"
    weight = 0.85
    rate_note = "300 requests/day without a key"

    async def hunt(self, ctx: HuntContext) -> list[RawHit]:
        sites = ("stackoverflow", "opendata", "academia")
        out: list[RawHit] = []
        for site in sites:
            try:
                resp = await ctx.client.get("https://api.stackexchange.com/2.3/search/advanced",
                                            params={"order": "desc", "sort": "creation",
                                                    "q": ctx.plan.terms, "site": site,
                                                    "pagesize": 10, "filter": "default"})
                if resp.status_code >= 400:
                    continue
                items = (resp.json() or {}).get("items") or []
            except Exception:
                continue
            for item in items:
                out.append(RawHit(
                    url=item.get("link") or "", title=clean(item.get("title")) or "",
                    snippet=clean(" ".join(item.get("tags") or [])), kind="page",
                    published=_iso(item.get("creation_date")), tags=("qa", site),
                    meta={"site": site, "answers": item.get("answer_count")}))
        return [hit for hit in out if hit.url][:ctx.limit]


class CratesNew(Provider):
    id, name, family, layer = "crates-new", "crates.io (newest)", "realtime", "remote"
    description = "Rust crates sorted by recency, straight from the registry index."
    lenses = ("all", "datasets")
    homepage = "https://crates.io/"
    weight = 0.75
    rate_note = "1 request/second; contact UA required"

    async def hunt(self, ctx: HuntContext) -> list[RawHit]:
        resp = await ctx.client.get("https://crates.io/api/v1/crates", params={
            "q": _terms(ctx), "sort": "new", "per_page": min(ctx.limit, 25)},
            headers={"User-Agent": "Nighthawk (nighthawk@example.org)"})
        resp.raise_for_status()
        out: list[RawHit] = []
        for crate in ((resp.json() or {}).get("crates") or [])[:ctx.limit]:
            name = crate.get("name")
            if not name:
                continue
            out.append(RawHit(
                url=f"https://crates.io/crates/{name}",
                title=clean(f"{name} {crate.get('newest_version', '')}".strip()),
                snippet=clean(crate.get("description") or ""), kind="package",
                published=_iso(crate.get("updated_at")),
                tags=("rust", "package"), meta={"downloads": crate.get("downloads")}))
        return out


class GitLabProjects(Provider):
    id, name, family, layer = "gitlab-projects", "GitLab (last activity)", "realtime", "remote"
    description = "Public repositories by last activity — work in progress, not stars."
    lenses = ("all", "datasets")
    homepage = "https://gitlab.com/explore/projects"
    weight = 0.8
    rate_note = "public API; 300 requests/minute"

    async def hunt(self, ctx: HuntContext) -> list[RawHit]:
        data = await get_json(ctx, "https://gitlab.com/api/v4/projects", params={
            "search": _terms(ctx), "order_by": "last_activity_at", "sort": "desc",
            "per_page": min(ctx.limit, 25)})
        out: list[RawHit] = []
        for project in (data or [])[:ctx.limit]:
            url = project.get("web_url")
            if not url:
                continue
            out.append(RawHit(url=url, title=clean(project.get("name_with_namespace")
                                                   or project.get("name")) or url,
                              snippet=clean(project.get("description") or "", 320), kind="repo",
                              published=_iso(project.get("last_activity_at")),
                              tags=("code", "gitlab"),
                              meta={"stars": project.get("star_count")}))
        return out


class NpmNew(Provider):
    id, name, family, layer = "npm-new", "npm registry (newest)", "realtime", "remote"
    description = "Packages by publish date from the registry search index."
    lenses = ("all", "datasets")
    homepage = "https://www.npmjs.com/"
    weight = 0.8
    rate_note = "public registry search"

    async def hunt(self, ctx: HuntContext) -> list[RawHit]:
        data = await get_json(ctx, "https://registry.npmjs.org/-/v1/search", params={
            "text": _terms(ctx), "size": min(ctx.limit, 25)})
        out: list[RawHit] = []
        for obj in (data.get("objects") or [])[:ctx.limit]:
            package = obj.get("package") or {}
            name = package.get("name")
            if not name:
                continue
            out.append(RawHit(url=package.get("links", {}).get("npm")
                              or f"https://www.npmjs.com/package/{name}",
                              title=clean(f"{name} {package.get('version', '')}".strip()),
                              snippet=clean(package.get("description") or "", 320), kind="package",
                              published=_iso(package.get("date")),
                              tags=("npm", "package"), meta={"version": package.get("version")}))
        out.sort(key=lambda hit: str(hit.published or ""), reverse=True)
        return out


class GitHubAdvisories(Provider):
    id, name, family, layer = "ghsa", "GitHub advisories (newest)", "realtime", "remote"
    description = "Security advisories in publication order — the freshest CVE-adjacent data."
    lenses = ("all", "datasets")
    homepage = "https://github.com/advisories"
    weight = 0.75
    rate_note = "public REST; 60 requests/hour unauthenticated"

    async def hunt(self, ctx: HuntContext) -> list[RawHit]:
        data = await get_json(ctx, "https://api.github.com/advisories", params={
            "sort": "published", "direction": "desc", "per_page": min(ctx.limit, 25)},
            headers={"Accept": "application/vnd.github+json"})
        words = [w for w in re.split(r"\W+", ctx.plan.terms.lower()) if len(w) > 3]
        out: list[RawHit] = []
        for advisory in (data or []):
            summary = advisory.get("summary") or ""
            haystack = f"{summary} {' '.join(advisory.get('identifiers') or [])}".lower()
            if words and not any(word in haystack for word in words):
                continue
            url = advisory.get("html_url")
            if not url:
                continue
            out.append(RawHit(url=url, title=clean(summary) or url,
                              snippet=clean(advisory.get("ghsa_id") or "", 160), kind="page",
                              published=_iso(advisory.get("published_at")),
                              tags=("security", "advisory"),
                              meta={"severity": advisory.get("severity")}))
        return out
