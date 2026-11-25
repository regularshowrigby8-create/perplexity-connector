"""One registry of every independent engine the monster can call."""
from __future__ import annotations

from .providers import (archives, code, datasets, filehosts, launchers, metasearch, opendata,
                        openscience, opportunities, opportunities_live, realtime, scholar, vault,
                        web)
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
# ---- the freshness layer (added to make newest-first truthful) -------------
REALTIME = [
    realtime.GDelt(), realtime.RSSFirehose(), realtime.RedditNew(), realtime.RedditSubreddit(),
    realtime.HackerNewsNew(), realtime.Lobsters(), realtime.MastodonTag(), realtime.BlueskySearch(),
    realtime.GitHubCommits(), realtime.GitHubIssues(), realtime.GitLabProjects(),
    realtime.GitHubAdvisories(), realtime.WikipediaRevisions(), realtime.StackExchangeNew(),
    realtime.CratesNew(), realtime.NpmNew(),
]
OPEN_SCIENCE = [
    openscience.ArxivNewest(), openscience.BioRxivNewest(), openscience.MedRxivNewest(),
    openscience.CrossrefNewest(), openscience.OpenAlexNewest(), openscience.SemanticScholarNewest(),
    openscience.EuropePMC(), openscience.PubMedNewest(), openscience.DOAJNewest(),
    openscience.DataCite(), openscience.Dryad(), openscience.HAL(), openscience.OpenAIRE(),
    openscience.OSFPreprints(),
]
OPEN_DATA = [
    opendata.SocrataCatalog(), opendata.FederalRegister(), opendata.USAspendingNew(),
    opendata.DataGouvFr(), opendata.DataEuropa(), opendata.CKANRecent(), opendata.ArcGISHub(),
    opendata.ClinicalTrials(), opendata.SECEdgarCurrent(), opendata.ZenodoNewest(),
    opendata.HuggingFaceRecent(), opendata.WikidataRecent(),
]
OPPORTUNITIES_LIVE = [
    opportunities_live.GrantsGovLive(), opportunities_live.TED(),
    opportunities_live.UKRIGateway(), opportunities_live.FindATenderUK(),
    opportunities_live.WorldBankProcurement(), opportunities_live.CORDIS(),
    opportunities_live.FundsforNGOsSearch(), opportunities_live.UNDPProcurement(),
]
# The file hosts: the only engines here that look inside MediaFire, APKPure,
# archive.org's software collection or SourceForge. Dispatched when a query
# names a file type or a host, and alongside the files lens.
FILE_HOSTS = [engine() for engine in filehosts.FILE_HOSTS]
LOCAL = [vault.Vault(), vault.VaultFullText()]
LAUNCHERS = [launchers.Portals(), launchers.DorkLauncher()]

PROVIDERS: list[Provider] = [*WEB, *METASEARCH, *ARCHIVES, *OPPORTUNITIES, *SCHOLAR,
                             *DATASETS, *CODE, *REALTIME, *OPEN_SCIENCE, *OPEN_DATA,
                             *OPPORTUNITIES_LIVE, *FILE_HOSTS, *LOCAL, *LAUNCHERS]

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


def file_hosts() -> list[Provider]:
    """The file-host engines, dispatched when the query asks for files."""
    return list(FILE_HOSTS)


def describe() -> list[dict]:
    return [{
        "id": p.id, "name": p.name, "family": p.family, "layer": p.layer,
        "description": p.description, "lenses": list(p.lenses), "homepage": p.homepage,
        "requires": list(p.requires), "needs_network": p.needs_network,
        "rate_note": p.rate_note, "status": p.status(), "opt_in": p.opt_in,
        "retired": p.retired, "weight": p.weight,
    } for p in PROVIDERS]
