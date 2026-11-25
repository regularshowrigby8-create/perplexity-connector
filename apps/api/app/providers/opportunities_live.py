"""Opportunity layer, newest first: tenders and calls the hour they are published.

The existing opportunity engines answer "who funds this?". These answer "what was
published since you last looked?" — which is the only question a newest-first
result list can honestly sort on.
"""
from __future__ import annotations

import re

from .base import HuntContext, Provider, RawHit, clean, get_json, post_json
from .realtime import BROWSER_UA, _iso, _strip_tags, _terms


class TED(Provider):
    id, name, family, layer = "ted", "TED (EU tenders)", "opportunities", "remote"
    description = "EU Tenders Electronic Daily, notices in publication order."
    lenses = ("all", "opportunities", "files")
    homepage = "https://ted.europa.eu/"
    weight = 1.15
    rate_note = "official v3 search API; no key"

    async def hunt(self, ctx: HuntContext) -> list[RawHit]:
        body = {
            "query": f'FT~("{_terms(ctx, 4)}")',
            "fields": ["publication-number", "notice-title", "publication-date",
                       "deadline-date-lot", "buyer-name", "links"],
            "page": 1, "limit": min(ctx.limit, 25),
            "sortField": "publication-date", "sortOrder": "DESC",
        }
        data = await post_json(ctx, "https://api.ted.europa.eu/v3/notices/search",
                               json=body, headers={"Accept": "application/json"})
        notices = data.get("notices") or data.get("results") or []
        out: list[RawHit] = []
        for notice in notices[:ctx.limit]:
            number = notice.get("publication-number") or notice.get("publicationNumber")
            title = notice.get("notice-title") or notice.get("title")
            if isinstance(title, dict):
                title = next(iter(title.values()), "") if title else ""
            if isinstance(title, list):
                title = title[0] if title else ""
            if not number:
                continue
            stamp = notice.get("publication-date") or notice.get("publicationDate")
            out.append(RawHit(
                url=f"https://ted.europa.eu/en/notice/-/detail/{number}",
                title=clean(title) or f"TED notice {number}",
                snippet=clean(str(notice.get("buyer-name") or ""), 320),
                kind="opportunity", published=_iso(str(stamp)[:10] if stamp else None),
                tags=("tender", "eu"),
                meta={"notice": number, "deadline": notice.get("deadline-date-lot")}))
        return out


class GrantsGovLive(Provider):
    id, name, family, layer = "grantsgov-live", "Grants.gov (posted today)", "opportunities", "remote"
    description = "Federal funding opportunities ordered by open date via the v1 API."
    lenses = ("all", "opportunities", "files")
    homepage = "https://www.grants.gov/search-results"
    weight = 1.2
    rate_note = "public search2 endpoint"

    async def hunt(self, ctx: HuntContext) -> list[RawHit]:
        data = await post_json(ctx, "https://api.grants.gov/v1/api/search2", json={
            "keyword": ctx.plan.terms, "oppStatuses": "forecasted|posted",
            "rows": min(ctx.limit, 25), "sortBy": "openDate|desc", "startRecordNum": 0})
        hits = ((data.get("data") or {}).get("oppHits")) or []
        out: list[RawHit] = []
        for hit in hits[:ctx.limit]:
            url = hit.get("link") or (f"https://www.grants.gov/search-results-detail/{hit.get('id')}"
                                      if hit.get("id") else None)
            if not url:
                continue
            out.append(RawHit(url=url, title=clean(hit.get("title")) or url,
                              snippet=clean(f"{hit.get('agencyName', '')} · "
                                            f"closes {hit.get('closeDate', '')}", 320),
                              kind="opportunity",
                              published=_iso(hit.get("openDate")),
                              deadline=hit.get("closeDate") or None,
                              tags=("grant", "usa"),
                              meta={"number": hit.get("number"), "agency": hit.get("agencyName")}))
        return out


