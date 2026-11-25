"""Structured-data mining: turn schema.org markup into specific opportunity records.

Imported from:
  * scrapinghub/extruct     — JSON-LD / microdata / RDFa extraction
  * schema.org vocabulary   — JobPosting, Grant, MonetaryGrant, Event, Dataset, Offer
  * googleprojectzero/… no — the *idea* is Google Jobs' "structured job posting" contract:
    if a page publishes validUntil + hiringOrganization, you can surface its deadline
    with confidence instead of guessing from prose.

This is the difference between "a page that mentions a grant" and "a £40,000 grant
closing 28 February 2026, funded by X".
"""
from __future__ import annotations

import json
import re
from typing import Any

OPPORTUNITY_TYPES = {
    "jobposting", "grant", "monetarygrant", "event", "educationevent", "businessevent",
    "offer", "demand", "educationaloccupationalprogram", "course", "scholarship",
    "researchproject", "fundingopportunity", "callforproposals",
}
DATA_TYPES = {"dataset", "datacatalog", "table", "digitaldocument", "creativework",
              "report", "publicationissue", "scholarlyarticle"}
ORG_TYPES = {"organization", "ngo", "governmentorganization", "educationalorganization",
             "corporation", "foundation"}

DEADLINE_KEYS = ("validThrough", "applicationDeadline", "endDate", "deadline",
                 "closes", "applicationCloseDate", "closeDate")
AMOUNT_KEYS = ("amount", "value", "price", "fundingAmount", "totalPaymentDue")
CURRENCY_KEYS = ("currency", "priceCurrency", "currencyCode")


def _as_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return re.sub(r"<[^>]+>", " ", value).strip()
    if isinstance(value, (int, float)):
        return str(value)
    if isinstance(value, dict):
        for key in ("name", "@value", "value", "text"):
            if key in value:
                return _as_text(value[key])
    if isinstance(value, list) and value:
        return _as_text(value[0])
    return ""


def _types(node: dict) -> set[str]:
    raw = node.get("@type") or node.get("type") or ""
    values = raw if isinstance(raw, list) else [raw]
    return {str(v).split("/")[-1].split(":")[-1].lower() for v in values if v}


def _walk(node: Any, out: list[dict], depth: int = 0) -> None:
    if depth > 6:
        return
    if isinstance(node, list):
        for item in node:
            _walk(item, out, depth + 1)
        return
    if not isinstance(node, dict):
        return
    if node.get("@type"):
        out.append(node)
    for key in ("@graph", "itemListElement", "mainEntity", "hasPart", "subjectOf"):
        if key in node:
            _walk(node[key], out, depth + 1)


def jsonld_blocks(html: str) -> list[Any]:
    """Every ``application/ld+json`` block, parsed — tolerant of trailing commas.

    extruct is the heavyweight path (microdata + RDFa too), but JSON-LD is where
    ~90% of real opportunity markup lives, so it gets a dependency-free parser
    that never silently returns nothing.
    """
    blocks: list[Any] = []
    pattern = re.compile(r"<script[^>]+type=[\"']application/ld\+json[\"'][^>]*>(.*?)</script>",
                         re.I | re.S)
    for match in pattern.finditer(html or ""):
        raw = match.group(1).strip().strip("\ufeff")
        for candidate in (raw, re.sub(r",\s*([}\]])", r"\1", raw)):
            try:
                blocks.append(json.loads(candidate))
                break
            except ValueError:
                continue
    return blocks


def extract(html: str, url: str = "") -> list[dict]:
    """Return normalised structured records found in a page."""
    nodes: list[dict] = []
    for block in jsonld_blocks(html):
        _walk(block, nodes)
    try:
        import extruct

        try:
            data = extruct.extract(html, base_url=url or None,
                                   syntaxes=["microdata", "rdfa"], errors="ignore")
        except TypeError:
            data = extruct.extract(html, base_url=url or None,
                                   syntaxes=["microdata", "rdfa"])
        for syntax in ("microdata", "rdfa"):
            _walk(data.get(syntax) or [], nodes)
    except Exception:
        pass

    records: list[dict] = []
    seen: set[str] = set()
    for node in nodes:
        types = _types(node)
        if not types:
            continue
        interest = types & (OPPORTUNITY_TYPES | DATA_TYPES | ORG_TYPES)
        if not interest:
            continue
        kind = sorted(interest)[0]
        title = _as_text(node.get("name") or node.get("headline") or node.get("title"))
        if not title or len(title) < 4:
            continue
        key = f"{kind}:{title.lower()[:80]}"
        if key in seen:
            continue
        seen.add(key)

        deadline = ""
        for candidate in DEADLINE_KEYS:
            if node.get(candidate):
                deadline = _as_text(node.get(candidate))[:40]
                break

        amount, currency = "", ""
        for holder in ("baseSalary", "salary", "offeredBy", "amount", "priceSpecification",
                       "estimatedSalary", "grant", "funding"):
            value = node.get(holder)
            if isinstance(value, dict):
                for currency_key in CURRENCY_KEYS:
                    if value.get(currency_key):
                        currency = _as_text(value[currency_key])[:8]
                for amount_key in AMOUNT_KEYS:
                    if value.get(amount_key) not in (None, ""):
                        amount = _as_text(value[amount_key])[:20]
                        break
                if not amount:
                    nested = value.get("value")
                    if isinstance(nested, dict) and nested.get("value") not in (None, ""):
                        amount = _as_text(nested.get("value"))[:20]
            if amount:
                break
        if not currency:
            for key in CURRENCY_KEYS:
                if node.get(key):
                    currency = _as_text(node.get(key))[:8]
                    break

        org = ""
        for key in ("hiringOrganization", "funder", "offeredBy", "provider", "publisher",
                    "sponsor", "organizer", "sourceOrganization", "parentOrganization"):
            if node.get(key):
                org = _as_text(node[key])[:120]
                if org:
                    break

        location = ""
        for key in ("jobLocation", "location", "areaServed", "address"):
            if node.get(key):
                location = _as_text(node[key])[:120]
                if location:
                    break

        description = _as_text(node.get("description") or "")[:400]
        keywords = node.get("keywords")
        if isinstance(keywords, list):
            keywords = ", ".join(_as_text(k) for k in keywords[:8])
        records.append({
            "type": kind,
            "title": title[:200],
            "organization": org,
            "deadline": deadline,
            "amount": amount,
            "currency": currency,
            "location": location,
            "description": description,
            "keywords": _as_text(keywords)[:160],
            "url": _as_text(node.get("url")) or url,
            "category": ("opportunity" if interest & OPPORTUNITY_TYPES
                         else "dataset" if interest & DATA_TYPES else "organisation"),
        })
    return records


