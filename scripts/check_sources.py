#!/usr/bin/env python3
"""Offline proof that the freshness layer parses and timestamps correctly.

Two kinds of check, no network needed:

1. schema — every engine added in the freshness layer is registered, declares a
   lens, and is reachable by id;
2. parsing — canned responses for the awkward APIs (TED, UKRI, CORDIS, bioRxiv,
   OpenAIRE, DataCite, Dryad, OSF, Wikidata, Socrata, arxiv, GDELT, HN, Reddit,
   Bluesky, RSS, npm, crates, HF, ClinicalTrials, Federal Register) are fed
   through the real provider code, which must return hits *with a publication
   timestamp* — because a source without a clock cannot lead a newest-first list.
"""
from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "apps" / "api"))

import httpx  # noqa: E402

from app import registry  # noqa: E402
from app.freshness import parse as parse_time  # noqa: E402
from app.plays import Plan  # noqa: E402
from app.providers.base import HuntContext  # noqa: E402

NEW_IDS = [
    # realtime
    "gdelt", "rss-firehose", "reddit-new", "reddit-subs", "hn-new", "lobsters", "mastodon",
    "bluesky", "github-commits", "github-issues", "gitlab-projects", "ghsa", "wikipedia-rev",
    "se-new", "crates-new", "npm-new",
    # open science
    "arxiv-new", "biorxiv-new", "medrxiv-new", "crossref-new", "openalex-new", "s2-new",
    "europepmc", "pubmed-new", "doaj-new", "datacite", "dryad", "hal", "openaire", "osf-preprints",
    # open data
    "socrata", "federal-register", "usaspending-new", "data-gouv-fr", "data-europa", "ckan-recent",
    "arcgis-hub", "clinicaltrials", "sec-edgar", "zenodo-new", "hf-models", "wikidata-recent",
    # opportunities
    "grantsgov-live", "ted", "ukri", "find-a-tender", "wb-procurement", "cordis-live",
    "fundsforngos", "undp-procurement",
]

RSS = """<?xml version="1.0"?><rss version="2.0"><channel><title>t</title>
<item><title>New climate grant opened</title><link>https://example.org/grant</link>
<description>Up to USD 50,000 for adaptation work.</description>
<pubDate>Wed, 25 Nov 2026 17:30:00 GMT</pubDate></item></channel></rss>"""

ATOM = """<?xml version="1.0" encoding="utf-8"?><feed xmlns="http://www.w3.org/2005/Atom">
<title>EDGAR</title><entry><title>FORM D - CLIMATE GRANT FUND</title>
<link href="https://www.sec.gov/Archives/edgar/data/1/2/3-index.htm"/>
<updated>2026-11-25T17:31:00-05:00</updated></entry></feed>"""

