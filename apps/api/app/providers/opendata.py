"""Open-data layer: portals that stamp every record with a modification time.

These engines are where a spreadsheet or a dump appears first. Each one reports
``metadata_created`` / ``modified`` / ``last_update``, so a dataset that landed
ten minutes ago can lead a newest-first result instead of waiting to be linked.
"""
from __future__ import annotations

import json
import re
from datetime import datetime, timedelta, timezone

from .base import HuntContext, Provider, RawHit, clean, get_json, post_json
from .realtime import _iso, _strip_tags, _terms


def _recent(iso_text: str | None, days: int = 400) -> bool:
    """Cheap guard so portals that ignore the sort parameter cannot flood a hunt."""
    stamp = _iso(iso_text)
    if not stamp:
        return True
    try:
        parsed = datetime.fromisoformat(stamp.replace("Z", "+00:00"))
    except ValueError:
        return True
    return parsed >= datetime.now(timezone.utc) - timedelta(days=days)


class SocrataCatalog(Provider):
    id, name, family, layer = "socrata", "Socrata catalog", "opendata", "remote"
    description = "Discovery API across every Socrata city/state/federal portal."
    lenses = ("all", "datasets", "files")
    homepage = "https://api.us.socrata.com/api/catalog/v1"
    weight = 1.05
    rate_note = "no key"

    async def hunt(self, ctx: HuntContext) -> list[RawHit]:
        data = await get_json(ctx, "https://api.us.socrata.com/api/catalog/v1", params={
            "q": ctx.plan.terms, "limit": min(ctx.limit, 25), "only": "dataset"})
        out: list[RawHit] = []
        for result in (data.get("results") or [])[:ctx.limit]:
            resource = result.get("resource") or {}
            metadata = result.get("metadata") or {}
            domain = (metadata.get("domain") or "").replace("http://", "").replace("https://", "")
            rid = resource.get("id")
            if not (domain and rid):
                continue
            out.append(RawHit(
                url=f"https://{domain}/d/{rid}",
                title=clean(resource.get("name")) or rid,
                snippet=clean(resource.get("description") or metadata.get("description") or "", 320),
                kind="dataset", published=_iso(resource.get("updatedAt") or resource.get("createdAt")),
                tags=("dataset", "socrata"),
                meta={"portal": domain, "rows": resource.get("rowsUpdatedAt")}))
        return out


class SECEdgarCurrent(Provider):
    id, name, family, layer = "sec-edgar", "SEC EDGAR (latest filings)", "opendata", "remote"
    description = "Filings as they hit EDGAR, minutes after the filing agent submits them."
    lenses = ("all", "files", "opportunities")
    homepage = "https://www.sec.gov/edgar/searchedgar/currentevents.htm"
    weight = 0.95
    rate_note = "10 requests/second with a contact User-Agent"

    async def hunt(self, ctx: HuntContext) -> list[RawHit]:
        resp = await ctx.client.get(
            "https://www.sec.gov/cgi-bin/browse-edgar",
            params={"action": "getcurrent", "type": "", "company": "", "dateb": "",
                    "owner": "include", "count": min(ctx.limit, 40), "output": "atom"},
            headers={"User-Agent": "Nighthawk research nighthawk@example.org"})
        resp.raise_for_status()
        import xml.etree.ElementTree as ET

        root = ET.fromstring(resp.text)
        out: list[RawHit] = []
        for entry in root.iter("{http://www.w3.org/2005/Atom}entry"):
            title = (entry.findtext("{http://www.w3.org/2005/Atom}title") or "").strip()
            link_el = entry.find("{http://www.w3.org/2005/Atom}link")
            url = link_el.get("href") if link_el is not None else None
            updated = entry.findtext("{http://www.w3.org/2005/Atom}updated")
            if not (url and title):
                continue
            if ctx.plan.terms and not any(word in title.lower()
                                          for word in ctx.plan.terms.lower().split()[:4]):
                continue
            out.append(RawHit(url=url, title=clean(title), snippet="SEC filing",
                              kind="document", published=_iso(updated),
                              tags=("sec", "filing")))
        return out[:ctx.limit]


