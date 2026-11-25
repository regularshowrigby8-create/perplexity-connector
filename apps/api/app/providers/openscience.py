"""Open-science layer: preprint servers, registries and repositories that expose
a *submission* timestamp per record.

The point is accuracy on the freshness axis: a preprint posted forty minutes ago
is the freshest scholarly artefact that exists, and most engines only surface it
weeks later, once citations accrue.
"""
from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone
from urllib.parse import quote

from .base import HuntContext, Provider, RawHit, clean, get_json, post_json
from .realtime import _iso, _strip_tags, _terms


def _window(days: int = 14) -> tuple[str, str]:
    today = datetime.now(timezone.utc).date()
    return (today - timedelta(days=days)).isoformat(), today.isoformat()


def _date_parts(value) -> str | None:
    """Crossref/DataCite ``date-parts`` → ISO."""
    parts = (value or {}).get("date-parts") if isinstance(value, dict) else None
    if not parts or not parts[0]:
        return None
    nums = [str(p) for p in parts[0] if p]
    if not nums:
        return None
    while len(nums) < 3:
        nums.append("01")
    return "-".join(nums[:3])


class ArxivNewest(Provider):
    id, name, family, layer = "arxiv-new", "arXiv (submitted today)", "open-science", "remote"
    description = "Preprints sorted by submission time, not by relevance."
    lenses = ("all", "files", "datasets")
    homepage = "https://arxiv.org/list/cs.AI/new"
    weight = 1.15
    rate_note = "3 requests/second courtesy limit"

    async def hunt(self, ctx: HuntContext) -> list[RawHit]:
        query = " OR ".join(f"all:{t}" for t in ctx.plan.terms.split()[:5]) or "all:search"
        resp = await ctx.client.get("http://export.arxiv.org/api/query", params={
            "search_query": query, "sortBy": "submittedDate", "sortOrder": "descending",
            "max_results": min(ctx.limit, 25)})
        resp.raise_for_status()
        import xml.etree.ElementTree as ET

        root = ET.fromstring(resp.text)
        ns = {"a": "http://www.w3.org/2005/Atom"}
        out: list[RawHit] = []
        for entry in root.findall("a:entry", ns)[:ctx.limit]:
            title = clean(entry.findtext("a:title", default="", namespaces=ns))
            summary = clean(entry.findtext("a:summary", default="", namespaces=ns), 320)
            published = entry.findtext("a:published", default="", namespaces=ns) or None
            pdf = None
            for link in entry.findall("a:link", ns):
                if link.get("title") == "pdf":
                    pdf = link.get("href")
            alt = entry.findtext("a:id", default="", namespaces=ns)
            if pdf or alt:
                out.append(RawHit(url=pdf or alt, title=title, snippet=summary, kind="paper",
                                  published=_iso(published), tags=("preprint", "arxiv")))
        return out


class _BioRxivBase(Provider):
    """bioRxiv and medRxiv share one endpoint; both publish a per-version date."""
    server = "biorxiv"
    label = "bioRxiv"
    home = "https://www.biorxiv.org/"
    weight = 1.1

    async def hunt(self, ctx: HuntContext) -> list[RawHit]:
        start, end = _window(10)
        data = await get_json(ctx, f"https://api.biorxiv.org/details/{self.server}/{start}/{end}",
                              params={"cursor": 0})
        collection = (data.get("collection") or [])[:600]
        words = [w for w in re.split(r"\W+", ctx.plan.terms.lower()) if len(w) > 3]
        out: list[RawHit] = []
        for item in collection:
            title = item.get("title") or ""
            haystack = f"{title} {item.get('abstract', '')}".lower()
            if words and not any(w in haystack for w in words):
                continue
            doi = item.get("doi")
            if not doi:
                continue
            out.append(RawHit(
                url=f"https://www.{self.server}.org/content/{doi}v{item.get('version', '1')}",
                title=clean(title) or doi,
                snippet=clean(item.get("abstract") or item.get("category") or "", 320),
                kind="paper", published=_iso(item.get("date")),
                tags=("preprint", self.server),
                meta={"doi": doi, "category": item.get("category")}))
        out.sort(key=lambda h: str(h.published or ""), reverse=True)
        return out[:ctx.limit]


