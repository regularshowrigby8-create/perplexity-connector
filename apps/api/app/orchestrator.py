"""Fan-out, fusion and ranking across every engine, with streaming."""
from __future__ import annotations

import asyncio
import hashlib
import json
import time
from typing import Any, Awaitable, Callable

import httpx

from . import local_index, near_dup, registry
from .config import settings
from .extract import (canonical_url, depth_score, fingerprint, find_deadline, opportunity_tags,
                      truncate)
from .models import Deadline, Hit, HuntRequest, HuntResponse, HuntStats, ProviderRef
from .keyterms import expand_terms, keyphrases
from .schemaorg import guess_fields
from .plays import build_plan
from .priority import NOISE, is_document
from .portals import portal_domains
from .urlnorm import registrable
from .providers.base import HuntContext, Provider, RawHit

Emit = Callable[[dict], Awaitable[None]]

_cache: dict[str, tuple[float, HuntResponse]] = {}


def _cache_key(req: HuntRequest) -> str:
    blob = json.dumps(req.model_dump(exclude={"keys", "fresh"}), sort_keys=True)
    return hashlib.sha256(blob.encode()).hexdigest()


def _urgency(days: int) -> str:
    if days < 0:
        return "closed"
    if days == 0:
        return "today"
    if days <= 14:
        return "soon"
    if days <= 60:
        return "upcoming"
    return "later"


def build_hit(raw: RawHit, provider: Provider, rank: int, lens: str,
              terms: list[str] | None = None) -> Hit | None:
    url = (raw.url or "").strip()
    if not url.startswith(("http://", "https://")):
        return None
    ext, kind, mime, domain = fingerprint(url)
    if raw.kind:
        kind = raw.kind if kind == "page" else kind
    deadline: Deadline | None = None
    if raw.deadline:
        deadline = find_deadline(raw.snippet, explicit=raw.deadline)
    elif raw.snippet:
        deadline = find_deadline(raw.snippet)
    text = f"{raw.title} {raw.snippet}"
    if raw.url and provider.layer != "portal" and NOISE.search(raw.url):
        return None  # login walls, carts and cookie pages are not answers
    coverage = 0.0
    if terms:
        haystack = f"{raw.title} {raw.snippet} {raw.url}".lower()
        matched = sum(1 for term in terms if term and term in haystack)
        coverage = matched / max(1, len(terms))
    hit = Hit(
        url=url, title=raw.title or url, snippet=truncate(raw.snippet, 360),
        provider=provider.id, provider_name=provider.name, kind=kind, file_ext=ext,
        mime=mime, domain=domain, published=raw.published, deadline=deadline,
        depth=depth_score(url, ext, raw.archive, text),
        archive=raw.archive, portal=raw.kind == "portal",
        tags=list(dict.fromkeys([*raw.tags, *opportunity_tags(text)])), meta=raw.meta,
    )
    hit.sources = [ProviderRef(provider=provider.id, name=provider.name, rank=rank, url=url)]

    rrf = provider.weight * 1000.0 / (40 + rank)
    boost = 1.0
    if lens in ("files", "datasets") and ext:
        boost *= 1.35
    if lens == "opportunities" and any(t in hit.tags for t in
                                       ("grant", "tender", "fellowship", "scholarship", "job", "call")):
        boost *= 1.3
    if lens == "applications" and ("application" in text.lower() or "apply" in text.lower()):
        boost *= 1.25
    if lens == "exposed" and ext in ("env", "bak", "sql", "db", "log", "yml", "zip"):
        boost *= 1.4
    if deadline:
        if deadline.days_left < 0:
            boost *= 0.85
        elif deadline.days_left <= 7:
            boost *= 1.45
        elif deadline.days_left <= 30:
            boost *= 1.2
        elif deadline.days_left <= 90:
            boost *= 1.05
    if raw.published:
        import datetime as _dt

        try:
            year = int(str(raw.published)[:4])
            if year >= _dt.datetime.now().year:
                boost *= 1.08
        except ValueError:
            pass
    boost *= 1.0 + (hit.depth / 100.0) * 0.4
    boost *= 1.0 + 0.45 * coverage
    if is_document(url):
        boost *= 1.12
    if raw.kind == "portal":
        boost *= 0.45
    if raw.kind == "dork":
        boost *= 0.35
    hit.meta["coverage"] = round(coverage, 3)
    try:
        inherited = (raw.meta or {}).get("keyphrases")
        hit.keyphrases = list(inherited)[:6] if isinstance(inherited, list) and inherited \
            else keyphrases(text, limit=6)
    except Exception:
        hit.keyphrases = []
    if raw.meta.get("structured"):
        hit.schema_type = str(raw.meta["structured"])[:60]
    for key in ("funder", "amount", "currency", "location", "structured"):
        value = (raw.meta or {}).get(key)
        if value:
            setattr(hit, key, str(value)[:120])
    meta = raw.meta or {}
    if meta.get("schema_type") and not hit.schema_type:
        hit.schema_type = str(meta["schema_type"])[:60]
    if meta.get("sniffed"):
        hit.sniffed = str(meta["sniffed"])[:40]
    try:
        if meta.get("size"):
            hit.size = int(float(meta["size"]))
    except (TypeError, ValueError):
        pass
    if not hit.amount or not hit.funder:
        guessed = guess_fields(f"{raw.title} {raw.snippet}") or {}
        hit.funder = hit.funder or (guessed.get("organization") or None)
        hit.amount = hit.amount or (guessed.get("amount") or None)
        hit.currency = hit.currency or (guessed.get("currency") or None)
        hit.location = hit.location or (guessed.get("location") or None)
    # specificity is only known once the fields are populated
    if hit.funder and hit.amount and hit.deadline:
        boost *= 1.3      # a complete record answers the question by itself
    elif hit.funder and hit.amount:
        boost *= 1.3
    elif hit.amount or hit.funder:
        boost *= 1.12
    if hit.structured:
        boost *= 1.18
    if hit.kind in ("opportunity", "grant"):
        boost *= 1.22
    elif hit.kind == "page":
        boost *= 0.95
    hit.score = round(rrf * boost, 3)
    return hit


