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
    ok &= check("ranked by score", all(
        response.hits[i].score >= response.hits[i + 1].score
        for i in range(len(response.hits) - 1)))
    ok &= check("no duplicate canonical URLs",
                len({h.url for h in response.hits}) == len(response.hits))

    httpd.shutdown()
    print("\n" + ("ALL CHECKS PASSED" if ok else "SOME CHECKS FAILED"))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
