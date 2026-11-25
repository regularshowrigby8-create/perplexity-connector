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
        f"- files of the asked type cut by the window: {stats.get('cut_older_files', 0)}",
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


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", default="http://127.0.0.1:8000")
    parser.add_argument("--q", default="diary of a wimpy kid pdf")
    parser.add_argument("--limit", type=int, default=40)
    parser.add_argument("--budget-ms", type=int, default=4000)
    parser.add_argument("--json", default="")
    parser.add_argument("--markdown", default="")
    args = parser.parse_args()

    if not wait_for(args.base):
        print(f"no answer from {args.base} — is it running?", file=sys.stderr)
        return 2

    started = time.time()
    report = call(args.base, "/api/v1/hunt", {
        "q": args.q, "limit": args.limit, "fresh": True, "budget_ms": args.budget_ms,
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