class DataGouvFr(Provider):
    id, name, family, layer = "data-gouv-fr", "data.gouv.fr", "opendata", "remote"
    description = "French national open-data portal, newest datasets first."
    lenses = ("all", "datasets", "files")
    homepage = "https://www.data.gouv.fr/"
    weight = 0.9
    rate_note = "no key"

    async def hunt(self, ctx: HuntContext) -> list[RawHit]:
        data = await get_json(ctx, "https://www.data.gouv.fr/api/1/datasets/", params={
            "q": ctx.plan.terms, "page_size": min(ctx.limit, 25), "sort": "-last_update"})
        out: list[RawHit] = []
        for item in (data.get("data") or [])[:ctx.limit]:
            url = item.get("page")
            if not url:
                continue
            out.append(RawHit(url=url, title=clean(item.get("title")) or url,
                              snippet=clean(item.get("description") or "", 320), kind="dataset",
                              published=_iso(item.get("last_update") or item.get("created_at")),
                              tags=("dataset", "france"),
                              meta={"org": (item.get("organization") or {}).get("name")}))
        return out


class DataEuropa(Provider):
    id, name, family, layer = "data-europa", "data.europa.eu", "opendata", "remote"
    description = "EU open-data catalogue via its CKAN endpoint, newest first."
    lenses = ("all", "datasets", "files")
    homepage = "https://data.europa.eu/"
    weight = 0.9
    rate_note = "CKAN API"

    async def hunt(self, ctx: HuntContext) -> list[RawHit]:
        data = await get_json(ctx, "https://data.europa.eu/api/hub/search/search", params={
            "q": ctx.plan.terms, "limit": min(ctx.limit, 25), "facets": "{}",
            "sort": "modified desc"})
        results = ((data.get("result") or {}).get("results")) or []
        out: list[RawHit] = []
        for item in results[:ctx.limit]:
            url = item.get("id") or item.get("landingPage")
            if not url:
                continue
            out.append(RawHit(url=url if str(url).startswith("http")
                              else f"https://data.europa.eu/data/datasets/{url}",
                              title=clean(item.get("title")) or url,
                              snippet=clean(item.get("description") or "", 320), kind="dataset",
                              published=_iso(item.get("modified") or item.get("issued")),
                              tags=("dataset", "eu")))
        return out


class USAspendingNew(Provider):
    id, name, family, layer = "usaspending-new", "USAspending (new awards)", "opendata", "remote"
    description = "Federal awards sorted by start date — money that moved this week."
    lenses = ("all", "opportunities", "datasets")
    homepage = "https://www.usaspending.gov/"
    weight = 1.0
    rate_note = "POST API, no key"

    async def hunt(self, ctx: HuntContext) -> list[RawHit]:
        body = {
            "filters": {"keywords": [ctx.plan.terms],
                        "award_type_codes": ["A", "B", "C", "D"]},
            "fields": ["Award ID", "Recipient Name", "Award Amount", "Description",
                       "Start Date", "Awarding Agency", "generated_internal_id"],
            "page": 1, "limit": min(ctx.limit, 25), "sort": "Start Date", "order": "desc",
            "subawards": False,
        }
        data = await post_json(ctx, "https://api.usaspending.gov/api/v2/search/spending_by_award/",
                               json=body)
        out: list[RawHit] = []
        for row in (data.get("results") or [])[:ctx.limit]:
            internal = row.get("generated_internal_id") or row.get("Award ID")
            if not internal:
                continue
            out.append(RawHit(
                url=f"https://www.usaspending.gov/award/{internal}",
                title=clean(f"{row.get('Recipient Name', '')} — {row.get('Description', '')}")[:160],
                snippet=clean(f"{row.get('Awarding Agency', '')} · {row.get('Award Amount', '')}"),
                kind="opportunity", published=_iso(row.get("Start Date")),
                tags=("award", "funding", "usa"),
                meta={"amount": row.get("Award Amount"), "agency": row.get("Awarding Agency")}))
        return out


class ArcGISHub(Provider):
    id, name, family, layer = "arcgis-hub", "ArcGIS Hub", "opendata", "remote"
    description = "Every municipal, state and NGO ArcGIS portal, sorted by modification."
    lenses = ("all", "datasets", "files")
    homepage = "https://hub.arcgis.com/search"
    weight = 0.85
    rate_note = "public sharing API"

    async def hunt(self, ctx: HuntContext) -> list[RawHit]:
        data = await get_json(ctx, "https://www.arcgis.com/sharing/rest/search", params={
            "q": ctx.plan.terms, "num": min(ctx.limit, 25), "sortField": "modified",
            "sortOrder": "desc", "f": "json"})
        out: list[RawHit] = []
        for item in (data.get("results") or [])[:ctx.limit]:
            url = item.get("url") or (f"https://www.arcgis.com/home/item.html?id={item.get('id')}"
                                      if item.get("id") else None)
            if not url:
                continue
            out.append(RawHit(url=url, title=clean(item.get("title")) or url,
                              snippet=clean(item.get("snippet") or item.get("type") or "", 320),
                              kind="dataset", published=_iso(item.get("modified")),
                              tags=("dataset", "gis"), meta={"type": item.get("type")}))
        return out