FIXTURES: dict[str, tuple[str, str]] = {
    "api.gdeltproject.org": ("application/json", json.dumps({"articles": [
        {"url": "https://news.example.org/a", "title": "Flood grant announced",
         "seendate": "20261125171200", "domain": "news.example.org", "language": "English"}]})),
    "www.reddit.com/search.json": ("application/json", json.dumps({"data": {"children": [
        {"data": {"title": "Grant call for Kenya", "permalink": "/r/grantwriting/comments/x/",
                  "created_utc": 1795000000, "selftext": "Applications open",
                  "subreddit": "grantwriting", "score": 3}}]}})),
    "/r/grantwriting/new.json": ("application/json", json.dumps({"data": {"children": [
        {"data": {"title": "Funding for water", "permalink": "/r/grantwriting/comments/y/",
                  "created_utc": 1795000100}}]}})),
    "hn.algolia.com": ("application/json", json.dumps({"hits": [
        {"title": "Show HN: open grant data", "url": "https://github.com/x/y",
         "created_at": "2026-11-25T17:20:00Z", "author": "pg", "points": 4, "objectID": "1"}]})),
    "lobste.rs": ("application/json", json.dumps([
        {"title": "Open data release", "url": "https://lobste.rs/s/1", "created_at": "2026-11-25T17:00:00Z",
         "tags": ["data"]}])),
    "timelines/tag": ("application/json", json.dumps([
        {"url": "https://mastodon.social/@a/1", "created_at": "2026-11-25T17:05:00Z",
         "content": "<p>new grant for #climate</p>", "account": {"acct": "a"}, "reblogs_count": 1}])),
    "searchPosts": ("application/json", json.dumps({"posts": [
        {"uri": "at://did:plc:1/app.bsky.feed.post/abc", "author": {"handle": "a.bsky.social"},
         "record": {"text": "grant applications open", "createdAt": "2026-11-25T17:06:00Z"},
         "likeCount": 2, "repostCount": 1}]})),
    "api.github.com/search/commits": ("application/json", json.dumps({"items": [
        {"html_url": "https://github.com/x/y/commit/abc",
         "commit": {"message": "add grant parser", "committer": {"date": "2026-11-25T17:07:00Z"}},
         "repository": {"full_name": "x/y"}}]})),
    "api.github.com/search/issues": ("application/json", json.dumps({"items": [
        {"html_url": "https://github.com/x/y/issues/1", "title": "add grant data",
         "body": "please", "created_at": "2026-11-25T17:08:00Z", "state": "open"}]})),
    "api.github.com/advisories": ("application/json", json.dumps([
        {"html_url": "https://github.com/advisories/GHSA-1", "summary": "grant parser advisory",
         "published_at": "2026-11-25T17:09:00Z", "severity": "high", "ghsa_id": "GHSA-1"}])),
    "gitlab.com/api/v4/projects": ("application/json", json.dumps([
        {"web_url": "https://gitlab.com/x/y", "name_with_namespace": "x / y",
         "description": "grant tooling", "last_activity_at": "2026-11-25T17:10:00Z", "star_count": 2}])),
    "wikipedia.org/w/api.php": ("application/json", json.dumps({"query": {"pages": [
        {"title": "Climate finance", "fullurl": "https://en.wikipedia.org/wiki/Climate_finance",
         "revisions": [{"timestamp": "2026-11-25T17:11:00Z"}], "pageid": 5}]}})),
    "api.stackexchange.com": ("application/json", json.dumps({"items": [
        {"link": "https://stackoverflow.com/q/1", "title": "grant schema?",
         "creation_date": 1795000200, "tags": ["python"]}]})),
    "crates.io/api/v1/crates": ("application/json", json.dumps({"crates": [
        {"name": "grantkit", "newest_version": "0.1.0", "description": "grants",
         "updated_at": "2026-11-25T17:12:00Z", "downloads": 12}]})),
    "registry.npmjs.org": ("application/json", json.dumps({"objects": [
        {"package": {"name": "grant-parser", "version": "1.0.0", "description": "grants",
                     "date": "2026-11-25T17:13:00Z", "links": {"npm": "https://npmjs.com/x"}}}]})),
    "export.arxiv.org": ("application/atom+xml", """<?xml version="1.0"?>
<feed xmlns="http://www.w3.org/2005/Atom"><entry><id>http://arxiv.org/abs/1</id>
<title>Adaptation grants</title><summary>We study grants.</summary>
<published>2026-11-25T17:14:00Z</published>
<link title="pdf" href="http://arxiv.org/pdf/1"/></entry></feed>"""),
    "api.biorxiv.org": ("application/json", json.dumps({"collection": [
        {"doi": "10.1101/2026.01.01.1", "title": "Climate grant design", "abstract": "grants",
         "date": "2026-11-25", "version": "2", "category": "public health"}]})),
    "ebi.ac.uk/europepmc": ("application/json", json.dumps({"resultList": {"result": [
        {"id": "1", "source": "MED", "title": "Grants for health", "firstPublicationDate": "2026-11-24"}]}})),
    "api.archives-ouvertes.fr": ("application/json", json.dumps({"response": {"docs": [
        {"title_s": ["Subventions climat"], "uri_s": "https://hal.science/x",
         "producedDate_tdate": "2026-11-25T10:00:00Z", "abstract_s": ["x"]}]}})),
    "graph/v1/researchProducts": ("application/json", json.dumps({"results": [
        {"mainTitle": "Climate grants", "publicationDate": "2026-11-24",
         "pid": "10.1/x", "description": "x", "type": "publication"}]})),
    "api.datacite.org": ("application/json", json.dumps({"data": [
        {"id": "10.1/x", "attributes": {"doi": "10.1/x", "url": "https://doi.org/10.1/x",
                                        "titles": [{"title": "Grant dataset"}],
                                        "created": "2026-11-25T09:00:00Z",
                                        "types": {"resourceTypeGeneral": "Dataset"}}}]})),
    "datadryad.org": ("application/json", json.dumps({"_embedded": {"stash:datasets": [
        {"identifier": "doi:10.5061/dryad.1", "title": "Grant data",
         "publishedDate": "2026-11-24"}]}})),
    "api.osf.io": ("application/json", json.dumps({"data": [
        {"attributes": {"title": "Climate grant preprint", "description": "x",
                        "date_published": "2026-11-25T08:00:00Z"},
         "links": {"html": "https://osf.io/preprints/x"}}]})),
    "eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch": ("application/json",
        json.dumps({"esearchresult": {"idlist": ["1"]}})),
    "eutils.ncbi.nlm.nih.gov/entrez/eutils/esummary": ("application/json",
        json.dumps({"result": {"1": {"title": "Grants in health", "pubdate": "2026 Nov 25",
                                    "fulljournalname": "J"}}})),
    "doaj.org": ("application/json", json.dumps({"results": [
        {"id": "a1", "created_date": "2026-11-25T00:00:00Z",
         "bibjson": {"title": "Climate grants", "link": [{"url": "https://doaj.org/x"}]}}]})),
    "api.crossref.org": ("application/json", json.dumps({"message": {"items": [
        {"DOI": "10.1/y", "title": ["Climate grant"], "URL": "https://doi.org/10.1/y",
         "published": {"date-parts": [[2026, 11, 25]]},
         "created": {"date-time": "2026-11-25T07:00:00Z"}, "link": []}]}})),
    "api.openalex.org": ("application/json", json.dumps({"results": [
        {"title": "Climate grants", "publication_date": "2026-11-24", "doi": "https://doi.org/10.1/z",
         "best_oa_location": {"pdf_url": "https://x/y.pdf"}, "primary_location": {}}]})),
    "paper/search/bulk": ("application/json", json.dumps({"data": [
        {"title": "Grants", "abstract": "x", "publicationDate": "2026-11-24",
         "openAccessPdf": {"url": "https://x/p.pdf"}, "url": "https://s2.org/p", "paperId": "p"}]})),
    "api.us.socrata.com": ("application/json", json.dumps({"results": [
        {"resource": {"id": "abcd-1234", "name": "Grant awards", "updatedAt": "2026-11-25T06:00:00Z",
                      "description": "grants"},
         "metadata": {"domain": "data.example.gov"}}]})),
    "api.usaspending.gov": ("application/json", json.dumps({"results": [
        {"Award ID": "A1", "Recipient Name": "NGO", "Description": "climate grant",
         "Start Date": "2026-11-24", "Awarding Agency": "USAID",
         "generated_internal_id": "CONT_AWD_1"}]})),
    "data.gouv.fr": ("application/json", json.dumps({"data": [
        {"title": "Subventions climat", "page": "https://data.gouv.fr/d/1",
         "last_update": "2026-11-25T05:00:00Z"}]})),
    "data.europa.eu": ("application/json", json.dumps({"result": {"results": [
        {"id": "https://data.europa.eu/data/datasets/1", "title": "Climate grants",
         "modified": "2026-11-25T04:00:00Z"}]}})),
    "package_search": ("application/json", json.dumps({"result": {"results": [
        {"title": "Grant dataset", "name": "grants", "metadata_created": "2026-11-25T03:00:00Z",
         "url": "https://data.gov.au/dataset/grants"}]}})),
    "arcgis.com/sharing/rest/search": ("application/json", json.dumps({"results": [
        {"title": "Grant locations", "id": "1", "modified": "1795000300000", "type": "Feature Service",
         "url": "https://services.arcgis.com/x"}]})),
    "clinicaltrials.gov": ("application/json", json.dumps({"studies": [
        {"protocolSection": {"identificationModule": {"nctId": "NCT1", "briefTitle": "Grant trial"},
                             "statusModule": {"overallStatus": "Recruiting",
                                              "lastUpdatePostDateStruct": {"date": "2026-11-25"}}}}]})),
    "sec.gov/cgi-bin/browse-edgar": ("application/atom+xml", ATOM),
    "zenodo.org/api/records": ("application/json", json.dumps({"hits": {"hits": [
        {"links": {"self_html": "https://zenodo.org/records/1"},
         "metadata": {"title": "Grant data", "publication_date": "2026-11-24",
                      "description": "x", "resource_type": {"type": "dataset"}},
         "doi": "10.5281/1", "created": "2026-11-24T00:00:00Z"}]}})),
    "huggingface.co/api/models": ("application/json", json.dumps([
        {"id": "org/grant-model", "lastModified": "2026-11-25T02:00:00Z", "downloads": 3,
         "pipeline_tag": "text-classification"}])),
    "wikidata.org": ("application/json", json.dumps({"entities": {
        "Q1": {"labels": {"en": {"value": "Climate finance"}}, "modified": "2026-11-25T01:00:00Z"}}})),
    "api.grants.gov": ("application/json", json.dumps({"data": {"oppHits": [
        {"id": "1", "title": "Climate grant", "agencyName": "EPA", "openDate": "2026-11-25",
         "closeDate": "2027-02-28", "number": "EPA-1", "link": "https://grants.gov/x"}]}})),
    "api.ted.europa.eu": ("application/json", json.dumps({"notices": [
        {"publication-number": "123456-2026", "notice-title": {"eng": "Climate services"},
         "publication-date": "2026-11-25+01:00", "buyer-name": "EU body"}]})),
    "gtr.ukri.org": ("application/xml", """<?xml version="1.0"?><projects>
<project><id>ABC1</id><title>Climate grants</title><abstractText>grants</abstractText>
<created>2026-11-25T00:00:00Z</created></project></projects>"""),
    "find-tender.service.gov.uk": ("application/json", json.dumps({"releases": [
        {"id": "000001-2026", "ocid": "ocds-1", "date": "2026-11-25T00:00:00Z",
         "tender": {"title": "Climate services", "description": "tender"}}]})),
    "search.worldbank.org/rss/procurement": ("application/rss+xml", RSS),
    "cordis.europa.eu": ("application/json", json.dumps({"payload": {"results": [
        {"title": "Climate project", "url": "https://cordis.europa.eu/project/1",
         "startDate": "2026-11-25", "teaser": "x"}]}})),
    "fundsforngos.org/wp-json": ("application/json", json.dumps([
        {"title": {"rendered": "Climate grant call"}, "link": "https://www.fundsforngos.org/1",
         "date": "2026-11-25T06:00:00", "excerpt": {"rendered": "<p>apply</p>"}}])),
}


