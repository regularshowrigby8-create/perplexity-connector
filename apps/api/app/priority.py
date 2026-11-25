"""Focused-crawl URL prioritisation.

Imported from:
  * scrapy/frontera        — priority queue + score function for the frontier
  * apify/crawlee          — request priority and max-requests-per-crawl semantics
  * projectdiscovery/katana— path/extension heuristics used by recon crawlers
  * opsdisk/metagoofil     — the file extensions worth chasing first

The crawler used to be a FIFO queue with a uniform delay. Now every discovered URL is
scored, so the frontier spends its budget on documents and calls instead of login pages.
"""
from __future__ import annotations

import re
import urllib.parse

# 8 types metagoofil targets, plus the formats buried-file hunters actually find.
PRIORITY_EXTENSIONS: dict[str, float] = {
    "pdf": 3.4, "docx": 3.0, "xlsx": 3.2, "csv": 3.1, "pptx": 2.8, "doc": 2.6,
    "xls": 2.8, "ppt": 2.4, "odt": 2.2, "ods": 2.2, "zip": 2.6, "json": 2.3,
    "xml": 2.0, "geojson": 2.6, "sql": 2.8, "sqlite": 2.8, "db": 2.6, "env": 2.7,
    "bak": 2.7, "log": 2.2, "yml": 2.0, "yaml": 2.0, "parquet": 3.0, "xlsm": 2.8,
}

FILE_HINT = re.compile(
    r"(files?|documents?|docs?|downloads?|uploads?|attachments?|assets?|media|archive|"
    r"backup|exports?|data|datasets?|publications?|reports?|resources?|tenders?|grants?|"
    r"procurement|opportunit|apply|applications?|admissions?|index[\s_-]?of)", re.I)
NOISE = re.compile(
    r"(login|signin|sign-in|signup|register|cart|checkout|logout|password|subscribe|"
    r"cookie|privacy|terms|imprint|contact|about|search\?|/tag/|/category/|/author/|"
    r"\.(css|js|png|jpe?g|gif|svg|ico|woff2?|ttf|eot|mp4|webm)$)", re.I)
OPPORTUNITY_HINT = re.compile(
    r"(grant|tender|rfp|rfi|call[-_ ]for|fellowship|scholarship|vacanc|job|career|"
    r"apply|application|opportunit|funding|bourse|prize|award|bounty)", re.I)


def score(url: str, anchor: str = "", query_terms: list[str] | tuple[str, ...] = (),
          depth: int = 0, from_sitemap: bool = False, same_host: bool = True) -> float:
    """Higher is crawled sooner. Deterministic, bounded, cheap to compute."""
    try:
        parts = urllib.parse.urlsplit(url)
    except ValueError:
        return -10.0
    path = urllib.parse.unquote(parts.path)
    text = f"{path} {anchor}".lower()
    value = 1.0

    ext = path.rsplit(".", 1)[-1].lower() if "." in path.rsplit("/", 1)[-1] else ""
    value += PRIORITY_EXTENSIONS.get(ext, 0.0)
    if FILE_HINT.search(path):
        value += 1.1
    if OPPORTUNITY_HINT.search(text):
        value += 0.9
    for term in query_terms:
        if len(term) > 3 and term in text:
            value += 0.55
    if from_sitemap:
        value += 0.8
    if not same_host:
        value -= 4.0
    if NOISE.search(url):
        value -= 3.0
    value -= 0.35 * max(0, depth)
    if len(path) > 160:
        value -= 0.4
    return round(value, 3)


def is_document(url: str) -> bool:
    path = urllib.parse.urlsplit(url).path
    ext = path.rsplit(".", 1)[-1].lower() if "." in path.rsplit("/", 1)[-1] else ""
    return ext in PRIORITY_EXTENSIONS