class ClinicalTrials(Provider):
    id, name, family, layer = "clinicaltrials", "ClinicalTrials.gov (updated)", "opendata", "remote"
    description = "Trials by last-update date — protocols change before papers appear."
    lenses = ("all", "datasets", "opportunities")
    homepage = "https://clinicaltrials.gov/"
    weight = 0.95
    rate_note = "API v2, no key"

    async def hunt(self, ctx: HuntContext) -> list[RawHit]:
        data = await get_json(ctx, "https://clinicaltrials.gov/api/v2/studies", params={
            "query.term": ctx.plan.terms, "sort": "LastUpdatePostDate:desc",
            "pageSize": min(ctx.limit, 25), "fields": "NCTId,BriefTitle,LastUpdatePostDate,OverallStatus"})
        out: list[RawHit] = []
        for study in (data.get("studies") or [])[:ctx.limit]:
            section = (study.get("protocolSection") or {})
            ident = section.get("identificationModule") or {}
            status = section.get("statusModule") or {}
            nct = ident.get("nctId")
            if not nct:
                continue
            out.append(RawHit(url=f"https://clinicaltrials.gov/study/{nct}",
                              title=clean(ident.get("briefTitle")) or nct,
                              snippet=clean(status.get("overallStatus") or ""), kind="paper",
                              published=_iso((status.get("lastUpdatePostDateStruct") or {}).get("date")),
                              tags=("trial",), meta={"status": status.get("overallStatus")}))
        return out


class CKANRecent(Provider):
    """Three national portals, one provider, each queried with a real sort."""
    id, name, family, layer = "ckan-recent", "CKAN portals (latest)", "opendata", "remote"
    description = "data.gov.au, data.gov.ie and data.govt.nz sorted by creation time."
    lenses = ("all", "datasets", "files")
    homepage = "https://ckan.org/"
    weight = 0.9
    rate_note = "CKAN action API; one request per portal"
    PORTALS = (
        ("https://data.gov.au/data", "Australia"),
        ("https://data.gov.ie/api/3", "Ireland"),
        ("https://catalogue.data.govt.nz/api/3", "New Zealand"),
    )

    async def hunt(self, ctx: HuntContext) -> list[RawHit]:
        import asyncio

        async def one(base: str, label: str) -> list[RawHit]:
            try:
                data = await get_json(ctx, f"{base.rstrip('/')}/action/package_search", params={
                    "q": ctx.plan.terms, "rows": 10, "sort": "metadata_created desc"})
                results = ((data.get("result") or {}).get("results")) or []
            except Exception:
                return []
            hits = []
            for item in results:
                title = item.get("title") or item.get("name")
                if not title:
                    continue
                hits.append(RawHit(url=item.get("url") or f"{base}/dataset/{item.get('name')}",
                                   title=clean(title),
                                   snippet=clean(item.get("notes") or "", 320), kind="dataset",
                                   published=_iso(item.get("metadata_created")
                                                  or item.get("metadata_modified")),
                                   tags=("dataset", label.lower()),
                                   meta={"portal": label}))
            return hits

        import asyncio as _asyncio

        batches = await _asyncio.gather(*(one(b, label) for b, label in self.PORTALS),
                                        return_exceptions=True)
        out: list[RawHit] = []
        for batch in batches:
            if isinstance(batch, list):
                out.extend(batch)
        return out[:ctx.limit]


class FederalRegister(Provider):
    id, name, family, layer = "federal-register", "Federal Register", "opendata", "remote"
    description = "US rules, notices and funding announcements the hour they publish."
    lenses = ("all", "opportunities", "files")
    homepage = "https://www.federalregister.gov/"
    weight = 1.1
    rate_note = "no key"

    async def hunt(self, ctx: HuntContext) -> list[RawHit]:
        data = await get_json(ctx, "https://www.federalregister.gov/api/v1/documents.json", params={
            "conditions[term]": ctx.plan.terms, "order": "newest",
            "per_page": min(ctx.limit, 25),
            "fields[]": ["html_url", "title", "publication_date", "type", "abstract"]})
        out: list[RawHit] = []
        for doc in (data.get("results") or [])[:ctx.limit]:
            url = doc.get("html_url")
            if not url:
                continue
            out.append(RawHit(url=url, title=clean(doc.get("title")) or url,
                              snippet=clean(doc.get("abstract") or doc.get("type") or "", 320),
                              kind="document", published=_iso(doc.get("publication_date")),
                              tags=("regulation", "usa"), meta={"type": doc.get("type")}))
        return out