class BioRxivNewest(_BioRxivBase):
    id, name, family, layer = "biorxiv-new", "bioRxiv (last 10 days)", "open-science", "remote"
    description = "Biology preprints by posting date, keyword-filtered."
    lenses = ("all", "files", "datasets")
    homepage = "https://www.biorxiv.org/"
    server, label = "biorxiv", "bioRxiv"


class MedRxivNewest(_BioRxivBase):
    id, name, family, layer = "medrxiv-new", "medRxiv (last 10 days)", "open-science", "remote"
    description = "Health-sciences preprints by posting date, keyword-filtered."
    lenses = ("all", "files", "datasets", "opportunities")
    homepage = "https://www.medrxiv.org/"
    server, label = "medrxiv", "medRxiv"


class EuropePMC(Provider):
    id, name, family, layer = "europepmc", "Europe PMC (newest)", "open-science", "remote"
    description = "35M+ life-science records sorted by first publication date."
    lenses = ("all", "files", "datasets")
    homepage = "https://europepmc.org/"
    weight = 1.05
    rate_note = "no key; be polite"

    async def hunt(self, ctx: HuntContext) -> list[RawHit]:
        data = await get_json(ctx, "https://www.ebi.ac.uk/europepmc/webservices/rest/search",
                              params={"query": f"({ctx.plan.terms}) AND SRC:MED",
                                      "format": "json", "sort": "P_PDATE_D desc",
                                      "pageSize": min(ctx.limit, 25), "resultType": "core"})
        results = ((data.get("resultList") or {}).get("result")) or []
        out: list[RawHit] = []
        for item in results[:ctx.limit]:
            url = (f"https://europepmc.org/article/{item.get('source', 'MED')}/{item.get('id')}"
                   if item.get("id") else None)
            if not url:
                continue
            out.append(RawHit(url=url, title=clean(item.get("title")) or url,
                              snippet=clean(item.get("journalTitle") or item.get("abstractText") or "",
                                            320),
                              kind="paper", published=_iso(item.get("firstPublicationDate")),
                              tags=("open-access", "europepmc"),
                              meta={"doi": item.get("doi"), "pmid": item.get("pmid")}))
        return out


class HAL(Provider):
    id, name, family, layer = "hal", "HAL (French archive)", "open-science", "remote"
    description = "French national open archive, sorted by deposit date."
    lenses = ("all", "files", "datasets")
    homepage = "https://hal.science/"
    weight = 0.95
    rate_note = "no key"

    async def hunt(self, ctx: HuntContext) -> list[RawHit]:
        data = await get_json(ctx, "https://api.archives-ouvertes.fr/search/", params={
            "q": ctx.plan.terms, "rows": min(ctx.limit, 25), "wt": "json",
            "fl": "title_s,uri_s,producedDateY_i,producedDate_tdate,abstract_s,docType_s",
            "sort": "producedDate_tdate desc"})
        docs = ((data.get("response") or {}).get("docs")) or []
        out: list[RawHit] = []
        for doc in docs[:ctx.limit]:
            url = doc.get("uri_s")
            if not url:
                continue
            title = (doc.get("title_s") or [""])[0] if isinstance(doc.get("title_s"), list) else doc.get("title_s")
            abstract = (doc.get("abstract_s") or [""])[0] if isinstance(doc.get("abstract_s"), list) else doc.get("abstract_s")
            out.append(RawHit(url=url, title=clean(title) or url, snippet=clean(abstract or "", 320),
                              kind="paper",
                              published=_iso(doc.get("producedDate_tdate") or doc.get("producedDateY_i")),
                              tags=("open-access", "hal")))
        return out