class UKRIGateway(Provider):
    id, name, family, layer = "ukri", "UKRI Gateway to Research", "opportunities", "remote"
    description = "UK Research and Innovation projects as they are created."
    lenses = ("all", "opportunities", "files")
    homepage = "https://gtr.ukri.org/"
    weight = 1.0
    rate_note = "public XML API"

    async def hunt(self, ctx: HuntContext) -> list[RawHit]:
        resp = await ctx.client.get("https://gtr.ukri.org/gtr/api/projects", params={
            "q": ctx.plan.terms, "p": 1, "s": min(ctx.limit, 25)},
            headers={"Accept": "application/xml"})
        resp.raise_for_status()
        import xml.etree.ElementTree as ET

        root = ET.fromstring(resp.text)
        out: list[RawHit] = []
        for project in root.iter():
            if not project.tag.lower().endswith("project"):
                continue
            values = {child.tag.split("}")[-1].lower(): (child.text or "").strip()
                      for child in project}
            title = values.get("title")
            pid = values.get("id")
            if not (title and pid):
                continue
            out.append(RawHit(url=f"https://gtr.ukri.org/projects?ref={pid}", title=clean(title),
                              snippet=clean(values.get("abstracttext", ""), 320),
                              kind="opportunity",
                              published=_iso(values.get("created") or values.get("start")),
                              tags=("grant", "uk"),
                              meta={"led_by": values.get("leadfunder")}))
        return out[:ctx.limit]


class WorldBankProcurement(Provider):
    id, name, family, layer = "wb-procurement", "World Bank procurement", "opportunities", "remote"
    description = "Bank-funded tender notices, newest first, straight from the RSS."
    lenses = ("all", "opportunities")
    homepage = "https://search.worldbank.org/procurement"
    weight = 0.95
    rate_note = "public RSS"

    async def hunt(self, ctx: HuntContext) -> list[RawHit]:
        resp = await ctx.client.get("https://search.worldbank.org/rss/procurement", params={
            "qterm": ctx.plan.terms, "format": "rss"}, headers={"User-Agent": BROWSER_UA})
        if resp.status_code >= 400:
            return []
        try:
            import feedparser

            entries = getattr(feedparser.parse(resp.text), "entries", []) or []
        except Exception:
            return []
        out: list[RawHit] = []
        for entry in entries[:ctx.limit]:
            link = entry.get("link")
            if not link:
                continue
            out.append(RawHit(url=link, title=clean(entry.get("title")) or link,
                              snippet=_strip_tags(entry.get("summary", ""), 320),
                              kind="opportunity", published=_iso(entry.get("published")),
                              tags=("tender", "worldbank")))
        return out


class FindATenderUK(Provider):
    id, name, family, layer = "find-a-tender", "Find a Tender (UK OCDS)", "opportunities", "remote"
    description = "UK public contracts in OCDS, releases ordered by date."
    lenses = ("all", "opportunities", "files")
    homepage = "https://www.find-tender.service.gov.uk/"
    weight = 1.0
    rate_note = "OCDS release packages; no key"

    async def hunt(self, ctx: HuntContext) -> list[RawHit]:
        data = await get_json(ctx, "https://www.find-tender.service.gov.uk/api/1.0/ocdsReleasePackages",
                              params={"limit": min(ctx.limit, 25), "stages": "tender"})
        releases = []
        for package in (data.get("releases") or data.get("packages") or []):
            releases.extend(package.get("releases") or [])
        if not releases:
            releases = data.get("releases") or []
        out: list[RawHit] = []
        for release in releases[:ctx.limit]:
            tender = release.get("tender") or {}
            title = tender.get("title") or release.get("ocid")
            rid = release.get("id") or release.get("ocid")
            if not rid:
                continue
            out.append(RawHit(url=f"https://www.find-tender.service.gov.uk/Notice/{rid}",
                              title=clean(title) or rid,
                              snippet=clean(tender.get("description") or "", 320),
                              kind="opportunity", published=_iso(release.get("date")),
                              deadline=(tender.get("tenderPeriod") or {}).get("endDate"),
                              tags=("tender", "uk"), meta={"ocid": release.get("ocid")}))
        return out