class ZenodoNewest(Provider):
    id, name, family, layer = "zenodo-new", "Zenodo (most recent)", "opendata", "remote"
    description = "CERN's repository sorted by publication date — datasets, code, reports."
    lenses = ("all", "datasets", "files")
    homepage = "https://zenodo.org/"
    weight = 1.0
    rate_note = "no key; 60 requests/minute"

    async def hunt(self, ctx: HuntContext) -> list[RawHit]:
        data = await get_json(ctx, "https://zenodo.org/api/records", params={
            "q": ctx.plan.terms, "sort": "mostrecent", "size": min(ctx.limit, 25)})
        out: list[RawHit] = []
        for record in ((data.get("hits") or {}).get("hits") or [])[:ctx.limit]:
            meta = record.get("metadata") or {}
            url = ((record.get("links") or {}).get("self_html")
                   or ((record.get("links") or {}).get("self")))
            if not url:
                continue
            out.append(RawHit(url=url, title=clean(meta.get("title")) or url,
                              snippet=clean(meta.get("description") or "", 320), kind="dataset",
                              published=_iso(meta.get("publication_date") or record.get("created")),
                              tags=("dataset", "zenodo"),
                              meta={"doi": record.get("doi"),
                                    "type": (meta.get("resource_type") or {}).get("type")}))
        return out


class HuggingFaceRecent(Provider):
    id, name, family, layer = "hf-models", "Hugging Face (last modified)", "opendata", "remote"
    description = "Models, datasets and spaces by last modification — seconds of latency."
    lenses = ("all", "datasets", "files")
    homepage = "https://huggingface.co/models"
    weight = 1.0
    rate_note = "no key"

    async def hunt(self, ctx: HuntContext) -> list[RawHit]:
        out: list[RawHit] = []
        for kind, path in (("model", "models"), ("dataset", "datasets")):
            try:
                data = await get_json(ctx, f"https://huggingface.co/api/{path}", params={
                    "search": ctx.plan.terms, "sort": "lastModified", "direction": -1,
                    "limit": min(ctx.limit, 20)})
            except Exception:
                continue
            for repo in data or []:
                rid = repo.get("id") or repo.get("modelId")
                if not rid:
                    continue
                out.append(RawHit(url=f"https://huggingface.co/{path}/{rid}", title=rid,
                                  snippet=clean(f"{kind} · {repo.get('pipeline_tag') or ''}"),
                                  kind="dataset" if kind == "dataset" else "repo",
                                  published=_iso(repo.get("lastModified")),
                                  tags=(kind, "ml"), meta={"downloads": repo.get("downloads")}))
        return out[:ctx.limit]


class WikidataRecent(Provider):
    id, name, family, layer = "wikidata-recent", "Wikidata (last modified)", "opendata", "remote"
    description = "Entities matching the query with their last-revision timestamp."
    lenses = ("all", "datasets")
    homepage = "https://www.wikidata.org/"
    weight = 0.7
    rate_note = "MediaWiki API"

    async def hunt(self, ctx: HuntContext) -> list[RawHit]:
        search = await get_json(ctx, "https://www.wikidata.org/w/api.php", params={
            "action": "query", "list": "search", "srsearch": ctx.plan.terms,
            "srlimit": min(ctx.limit, 20), "format": "json"})
        ids = [hit.get("title") for hit in
               ((search.get("query") or {}).get("search") or []) if hit.get("title")]
        if not ids:
            return []
        entities = await get_json(ctx, "https://www.wikidata.org/w/api.php", params={
            "action": "wbgetentities", "ids": "|".join(ids[:20]), "props": "info|labels",
            "languages": "en", "format": "json"})
        out: list[RawHit] = []
        for qid, entity in (entities.get("entities") or {}).items():
            if not isinstance(entity, dict) or "missing" in entity:
                continue
            label = ((entity.get("labels") or {}).get("en") or {}).get("value") or qid
            out.append(RawHit(url=f"https://www.wikidata.org/wiki/{qid}", title=clean(label),
                              snippet=f"Wikidata entity {qid}", kind="page",
                              published=_iso(entity.get("modified")), tags=("reference", "wikidata"),
                              meta={"qid": qid}))
        return out