class OpenAIRE(Provider):
    id, name, family, layer = "openaire", "OpenAIRE Graph", "open-science", "remote"
    description = "EU aggregator of funded research outputs, newest first."
    lenses = ("all", "files", "datasets", "opportunities")
    homepage = "https://graph.openaire.eu/"
    weight = 1.0
    rate_note = "public graph API"

    async def hunt(self, ctx: HuntContext) -> list[RawHit]:
        data = await get_json(ctx, "https://api.openaire.eu/graph/v1/researchProducts", params={
            "search": ctx.plan.terms, "type": "publication", "sortBy": "publicationDate",
            "sortOrder": "desc", "size": min(ctx.limit, 25)})
        results = (data.get("results") or [])[:ctx.limit]
        out: list[RawHit] = []
        for item in results:
            url = (item.get("pid") if str(item.get("pid", "")).startswith("http")
                   else f"https://doi.org/{item.get('pid')}") if item.get("pid") else None
            if not url:
                continue
            out.append(RawHit(url=url, title=clean(item.get("mainTitle")) or url,
                              snippet=clean(item.get("description") or "", 320), kind="paper",
                              published=_iso(item.get("publicationDate")),
                              tags=("open-access", "openaire"),
                              meta={"type": item.get("type")}))
        return out


class DataCite(Provider):
    id, name, family, layer = "datacite", "DataCite (newest DOIs)", "open-science", "remote"
    description = "Dataset and software DOIs by creation date — the moment a dataset lands."
    lenses = ("all", "datasets", "files")
    homepage = "https://datacite.org/"
    weight = 1.1
    rate_note = "public; polite pooling"

    async def hunt(self, ctx: HuntContext) -> list[RawHit]:
        data = await get_json(ctx, "https://api.datacite.org/dois", params={
            "query": ctx.plan.terms, "sort": "-created", "page[size]": min(ctx.limit, 25)})
        rows = ((data.get("data")) or [])[:ctx.limit]
        out: list[RawHit] = []
        for row in rows:
            attrs = row.get("attributes") or {}
            doi = attrs.get("doi") or row.get("id")
            if not doi:
                continue
            titles = attrs.get("titles") or [{}]
            out.append(RawHit(url=attrs.get("url") or f"https://doi.org/{doi}",
                              title=clean(titles[0].get("title")) or doi,
                              snippet=clean((attrs.get("publisher") or "") + " · " +
                                            (attrs.get("types") or {}).get("resourceTypeGeneral", ""),
                                            320),
                              kind="dataset", published=_iso(attrs.get("created") or attrs.get("published")),
                              tags=("dataset", "doi"), meta={"doi": doi,
                                                             "published": attrs.get("published")}))
        return out


class Dryad(Provider):
    id, name, family, layer = "dryad", "Dryad", "open-science", "remote"
    description = "Curated research data with a per-dataset publication date."
    lenses = ("all", "datasets", "files")
    homepage = "https://datadryad.org/"
    weight = 0.95
    rate_note = "no key"

    async def hunt(self, ctx: HuntContext) -> list[RawHit]:
        data = await get_json(ctx, "https://datadryad.org/api/v2/search", params={
            "q": ctx.plan.terms, "per_page": min(ctx.limit, 25)})
        embedded = (data.get("_embedded") or {})
        rows = embedded.get("stash:datasets") or []
        out: list[RawHit] = []
        for row in rows[:ctx.limit]:
            doi = row.get("identifier")
            if not doi:
                continue
            out.append(RawHit(url=f"https://doi.org/{doi}", title=clean(row.get("title")) or doi,
                              snippet="Dryad research data", kind="dataset",
                              published=_iso(row.get("publishedDate")),
                              tags=("dataset", "dryad"), meta={"doi": doi}))
        return out


