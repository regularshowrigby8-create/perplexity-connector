#!/usr/bin/env python3
"""Ask a running Nighthawk instance a real question and print the answer.

This is the honest test: it talks to the API the way the page does, over the
real network, and prints what came back — including how many engines answered,
what the window cut, and what was set aside. Written so it can run in this
repo's GitHub Actions workflow (.github/workflows/live-search.yml), where the
network is open, and against the deployed instance, where it is too.

    python scripts/live_search.py --q "diary of a wimpy kid pdf" --limit 30
    python scripts/live_search.py --base https://nighthawk-4mvl.onrender.com --q "water tender"
"""
from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone


def call(base: str, path: str, body: dict | None = None, timeout: int = 120):
    url = base.rstrip("/") + path
    data = json.dumps(body).encode() if body is not None else None
    headers = {"Content-Type": "application/json"} if data else {}
    request = urllib.request.Request(url, data=data, headers=headers)
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.load(response)


def wait_for(base: str, seconds: int = 90) -> bool:
    started = time.time()
    while time.time() - started < seconds:
        try:
            call(base, "/api/v1/health", timeout=5)
            return True
        except Exception:
            time.sleep(2)
    return False


def human_age(hit: dict) -> str:
    return hit.get("age_human") or (hit.get("published") or "")[:10] or "no date"


def render(report: dict, query: str) -> str:
    stats = report.get("stats") or {}
    hits = report.get("hits") or []
    understanding = report.get("understanding") or {}
    lines = [
        f"### `{query}`",
        "",
        f"- **{len(hits)} results** in {stats.get('took_ms', '?')} ms "
        f"(post-processing {stats.get('post_ms', 0)} ms)",
        f"- **{stats.get('providers_ok', 0)} sources answered**, "
        f"{stats.get('providers_failed', 0)} could not be reached",
        f"- window: last {stats.get('window_days', 0)} days · cut {stats.get('cut_older', 0)} older · "
        f"cut {stats.get('cut_future', 0)} future-dated · {stats.get('undated_kept', 0)} undated kept",
        f"- set aside: {stats.get('off_topic', 0)} not about the words · "
        f"{(report.get('intent') or {}).get('removed_by_type', 0)} of another type · "
        f"{stats.get('local_excluded', 0)} practice-site",
        f"- one hop out: opened {stats.get('hop_pages', 0)} page(s), took "
        f"{stats.get('hop_found', 0)} file(s) out of them, "
        f"{stats.get('hop_skipped', 0)} page(s) unreadable",
        f"- older results that offered the asked type, cut by the window: "
        f"{stats.get('cut_older_matches', 0)}",
        f"- read as: {understanding.get('summary', '—')}",
        "",
    ]
    if not hits:
        lines.append("_No results._")
        return "\n".join(lines)

    lines.append("| # | file | title | host | age | words |")
    lines.append("|---|---|---|---|---|---|")
    for index, hit in enumerate(hits[:40], start=1):
        ext = hit.get("file_ext") or hit.get("kind") or ""
        title = (hit.get("title") or "").replace("|", "·")[:70]
        flag = "·" if hit.get("off_topic") else str(hit.get("words_hit", ""))
        lines.append(f"| {index} | `{ext}` | {title} | {hit.get('domain') or ''} | {human_age(hit)} | {flag} |")

    pdfs = [h for h in hits if (h.get("file_ext") or "").lower() == "pdf"]
    lines += ["", f"**PDF files: {len(pdfs)}**"]
    for hit in pdfs[:10]:
        lines.append(f"- {hit.get('title', '')[:60]} — {hit.get('url')}")
    return "\n".join(lines)


# The mission is "a search returns what was asked for" — not "this one book
# query works". Five of the six modes can only be judged by a query that needs
# them, so the live test asks one of each, plus the three things a person does
# most often: a plain question, a fresh local one, and a site search.
SUITE = [
    {"q": "how to renew a passport in south africa", "lens": "all",
     "why": "a plain how-to: does it fetch the instructions, or a pile of noise"},
    {"q": "load shedding schedule today", "lens": "all",
     "why": "freshness: the answer has to be from this week, not 2019"},
    {"q": "signal apk", "lens": "files",
     "why": "files mode with a type word that is not pdf: does an apk come back"},
    {"q": "small business grant south africa 2026", "lens": "opportunities",
     "why": "opportunities mode: money with a deadline, not articles about money"},
    {"q": "learnership application 2026", "lens": "applications",
     "why": "applications mode: things a person can actually apply to"},
    {"q": "population by province south africa csv", "lens": "datasets",
     "why": "datasets mode: a table, not a news story about the census"},
    {"q": "public s3 bucket open data csv", "lens": "exposed",
     "why": "exposed mode: data left open, found without a key"},
    {"q": "tender documents", "site": "gov.za", "lens": "all",
     "why": "a site-limited search: does the site stay the site"},
]


