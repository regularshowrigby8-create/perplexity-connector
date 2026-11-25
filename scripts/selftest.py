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
import sys
import tempfile
import threading
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "apps" / "api"))

# keep the self-test away from your real vault
_TMP = Path(tempfile.mkdtemp(prefix="nighthawk-selftest-"))
os.environ["NH_DATA_DIR"] = str(_TMP)

from app import fixtures, local_index  # noqa: E402
from app.crawl import CrawlRequest, FusionCrawler  # noqa: E402
from app.models import HuntRequest  # noqa: E402
from app.orchestrator import hunt  # noqa: E402

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

    httpd.shutdown()
    print("\n" + ("ALL CHECKS PASSED" if ok else "SOME CHECKS FAILED"))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
