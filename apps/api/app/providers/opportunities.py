"""Funding, tender and application engines with structured deadline fields."""
from __future__ import annotations

from .base import HuntContext, Provider, RawHit, clean, get_json, post_json


class GrantsGov(Provider):
    id, name, family, layer = "grantsgov", "Grants.gov", "opportunity", "remote"
    description = "US federal funding opportunities with official close dates."
    lenses = ("opportunities", "applications", "all")
    homepage = "https://www.grants.gov/"
    weight = 1.4

    async def hunt(self, ctx: HuntContext) -> list[RawHit]:
        data = await post_json(ctx, "https://api.grants.gov/v1/api/search2", json={
            "keyword": ctx.plan.terms, "oppStatuses": "forecasted|posted",
            "rows": min(ctx.limit, 25), "startRecordNum": 0, "sortBy": "openDate|desc"})
        hits = (((data.get("data") or {}).get("oppHits")) or [])
        out = []
        for item in hits[:ctx.limit]:
            oid = item.get("id") or item.get("number")
            out.append(RawHit(
                url=f"https://www.grants.gov/search-results-detail/{oid}",
                title=clean(item.get("title")), kind="opportunity",
                snippet=clean(f"{item.get('agencyName') or item.get('agency') or 'US federal'} · "
                              f"{item.get('oppStatus') or 'posted'} · {item.get('number') or ''}"),
                deadline=item.get("closeDate"),
                tags=("funding", "us-federal"),
                meta={"number": item.get("number"), "status": item.get("oppStatus"),
                      "open": item.get("openDate")}))
        return out


class ReliefWebJobs(Provider):
    id, name, family, layer = "reliefweb", "ReliefWeb Jobs", "opportunity", "remote"
    description = "Humanitarian vacancies, consultancies and tenders."
    lenses = ("opportunities", "all")
    homepage = "https://reliefweb.int/jobs"
    weight = 1.25

    async def hunt(self, ctx: HuntContext) -> list[RawHit]:
        data = await get_json(ctx, "https://api.reliefweb.int/v1/jobs", params={
            "appname": "nighthawk", "profile": "list", "limit": min(ctx.limit, 20),
            "query[value]": ctx.plan.terms, "sort[]": "date.created:desc",
            "fields[include][]": ["title", "url", "date.created", "source.name", "city"]})
        out = []
        for item in (data.get("data") or [])[:ctx.limit]:
            fields = item.get("fields") or {}
            src = (fields.get("source") or [{}])[0].get("name") or ""
            out.append(RawHit(
                url=fields.get("url") or f"https://reliefweb.int/node/{item.get('id')}",
                title=clean(fields.get("title")),
                snippet=clean(f"{src} · {', '.join(fields.get('city') or [])}"),
                kind="opportunity", published=(fields.get("date") or {}).get("created"),
                deadline=(fields.get("date") or {}).get("closing"),
                tags=("humanitarian", "job")))
        return out


class ReliefWebReports(Provider):
    id, name, family, layer = "reliefweb_reports", "ReliefWeb Reports", "document", "remote"
    description = "Humanitarian reports and assessments, many as direct PDFs."
    lenses = ("files", "opportunities", "datasets", "all")
    homepage = "https://reliefweb.int/updates"
    weight = 1.1

    async def hunt(self, ctx: HuntContext) -> list[RawHit]:
        data = await get_json(ctx, "https://api.reliefweb.int/v1/reports", params={
            "appname": "nighthawk", "profile": "list", "limit": min(ctx.limit, 20),
            "query[value]": ctx.plan.terms, "sort[]": "date.created:desc",
            "fields[include][]": ["title", "url", "date.created", "source.name", "file"]})
        out = []
        for item in (data.get("data") or [])[:ctx.limit]:
            fields = item.get("fields") or {}
            files = fields.get("file") or []
            url = (files[0].get("url") if files else None) or fields.get("url")
            out.append(RawHit(
                url=url or "", title=clean(fields.get("title")),
                snippet=clean(((fields.get("source") or [{}])[0]).get("name") or "ReliefWeb"),
                kind="document", published=(fields.get("date") or {}).get("created"),
                tags=("humanitarian", "pdf")))
        return [h for h in out if h.url]


class EuFunding(Provider):
    id, name, family, layer = "eu_sedia", "EU Funding & Tenders", "opportunity", "remote"
    description = "Horizon Europe and programme calls via the SEDIA search API."
    lenses = ("opportunities", "applications", "all")
    homepage = "https://ec.europa.eu/info/funding-tenders/opportunities/portal/screen/home"
    weight = 1.15

    async def hunt(self, ctx: HuntContext) -> list[RawHit]:
        data = await post_json(
            ctx, "https://api.tech.ec.europa.eu/search-api/search",
            params={"apiKey": "SEDIA", "text": ctx.plan.terms,
                    "pageSize": min(ctx.limit, 20), "pageNumber": 1}, json={})
        out = []
        for item in (data.get("results") or [])[:ctx.limit]:
            meta = item.get("metadata") or {}
            title = (meta.get("title") or item.get("title") or "")
            if isinstance(title, list):
                title = title[0] if title else ""
            ident = meta.get("identifier") or item.get("reference") or ""
            if isinstance(ident, list):
                ident = ident[0] if ident else ""
            deadline = (meta.get("deadlineDate") or meta.get("deadline") or "")
            if isinstance(deadline, list):
                deadline = deadline[0] if deadline else ""
            out.append(RawHit(
                url=item.get("url") or ("https://ec.europa.eu/info/funding-tenders/opportunities/portal/"
                                        f"screen/opportunities/topic-details/{ident}" if ident else ""),
                title=clean(str(title)), kind="opportunity",
                snippet=clean(str(meta.get("frameworkProgramme") or meta.get("status") or "EU call")),
                deadline=str(deadline)[:40] or None, tags=("eu", "funding")))
        return [h for h in out if h.url]
