"""The portal universe: real, high-signal sources that mainstream engines bury.

Every entry is a live public site. `search` is a deep link built with {q}; `domains`
are used to aim the archive crawlers (Common Crawl / Wayback / Internet Archive)
at places where documents actually live.
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Portal:
    name: str
    domains: tuple[str, ...]
    lenses: tuple[str, ...]
    search: str
    topics: tuple[str, ...] = ()
    note: str = ""
    kind: str = "portal"


P = Portal

PORTALS: tuple[Portal, ...] = (
    # ---------------------------------------------------------------- opportunities
    P("Grants.gov", ("grants.gov",), ("opportunities", "applications"),
      "https://www.grants.gov/search-results?keywords={q}", ("grant", "funding", "federal", "usa", "us"), "US federal funding opportunities, forecast + posted"),
    P("EU Funding & Tenders", ("ec.europa.eu",), ("opportunities", "applications"),
      "https://ec.europa.eu/info/funding-tenders/opportunities/portal/screen/opportunities/topic-search;keywords={q}",
      ("grant", "eu", "europe", "horizon", "funding"), "Horizon Europe + programme calls"),
    P("TED — Tenders Electronic Daily", ("ted.europa.eu",), ("opportunities",),
      "https://ted.europa.eu/en/search/result?FT={q}", ("tender", "procurement", "eu", "contract"), "EU public procurement notices"),
    P("UNGM — UN Global Marketplace", ("ungm.org",), ("opportunities",),
      "https://www.ungm.org/Public/Notice?keywords={q}", ("tender", "un", "procurement", "supplier"), "UN procurement notices"),
    P("ReliefWeb", ("reliefweb.int",), ("opportunities", "files"),
      "https://reliefweb.int/updates?search={q}", ("humanitarian", "ngo", "job", "tender", "crisis"), "Humanitarian jobs, tenders and reports"),
    P("UNjobs", ("unjobs.org",), ("opportunities",),
      "https://unjobs.org/search?q={q}", ("un", "job", "vacancy", "consultant"), "UN system vacancies"),
    P("UNDP Procurement", ("undp.org",), ("opportunities",),
      "https://www.undp.org/procurement", ("undp", "tender", "development"), "UNDP notices"),
    P("World Bank Procurement", ("worldbank.org",), ("opportunities", "files"),
      "https://projects.worldbank.org/en/projects-operations/procurement", ("world bank", "tender", "development"), "Bank-funded contracts"),
    P("SAM.gov", ("sam.gov",), ("opportunities",),
      "https://sam.gov/search/?keywords={q}", ("usa", "contract", "federal", "opportunity"), "US federal contract opportunities"),
    P("Find a Tender (UK)", ("find-tender.service.gov.uk",), ("opportunities",),
      "https://www.find-tender.service.gov.uk/Search/Results?keywords={q}", ("uk", "tender", "procurement"), "UK public contracts"),
    P("eTenders South Africa", ("etenders.gov.za",), ("opportunities",),
      "https://www.etenders.gov.za/Home/opportunities?id=1", ("south africa", "tender", "za", "procurement"), "SA government tenders"),
    P("CORDIS", ("cordis.europa.eu",), ("opportunities", "datasets", "files"),
      "https://cordis.europa.eu/search?q={q}", ("eu", "research", "project", "grant"), "EU-funded project results"),
    P("NSF Funding", ("nsf.gov",), ("opportunities",),
      "https://www.nsf.gov/funding/opportunities?q={q}", ("usa", "science", "research", "grant"), "US science funding"),
    P("NIH Grants", ("grants.nih.gov",), ("opportunities",),
      "https://grants.nih.gov/search/results?query={q}", ("usa", "health", "biomedical", "grant"), "US health research funding"),
    P("UKRI Opportunities", ("ukri.org",), ("opportunities",),
      "https://www.ukri.org/opportunity/?search={q}", ("uk", "research", "funding"), "UK Research & Innovation calls"),
    P("Wellcome Funding", ("wellcome.org",), ("opportunities",),
      "https://wellcome.org/grant-funding/schemes?search={q}", ("health", "research", "grant"), "Wellcome schemes"),
    P("IDRC Funding", ("idrc-crdi.ca",), ("opportunities",),
      "https://idrc-crdi.ca/en/funding?search={q}", ("canada", "development", "grant"), "Canadian development research grants"),
    P("Gates Foundation Grants", ("gatesfoundation.org",), ("opportunities",),
      "https://www.gatesfoundation.org/about/committed-grants?search={q}", ("health", "development", "grant"), "Committed grants database"),
    P("FundsforNGOs", ("fundsforngos.org",), ("opportunities",),
      "https://www2.fundsforngos.org/?s={q}", ("ngo", "grant", "funding"), "NGO funding calls"),
    P("Opportunity Desk", ("opportunitydesk.org",), ("opportunities", "applications"),
      "https://opportunitydesk.org/?s={q}", ("fellowship", "scholarship", "youth", "africa"), "Fellowships and scholarships"),
    P("Scholars4Dev", ("scholars4dev.com",), ("opportunities", "applications"),
      "https://www.scholars4dev.com/?s={q}", ("scholarship", "developing", "study"), "Scholarships for developing countries"),
    P("Idealist", ("idealist.org",), ("opportunities",),
      "https://www.idealist.org/en/search?q={q}", ("nonprofit", "job", "volunteer"), "Nonprofit jobs and actions"),
    P("Devex", ("devex.com",), ("opportunities",),
      "https://www.devex.com/search?q={q}", ("development", "job", "tender"), "Global development marketplace"),
    P("UN Careers", ("careers.un.org",), ("opportunities",),
      "https://careers.un.org/jobSearch?keyword={q}", ("un", "job", "career"), "UN secretariat vacancies"),
    P("African Development Bank", ("afdb.org",), ("opportunities", "files"),
      "https://www.afdb.org/en/projects-and-operations/procurement", ("africa", "tender", "development"), "AfDB procurement"),
    P("FCDO International Funding", ("gov.uk",), ("opportunities", "files"),
      "https://www.gov.uk/international-development-funding?keywords={q}", ("uk", "development", "funding"), "UK development funding"),
    P("Echoing Green", ("echoinggreen.org",), ("opportunities", "applications"),
      "https://echoinggreen.org/fellowship/", ("fellowship", "social", "entrepreneur"), "Social entrepreneurship fellowship"),
    P("Y Combinator", ("ycombinator.com",), ("opportunities", "applications"),
      "https://www.ycombinator.com/apply", ("startup", "accelerator", "funding"), "Startup accelerator applications"),
    # ------------------------------------------------------------------- documents
    P("World Bank Documents", ("documents.worldbank.org", "documents1.worldbank.org"), ("files", "datasets", "opportunities"),
      "https://documents.worldbank.org/en/publication/documents-reports?queryterm={q}", ("world bank", "report", "development"), "Bank reports, PDFs, datasets"),
    P("World Bank Open Knowledge", ("openknowledge.worldbank.org",), ("files", "datasets"),
      "https://openknowledge.worldbank.org/search?query={q}", ("report", "development", "policy"), "Open access publications"),
    P("UN Digital Library", ("digitallibrary.un.org", "documents.un.org"), ("files", "opportunities"),
      "https://digitallibrary.un.org/search?ln=en&p={q}", ("un", "resolution", "report"), "UN documents and resolutions"),
    P("WHO IRIS", ("iris.who.int",), ("files", "datasets"),
      "https://iris.who.int/discover?query={q}", ("health", "who", "report"), "WHO institutional repository"),
    P("FAO Documents", ("fao.org",), ("files", "datasets"),
      "https://www.fao.org/documents/en/?q={q}", ("food", "agriculture", "report"), "FAO document repository"),
    P("OECD", ("oecd.org",), ("files", "datasets"),
      "https://www.oecd.org/en/search-results.html?q={q}", ("policy", "economy", "report"), "OECD papers and data"),
    P("IMF Publications", ("imf.org",), ("files", "datasets"),
      "https://www.imf.org/en/Publications/Search#q={q}", ("economy", "finance", "report"), "IMF publications"),
    P("ILO", ("ilo.org",), ("files", "opportunities"),
      "https://www.ilo.org/publications?search={q}", ("labour", "work", "report"), "Labour research and calls"),
    P("UNHCR", ("unhcr.org",), ("files", "opportunities"),
      "https://www.unhcr.org/search?q={q}", ("refugee", "humanitarian", "report"), "Refugee data and reports"),
    P("Open Knowledge Repository", ("openknowledge.worldbank.org",), ("files", "datasets"),
      "https://openknowledge.worldbank.org/search?query={q}", ("repository", "open access", "report"), "Open access knowledge"),
    P("BASE", ("base-search.net",), ("files", "datasets"),
      "https://www.base-search.net/Search/Results?lookfor={q}", ("academic", "repository", "paper"), "100M+ scholarly documents"),
    P("CORE", ("core.ac.uk",), ("files", "datasets"),
      "https://core.ac.uk/search?q={q}", ("academic", "repository", "pdf"), "Open access paper aggregator"),
    P("OpenAIRE", ("openaire.eu",), ("files", "datasets"),
      "https://explore.openaire.eu/search/find?keyword={q}", ("eu", "research", "open science"), "EU research graph"),
    # -------------------------------------------------------------------- datasets
    P("Data.gov", ("catalog.data.gov", "data.gov"), ("datasets", "files"),
      "https://catalog.data.gov/dataset?q={q}", ("usa", "dataset", "open data"), "US federal open data"),
    P("Data.gov.uk", ("data.gov.uk",), ("datasets", "files"),
      "https://www.data.gov.uk/search?q={q}", ("uk", "dataset", "open data"), "UK open data"),
    P("EU Open Data Portal", ("data.europa.eu",), ("datasets", "files"),
      "https://data.europa.eu/data/datasets?query={q}", ("eu", "dataset", "open data"), "European open data"),
    P("Data.gov.au", ("data.gov.au",), ("datasets", "files"),
      "https://data.gov.au/search?q={q}", ("australia", "dataset", "open data"), "Australian open data"),
    P("Open Canada", ("open.canada.ca",), ("datasets", "files"),
      "https://open.canada.ca/en/search/reg?q={q}", ("canada", "dataset", "open data"), "Canadian open data"),
    P("Hugging Face Datasets", ("huggingface.co",), ("datasets", "files"),
      "https://huggingface.co/datasets?search={q}", ("ai", "dataset", "machine learning"), "ML datasets and files"),
    P("Zenodo", ("zenodo.org",), ("datasets", "files"),
      "https://zenodo.org/search?q={q}", ("research", "dataset", "doi"), "CERN research repository"),
    P("Figshare", ("figshare.com",), ("datasets", "files"),
      "https://figshare.com/search?q={q}", ("research", "dataset", "figure"), "Research outputs"),
    P("Dryad", ("datadryad.org",), ("datasets", "files"),
      "https://datadryad.org/search?q={q}", ("research", "dataset", "biology"), "Curated research data"),
    # ------------------------------------------------------------------ applications
    P("Common App", ("commonapp.org",), ("applications",),
      "https://www.commonapp.org/", ("university", "admission", "usa"), "US undergraduate applications"),
    P("DAAD Scholarships", ("daad.de",), ("applications", "opportunities"),
      "https://www2.daad.de/deutschland/stipendium/datenbank/en/21148-scholarship-database/?q={q}", ("germany", "scholarship", "study"), "German academic exchange"),
    P("Erasmus+", ("erasmus-plus.ec.europa.eu",), ("applications", "opportunities"),
      "https://erasmus-plus.ec.europa.eu/search?keys={q}", ("eu", "education", "exchange"), "EU education programmes"),
    P("Voluntary Service / ESC", ("europa.eu",), ("applications", "opportunities"),
      "https://europa.eu/youth/volunteering_en", ("volunteer", "youth", "eu"), "European Solidarity Corps"),
)

TOPIC_TOKENS = {
    "climate": ("climate", "environment", "energy", "green"),
    "health": ("health", "medical", "biomed", "disease", "who"),
    "africa": ("africa", "kenya", "nigeria", "ghana", "south africa", "uganda", "tanzania", "zambia", "rwanda", "ethiopia"),
    "ai": ("ai", "machine learning", "ml", "llm", "data science"),
    "education": ("school", "education", "student", "university", "scholarship"),
    "humanitarian": ("humanitarian", "refugee", "crisis", "relief", "emergency"),
    "development": ("development", "poverty", "sustainab", "sdg"),
}


def portal_hits(query: str, lens: str, limit: int = 14) -> list[tuple[Portal, str]]:
    """Rank portals by lens + topical fit and return (portal, deep link)."""
    from urllib.parse import quote_plus

    q = query.lower()
    scored: list[tuple[float, Portal, str]] = []
    for portal in PORTALS:
        if lens != "all" and lens not in portal.lenses:
            continue
        score = 0.0
        hay = " ".join((portal.name.lower(), *portal.topics, *portal.domains))
        for word in set(q.split()):
            if len(word) > 2 and word in hay:
                score += 3
        for topic, words in TOPIC_TOKENS.items():
            if topic in hay and any(w in q for w in words):
                score += 2
        if lens in portal.lenses:
            score += 1
        if not score:
            continue
        url = portal.search.replace("{q}", quote_plus(query))
        scored.append((score, portal, url))
    scored.sort(key=lambda item: -item[0])
    return [(portal, url) for _, portal, url in scored[:limit]]


def portal_domains(query: str, lens: str, site: str | None, cap: int = 6) -> list[str]:
    if site:
        return [site]
    picks = portal_hits(query, lens, limit=cap * 2)
    seen: list[str] = []
    for portal, _ in picks:
        domain = portal.domains[0]
        if domain not in seen:
            seen.append(domain)
        if len(seen) >= cap:
            break
    return seen
