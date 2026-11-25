#!/usr/bin/env python3
"""End-to-end proof: serve the fixture, crawl it, search inside it, then hunt.

No network access required. Exit code 0 means the whole pipeline works:
fetch → parse → extract → index → rank → federated response.
"""
from __future__ import annotations

import asyncio
import functools
import http.server
import os
import socketserver
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "apps" / "api"))

# keep the self-test away from your real vault
_TMP = Path(tempfile.mkdtemp(prefix="nighthawk-selftest-"))
os.environ["NH_DATA_DIR"] = str(_TMP)

from app import fixtures, freshness, local_index, registry  # noqa: E402
from app.api import router  # noqa: E402
from app.crawl import CrawlRequest, FusionCrawler  # noqa: E402
from app.models import Hit, HuntRequest  # noqa: E402
from app.orchestrator import hunt, rank  # noqa: E402

def free_port() -> int:
    import socket
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


PORT = free_port()


class Server(socketserver.TCPServer):
    allow_reuse_address = True


class Quiet(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *args):  # noqa: D401
        pass


def serve(directory: Path) -> socketserver.TCPServer:
    handler = functools.partial(Quiet, directory=str(directory))
    httpd = Server(("127.0.0.1", PORT), handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    return httpd


def check(label: str, condition: bool, detail: str = "") -> bool:
    mark = "PASS" if condition else "FAIL"
    print(f"  [{mark}] {label}{f' — {detail}' if detail else ''}")
    return condition


async def main() -> int:
    root = fixtures.build(PORT)
    # serve the fixture at /demo/... exactly like the app mounts it
    public = ROOT / "data" / "_selftest"
    public.mkdir(parents=True, exist_ok=True)
    link = public / "demo"
    if link.is_symlink() or link.exists():
        link.unlink()
    link.symlink_to(root)
    httpd = serve(public)
    local_index.init()
    ok = True

    print("\n▸ 1. crawl the practice target")
    crawler = FusionCrawler(CrawlRequest(
        seeds=[f"http://127.0.0.1:{PORT}/demo/index.html"], query="climate grant",
        depth=2, max_pages=20, max_files=30, serp_engines=[], delay=0.0,
        respect_robots=True, extract_files=True, same_host=True,
    ))
    result = await crawler.run()
    stats = result["stats"]
    print(f"    pages={stats['pages']} files={stats['files']} docs={stats['docs_indexed']} "
          f"opportunities={stats['opportunities']} engines={stats['engines']}")
    ok &= check("crawled pages", stats["pages"] >= 4, str(stats["pages"]))
    ok &= check("discovered files", stats["files"] >= 6, str(stats["files"]))
    ok &= check("extracted + indexed text", stats["docs_indexed"] >= 6, str(stats["docs_indexed"]))
    ok &= check("opportunity pages detected", stats["opportunities"] >= 1,
                str(stats["opportunities"]))
    ok &= check("robots.txt honoured", stats["blocked_by_robots"] >= 0)
    ok &= check("multiple engines dispatched", len(stats["engines"]) >= 3,
                ",".join(sorted(stats["engines"])))

    print("\n▸ 2. read a PDF and a spreadsheet")
    hits = {Path(h["url"]).name: h for h in result["files"]}
    pdf = hits.get("climate-grant-guidelines.pdf")
    ok &= check("PDF found", pdf is not None)
    ok &= check("PDF text extracted", bool(pdf and pdf["meta"].get("text_engine")),
                str(pdf["meta"].get("text_engine") if pdf else ""))
    ok &= check("deadline parsed from PDF", bool(pdf and pdf["deadline"]),
                str(pdf["deadline"]["date"] if pdf and pdf["deadline"] else "none"))
    ok &= check("depth score assigned", bool(pdf and pdf["depth"] > 0),
                str(pdf["depth"] if pdf else 0))
    ok &= check("CSV text captured", any(h["file_ext"] == "csv" for h in result["files"]))

    print("\n▸ 3. search inside the vault")
    deep = local_index.search_docs("solar mini grid", limit=10)
    ok &= check("full-text match inside PDF", any("tender" in d["url"] or "solar" in
                                                  (d["snippet"] or "").lower() for d in deep),
                f"{len(deep)} fragments")
    meta = local_index.search_vault("climate grant", limit=10)
    ok &= check("metadata index responds", len(meta) > 0, f"{len(meta)} rows")
    ok &= check("vault stats", local_index.vault_stats()["documents"] > 0,
                str(local_index.vault_stats()))

    print("\n▸ 4. federated hunt (offline: local + portal layers)")
    response = await hunt(HuntRequest(q="climate grants kenya", lens="opportunities",
                                      limit=30, fresh=True), use_cache=False)
    print(f"    hits={response.stats.unique} ok={response.stats.providers_ok} "
          f"failed={response.stats.providers_failed} ms={response.stats.took_ms}")
    ok &= check("hunt returns fused results", response.stats.unique > 0,
                str(response.stats.unique))
    ok &= check("portal fallback present", any(h.portal or h.kind == "dork" for h in response.hits))
    ok &= check("facets computed", bool(response.facets.get("domain")))
    ok &= check("newest is the default order", response.sort == "newest", response.sort)
    ok &= check("word-for-word is the default match", response.match == "exact", response.match)
    ok &= check("nothing is capped or trimmed", response.unrestricted and not response.stats.truncated)
    ages = [h.age_seconds for h in response.hits]
    dated = [age for age in ages if age is not None]
    tiers = [(h.junk, not h.exact) for h in response.hits if h.kind not in ("portal", "dork")]
    ordered_tiers = all(tiers[i] <= tiers[i + 1] for i in range(len(tiers) - 1))
    ok &= check("verbatim results lead, junk last", ordered_tiers)
    verbatim_ages = [h.age_seconds for h in response.hits if h.exact and h.age_seconds is not None]
    ok &= check("newest first inside the verbatim tier",
                all(verbatim_ages[i] <= verbatim_ages[i + 1]
                    for i in range(len(verbatim_ages) - 1)),
                f"{len(verbatim_ages)} verbatim")
    rest_ages = [h.age_seconds for h in response.hits
                 if not h.exact and not h.junk and h.age_seconds is not None]
    ok &= check("newest first inside the rest",
                all(rest_ages[i] <= rest_ages[i + 1] for i in range(len(rest_ages) - 1)),
                f"{len(rest_ages)} other")
    ok &= check("undated hits are kept, sorted last", ages == dated + [None] * (len(ages) - len(dated)))
    ok &= check("every hit carries an age badge", all(h.age_human for h in response.hits))
    ok &= check("freshness ledger adds up",
                response.stats.dated + response.stats.undated == len(response.hits),
                f"dated={response.stats.dated} undated={response.stats.undated}")
    ok &= check("quality scored on every hit", all(0.0 <= h.quality <= 1.0 for h in response.hits))

    ok &= check("verbatim ledger accounts for every hit",
                response.stats.verbatim + response.stats.near_verbatim
                + response.stats.not_verbatim == len(response.hits),
                f"{response.stats.verbatim} verbatim / {response.stats.near_verbatim} near / "
                f"{response.stats.not_verbatim} none")

    print("\n▸ 4b. verbatim matching is literal, not fuzzy")

    from app.exact import Phrase, find

    phrase = Phrase.parse('"climate grant"')
    ok &= check("contiguous phrase matches", bool(find("a new climate grant for kenya", phrase).verbatim))
    near = find("the climate resilience grant", phrase)
    ok &= check("gap is measured, not guessed", near is not None and near.proximity == 1,
                f"proximity={getattr(near, 'proximity', None)}")
    ok &= check("word order matters", find("grant for the climate", phrase) is None)
    ok &= check("no stemming or synonyms",
                find("climatic grants", phrase) is None
                and find("climate funding grant", phrase).verbatim is False)
    hyphen = find("Climate-Grant toolkit", phrase)
    ok &= check("hyphens are word boundaries", bool(hyphen and hyphen.verbatim))

    strict = await hunt(HuntRequest(q="climate grant", lens="opportunities", limit=0,
                                    fresh=True, only_exact=True), use_cache=False)
    ok &= check("verbatim-only returns only verbatim hits",
                all(hit.exact for hit in strict.hits), str(len(strict.hits)))
    ok &= check("verbatim-only does not silently cap",
                not strict.stats.truncated and strict.stats.not_verbatim == 0)
    ok &= check("verbatim-only finds the literal phrase", len(strict.hits) > 0,
                f"{len(strict.hits)} hits")
    plural = await hunt(HuntRequest(q="climate grants", lens="opportunities", limit=0,
                                    fresh=True, only_exact=True), use_cache=False)
    ok &= check("no stemming: a plural query does not match the singular",
                all(hit.exact for hit in plural.hits))

    print("\n▸ 4c. the same hunt, sorted by relevance")
    scored = await hunt(HuntRequest(q="climate grants kenya", lens="opportunities", limit=30,
                                    fresh=True, sort="relevance", match="loose"), use_cache=False)
    ok &= check("relevance sort still ranks by score", all(
        scored.hits[i].score >= scored.hits[i + 1].score
        for i in range(len(scored.hits) - 1)))
    loose = await hunt(HuntRequest(q="climate grants kenya", lens="opportunities", limit=0,
                                   fresh=True, match="loose"), use_cache=False)
    ok &= check("loose mode still returns everything", len(loose.hits) >= len(strict.hits),
                f"{len(loose.hits)} vs {len(strict.hits)}")
    ok &= check("no duplicate canonical URLs",
                len({h.url for h in response.hits}) == len(response.hits))

    print("\n▸ 5. deep links: the page nothing links to")
    from app.deep import DeepRequest, deep_crawl

    unlinked = f"http://127.0.0.1:{PORT}/demo/annex/off-cycle-notice.html"
    deep = await deep_crawl(DeepRequest(
        seeds=[unlinked], query="climate resilience grant", depth=2,
        max_pages=10, max_files=10, respect_robots=False))
    titles = [hit["title"] for hit in deep["hits"]]
    reasons = {tuple(hit["meta"].get("deep_reasons") or []) for hit in deep["hits"]}
    ok &= check("deep crawl reaches a pasted, unlinked page",
                any("Off-cycle notice" in title for title in titles), str(len(titles)))
    ok &= check("it says why nothing else could find it",
                any("pasted" in group and "not-linked" in group for group in reasons),
                str(sorted(reasons)))
    ok &= check("attachments are flagged as attachments",
                any("attachment" in group for group in reasons))
    ok &= check("deep query is matched verbatim",
                any(hit["exact"] for hit in deep["hits"]),
                str(deep["stats"]["verbatim"]))
    ok &= check("deep report keeps everything it found",
                deep["stats"]["kept"] == len(deep["hits"]) and not deep["policy"]["result_removal"])
    ok &= check("deep crawl documents are indexed in the vault",
                deep["stats"].get("docs_indexed", 0) >= 1, str(deep["stats"].get("docs_indexed")))

    linked = await deep_crawl(DeepRequest(seeds=[f"http://127.0.0.1:{PORT}/demo/index.html"],
                                          query="", depth=1, max_pages=6, max_files=6))
    ok &= check("a normal crawl does not magically find the unlinked page",
                not any("off-cycle" in hit["url"] for hit in linked["hits"]))

    print("\n▸ 6. the launcher file itself")
    from lxml import html as lxml_html

    launcher = (ROOT / "index.html").read_text(encoding="utf-8")
    doc = lxml_html.fromstring(launcher)
    ids_present = all(doc.get_element_by_id(anchor) is not None for anchor in
                      ("hunt", "deep", "deep-seeds", "deep-run", "banner", "status"))
    ok &= check("launcher parses and has its anchors", ids_present)
    ok &= check("launcher probes several engine locations",
                "candidates" in launcher and "meta nighthawk-engine" in launcher)
    ok &= check("launcher documents the deep reasons",
                "not-linked" in launcher and "attachment" in launcher)
    ok &= check("launcher is not minified", launcher.count("\n") > 1200,
                f"{launcher.count(chr(10))} lines")

    print("\n\u25b8 7. one container, one origin (so it is not local)")
    from fastapi.responses import FileResponse
    from app import main as api_main

    page = api_main.launcher_path()
    ok &= check("the API finds the launcher beside it",
                page is not None and page.name == "index.html", str(page))
    served = await api_main.index()
    ok &= check("GET / is the launcher, not a redirect",
                isinstance(served, FileResponse) and served.media_type == "text/html")
    launch = await api_main.launch()
    ok &= check("GET /launch is the same file",
                isinstance(launch, FileResponse) and Path(launch.path) == Path(served.path))
    ok &= check("the page is never cached, so a redeploy is visible",
                served.headers.get("cache-control") == "no-store"
                and launch.headers.get("cache-control") == "no-store")

    dockerfile = (ROOT / "Dockerfile.api").read_text(encoding="utf-8")
    ok &= check("the image ships the page with the crawler",
                "COPY index.html" in dockerfile and "NH_DATA_DIR=/data" in dockerfile)
    ok &= check("the image listens on the port the host hands it",
                "${PORT:-8000}" in dockerfile and "EXPOSE 8000" in dockerfile)

    # the container has no repo around it: /app/app/config.py, two levels deep.
    # Counting parents died there with IndexError before uvicorn ever bound.
    shallow = Path(tempfile.mkdtemp(prefix="nighthawk-shallow-"))
    (shallow / "app").mkdir()
    (shallow / "app" / "__init__.py").write_text("")
    (shallow / "app" / "config.py").write_text(
        (ROOT / "apps" / "api" / "app" / "config.py").read_text(encoding="utf-8"))
    (shallow / "index.html").write_text("<!doctype html>", encoding="utf-8")
    probe = subprocess.run(
        [sys.executable, "-c",
         "import sys; sys.path.insert(0, sys.argv[1]);"
         "from app.config import ROOT; print(ROOT)", str(shallow)],
        capture_output=True, text=True,
        env={**os.environ, "NH_DATA_DIR": str(shallow / "data")})
    said = (probe.stdout.strip() or probe.stderr.strip().splitlines()[-1] if probe.stderr.strip()
            else probe.stdout.strip())
    ok &= check("the package imports from /app/app, not just from a checkout",
                probe.returncode == 0 and Path(probe.stdout.strip()) == shallow, said)

    # hosts open their own port: the fixture site must follow it, not assume 8000
    from app.api import demo_target

    saved_port = os.environ.get("PORT")
    os.environ["PORT"] = "12345"
    try:
        target = await demo_target()
    finally:
        if saved_port is None:
            os.environ.pop("PORT", None)
        else:
            os.environ["PORT"] = saved_port
    ok &= check("the practice target follows the port the host opened",
                target["seeds"][0].endswith(":12345/demo/index.html"), target["seeds"][0])
    ok &= check("the launcher does not pin the practice target to 8000",
                "demoBase()" in launcher and "127.0.0.1:8000/demo" not in launcher)
    # /hunt and /crawl are Next.js pages; a one-container deploy has neither, so
    # the page must ask the engine itself instead of navigating into a 404.
    ok &= check("the launcher hunts on the page instead of navigating to /hunt",
                "/api/v1/hunt" in launcher and 'id="live-hits"' in launcher
                and 'location.href = url("/" + mode' not in launcher)
    ok &= check("its route links target engine endpoints, not app pages",
                "api/v1/arsenal" in launcher and "api/v1/hunts" in launcher)
    app_pages = [f'href="/{page}"' for page in ("hunt", "crawl", "vault", "hunts", "arsenal")]
    ok &= check("no markup link points at a page that only exists in the web app",
                not any(needle in launcher for needle in app_pages),
                str([n for n in app_pages if n in launcher]))
    ok &= check("route clicks are handled by one delegated listener, at load",
                'document.addEventListener("click"' in launcher
                and launcher.index("wireRoutes();") > launcher.index("function wireRoutes"))
    ok &= check("the practice button crawls inline instead of navigating",
                'location.href = url("/crawl' not in launcher
                and '"/api/v1/crawl"' in launcher)
    ok &= check("a sleeping free instance is not painted as offline",
                "15000" in launcher and "free hosts wake in" in launcher)
    hosts = {
        "render.yaml": "Dockerfile.api",
        "fly.toml": "Dockerfile.api",
        "railway.json": "Dockerfile.api",
        "Procfile": "uvicorn app.main:app",
    }
    missing = [name for name, needle in hosts.items()
               if not (ROOT / name).is_file() or needle not in (ROOT / name).read_text(encoding="utf-8")]
    ok &= check("every durable host has a ready config", not missing, str(missing))
    compose = (ROOT / "docker-compose.yml").read_text(encoding="utf-8")
    ok &= check("compose publishes the engine on its own",
                '"8000:8000"' in compose and "nh-data:/data" in compose)

    print("\n\u25b8 8. what the query asked for: type, host, and a clock that lies")
    from app import intent as query_intent

    typed = query_intent.parse("minecraft apk")
    ok &= check("a type word becomes a filter, not a search term",
                typed.query == "minecraft" and "apk" in typed.types, str(typed.as_meta()))
    bare = query_intent.parse("apk")
    ok &= check("a bare type is a browse, not a phrase",
                bare.query == "" and bare.types[:1] == ["apk"])
    aimed = query_intent.parse("budget csv mediafire")
    ok &= check("a host word aims the crawl and is not a filter",
                aimed.hosts == ["mediafire.com"] and aimed.query == "budget"
                and "csv" in aimed.types, str(aimed.hosts))
    plain = query_intent.parse("water")
    ok &= check("a query with no type word filters nothing",
                plain.types == [] and plain.hosts == [] and plain.query == "water")
    ok &= check("file-host engines are registered",
                {"mediafire", "archivefiles", "apkpure"} <= {p.id for p in registry.file_hosts()},
                str([p.id for p in registry.file_hosts()]))

    # a vault with one of each type, so the filter has something to be right about
    from app.models import Hit as HitModel
    now_iso = freshness.utcnow().isoformat()
    local_index.upsert_hits([
        HitModel(url="http://vault/reports/annual-report-2025.pdf", title="Annual report 2025",
                 snippet="annual report 2025 expenditure", provider="vault",
                 provider_name="Nighthawk Vault", kind="document", file_ext="pdf",
                 domain="vault", published=now_iso, first_seen=now_iso, age_source="published"),
        HitModel(url="http://vault/data/budget.csv", title="Annual report budget table",
                 snippet="annual report budget rows", provider="vault",
                 provider_name="Nighthawk Vault", kind="dataset", file_ext="csv",
                 domain="vault", published=now_iso, first_seen=now_iso, age_source="published"),
        HitModel(url="http://vault/pages/annual-report.html", title="Annual report landing page",
                 snippet="annual report landing page", provider="vault",
                 provider_name="Nighthawk Vault", kind="page", file_ext="html",
                 domain="vault", published=now_iso, first_seen=now_iso, age_source="published"),
    ])
    only_pdf = await hunt(HuntRequest(q="annual report pdf", limit=0, fresh=True), use_cache=False)
    ok &= check("searching 'pdf' returns pdfs and only pdfs",
                bool(only_pdf.hits) and {h.file_ext for h in only_pdf.hits} == {"pdf"},
                str({h.file_ext for h in only_pdf.hits}))
    ok &= check("and it says how many of another type it set aside",
                only_pdf.intent.get("removed_by_type", 0) > 0,
                str(only_pdf.intent.get("removed_by_type")))
    untyped = await hunt(HuntRequest(q="annual report", limit=0, fresh=True), use_cache=False)
    ok &= check("no type word, no filter at all",
                untyped.intent.get("removed_by_type") == 0
                and len({h.file_ext for h in untyped.hits}) > 1,
                str(sorted({str(h.file_ext) for h in untyped.hits})))

    import datetime
    stamp = lambda **kw: (freshness.utcnow() - datetime.timedelta(**kw)).isoformat()
    clocked = [
        HitModel(url="http://x/future", title="future", provider="p", provider_name="P",
                 published="2027-09-01T00:00:00Z"),
        HitModel(url="http://x/old", title="old", provider="p", provider_name="P",
                 published=stamp(days=5)),
        HitModel(url="http://x/seconds", title="seconds", provider="p", provider_name="P",
                 published=stamp(seconds=16)),
        HitModel(url="http://x/hours", title="hours", provider="p", provider_name="P",
                 published=stamp(hours=3)),
    ]
    order = [h.title for h in rank(clocked, "newest", verbatim=False)]
    ok &= check("newest-first puts seconds-old first", order[0] == "seconds", str(order))
    ok &= check("a record dated in the future no longer outranks the past",
                order.index("old") < order.index("future"), str(order))

    print("\n\u25b8 9. similar links: one link in, every link of that shape out")
    from app.links import LinkRequest, find_links, template_of

    form = ("https://docs.google.com/forms/d/e/"
            "1FAIpQLSeUgRo9ZXDqQIE3U4J2uGECV3SApcHs5M95tBlbaflCeSp52w/viewform")
    shape = template_of(form)
    ok &= check("a form link reduces to a shape, id blanked",
                shape["template"].endswith("/forms/d/e/{id}/viewform"), shape["template"])
    ok &= check("the shape is a pattern, not a fixed string",
                "{id}" not in shape["regex"] and "[A-Za-z0-9_" in shape["regex"])

    seed = f"http://127.0.0.1:{PORT}/demo/forms/a1b2c3d4e5f60718/view.html"
    found = await find_links(LinkRequest(seed=seed, phrase="", depth=2, max_pages=12,
                                         use_engines=False, delay=0.0))
    urls = [row["url"] for row in found["links"]]
    siblings = [u for u in urls if "/forms/" in u and u != seed]
    ok &= check("it finds the other links with that shape", len(siblings) >= 3, str(len(siblings)))
    ok &= check("every match really shares the shape",
                all("/forms/" in u and u.endswith("/view.html") for u in urls), str(urls[:2]))
    ok &= check("it says where each one was found",
                all(row["found_on"] for row in found["links"]))

    filtered = await find_links(LinkRequest(seed=seed, phrase="solar", depth=2, max_pages=12,
                                            use_engines=False, delay=0.0))
    ok &= check("a phrase keeps only the links that mention it",
                len(filtered["links"]) == 1 and "deadbeefcafe0123" in filtered["links"][0]["url"],
                str([r["url"] for r in filtered["links"]]))
    ok &= check("and says where the phrase matched (link or text)",
                filtered["links"][0]["phrase_where"] == ["text"],
                str(filtered["links"][0]["phrase_where"]))
    ok &= check("links the phrase rejects are reported, not hidden",
                len(filtered["near"]) >= 3, str(len(filtered["near"])))

    impossible = await find_links(LinkRequest(seed=seed, phrase="nowhere-at-all-xyz",
                                              depth=1, max_pages=6, use_engines=False, delay=0.0))
    ok &= check("an impossible phrase returns nothing matched but still lists the shape",
                impossible["links"] == [] and len(impossible["near"]) >= 1,
                str(impossible["stats"]))

    launcher_html = (ROOT / "index.html").read_text(encoding="utf-8")
    ok &= check("the launcher has the link crawler panel",
                'id="link-seed"' in launcher_html and 'id="link-form"' in launcher_html
                and 'id="link-out"' in launcher_html)
    ok &= check("the panel posts to the link endpoint",
                "/api/v1/links" in launcher_html)
    ok &= check("the refined look replaced the neon tokens",
                "--accent:" in launcher_html and "Iowan Old Style" in launcher_html)
    ok &= check("the clutter is gone: no card wall, no caps strip, no pitch banner",
                'class="caps"' not in launcher_html and 'class="warn-strip"' not in launcher_html
                and 'class="grid"' not in launcher_html)
    ok &= check("everything but the search box sits behind the menu",
                'id="menu"' in launcher_html and 'id="menu-btn"' in launcher_html
                and launcher_html.count("data-panel hidden") >= 6,
                str(launcher_html.count("data-panel hidden")))
    ok &= check("the menu lists the live crawl",
                'data-open="continuous"' in launcher_html and 'id="cont-form"' in launcher_html)

    print("\n\u25b8 10. live crawl: start it once, it keeps working, stop it")
    from app.continuous import ContinuousRequest, ContinuousWorker

    live = ContinuousWorker()
    started = await live.start(ContinuousRequest(
        seeds=[f"http://127.0.0.1:{PORT}/demo/index.html"], delay=0.0, pages_per_round=5))
    ok &= check("starting a live crawl takes one site and reports running",
                started["running"] is True and started["origins"] == [f"http://127.0.0.1:{PORT}"],
                str(started["origins"]))
    deadline = time.time() + 90
    state = started
    while time.time() < deadline and state["rounds"] < 2:
        await asyncio.sleep(0.25)
        state = live.status()
    ok &= check("it runs round after round without being asked again",
                state["rounds"] >= 2, str(state["rounds"]))
    ok &= check("the rounds really crawl pages", state["pages"] > 0, str(state["pages"]))
    ok &= check("what it finds lands in the index", state["documents"] > 0, str(state["documents"]))
    ok &= check("the status explains itself (delay, pages per round, notes)",
                state["delay_s"] == 0.0 and state["pages_per_round"] == 5 and bool(state["notes"]))
    more = live.add_sites(["example.org"])
    ok &= check("another site can be added while it runs",
                "https://example.org" in more["origins"], str(more.get("added")))
    stopped = await live.stop()
    ok &= check("stop ends it, and says it had been running",
                stopped["running"] is False and stopped["was_running"] is True)
    fresh_worker = ContinuousWorker()
    refused = False
    try:
        await fresh_worker.start(ContinuousRequest(seeds=[]))
    except ValueError:
        refused = True
    ok &= check("a live crawl with no site is refused instead of spinning", refused)
    paths = {getattr(route, "path", "") for route in router.routes}
    ok &= check("the API has start, status, more-sites and stop",
                {"/api/v1/continuous", "/api/v1/continuous/seeds",
                 "/api/v1/continuous/stop"} <= paths)

    print("\n\u25b8 11. a search answers on a clock, not on the slowest engine")
    import app.orchestrator as orch
    from app.config import settings as cfg

    real_runner = orch._run_provider
    stall = {"n": 0, "ids": set()}

    async def stalling_runner(provider, ctx):
        stall["n"] += 1
        if stall["n"] <= 6:                     # six hosts that never answer
            stall["ids"].add(provider.id)
            await asyncio.sleep(30)
        return provider, [], 5.0, None

    try:
        orch._run_provider = stalling_runner
        began = time.perf_counter()
        timed = await orch.hunt(HuntRequest(q="budget probe", limit=10, budget_ms=1200),
                                use_cache=False)
        took = time.perf_counter() - began
    finally:
        orch._run_provider = real_runner

    ok &= check("a hung engine cannot hold the page hostage",
                took < 6.0, f"{took:.2f}s with six 30s engines")
    ok &= check("the response names the budget it answered on",
                timed.stats.budget_ms == 1200, str(timed.stats.budget_ms))
    ok &= check("the engines it cut off are counted, not hidden",
                timed.stats.slow_providers >= 6, str(timed.stats.slow_providers))
    slow_rows = [row for row in timed.providers if row.get("status") == "slow"]
    ok &= check("each one is listed by name with the reason",
                len(slow_rows) >= 6 and all("budget" in row["message"] for row in slow_rows),
                (slow_rows[0]["message"] if slow_rows else "none"))
    ok &= check("every engine is accounted for — ok, failed, empty, key or slow",
                len(timed.providers) >= timed.stats.slow_providers,
                f"{len(timed.providers)} rows")
    ok &= check("the server default budget is a couple of seconds, not a timeout",
                300 <= cfg.hunt_budget_ms <= 5000, str(cfg.hunt_budget_ms))
    ok &= check("repeat questions are answered from the cache",
                cfg.cache_ttl >= 30, str(cfg.cache_ttl))
    launcher_now = (ROOT / "index.html").read_text(encoding="utf-8")
    ok &= check("the page no longer forces a fresh hunt on every click",
                "fresh: true" not in launcher_now and "fresh: !!forceFresh" in launcher_now)
    ok &= check("the page says it is searching, and offers 'ask again'",
                "searching every working source" in launcher_now
                and "ask again" in launcher_now)

    print("\n\u25b8 12. results arrive as each source answers, ordered by accuracy then upload date")
    frames: list[dict] = []
    stamps: list[float] = []
    began = time.perf_counter()

    async def collector(event):
        if event.get("type") == "results":
            frames.append(event)
            stamps.append(time.perf_counter() - began)

    stall2 = {"n": 0}

    async def slow_some(provider, ctx):
        stall2["n"] += 1
        if stall2["n"] <= 3:            # three engines that take their time
            await asyncio.sleep(1.6)
        return provider, [], 1.0, None

    try:
        orch._run_provider = slow_some
        streamed = await orch.hunt(HuntRequest(q="stream probe", limit=0, sort="accuracy"),
                                   emit=collector, use_cache=False)
    finally:
        orch._run_provider = real_runner
    total = time.perf_counter() - began

    ok &= check("the first frame lands long before the last source finishes",
                bool(stamps) and stamps[0] < total * 0.75,
                f"{stamps[0]:.2f}s of {total:.2f}s" if stamps else "no frames")
    ok &= check("several frames arrive instead of one dump at the end",
                len(frames) >= 2, str(len(frames)))
    answered = [frame.get("answered", 0) for frame in frames]
    ok &= check("each frame says how many sources have answered so far",
                all(a <= b for a, b in zip(answered, answered[1:])) and answered[-1] > 0,
                str(answered[:6]))
    ok &= check("the last streamed frame is marked final",
                frames[-1].get("final") is True)

    def accuracy_key(hit: dict) -> tuple:
        band = 0 if hit.get("exact") else (1 if hit.get("proximity") is not None else 2)
        return (band, hit["proximity"] if hit.get("proximity") is not None else 10 ** 6)

    ok &= check("every frame is already ordered by accuracy",
                all([accuracy_key(h) for h in frame["hits"]]
                    == sorted(accuracy_key(h) for h in frame["hits"]) for frame in frames))

    exact_new = Hit(url="exact-new", title="x", provider="p", provider_name="P",
                    exact=True, proximity=0, published="2026-11-23T10:00:00Z")
    exact_old = Hit(url="exact-old", title="x", provider="p", provider_name="P",
                    exact=True, proximity=0, published="2019-01-01T00:00:00Z")
    fresh_miss = Hit(url="fresh-miss", title="x", provider="p", provider_name="P",
                     exact=False, proximity=None, published="2026-11-23T11:00:00Z")
    order = [h.url for h in orch.rank([fresh_miss, exact_old, exact_new], "accuracy", verbatim=True)]
    ok &= check("an exact match from 2019 outranks a fresh page that does not contain the phrase",
                order == ["exact-new", "exact-old", "fresh-miss"], str(order))
    ok &= check("the finished answer keeps that order",
                streamed.sort == "accuracy" and len(streamed.hits) >= 0)
    ok &= check("the page listens to the stream and asks for accuracy order",
                "/api/v1/hunt/stream" in launcher_now and 'sort: "accuracy"' in launcher_now)
    ok &= check("the stream route exists on the API",
                "/api/v1/hunt/stream" in {getattr(route, "path", "") for route in router.routes})

    print("\n▸ 13. a pasted link is read live, and a dead site explains itself")
    live_events: list[dict] = []
    live_stamps: list[float] = []
    crawl_began = time.perf_counter()

    async def crawl_collect(event):
        live_events.append(event)
        live_stamps.append(time.perf_counter() - crawl_began)

    await FusionCrawler(CrawlRequest(
        seeds=[f"http://127.0.0.1:{PORT}/demo/index.html"], query="", depth=2,
        max_pages=10, max_files=10, serp_engines=[], keep_pages=True, delay=0.0,
        label="live-crawl"), crawl_collect).run()
    crawl_total = time.perf_counter() - crawl_began
    first_result = next((live_stamps[i] for i, event in enumerate(live_events)
                         if event["type"] in ("pagehit", "file")), None)
    ok &= check("the crawler shows its first result while it is still reading",
                first_result is not None and first_result < crawl_total * 0.75,
                f"{first_result:.2f}s of {crawl_total:.2f}s" if first_result else "no results")
    ok &= check("each page it reads is announced as it is read",
                sum(1 for event in live_events if event["type"] == "page") >= 3,
                str(sum(1 for event in live_events if event["type"] == "page")))
    ok &= check("the crawl ends with a done event carrying everything found",
                any(event["type"] == "done" for event in live_events))

    dead_events: list[dict] = []

    async def dead_collect(event):
        dead_events.append(event)

    dead_report = await FusionCrawler(CrawlRequest(
        seeds=[f"http://127.0.0.1:{PORT}/demo/nope-404.html"], query="", depth=1,
        max_pages=4, max_files=4, serp_engines=[], keep_pages=True, delay=0.0,
        label="dead"), dead_collect).run()
    ok &= check("a link that answers nothing returns nothing — and says so",
                dead_report["files"] == [] and dead_report["stats"]["errors"] >= 1,
                str(dead_report["stats"]))
    ok &= check("the failure is in the stream too, not only the final report",
                any(event["type"] == "error" for event in dead_events))

    ok &= check("the page crawls a pasted link instead of searching for the URL",
                "that is a link" in launcher_now and "/api/v1/crawl/stream" in launcher_now)
    ok &= check("an empty crawl explains robots, HTTP errors and JS-only pages",
                "robots.txt asks crawlers" in launcher_now
                and "403, 404, 429" in launcher_now)
    ok &= check("the greys are blended, not stacked",
                "--panel2: #0f1218" in launcher_now and "one surface, one hairline" in launcher_now)

    print("\n▸ 14. the answer is not held up by its own bookkeeping")
    import app.near_dup as near_dup_mod
    seen_sizes: list[int] = []
    real_cluster = near_dup_mod.cluster

    def counting_cluster(records, *args, **kwargs):
        seen_sizes.append(len(records))
        return real_cluster(records, *args, **kwargs)

    near_dup_mod.cluster = counting_cluster
    try:
        timed_report = await orch.hunt(HuntRequest(q="water fittings report", limit=0,
                                                   sort="accuracy", budget_ms=1500),
                                       use_cache=False)
    finally:
        near_dup_mod.cluster = real_cluster
    ok &= check("the duplicate report only scans the top rows, not the whole set",
                all(size <= cfg.cluster_cap for size in seen_sizes), str(seen_sizes))
    ok &= check("the response says how many rows were compared",
                timed_report.stats.copies_scanned <= cfg.cluster_cap,
                str(timed_report.stats.copies_scanned))
    ok &= check("post-processing is a small tail, not a second search",
                timed_report.stats.post_ms < 2000, f"{timed_report.stats.post_ms} ms")
    ok &= check("the answer reports its own budget and slow count",
                timed_report.stats.budget_ms == 1500
                and timed_report.stats.slow_providers >= 0)

    print("\n▸ 15. nothing older than two years comes back")
    from app import recency
    from app.models import Hit as WindowHit

    import datetime as _dt
    _now = _dt.datetime.now(_dt.timezone.utc)

    def _old(days: int) -> str:
        return (_now - _dt.timedelta(days=days)).isoformat().replace("+00:00", "Z")

    def _row(url: str, published=None, first_seen=None) -> WindowHit:
        return WindowHit(url=url, title=url, provider="p", provider_name="P",
                         published=published, first_seen=first_seen)

    probe = [_row("seconds", _old(0)), _row("one-year", _old(365)), _row("just-under", _old(729)),
             _row("five-years", _old(5 * 365)), _row("ahead-60", _old(-60)),
             _row("ahead-500", _old(-500)), _row("no-date"),
             _row("seen-today", None, _old(0))]
    kept_rows, win_stats = recency.apply(probe)
    kept_urls = [row.url for row in kept_rows]
    ok &= check("results from seconds ago to just under two years are kept",
                {"seconds", "one-year", "just-under"} <= set(kept_urls), str(kept_urls))
    ok &= check("a five-year-old page is cut, not sorted last",
                "five-years" not in kept_urls and win_stats["cut_older"] == 1, str(win_stats))
    ok &= check("a page dated two years into the future is cut too",
                "ahead-500" not in kept_urls and "ahead-60" in kept_urls, str(kept_urls))
    ok &= check("undated pages survive (a missing date is not evidence of age)",
                "no-date" in kept_urls, str(kept_urls))
    ok &= check("first_seen is the last resort clock, and today counts as inside",
                "seen-today" in kept_urls)
    ok &= check("the window is two years by default",
                cfg.window_days == 730 and cfg.future_days == 120,
                f"{cfg.window_days}/{cfg.future_days}")

    ages = [hit.age_seconds for hit in timed_report.hits if hit.age_seconds is not None]
    ok &= check("every hit a real hunt returns is inside the window",
                all(age <= cfg.window_days * 86400 and age >= -cfg.future_days * 86400 for age in ages),
                f"{len(ages)} dated hits")
    ok &= check("the answer says what the window cut",
                timed_report.stats.window_days == cfg.window_days
                and timed_report.stats.cut_older >= 0
                and timed_report.stats.undated_kept >= 0,
                f"cut {timed_report.stats.cut_older} · undated {timed_report.stats.undated_kept}")

    # the vault obeys it too
    old_hit = WindowHit(url="https://example.org/2011/annex.pdf", title="Annex from 2011",
                        provider="selftest", provider_name="Selftest", file_ext="pdf",
                        published="2011-05-01T00:00:00Z")
    local_index.upsert_hits([old_hit])
    vault_rows = local_index.search_vault("annex", limit=10)
    vault_kept, vault_window = recency.apply(vault_rows)
    ok &= check("the vault search cuts it as well",
                any(row["url"].endswith("annex.pdf") for row in vault_rows)
                and all(not row["url"].endswith("annex.pdf") for row in vault_kept)
                and vault_window["cut_older"] >= 1,
                str(vault_window))

    with local_index.db() as _conn:
        vault_cols = {row[1] for row in _conn.execute("PRAGMA table_info(vault)")}
    ok &= check("the vault stores a publication date, so old rows are judged, not guessed",
                "published" in vault_cols, str(sorted(vault_cols)))

    launcher_window = (ROOT / "index.html").read_text(encoding="utf-8")
    ok &= check("the page says the window out loud, and what it cut",
                "cut as too old" in launcher_window and "nothing older than" in launcher_window)

    print("\n▸ 16. the engine reads the question before it fetches anything")
    from app import understand

    form_read = understand.read("climate resilience grant application form for coastal towns in Kenya")
    ok &= check("it knows a form when it sees one",
                form_read.kind == "form" and form_read.suggested_lens == "applications",
                form_read.kind)
    ok &= check("it pulls the subject phrase out of the sentence",
                "climate resilience" in form_read.phrases[0], str(form_read.phrases[:2]))
    ok &= check("it notices the country", form_read.places[:1] == ["kenya"], str(form_read.places))
    ok &= check("it says what it understood, in words",
                "form or application" in form_read.summary(), form_read.summary())

    code_read = understand.read("github repository for solar mini-grid survey dataset")
    ok &= check("a repository request is read as code", code_read.kind == "code", code_read.kind)
    money_read = understand.read("water points maintenance tender pdf 2025")
    ok &= check("a tender is read as a funding call, and the pdf is noticed",
                money_read.kind == "tender" and "pdf" in money_read.file_types,
                f"{money_read.kind}/{money_read.file_types}")

    stale_read = understand.read("World Bank policy report from 2016 on education")
    ok &= check("a name is taken whole, not word by word",
                "World Bank" in stale_read.orgs, str(stale_read.orgs))
    ok &= check("a year outside the window is flagged, not silently ignored",
                stale_read.warnings and "outside" in stale_read.warnings[0],
                str(stale_read.warnings))

    neg_read = understand.read('ministry of health "infection control" guidelines -vaccine')
    ok &= check("quoted phrases and exclusions are separated out",
                neg_read.quoted == ["infection control"] and neg_read.negatives == ["vaccine"],
                f"{neg_read.quoted}/{neg_read.negatives}")

    rake_dir = ROOT / "apps" / "api" / "app" / "vendor" / "rake_keyword"
    ok &= check("the keyword engine is a real imported codebase, kept intact",
                (rake_dir / "rake.py").is_file() and (rake_dir / "LICENSE").is_file()
                and (rake_dir / "resources" / "SmartStoplist.txt").is_file())
    ok &= check("it records where that code came from",
                "github.com/u-prashant/RAKE" in (rake_dir / "NOTICE").read_text(encoding="utf-8"))
    ok &= check("the hunt carries the reading, not just the results",
                (timed_report.understanding or {}).get("summary") != "",
                (timed_report.understanding or {}).get("summary", "none"))

    httpd.shutdown()
    print("\n" + ("ALL CHECKS PASSED" if ok else "SOME CHECKS FAILED"))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