class CORDIS(Provider):
    id, name, family, layer = "cordis-live", "CORDIS projects (newest)", "opportunities", "remote"
    description = "EU-funded research projects by start date, with deliverables."
    lenses = ("all", "opportunities", "files", "datasets")
    homepage = "https://cordis.europa.eu/"
    weight = 0.95
    rate_note = "public search API"

    async def hunt(self, ctx: HuntContext) -> list[RawHit]:
        data = await get_json(ctx, "https://cordis.europa.eu/api/search/results", params={
            "q": f'content~"{_terms(ctx, 4)}"', "p": 1, "num": min(ctx.limit, 25),
            "format": "json", "srt": "startDate:decreasing"})
        payload = data.get("payload") or {}
        results = payload.get("results") or data.get("results") or []
        out: list[RawHit] = []
        for item in results[:ctx.limit]:
            url = item.get("url") or item.get("link")
            if not url:
                continue
            out.append(RawHit(
                url=url if str(url).startswith("http") else f"https://cordis.europa.eu{url}",
                title=clean(item.get("title")) or str(url),
                snippet=clean(item.get("teaser") or item.get("objective") or "", 320),
                kind="opportunity", published=_iso(str(item.get("startDate") or "")[:10] or None),
                tags=("eu", "project"), meta={"reference": item.get("reference")}))
        return out


class FundsforNGOsSearch(Provider):
    id, name, family, layer = "fundsforngos", "FundsforNGOs search", "opportunities", "remote"
    description = "Grant announcements via the site's own REST index, newest first."
    lenses = ("all", "opportunities")
    homepage = "https://www.fundsforngos.org/"
    weight = 0.9
    rate_note = "WordPress REST API"

    async def hunt(self, ctx: HuntContext) -> list[RawHit]:
        data = await get_json(ctx, "https://www.fundsforngos.org/wp-json/wp/v2/posts", params={
            "search": ctx.plan.terms, "per_page": min(ctx.limit, 20),
            "_fields": "link,title,date,excerpt"})
        out: list[RawHit] = []
        for item in (data or [])[:ctx.limit]:
            url = item.get("link")
            title = item.get("title")
            if isinstance(title, dict):
                title = title.get("rendered", "")
            excerpt = item.get("excerpt")
            if isinstance(excerpt, dict):
                excerpt = excerpt.get("rendered", "")
            if not url:
                continue
            out.append(RawHit(url=url, title=clean(title) or url,
                              snippet=_strip_tags(str(excerpt or ""), 320),
                              kind="opportunity", published=_iso(item.get("date")),
                              tags=("grant", "ngo")))
        return out


class UNDPProcurement(Provider):
    id, name, family, layer = "undp-procurement", "UNDP procurement", "opportunities", "remote"
    description = "UNDP notices and calls for proposals, newest first."
    lenses = ("all", "opportunities")
    homepage = "https://procurement-notices.undp.org/"
    weight = 0.9
    rate_note = "public listing; HTML parsed defensively"

    async def hunt(self, ctx: HuntContext) -> list[RawHit]:
        resp = await ctx.client.get("https://procurement-notices.undp.org/index.cfm",
                                    params={"go": "all"}, headers={"User-Agent": BROWSER_UA})
        if resp.status_code >= 400:
            return []
        html = resp.text
        out: list[RawHit] = []
        for row in re.split(r"<tr", html, flags=re.I)[1:]:
            anchor = re.search(r'<a[^>]+href="([^"]*?notice_id=\d+[^"]*)"[^>]*>(.*?)</a>',
                               row, re.I | re.S)
            if not anchor:
                continue
            href, label = anchor.group(1), _strip_tags(anchor.group(2), 160)
            if not label:
                continue
            stamp = re.search(r"\b(\d{1,2}[-/ ](?:[A-Za-z]{3,9}|\d{1,2})[-/ ]\d{2,4}"
                              r"|\d{4}-\d{2}-\d{2})\b", _strip_tags(row, 600))
            url = (href if href.startswith("http")
                   else f"https://procurement-notices.undp.org/{href.lstrip('/')}")
            out.append(RawHit(url=url, title=clean(label), snippet="UNDP procurement notice",
                              kind="opportunity",
                              published=_iso(stamp.group(1) if stamp else None),
                              tags=("tender", "undp")))
            if len(out) >= ctx.limit:
                break
        return out
