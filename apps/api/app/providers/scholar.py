"""Scholarly + reference engines: papers, PDFs, books, entities."""
from __future__ import annotations

import re
import xml.etree.ElementTree as ET

from .base import HuntContext, Provider, RawHit, clean, get_json, post_json


class OpenAlex(Provider):
    id, name, family, layer = "openalex", "OpenAlex", "scholar", "remote"
    description = "250M+ scholarly works with open-access PDF links."
    lenses = ("files", "datasets", "all")
    homepage = "https://openalex.org/"
    weight = 1.3

    async def hunt(self, ctx: HuntContext) -> list[RawHit]:
        data = await get_json(ctx, "https://api.openalex.org/works", params={
            "search": ctx.plan.terms, "per-page": min(ctx.limit, 25), "mailto": "nighthawk@example.org"})
        out = []
        for work in (data.get("results") or [])[:ctx.limit]:
            oa = work.get("best_oa_location") or {}
            url = oa.get("pdf_url") or oa.get("landing_page_url") or work.get("doi") or work.get("id")
            if not url:
                continue
            out.append(RawHit(
                url=url, title=clean(work.get("title")),
                snippet=clean((work.get("abstract_inverted_index") and "Abstract available") or
                              ((work.get("primary_location") or {}).get("source") or {}).get("display_name")),
                kind="paper", published=work.get("publication_date"),
                tags=("open-access",) if oa.get("pdf_url") else ("scholarly",),
                meta={"cited_by": work.get("cited_by_count"), "doi": work.get("doi")},
            ))
        return out


class Crossref(Provider):
    id, name, family, layer = "crossref", "Crossref", "scholar", "remote"
    description = "DOI registry — 150M+ records, licensing and full-text links."
    lenses = ("files", "all")
    homepage = "https://www.crossref.org/"
    weight = 1.1

    async def hunt(self, ctx: HuntContext) -> list[RawHit]:
        data = await get_json(ctx, "https://api.crossref.org/works", params={
            "query": ctx.plan.terms, "rows": min(ctx.limit, 20),
            "select": "DOI,title,URL,issued,container-title,link,author"})
        items = ((data.get("message") or {}).get("items")) or []
        out = []
        for item in items[:ctx.limit]:
            pdf = next((l.get("URL") for l in (item.get("link") or [])
                        if "pdf" in (l.get("content-type") or "")), None)
            issued = ((item.get("issued") or {}).get("date-parts") or [[None]])[0]
            out.append(RawHit(
                url=pdf or item.get("URL") or f"https://doi.org/{item.get('DOI')}",
                title=clean((item.get("title") or [""])[0]),
                snippet=clean((item.get("container-title") or [""])[0]),
                kind="paper", published="-".join(str(p) for p in issued if p) or None,
                tags=("doi",), meta={"doi": item.get("DOI")},
            ))
        return out


class Arxiv(Provider):
    id, name, family, layer = "arxiv", "arXiv", "scholar", "remote"
    description = "Preprint server with direct PDF endpoints."
    lenses = ("files", "datasets", "all")
    homepage = "https://arxiv.org/"
    weight = 1.2

    async def hunt(self, ctx: HuntContext) -> list[RawHit]:
        query = " OR ".join(f"all:{t}" for t in ctx.plan.terms.split()[:6]) or "all:search"
        resp = await ctx.client.get("http://export.arxiv.org/api/query", params={
            "search_query": query, "max_results": min(ctx.limit, 20), "sortBy": "relevance"})
        resp.raise_for_status()
        root = ET.fromstring(resp.text)
        ns = {"a": "http://www.w3.org/2005/Atom"}
        out = []
        for entry in root.findall("a:entry", ns)[:ctx.limit]:
            title = clean((entry.findtext("a:title", default="", namespaces=ns)))
            summary = clean(entry.findtext("a:summary", default="", namespaces=ns), 320)
            published = entry.findtext("a:published", default="", namespaces=ns)[:10] or None
            pdf = None
            for link in entry.findall("a:link", ns):
                if link.get("title") == "pdf":
                    pdf = link.get("href")
            alt = entry.findtext("a:id", default="", namespaces=ns)
            if pdf or alt:
                out.append(RawHit(url=pdf or alt, title=title, snippet=summary,
                                  kind="paper", published=published, tags=("preprint", "pdf")))
        return out