RICH_FIELDS = ("funder", "amount", "currency", "location", "structured", "schema_type",
               "sniffed", "size")


def hit_specificity(hit: Hit) -> int:
    """How much *specific* detail a hit carries (drives merge truth and ranking)."""
    score = sum(2 for field in RICH_FIELDS if getattr(hit, field, None))
    if hit.deadline:
        score += 3
    if hit.kind in ("opportunity", "grant"):
        score += 4
    elif hit.kind == "document":
        score += 1
    return score


def merge_hits(hits: list[Hit]) -> list[Hit]:
    """Fold duplicate URLs, keeping the *most specific* record as the base.

    Score decides freshness, specificity decides truth: the crawl's structured
    record (funder + amount + schema type) must survive a merge with a weaker
    full-text snippet of the same page.
    """
    merged: dict[str, Hit] = {}
    for hit in hits:
        key = canonical_url(hit.url)
        existing = merged.get(key)
        if existing is None:
            merged[key] = hit
            continue
        if hit_specificity(hit) > hit_specificity(existing):
            primary, secondary = hit, existing
            merged[key] = hit
        else:
            primary, secondary = existing, hit
        known = {source.provider for source in primary.sources}
        primary.sources = [*primary.sources,
                           *[s for s in secondary.sources if s.provider not in known]]
        primary.tags = list(dict.fromkeys([*primary.tags, *secondary.tags]))
        for field in RICH_FIELDS:
            if getattr(primary, field, None) in (None, "", 0) and getattr(secondary, field, None):
                setattr(primary, field, getattr(secondary, field))
        if not primary.keyphrases and secondary.keyphrases:
            primary.keyphrases = list(secondary.keyphrases)
        primary.score = max(primary.score, secondary.score)
        primary.depth = max(primary.depth, secondary.depth)
        primary.archive = primary.archive or secondary.archive
        if not primary.deadline:
            primary.deadline = secondary.deadline
        if len(secondary.snippet) > len(primary.snippet):
            primary.snippet = secondary.snippet
    return list(merged.values())