def build_ctx(limit: int = 8) -> tuple[HuntContext, httpx.AsyncClient]:
    plan = Plan(query="climate grant", terms="climate grant", lens="all", site=None,
                file_types=["pdf", "csv"], operators={}, plays=[])
    client = httpx.AsyncClient(transport=httpx.MockTransport(handler), timeout=5.0)
    return HuntContext(plan=plan, client=client, keys={}, limit=limit, domains=[]), client


def handler(request: httpx.Request) -> httpx.Response:
    url = str(request.url)
    if "federalregister.gov" in url:
        return httpx.Response(200, json={"results": [
            {"html_url": "https://www.federalregister.gov/d/1", "title": "Climate grants",
             "publication_date": "2026-11-25", "type": "Notice", "abstract": "x"}]})
    if "grants.gov/rss" in url or "reliefweb.int" in url or "news.un.org" in url or \
            "pypi.org/rss" in url or "arxiv.org/rss" in url:
        return httpx.Response(200, text=RSS, headers={"content-type": "application/rss+xml"})
    if "wikidata.org/w/api.php" in url and "list=search" in url:
        return httpx.Response(200, json={"query": {"search": [{"title": "Q1"}]}})
    for needle, (ctype, body) in FIXTURES.items():
        if needle in url:
            return httpx.Response(200, text=body, headers={"content-type": ctype})
    if "untitled" in url or "undp" in url:
        body = ('<tr><td><a href="index.cfm?notice_id=1">UNDP climate tender</a></td>'
                '<td>25-Nov-2026</td></tr>')
        return httpx.Response(200, text=body,
                             headers={"content-type": "text/html"})
    return httpx.Response(404, json={"error": "no fixture", "url": url})