def run_one(base: str, spec: dict, limit: int, budget_ms: int) -> dict:
    started = time.time()
    # the order the page asks for, not the API's default: the suite has to test
    # what a person is actually shown
    body = {"q": spec["q"], "limit": limit, "fresh": True, "budget_ms": budget_ms,
            "lens": spec.get("lens", "all"), "sort": spec.get("sort", "accuracy")}
    if spec.get("site"):
        body["site"] = spec["site"]
    report = call(base, "/api/v1/hunt", body)
    report["_wall_s"] = round(time.time() - started, 2)
    report["_spec"] = spec
    return report


def top_line(report: dict) -> str:
    hits = report.get("hits") or []
    if not hits:
        return "**nothing**"
    first = hits[0]
    title = (first.get("title") or first.get("url") or "").strip()
    return f"{title[:80]} — {first.get('domain') or ''} ({human_age(first)})"


def suite_markdown(reports: list[dict]) -> str:
    lines = ["### the engine, asked eight different things", "",
             "One query per mode, the way a person would type them. Each row is a real",
             "live search against the branch: open network, real engines, no cache.", "",
             "| mode | asked | results | sources | time | top result |",
             "|---|---|---|---|---|---|"]
    for report in reports:
        spec, stats = report["_spec"], report.get("stats") or {}
        asked = spec["q"] + (f" (site:{spec['site']})" if spec.get("site") else "")
        lines.append(f"| {spec.get('lens', 'all')} | {asked} | {len(report.get('hits') or [])} | "
                     f"{stats.get('providers_ok', 0)} | {report.get('_wall_s')} s | "
                     f"{top_line(report)} |")
    lines.append("")
    for report in reports:
        lines.append(f"#### {report['_spec'].get('lens', 'all')} · `{report['_spec']['q']}`")
        lines.append(f"_{report['_spec'].get('why', '')}_")
        lines.append("")
        lines.append(render(report, report["_spec"]["q"]))
        lines.append("")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", default="http://127.0.0.1:8000")
    parser.add_argument("--q", default="")
    parser.add_argument("--lens", default="all")
    parser.add_argument("--site", default="")
    parser.add_argument("--suite", action="store_true",
                        help="ask one question per mode instead of a single query")
    parser.add_argument("--limit", type=int, default=40)
    parser.add_argument("--budget-ms", type=int, default=4000)
    parser.add_argument("--json", default="")
    parser.add_argument("--markdown", default="")
    args = parser.parse_args()

    if not wait_for(args.base):
        print(f"no answer from {args.base} — is it running?", file=sys.stderr)
        return 2

    if args.suite or not args.q:
        reports = []
        for spec in SUITE:
            print(f"… {spec.get('lens', 'all'):13} {spec['q']}", file=sys.stderr)
            try:
                reports.append(run_one(args.base, spec, args.limit, args.budget_ms))
            except Exception as error:                    # one bad query is one row
                print(f"  failed: {error}", file=sys.stderr)
                reports.append({"hits": [], "stats": {}, "_spec": spec, "_wall_s": 0,
                                "providers": [], "_error": str(error)[:200]})
        markdown = suite_markdown(reports)
        print(markdown)
        if args.json:
            with open(args.json, "w", encoding="utf-8") as handle:
                json.dump({"suite": reports}, handle, indent=1, default=str)
        if args.markdown:
            with open(args.markdown, "w", encoding="utf-8") as handle:
                handle.write(markdown + "\n")
        return 0

    started = time.time()
    report = call(args.base, "/api/v1/hunt", {
        "q": args.q, "limit": args.limit, "fresh": True, "budget_ms": args.budget_ms,
        "lens": args.lens, **({"site": args.site} if args.site else {}),
    })
    wall = time.time() - started

    markdown = render(report, args.q)
    print(markdown)
    print(f"\n_wall clock, request to answer: {wall:.2f} s · "
          f"{datetime.now(timezone.utc).isoformat(timespec='seconds')}_")

    if args.json:
        with open(args.json, "w", encoding="utf-8") as handle:
            json.dump(report, handle, indent=1, default=str)
    if args.markdown:
        with open(args.markdown, "w", encoding="utf-8") as handle:
            handle.write(markdown + "\n")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except urllib.error.URLError as error:
        print(f"transport failed: {error}", file=sys.stderr)
        raise SystemExit(2)
