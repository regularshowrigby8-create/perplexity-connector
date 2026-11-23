"""Open-data catalogues: CKAN portals, World Bank, Hugging Face."""
from __future__ import annotations

from .base import HuntContext, Provider, RawHit, clean, get_json


class CKAN(Provider):
    id, name, family, layer = "ckan", "CKAN Portal", "dataset", "remote"
    description = "Any CKAN catalogue: datasets + direct resource file links."
    lenses = ("datasets", "files", "all")
    homepage = "https://ckan.org/"
    base = "https://catalog.data.gov"
    weight = 1.2

    async def hunt(self, ctx: HuntContext) -> list[RawHit]:
        data = await get_json(ctx, f"{self.base}/api/3/action/package_search", params={
            "q": ctx.plan.terms, "rows": min(ctx.limit, 15)})
        result = data.get("result") or {}
        out: list[RawHit] = []
        for pkg in (result.get("results") or [])[:ctx.limit]:
            org = (pkg.get("organization") or {}).get("title") or ""
            for res in (pkg.get("resources") or [])[:2]:
                url = res.get("url") or ""
                if not url:
                    continue
                out.append(RawHit(
                    url=url, title=clean(res.get("name") or pkg.get("title")),
                    snippet=clean(f"{org} · {res.get('format') or 'file'} · {pkg.get('title')}"),
                    kind="dataset", published=(res.get("last_modified") or "")[:10] or None,
                    tags=("open-data", (res.get("format") or "").lower()),
                    meta={"package": pkg.get("title")}))
        return out


def _ckan_variant(base: str, name: str, pid: str, homepage: str) -> type[CKAN]:
    return type(f"CKAN_{pid}", (CKAN,), {
        "id": pid, "name": name, "base": base, "homepage": homepage, "weight": 0.9,
        "description": f"{name} open-data catalogue (CKAN API)."})


DataGov = _ckan_variant("https://catalog.data.gov", "Data.gov", "datagov", "https://data.gov/")
DataGovUK = _ckan_variant("https://data.gov.uk", "Data.gov.uk", "datagovuk", "https://data.gov.uk/")
DataGovAU = _ckan_variant("https://data.gov.au", "Data.gov.au", "datagovau", "https://data.gov.au/")
DataGovEU = _ckan_variant("https://data.europa.eu", "EU Open Data", "dataeuropa", "https://data.europa.eu/")
OpenCanada = _ckan_variant("https://open.canada.ca", "Open Canada", "opencanada", "https://open.canada.ca/")


class WorldBankDocs(Provider):
    id, name, family, layer = "worldbank_docs", "World Bank Documents", "document", "remote"
    description = "Project documents, reports and PDFs from the World Bank."
    lenses = ("files", "datasets", "opportunities")
    homepage = "https://documents.worldbank.org/"
    weight = 1.2

    async def hunt(self, ctx: HuntContext) -> list[RawHit]:
        data = await get_json(ctx, "https://search.worldbank.org/api/v2/wds", params={
            "format": "json", "qterm": ctx.plan.terms,
            "fl": "docdt,display_title,pdfurl,txturl,count,docna", "rows": min(ctx.limit, 15)})
        docs = data.get("documents") or {}
        out = []
        for key, doc in docs.items():
            if not isinstance(doc, dict) or key == "facets":
                continue
            url = doc.get("pdfurl") or doc.get("txturl")
            if not url:
                continue
            out.append(RawHit(url=url, title=clean(doc.get("display_title")),
                              snippet=clean(f"World Bank · {doc.get('count') or 'document'}"),
                              kind="document", published=(doc.get("docdt") or "")[:10] or None,
                              tags=("world-bank", "pdf")))
        return out[:ctx.limit]


class WorldBankData(Provider):
    id, name, family, layer = "worldbank_data", "World Bank Data", "dataset", "remote"
    description = "Indicator time-series — numbers engines ignore."
    lenses = ("datasets",)
    homepage = "https://data.worldbank.org/"
    weight = 0.9

    async def hunt(self, ctx: HuntContext) -> list[RawHit]:
        from urllib.parse import quote
        data = await get_json(ctx, f"https://api.worldbank.org/v2/indicator?format=json&per_page=20&q={quote(ctx.plan.terms)}")
        rows = data[1] if isinstance(data, list) and len(data) > 1 else []
        return [RawHit(url=f"https://data.worldbank.org/indicator/{r.get('id')}",
                       title=clean(r.get("name")), snippet=clean(r.get("sourceNote"), 300),
                       kind="dataset", tags=("indicator",))
                for r in (rows or [])[:ctx.limit] if r.get("id")]


class HuggingFaceDatasets(Provider):
    id, name, family, layer = "huggingface", "Hugging Face Datasets", "dataset", "remote"
    description = "ML datasets and Parquet/CSV files behind model training."
    lenses = ("datasets", "files")
    homepage = "https://huggingface.co/datasets"
    weight = 0.9

    async def hunt(self, ctx: HuntContext) -> list[RawHit]:
        data = await get_json(ctx, "https://huggingface.co/api/datasets", params={
            "search": ctx.plan.terms, "limit": min(ctx.limit, 20)})
        return [RawHit(url=f"https://huggingface.co/datasets/{d.get('id')}",
                       title=str(d.get("id")), snippet=clean(", ".join(d.get("tags") or []), 240),
                       published=(d.get("lastModified") or "")[:10] or None,
                       kind="dataset", tags=("ml", "dataset"))
                for d in (data or [])[:ctx.limit]]