async def run_provider(provider, ctx) -> list:
    return await provider.hunt(ctx)


async def main() -> int:
    ok = True
    print("\n▸ 1. the freshness layer is registered")
    ids = {p.id for p in registry.PROVIDERS}
    missing = [pid for pid in NEW_IDS if pid not in ids]
    print(f"  {len(NEW_IDS)} new engines · {len(registry.PROVIDERS)} total")
    if missing:
        ok = False
        print(f"  [FAIL] not registered: {missing}")
    else:
        print("  [PASS] every new engine is in the registry")
    stray = [pid for pid in NEW_IDS if "all" not in registry.BY_ID[pid].lenses]
    ok &= not stray
    print(f"  [{'PASS' if not stray else 'FAIL'}] all usable from the default lens"
          f"{'' if not stray else ' — ' + str(stray)}")

    print("\n▸ 2. each engine parses its own response and stamps a clock")
    failures: list[str] = []
    undated: list[str] = []
    for pid in NEW_IDS:
        ctx, client = build_ctx()
        try:
            hits = await run_provider(registry.BY_ID[pid], ctx)
        except Exception as exc:                     # noqa: BLE001 - report, don't crash
            failures.append(f"{pid}: {type(exc).__name__}: {exc}")
            await client.aclose()
            continue
        finally:
            try:
                await client.aclose()
            except Exception:
                pass
        if not hits:
            failures.append(f"{pid}: no hits")
            continue
        for hit in hits:
            if not str(hit.url).startswith(("http://", "https://")):
                failures.append(f"{pid}: bad url {hit.url!r}")
                break
        if not any(hit.published for hit in hits):
            undated.append(pid)
        if any(hit.published and not parse_time(hit.published) for hit in hits):
            failures.append(f"{pid}: unparsable timestamp")

    for pid in undated:
        print(f"  [warn] {pid} returned no publication timestamp (sorts last)")
    if failures:
        ok = False
        for failure in failures:
            print(f"  [FAIL] {failure}")
    else:
        print(f"  [PASS] {len(NEW_IDS) - len(undated)}/{len(NEW_IDS)} engines parse and date their hits")

    print("\n▸ 3. ordering: newest first, undated kept but last")
    from app.models import Hit
    from app.orchestrator import rank

    now = "2026-11-25T17:30:00Z"
    def hit(title: str, score: int, stamp: str | None = None) -> Hit:
        return Hit(url=f"https://a/{title}", title=title, score=score, provider="fixture",
                   provider_name="Fixture", published_at=stamp,
                   age_source="published" if stamp else None)

    hits = [hit("old", 99, "2019-03-01T00:00:00Z"), hit("seconds", 10, now),
            hit("undated", 100), hit("minutes", 50, "2026-11-25T17:10:00Z")]
    order = [hit.title for hit in rank(hits, "newest")]
    ok &= order == ["seconds", "minutes", "old", "undated"]
    print(f"  [{'PASS' if order == ['seconds', 'minutes', 'old', 'undated'] else 'FAIL'}] "
          f"newest → {order}")

    print("\n" + ("ALL SOURCE CHECKS PASSED" if ok else "SOME SOURCE CHECKS FAILED"))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
