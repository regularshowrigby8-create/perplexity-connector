"""One registry of every independent engine the monster can call."""
from __future__ import annotations

from .providers import archives, code, datasets, launchers, metasearch, opportunities, scholar, vault, web
from .providers.base import Provider

WEB = [
    web.SearxNG(), web.Brave(), web.Tavily(), web.Exa(), web.Serper(), web.SerpApi(),
    web.SearchApi(), web.GoogleCSE(), web.Perplexity(), web.YouCom(),
    web.SerpApiBing(), web.SerpApiYahoo(), web.SerpApiEcosia(), web.SerpApiStartpage(),
    web.SerpApiYandex(), web.SerpApiScholar(), web.SerpApiNews(),
]
METASEARCH = [
    metasearch.Mojeek(), metasearch.Qwant(), metasearch.MetaGer(), metasearch.Whoogle(),
    metasearch.LibreX(), metasearch.Forget(), metasearch.YaCy(), metasearch.Wiby(),
    metasearch.Marginalia(), metasearch.Gigablast(),
]
ARCHIVES = [
    archives.CommonCrawl(), archives.Wayback(), archives.InternetArchive(), archives.ArquivoPT(),
]
OPPORTUNITIES = [
    opportunities.GrantsGov(), opportunities.ReliefWebJobs(), opportunities.ReliefWebReports(),
    opportunities.EuFunding(), opportunities.NihReporter(), opportunities.NsfAwards(),
    opportunities.UsaSpending(),
]
SCHOLAR = [
    scholar.OpenAlex(), scholar.Crossref(), scholar.Arxiv(), scholar.DOAJ(), scholar.PubMed(),
    scholar.SemanticScholar(), scholar.CORE(), scholar.Wikipedia(), scholar.Wikidata(),
    scholar.OpenLibrary(), scholar.Zenodo(), scholar.Figshare(),
]
DATASETS = [
    datasets.DataGov(), datasets.DataGovUK(), datasets.DataGovEU(), datasets.DataGovAU(),
    datasets.OpenCanada(), datasets.WorldBankDocs(), datasets.WorldBankData(),
    datasets.HuggingFaceDatasets(), datasets.CKAN(),
]
CODE = [
    code.GitHub(), code.GitLab(), code.HackerNews(), code.StackExchange(), code.Npm(),
    code.Crates(),
]
LOCAL = [vault.Vault(), vault.VaultFullText()]
LAUNCHERS = [launchers.Portals(), launchers.DorkLauncher()]

PROVIDERS: list[Provider] = [*WEB, *METASEARCH, *ARCHIVES, *OPPORTUNITIES, *SCHOLAR,
                             *DATASETS, *CODE, *LOCAL, *LAUNCHERS]

CRAWLER = {
    "id": "crawler",
    "name": "Fusion Crawler",
    "family": "crawl",
    "layer": "core",
    "description": "Primary engine: own frontier, own fetchers, own extractors, no ceiling.",
    "lenses": ["all", "files", "opportunities", "applications", "exposed", "datasets"],
    "homepage": "/crawl",
    "requires": [],
    "needs_network": True,
    "rate_note": "self-hosted; politeness configurable",
    "configured": True,
}

BY_ID: dict[str, Provider] = {p.id: p for p in PROVIDERS}


def for_lens(lens: str) -> list[Provider]:
    if lens == "all":
        return [p for p in PROVIDERS if "all" in p.lenses]
    return [p for p in PROVIDERS if lens in p.lenses or "all" in p.lenses]


def describe() -> list[dict]:
    return [{
        "id": p.id, "name": p.name, "family": p.family, "layer": p.layer,
        "description": p.description, "lenses": list(p.lenses), "homepage": p.homepage,
        "requires": list(p.requires), "needs_network": p.needs_network,
        "rate_note": p.rate_note, "status": p.status(), "opt_in": p.opt_in,
        "retired": p.retired, "weight": p.weight,
    } for p in PROVIDERS]