def best_opportunity(html: str, url: str = "") -> dict | None:
    records = [r for r in extract(html, url) if r["category"] == "opportunity"]
    if not records:
        return None
    records.sort(key=lambda r: (bool(r["deadline"]), bool(r["amount"])), reverse=True)
    return records[0]


def summary(records: list[dict]) -> str:
    if not records:
        return ""
    record = records[0]
    bits = [record["title"]]
    if record["organization"]:
        bits.append(record["organization"])
    if record["amount"]:
        money = f"{record['currency']} {record['amount']}".strip()
        bits.append(money)
    if record["deadline"]:
        bits.append(f"closes {record['deadline']}")
    return " · ".join(bits)


# --------------------------------------------------------------- text fallback
# Most funder pages never publish JSON-LD. These patterns recover the same
# fields from prose, so a plain grants.gov result still arrives with an amount.
_CURRENCY = {
    "usd": "USD", "us$": "USD", "$": "USD", "eur": "EUR", "€": "EUR", "gbp": "GBP",
    "£": "GBP", "zar": "ZAR", "r": "ZAR", "kes": "KES", "ksh": "KES", "kshs": "KES",
    "ngn": "NGN", "₦": "NGN", "inr": "INR", "₹": "INR", "cad": "CAD", "aud": "AUD",
}
_AMOUNT = re.compile(
    r"(?:(?P<pre>US\$|USD|EUR|GBP|ZAR|KES|KShs?|NGN|INR|CAD|AUD|€|£|\$|₹)\s?"
    r"(?P<num>\d[\d.,]*)\s*(?P<mag>k|m|bn|million|billion)?)"
    r"|(?:(?P<num2>\d[\d.,]*)\s*(?P<mag2>k|m|bn|million|billion)\s?"
    r"(?P<post>USD|EUR|GBP|ZAR|KES|NGN|INR|CAD|AUD))", re.I)
_FUNDER = re.compile(
    r"(?i:funded by|funder|donor|sponsor(?:ed)? by|awarded by|issuing (?:agency|body)|"
    r"implemented by|commissioned by)\s*[:\-–]?\s*"
    r"(?:the\s+|an?\s+)?([A-Z][\w&,'’()\-]*(?:\s+[\w&,'’()\-]+){0,5})")
_LOCATION = re.compile(
    r"(?:location|based in|duty station|country|region|venue)\s*[:\-–]\s*"
    r"([\w ,.'’\-]{3,60})", re.I)
_MAGNITUDE = {"k": 1_000, "m": 1_000_000, "bn": 1_000_000_000,
              "million": 1_000_000, "billion": 1_000_000_000}


def _clean_amount(num: str, mag: str | None) -> tuple[str, str]:
    raw = num.replace(",", "").replace(" ", "")
    try:
        value = float(raw)
    except ValueError:
        return "", ""
    if mag:
        value *= _MAGNITUDE.get(mag.lower(), 1)
    if value < 100:  # "3 grants" is not a budget
        return "", ""
    return f"{value:,.0f}", ""


def guess_fields(text: str) -> dict:
    """Best-effort funder / amount / currency / location from unstructured text."""
    text = re.sub(r"\s+", " ", text or "")[:8000]
    out: dict[str, str] = {}
    match = _AMOUNT.search(text)
    while match:
        amount, _ = _clean_amount(match.group("num") or match.group("num2") or "",
                                  match.group("mag") or match.group("mag2"))
        if amount:
            code = (match.group("pre") or match.group("post") or "").lower().strip()
            out["amount"] = amount
            out["currency"] = _CURRENCY.get(code, code.upper() if len(code) == 3 else "")
            break
        match = _AMOUNT.search(text, match.end())
    funder = _FUNDER.search(text)
    if funder:
        name = funder.group(1).strip().rstrip(".,;:")
        name = re.sub(r"\s+(?:and|&|with|plus)\s+[\w'’.\-]+\.?$", "", name)
        name = re.sub(r"\s+(?:and|or|the|with|to|for|in|of|partners?)$", "", name, flags=re.I)
        if len(name) > 3:
            out["organization"] = name[:90]
    place = _LOCATION.search(text)
    if place:
        out["location"] = place.group(1).strip(" .,-")[:70]
    return out