class OSFPreprints(Provider):
    id, name, family, layer = "osf-preprints", "OSF Preprints", "open-science", "remote"
    description = "Newest preprints across OSF's subject servers, keyword-filtered."
    lenses = ("all", "files", "datasets")
    homepage = "https://osf.io/preprints/"
    weight = 0.9
    rate_note = "public v2 API"

    async def hunt(self, ctx: HuntContext) -> list[RawHit]:
        data = await get_json(ctx, "https://api.osf.io/v2/preprints/", params={
            "page[size]": 50, "sort": "-date_published"})
        words = [w for w in re.split(r"\W+", ctx.plan.terms.lower()) if len(w) > 3]
        out: list[RawHit] = []
        for row in (data.get("data") or []):
            attrs = row.get("attributes") or {}
            title = attrs.get("title") or ""
            haystack = f"{title} {attrs.get('description', '')}".lower()
            if words and not any(w in haystack for w in words):
                continue
            url = ((row.get("links") or {}).get("html"))
            if not url:
                continue
            out.append(RawHit(url=url, title=clean(title) or url,
                              snippet=clean(attrs.get("description") or "", 320), kind="paper",
                              published=_iso(attrs.get("date_published")),
                              tags=("preprint", "osf")))
            if len(out) >= ctx.limit:
                break
        return out


class PubMedNewest(Provider):
    id, name, family, layer = "pubmed-new", "PubMed (in press)", "open-science", "remote"
    description = "MEDLINE records sorted by entry date — the day they are indexed."
    lenses = ("all", "files")
    homepage = "https://pubmed.ncbi.nlm.nih.gov/"
    weight = 1.0
    rate_note = "NCBI E-utilities; 3 requests/second without key"

    async def hunt(self, ctx: HuntContext) -> list[RawHit]:
        search = await get_json(ctx, "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi",
                                params={"db": "pubmed", "term": ctx.plan.terms, "sort": "pub date",
                                        "retmax": min(ctx.limit, 20), "retmode": "json"})
        ids = ((search.get("esearchresult") or {}).get("idlist")) or []
        if not ids:
            return []
        summary = await get_json(ctx, "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esummary.fcgi",
                                 params={"db": "pubmed", "id": ",".join(ids), "retmode": "json"})
        result = summary.get("result") or {}
        out: list[RawHit] = []
        for pmid in ids:
            item = result.get(pmid) or {}
            if not item.get("title"):
                continue
            out.append(RawHit(url=f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/",
                              title=clean(item.get("title")),
                              snippet=clean(f"{item.get('fulljournalname', '')} · "
                                            f"{item.get('pubdate', '')}", 320),
                              kind="paper", published=_iso(item.get("pubdate")),
                              tags=("pubmed",), meta={"pmid": pmid}))
        return out


class DOAJNewest(Provider):
    id, name, family, layer = "doaj-new", "DOAJ (newest)", "open-science", "remote"
    description = "Open-access journal articles ordered by the date they were added."
    lenses = ("all", "files")
    homepage = "https://doaj.org/"
    weight = 0.9
    rate_note = "no key"

    async def hunt(self, ctx: HuntContext) -> list[RawHit]:
        data = await get_json(ctx, f"https://doaj.org/api/search/articles/{quote(ctx.plan.terms)}",
                              params={"pageSize": min(ctx.limit, 25), "sort": "created_date:desc"})
        out: list[RawHit] = []
        for item in (data.get("results") or [])[:ctx.limit]:
            bib = item.get("bibjson") or {}
            links = bib.get("link") or []
            url = (links[0].get("url") if links else None) or f"https://doaj.org/article/{item.get('id')}"
            out.append(RawHit(url=url, title=clean(bib.get("title")) or url,
                              snippet=clean((bib.get("journal") or {}).get("title") or "", 320),
                              kind="paper",
                              published=_iso(item.get("created_date") or bib.get("year")),
                              tags=("open-access", "doaj")))
        return out


