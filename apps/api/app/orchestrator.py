"""Fan-out, fusion and ranking across every engine, with streaming."""
from __future__ import annotations

import asyncio
import hashlib
import json
import time
from typing import Any, Awaitable, Callable

import httpx

from . import local_index, registry
from .config import settings
from .extract import (canonical_url, depth_score, fingerprint, find_deadline, opportunity_tags,
                      truncate)
from .models import Deadline, Hit, HuntRequest, HuntResponse, HuntStats, ProviderRef
from .plays import build_plan
from .portals import portal_domains
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


def build_hit(raw: RawHit, provider: Provider, rank: int, lens: str) -> Hit | None:
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
    if raw.kind == "portal":
        boost *= 0.45
    if raw.kind == "dork":
        boost *= 0.35
    hit.score = round(rrf * boost, 3)
    return hit


def merge_hits(hits: list[Hit]) -> list[Hit]:
    merged: dict[str, Hit] = {}
    for hit in hits:
        key = canonical_url(hit.url)
        existing = merged.get(key)
        if existing is None:
            merged[key] = hit
            continue
        existing.sources.extend(hit.sources)
        existing.tags = list(dict.fromkeys([*existing.tags, *hit.tags]))
        if hit.score > existing.score:
            keep_score, keep_provider = existing.score, existing.provider
            existing.__dict__.update({**hit.__dict__})
            existing.score = max(keep_score, hit.score)
            existing.provider = keep_provider
        if len(hit.snippet) > len(existing.snippet):
            existing.snippet = hit.snippet
        existing.depth = max(existing.depth, hit.depth)
        existing.archive = existing.archive or hit.archive
        if hit.deadline and (not existing.deadline or
                             abs(hit.deadline.days_left) < abs(existing.deadline.days_left)):
            existing.deadline = hit.deadline
    return list(merged.values())


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
                    "waiting": [p.id for p in waiting]})

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
        for finished in asyncio.as_completed(tasks):
            provider, raws, ms, error = await finished
            batch: list[Hit] = []
            for index, raw in enumerate(raws):
                hit = build_hit(raw, provider, index + 1, plan.lens)
                if hit:
                    batch.append(hit)
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
        took_ms=int((time.perf_counter() - started) * 1000),
        cached=False,
    )
    response = HuntResponse(query=plan.terms, lens=plan.lens, site=plan.site, hits=fused,
                            providers=statuses, facets=facets(fused), stats=stats,
                            plays=[p.dork for p in plan.plays])
    _cache[key] = (time.time(), response)
    if len(_cache) > settings.cache_max:
        for stale in sorted(_cache, key=lambda k: _cache[k][0])[:50]:
            _cache.pop(stale, None)
    if emit:
        await emit({"type": "done", **response.model_dump()})
    return response