def diversify(hits: list[Hit], per_site: int = 2, window: int = 24,
              penalty: float = 0.72) -> list[Hit]:
    """MMR-flavoured diversity: demote (not reorder) sites that hog the top.

    Scores are penalised geometrically for each extra hit from the same
    registrable domain inside the top window, so the final ranking stays
    strictly monotone while no single site owns the first page.
    """
    if len(hits) <= per_site:
        return hits
    local = {"vault", "vault_docs", "crawler"}
    counts: dict[str, int] = {}
    for index, hit in enumerate(hits):
        if index >= window:
            break
        if hit.provider in local or hit.provider_name == "Fusion Crawler":
            continue  # your own corpus is not "one site hogging the page"
        site = registrable(hit.url) or hit.domain
        seen = counts.get(site, 0)
        counts[site] = seen + 1
        if seen >= per_site:
            hit.score = round(hit.score * (penalty ** (seen - per_site + 1)), 3)
            hit.tags = sorted({*(hit.tags or []), "diversity-demoted"})
    hits.sort(key=lambda h: (-h.score, -h.depth))
    return hits


def rank(hits: list[Hit], sort: str) -> list[Hit]:
    if sort == "depth":
        hits.sort(key=lambda h: (-h.depth, -h.score))
    elif sort == "deadline":
        hits.sort(key=lambda h: (h.deadline is None,
                                 abs(h.deadline.days_left) if h.deadline else 10**6, -h.score))
    elif sort == "newest":
        hits.sort(key=lambda h: (h.published or "", -h.score), reverse=True)
    else:
        hits.sort(key=lambda h: (-h.score, -h.depth))
        hits = diversify(hits)
    return hits


def facets(hits: list[Hit]) -> dict[str, list[dict[str, Any]]]:
    def count(key: str, label: str | None = None) -> list[dict[str, Any]]:
        buckets: dict[str, int] = {}
        for hit in hits:
            value = getattr(hit, key, None)
            if key == "file_ext":
                value = hit.file_ext or "page"
            if not value:
                continue
            buckets[str(value)] = buckets.get(str(value), 0) + 1
        return sorted(({"value": k, "count": v} for k, v in buckets.items()),
                      key=lambda item: -item["count"])[:14]

    urgency: dict[str, int] = {}
    for hit in hits:
        if hit.deadline:
            urgency[hit.deadline.urgency] = urgency.get(hit.deadline.urgency, 0) + 1
    return {
        "domain": count("domain"),
        "provider": count("provider_name"),
        "file_ext": count("file_ext"),
        "kind": count("kind"),
        "deadline": [{"value": k, "count": v} for k, v in
                     sorted(urgency.items(), key=lambda kv: -kv[1])],
    }


async def _run_provider(provider: Provider, ctx: HuntContext) -> tuple[Provider, list[RawHit], float, str | None]:
    started = time.perf_counter()
    try:
        hits = await asyncio.wait_for(provider.hunt(ctx), timeout=settings.provider_timeout)
        return provider, hits[: settings.provider_result_cap], (time.perf_counter() - started) * 1000, None
    except asyncio.TimeoutError:
        return provider, [], (time.perf_counter() - started) * 1000, "timeout"
    except Exception as exc:  # provider isolation: one bad engine never breaks the hunt
        return provider, [], (time.perf_counter() - started) * 1000, str(exc)[:160]


def _has_credentials(provider: Provider, keys: dict[str, str]) -> bool:
    if not provider.requires:
        return True
    return all(keys.get(name) or keys.get(provider.id) or getattr(settings, name, "")
               for name in provider.requires)


def select_providers(req: HuntRequest, explicit: bool) -> tuple[list[Provider], list[Provider]]:
    """Return (runnable, waiting-for-credentials)."""
    if explicit and req.providers:
        chosen = [registry.BY_ID[pid] for pid in req.providers if pid in registry.BY_ID]
    else:
        chosen = registry.for_lens(req.lens)
    runnable = [p for p in chosen if _has_credentials(p, req.keys)]
    waiting = [p for p in chosen if not _has_credentials(p, req.keys)]
    return runnable, waiting