class CrossrefNewest(Provider):
    id, name, family, layer = "crossref-new", "Crossref (published today)", "open-science", "remote"
    description = "DOI registrations sorted by publication date — the exact deposit moment."
    lenses = ("all", "files", "datasets")
    homepage = "https://www.crossref.org/"
    weight = 1.05
    rate_note = "public; use mailto for the polite pool"

    async def hunt(self, ctx: HuntContext) -> list[RawHit]:
        data = await get_json(ctx, "https://api.crossref.org/works", params={
            "query": ctx.plan.terms, "sort": "published", "order": "desc",
            "rows": min(ctx.limit, 25), "mailto": "nighthawk@example.org",
            "select": "DOI,title,URL,issued,published,container-title,link,created"})
        items = ((data.get("message") or {}).get("items")) or []
        out: list[RawHit] = []
        for item in items[:ctx.limit]:
            pdf = next((link.get("URL") for link in (item.get("link") or [])
                        if "pdf" in (link.get("content-type") or "")), None)
            stamp = (_date_parts(item.get("published")) or _date_parts(item.get("issued"))
                     or (item.get("created") or {}).get("date-time"))
            out.append(RawHit(url=pdf or item.get("URL") or f"https://doi.org/{item.get('DOI')}",
                              title=clean((item.get("title") or [""])[0]) or item.get("DOI", ""),
                              snippet=clean((item.get("container-title") or [""])[0]),
                              kind="paper", published=_iso(stamp), tags=("doi",),
                              meta={"doi": item.get("DOI")}))
        return out


class OpenAlexNewest(Provider):
    id, name, family, layer = "openalex-new", "OpenAlex (by date)", "open-science", "remote"
    description = "Works sorted by publication date rather than citation count."
    lenses = ("all", "files", "datasets")
    homepage = "https://openalex.org/"
    weight = 1.1
    rate_note = "100k requests/day"

    async def hunt(self, ctx: HuntContext) -> list[RawHit]:
        data = await get_json(ctx, "https://api.openalex.org/works", params={
            "search": ctx.plan.terms, "sort": "publication_date:desc",
            "per-page": min(ctx.limit, 25), "mailto": "nighthawk@example.org"})
        out: list[RawHit] = []
        for work in (data.get("results") or [])[:ctx.limit]:
            oa = work.get("best_oa_location") or {}
            url = oa.get("pdf_url") or oa.get("landing_page_url") or work.get("doi") or work.get("id")
            if not url:
                continue
            out.append(RawHit(url=url, title=clean(work.get("title")) or url,
                              snippet=clean(((work.get("primary_location") or {}).get("source") or {})
                                            .get("display_name") or "", 320),
                              kind="paper", published=_iso(work.get("publication_date")),
                              tags=("open-access",) if oa.get("pdf_url") else ("scholarly",),
                              meta={"doi": work.get("doi")}))
        return out


class SemanticScholarNewest(Provider):
    id, name, family, layer = "s2-new", "Semantic Scholar (bulk)", "open-science", "remote"
    description = "Bulk search sorted by publication date, with open PDF links."
    lenses = ("all", "files")
    homepage = "https://www.semanticscholar.org/"
    weight = 1.0
    rate_note = "1 request/second unauthenticated"

    async def hunt(self, ctx: HuntContext) -> list[RawHit]:
        data = await get_json(ctx, "https://api.semanticscholar.org/graph/v1/paper/search/bulk",
                              params={"query": ctx.plan.terms, "sort": "publicationDate:desc",
                                      "fields": "title,abstract,publicationDate,externalIds,openAccessPdf,url"})
        out: list[RawHit] = []
        for paper in ((data.get("data") or []))[:ctx.limit]:
            url = ((paper.get("openAccessPdf") or {}).get("url") or paper.get("url")
                   or f"https://www.semanticscholar.org/paper/{paper.get('paperId')}")
            out.append(RawHit(url=url, title=clean(paper.get("title")) or url,
                              snippet=clean(paper.get("abstract") or "", 320), kind="paper",
                              published=_iso(paper.get("publicationDate")),
                              tags=("scholarly",), meta={"ids": paper.get("externalIds")}))
        return out