class DOAJ(Provider):
    id, name, family, layer = "doaj", "DOAJ", "scholar", "remote"
    description = "Directory of Open Access Journals — fully open full text."
    lenses = ("files", "all")
    homepage = "https://doaj.org/"
    weight = 1.0

    async def hunt(self, ctx: HuntContext) -> list[RawHit]:
        from urllib.parse import quote
        data = await get_json(ctx, f"https://doaj.org/api/search/articles/{quote(ctx.plan.terms)}",
                              params={"pageSize": min(ctx.limit, 20)})
        out = []
        for item in (data.get("results") or [])[:ctx.limit]:
            bib = item.get("bibjson") or {}
            links = bib.get("link") or []
            url = (links[0].get("url") if links else None) or f"https://doaj.org/article/{item.get('id')}"
            out.append(RawHit(url=url, title=clean(bib.get("title")),
                              snippet=clean((bib.get("journal") or {}).get("title")),
                              kind="paper", published=str(bib.get("year") or "") or None,
                              tags=("open-access",)))
        return out


class PubMed(Provider):
    id, name, family, layer = "pubmed", "PubMed", "scholar", "remote"
    description = "Biomedical literature via NCBI E-utilities."
    lenses = ("files", "all")
    homepage = "https://pubmed.ncbi.nlm.nih.gov/"
    weight = 1.05

    async def hunt(self, ctx: HuntContext) -> list[RawHit]:
        search = await get_json(ctx, "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi", params={
            "db": "pubmed", "term": ctx.plan.terms, "retmode": "json",
            "retmax": min(ctx.limit, 15)})
        ids = ((search.get("esearchresult") or {}).get("idlist")) or []
        if not ids:
            return []
        summary = await get_json(ctx, "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esummary.fcgi", params={
            "db": "pubmed", "id": ",".join(ids), "retmode": "json"})
        result = summary.get("result") or {}
        out = []
        for pid in ids:
            item = result.get(pid) or {}
            if not item.get("title"):
                continue
            out.append(RawHit(
                url=f"https://pubmed.ncbi.nlm.nih.gov/{pid}/", title=clean(item.get("title")),
                snippet=clean(item.get("fulljournalname") or item.get("source")),
                kind="paper", published=item.get("pubdate"), tags=("pubmed", "biomed")))
        return out


class SemanticScholar(Provider):
    id, name, family, layer = "semanticscholar", "Semantic Scholar", "scholar", "remote"
    description = "AI-ranked corpus of 200M+ papers with open PDFs."
    lenses = ("files", "all")
    homepage = "https://www.semanticscholar.org/"
    weight = 1.0

    async def hunt(self, ctx: HuntContext) -> list[RawHit]:
        data = await get_json(ctx, "https://api.semanticscholar.org/graph/v1/paper/search", params={
            "query": ctx.plan.terms, "limit": min(ctx.limit, 20),
            "fields": "title,abstract,url,openAccessPdf,year,externalIds"})
        out = []
        for paper in (data.get("data") or [])[:ctx.limit]:
            pdf = (paper.get("openAccessPdf") or {}).get("url")
            out.append(RawHit(url=pdf or paper.get("url") or "", title=clean(paper.get("title")),
                              snippet=clean(paper.get("abstract"), 320), kind="paper",
                              published=str(paper.get("year") or "") or None,
                              tags=("open-access",) if pdf else ()))
        return [h for h in out if h.url]


class CORE(Provider):
    id, name, family, layer = "core", "CORE", "scholar", "remote"
    description = "Aggregates 300M+ open-access documents from repositories."
    lenses = ("files", "datasets")
    homepage = "https://core.ac.uk/"
    requires = ("core_api_key",)
    weight = 1.0

    async def hunt(self, ctx: HuntContext) -> list[RawHit]:
        data = await get_json(
            ctx, "https://api.core.ac.uk/v3/search/works",
            params={"q": ctx.plan.terms, "limit": min(ctx.limit, 20)},
            headers={"Authorization": f"Bearer {self.key(ctx, 'core_api_key')}"})
        return [RawHit(url=r.get("downloadUrl") or r.get("sourceFulltextUrls", [None])[0] or "",
                       title=clean(r.get("title")), snippet=clean(r.get("abstract"), 300),
                       kind="paper", published=r.get("publishedDate"), tags=("open-access",))
                for r in (data.get("results") or [])[:ctx.limit] if r.get("title")]