async def hunt(req: HuntRequest, emit: Emit | None = None, use_cache: bool = True) -> HuntResponse:
    key = _cache_key(req)
    if use_cache and not req.fresh:
        cached = _cache.get(key)
        if cached and time.time() - cached[0] < settings.cache_ttl:
            response = cached[1].model_copy(deep=True)
            response.stats.cached = True
            if emit:
                await emit({"type": "meta", "cached": True, "providers": [],
                            "plan": {"query": response.query, "lens": response.lens,
                                     "plays": response.plays}})
                await emit({"type": "done", **response.model_dump()})
            return response

    started = time.perf_counter()
    plan = build_plan(req.q, req.lens, req.site, req.file_types)
    expanded = expand_terms(plan.terms, plan.lens)
    terms = [t for t in plan.terms.lower().replace(":", " ").split() if len(t) > 2][:8]
    domains = portal_domains(plan.terms, plan.lens, plan.site, cap=settings.max_domains_per_hunt)
    providers, waiting = select_providers(req, explicit=bool(req.providers))
    if not providers:
        providers = registry.LOCAL
    if emit:
        await emit({"type": "meta", "cached": False,
                    "plan": {"query": plan.query, "lens": plan.lens, "site": plan.site,
                             "suggested_lens": plan.suggested_lens,
                             "file_types": plan.file_types,
                             "plays": [{"id": p.id, "label": p.label, "dork": p.dork} for p in plan.plays]},
                    "domains": domains,
                    "providers": [p.id for p in providers],
                    "waiting": [p.id for p in waiting],
                    "expanded": expanded})

    async with httpx.AsyncClient(
        timeout=httpx.Timeout(settings.provider_timeout, connect=settings.connect_timeout),
        follow_redirects=True,
        headers={"User-Agent": settings.user_agent},
        limits=httpx.Limits(max_connections=40, max_keepalive_connections=20),
    ) as client:
        ctx = HuntContext(plan=plan, client=client, keys=req.keys,
                          limit=max(8, min(req.limit, 25)), domains=domains)
        tasks = [asyncio.create_task(_run_provider(p, ctx)) for p in providers]
        collected: list[Hit] = []
        statuses: list[dict[str, Any]] = [
            {"id": p.id, "name": p.name, "status": "needs_key", "count": 0, "ms": 0,
             "message": "credentials not set"} for p in waiting
        ]
        dropped = 0
        for finished in asyncio.as_completed(tasks):
            provider, raws, ms, error = await finished
            batch: list[Hit] = []
            for index, raw in enumerate(raws):
                hit = build_hit(raw, provider, index + 1, plan.lens, terms)
                if hit:
                    batch.append(hit)
                else:
                    dropped += 1
            collected.extend(batch)
            statuses.append({"id": provider.id, "name": provider.name,
                             "status": "error" if error else ("empty" if not raws else "ok"),
                             "count": len(batch), "ms": int(ms),
                             "message": error or ""})
            if emit and batch:
                preview = sorted(batch, key=lambda h: -h.score)[:12]
                await emit({"type": "results", "final": False,
                            "provider": provider.id, "provider_name": provider.name,
                            "hits": [h.model_dump() for h in preview]})
            elif emit:
                await emit({"type": "provider", **statuses[-1]})

    fused = merge_hits(collected)
    before = len(fused)
    fused, collapsed = near_dup.cluster(fused)
    for hit in fused:
        hit.near_dupes = int((hit.meta or {}).get("near_dupes") or 0)
    _ = before
    fused = rank(fused, req.sort)
    if len(fused) > req.limit:
        fused = fused[: req.limit]

    try:
        local_index.upsert_hits(fused)
    except Exception:
        pass

    stats = HuntStats(
        hits=sum(s["count"] for s in statuses),
        unique=len(fused),
        providers_ok=sum(1 for s in statuses if s["status"] == "ok"),
        providers_failed=sum(1 for s in statuses if s["status"] == "error"),
        files=sum(1 for h in fused if h.file_ext),
        opportunities=sum(1 for h in fused if h.kind in ("opportunity", "application")),
        closing_soon=sum(1 for h in fused if h.deadline and 0 <= h.deadline.days_left <= 30),
        duplicates_collapsed=int(collapsed),
        dropped_noise=int(dropped),
        took_ms=int((time.perf_counter() - started) * 1000),
        cached=False,
    )
    response = HuntResponse(query=plan.terms, lens=plan.lens, site=plan.site, hits=fused,
                            providers=statuses, facets=facets(fused), stats=stats,
                            plays=[p.dork for p in plan.plays], expanded=expanded)
    _cache[key] = (time.time(), response)
    if len(_cache) > settings.cache_max:
        for stale in sorted(_cache, key=lambda k: _cache[k][0])[:50]:
            _cache.pop(stale, None)
    if emit:
        await emit({"type": "done", **response.model_dump()})
    return response