class Wikipedia(Provider):
    id, name, family, layer = "wikipedia", "Wikipedia", "reference", "remote"
    description = "Encyclopaedic context for a query before you dig."
    lenses = ("all", "opportunities")
    homepage = "https://www.wikipedia.org/"

    async def hunt(self, ctx: HuntContext) -> list[RawHit]:
        data = await get_json(ctx, "https://en.wikipedia.org/w/api.php", params={
            "action": "query", "list": "search", "srsearch": ctx.plan.terms,
            "format": "json", "srlimit": min(ctx.limit, 8), "origin": "*"})
        out = []
        for item in ((data.get("query") or {}).get("search") or [])[:ctx.limit]:
            out.append(RawHit(
                url="https://en.wikipedia.org/wiki/" + item.get("title", "").replace(" ", "_"),
                title=clean(item.get("title")), snippet=clean(item.get("snippet")),
                kind="reference", published=(item.get("timestamp") or "")[:10] or None))
        return out


class Wikidata(Provider):
    id, name, family, layer = "wikidata", "Wikidata", "reference", "remote"
    description = "Structured entity graph: organisations, funders, places."
    lenses = ("all", "opportunities", "datasets")
    homepage = "https://www.wikidata.org/"
    weight = 0.8

    async def hunt(self, ctx: HuntContext) -> list[RawHit]:
        data = await get_json(ctx, "https://www.wikidata.org/w/api.php", params={
            "action": "wbsearchentities", "search": ctx.plan.terms, "language": "en",
            "format": "json", "limit": min(ctx.limit, 10)})
        return [RawHit(url=f"https://www.wikidata.org/wiki/{item.get('id')}",
                       title=clean(item.get("label") or item.get("id")),
                       snippet=clean(item.get("description")), kind="entity", tags=("entity",))
                for item in (data.get("search") or [])[:ctx.limit]]


class OpenLibrary(Provider):
    id, name, family, layer = "openlibrary", "Open Library", "reference", "remote"
    description = "Book metadata with borrowable and public-domain files."
    lenses = ("all", "files")
    homepage = "https://openlibrary.org/"

    async def hunt(self, ctx: HuntContext) -> list[RawHit]:
        data = await get_json(ctx, "https://openlibrary.org/search.json", params={
            "q": ctx.plan.terms, "limit": min(ctx.limit, 10)})
        return [RawHit(url=f"https://openlibrary.org{doc.get('key')}",
                       title=clean(doc.get("title")),
                       snippet=clean(", ".join((doc.get("author_name") or [])[:3])),
                       kind="book", published=str(doc.get("first_publish_year") or "") or None,
                       meta={"ebook_access": doc.get("ebook_access")})
                for doc in (data.get("docs") or [])[:ctx.limit]]


class Zenodo(Provider):
    id, name, family, layer = "zenodo", "Zenodo", "dataset", "remote"
    description = "CERN repository: datasets, software, preprints with DOIs."
    lenses = ("datasets", "files", "all")
    homepage = "https://zenodo.org/"

    async def hunt(self, ctx: HuntContext) -> list[RawHit]:
        data = await get_json(ctx, "https://zenodo.org/api/records", params={
            "q": ctx.plan.terms, "size": min(ctx.limit, 20), "sort": "mostrecent"})
        out = []
        for rec in ((data.get("hits") or {}).get("hits")) or []:
            meta = rec.get("metadata") or {}
            files = rec.get("files") or []
            url = (files[0].get("links", {}).get("self") if files else None) or rec.get("links", {}).get("self_html")
            out.append(RawHit(url=url or "", title=clean(meta.get("title")),
                              snippet=clean(meta.get("description"), 300), kind="dataset",
                              published=meta.get("publication_date"),
                              tags=tuple((meta.get("resource_type") or {}).get("type", "").split()) or ("doi",)))
        return [h for h in out if h.url][:ctx.limit]


class Figshare(Provider):
    id, name, family, layer = "figshare", "Figshare", "dataset", "remote"
    description = "Research outputs, figures and supplementary files."
    lenses = ("datasets", "files")
    homepage = "https://figshare.com/"
    weight = 0.8

    async def hunt(self, ctx: HuntContext) -> list[RawHit]:
        data = await post_json(ctx, "https://api.figshare.com/v2/articles/search", json={
            "search_for": ctx.plan.terms, "page_size": min(ctx.limit, 15)})
        out = []
        for art in (data or [])[:ctx.limit]:
            out.append(RawHit(url=art.get("url_public_html") or art.get("url") or "",
                              title=clean(art.get("title")),
                              snippet=clean(art.get("description"), 260), kind="dataset",
                              published=(art.get("published_date") or "")[:10] or None))
        return [h for h in out if h.url]
