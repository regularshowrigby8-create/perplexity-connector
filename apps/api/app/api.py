from __future__ import annotations

import asyncio
import json
import time
from collections import defaultdict, deque
from typing import Any, AsyncIterator

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import JSONResponse, StreamingResponse

from . import arsenal, local_index, registry
from .config import settings
from .crawl import CrawlRequest, FusionCrawler
from .change import content_hash, diff as diff_text
from .extract import canonical_url
from .models import HuntRequest
from .orchestrator import hunt
from .plays import build_plan
from .portals import PORTALS

router = APIRouter(prefix="/api/v1")

SSE_HEADERS = {
    "Cache-Control": "no-cache, no-transform",
    "Connection": "keep-alive",
    "X-Accel-Buffering": "no",
}

_buckets: dict[str, deque[float]] = defaultdict(deque)


def rate_limit(request: Request) -> None:
    ip = (request.headers.get("x-forwarded-for", "").split(",")[0].strip()
          or (request.client.host if request.client else "unknown"))
    bucket = _buckets[ip]
    now = time.time()
    while bucket and now - bucket[0] > 60:
        bucket.popleft()
    if len(bucket) >= settings.rate_limit_per_min:
        raise HTTPException(429, detail="Rate limit reached — slow the hunt down.")
    bucket.append(now)


def _sse(payload: dict[str, Any]) -> str:
    return f"data: {json.dumps(payload, default=str)}\n\n"


def sse_stream(producer) -> StreamingResponse:
    async def generator() -> AsyncIterator[str]:
        queue: asyncio.Queue[dict | None] = asyncio.Queue()

        async def emit(event: dict) -> None:
            await queue.put(event)

        async def runner() -> None:
            try:
                await producer(emit)
            except Exception as exc:  # surface, never hang the stream
                await queue.put({"type": "error", "message": f"{type(exc).__name__}: {exc}"[:300]})
            finally:
                await queue.put(None)

        task = asyncio.create_task(runner())
        try:
            while True:
                item = await queue.get()
                if item is None:
                    break
                yield _sse(item)
        finally:
            if not task.done():
                task.cancel()
            yield 'data: {"type": "end"}\n\n'

    return StreamingResponse(generator(), media_type="text/event-stream", headers=SSE_HEADERS)


# ------------------------------------------------------------------- meta routes

@router.get("/health")
async def health() -> dict[str, Any]:
    return {
        "ok": True, "app": settings.app_name, "version": "1.0.0",
        "engines_remote": len(registry.PROVIDERS),
        "engines_arsenal": len(arsenal.probe_all()),
        "arsenal_ready": sum(1 for e in arsenal.probe_all() if e["available"]),
        "portals": len(PORTALS),
        "vault": local_index.vault_stats(),
        "cache_ttl": settings.cache_ttl,
    }


@router.get("/arsenal")
async def get_arsenal(role: str | None = None) -> dict[str, Any]:
    rows = [dict(r) for r in arsenal.probe_all()]
    if role:
        rows = [r for r in rows if r["role"] == role]
    return {"summary": arsenal.summary(), "engines": rows,
            "roles": sorted({r["role"] for r in rows})}


@router.get("/engines")
async def get_engines() -> dict[str, Any]:
    providers = registry.describe()
    return {
        "providers": providers + [registry.CRAWLER],
        "counts": {
            "remote_providers": len(providers),
            "arsenal": len(arsenal.probe_all()),
            "arsenal_ready": sum(1 for e in arsenal.probe_all() if e["available"]),
            "portals": len(PORTALS),
            "total": len(providers) + len(arsenal.probe_all()) + len(PORTALS) + 1,
        },
        "layers": sorted({p["layer"] for p in providers}),
    }


@router.get("/portals")
async def get_portals() -> dict[str, Any]:
    return {"portals": [{"name": p.name, "domains": list(p.domains), "lenses": list(p.lenses),
                         "search": p.search, "note": p.note, "topics": list(p.topics)}
                        for p in PORTALS]}


@router.post("/plan")
async def get_plan(payload: HuntRequest) -> dict[str, Any]:
    plan = build_plan(payload.q, payload.lens, payload.site, payload.file_types)
    return {"query": plan.query, "lens": plan.lens, "suggested_lens": plan.suggested_lens,
            "site": plan.site, "file_types": plan.file_types,
            "plays": [{"id": p.id, "label": p.label, "dork": p.dork} for p in plan.plays]}


@router.get("/stats")
async def get_stats() -> dict[str, Any]:
    with local_index.db() as conn:
        runs = [dict(r) for r in conn.execute(
            "SELECT * FROM runs ORDER BY id DESC LIMIT 25").fetchall()]
    return {"vault": local_index.vault_stats(), "recent_runs": runs,
            "arsenal": arsenal.summary(), "providers": len(registry.PROVIDERS)}


# ------------------------------------------------------------------- hunt routes

@router.post("/hunt")
async def post_hunt(payload: HuntRequest, request: Request) -> dict[str, Any]:
    rate_limit(request)
    response = await hunt(payload)
    with local_index.db() as conn:
        conn.execute("INSERT INTO runs (query, lens, providers, hits, took_ms, created_at) "
                     "VALUES (?,?,?,?,?,?)",
                     (response.query, response.lens, len(response.providers),
                      response.stats.unique, response.stats.took_ms, local_index.now()))
    return response.model_dump()


@router.post("/hunt/stream")
async def post_hunt_stream(payload: HuntRequest, request: Request) -> StreamingResponse:
    rate_limit(request)

    async def producer(emit):
        response = await hunt(payload, emit)
        with local_index.db() as conn:
            conn.execute("INSERT INTO runs (query, lens, providers, hits, took_ms, created_at) "
                         "VALUES (?,?,?,?,?,?)",
                         (response.query, response.lens, len(response.providers),
                          response.stats.unique, response.stats.took_ms, local_index.now()))

    return sse_stream(producer)


@router.get("/vault")
async def get_vault(q: str = Query(default="", max_length=300),
                    mode: str = Query(default="both", pattern="^(both|meta|fulltext)$"),
                    limit: int = Query(default=40, ge=1, le=200)) -> dict[str, Any]:
    meta = local_index.search_vault(q, limit=limit) if mode in ("both", "meta") else []
    docs = local_index.search_docs(q, limit=limit) if mode in ("both", "fulltext") else []
    return {"query": q, "meta": meta, "fulltext": docs, "stats": local_index.vault_stats()}


# ------------------------------------------------------------------ crawl routes

@router.post("/crawl")
async def post_crawl(payload: CrawlRequest, request: Request) -> dict[str, Any]:
    rate_limit(request)
    crawler = FusionCrawler(payload)
    result = await crawler.run()
    return result


@router.post("/crawl/stream")
async def post_crawl_stream(payload: CrawlRequest, request: Request) -> StreamingResponse:
    rate_limit(request)

    async def producer(emit):
        crawler = FusionCrawler(payload, emit)
        await crawler.run()

    return sse_stream(producer)


@router.get("/demo-target")
async def demo_target() -> dict[str, Any]:
    return {
        "name": "Nighthawk practice target",
        "root": "/demo/index.html",
        "seeds": ["http://127.0.0.1:8000/demo/index.html"],
        "note": "A local fixture site with an index-of listing, three PDFs, a CSV, JSON, "
                "a ZIP and a robots-disallowed page. Used to prove the crawl pipeline "
                "without needing internet access.",
        "robots": ["/demo/robots.txt", "/demo/sitemap.xml"],
    }


# ------------------------------------------------------------------- saved hunts

@router.get("/hunts")
async def list_hunts() -> dict[str, Any]:
    with local_index.db() as conn:
        rows = [dict(r) for r in conn.execute(
            "SELECT h.*, (SELECT COUNT(*) FROM hunt_seen s WHERE s.hunt_id = h.id) AS seen "
            "FROM hunts h ORDER BY h.id DESC").fetchall()]
    return {"hunts": rows}


@router.post("/hunts")
async def create_hunt(payload: dict[str, Any]) -> dict[str, Any]:
    name = (payload.get("name") or payload.get("query") or "untitled").strip()[:120]
    query = (payload.get("query") or "").strip()
    if not query:
        raise HTTPException(400, detail="query is required")
    lens = payload.get("lens") or "all"
    site = payload.get("site") or None
    with local_index.db() as conn:
        cur = conn.execute("INSERT INTO hunts (name, query, lens, site, created_at) "
                           "VALUES (?,?,?,?,?)", (name, query, lens, site, local_index.now()))
        hunt_id = cur.lastrowid
    return {"id": hunt_id, "name": name, "query": query, "lens": lens, "site": site}


@router.delete("/hunts/{hunt_id}")
async def delete_hunt(hunt_id: int) -> dict[str, Any]:
    with local_index.db() as conn:
        conn.execute("DELETE FROM hunts WHERE id = ?", (hunt_id,))
        conn.execute("DELETE FROM hunt_seen WHERE hunt_id = ?", (hunt_id,))
    return {"deleted": hunt_id}


@router.post("/hunts/{hunt_id}/run")
async def run_hunt(hunt_id: int) -> dict[str, Any]:
    with local_index.db() as conn:
        row = conn.execute("SELECT * FROM hunts WHERE id = ?", (hunt_id,)).fetchone()
        if not row:
            raise HTTPException(404, detail="hunt not found")
        hunt_row = dict(row)
    request = HuntRequest(q=hunt_row["query"], lens=hunt_row["lens"], site=hunt_row["site"],
                          fresh=True, limit=60)
    response = await hunt(request, use_cache=False)
    new_items: list[dict[str, Any]] = []
    with local_index.db() as conn:
        for hit in response.hits:
            canon = canonical_url(hit.url)
            exists = conn.execute("SELECT 1 FROM hunt_seen WHERE hunt_id = ? AND canonical = ?",
                                  (hunt_id, canon)).fetchone()
            if not exists:
                conn.execute("INSERT INTO hunt_seen (hunt_id, canonical, first_seen) "
                             "VALUES (?,?,?)", (hunt_id, canon, local_index.now()))
                new_items.append(hit.model_dump())
        conn.execute("UPDATE hunts SET last_run_at = ?, last_count = ? WHERE id = ?",
                     (local_index.now(), len(response.hits), hunt_id))

    changed: list[dict[str, Any]] = []
    for hit in response.hits:
        canon = canonical_url(hit.url)
        text = local_index.doc_text(canon)
        if not text:
            continue
        digest = content_hash(text)
        prior = local_index.prior_hunt_doc(hunt_id, canon)
        if prior and prior.get("hash") and prior["hash"] != digest:
            delta = diff_text(prior.get("excerpt") or "", text[:6000])
            changed.append({"url": hit.url, "title": hit.title,
                            "added": delta["added"], "removed": delta["removed"],
                            "sample": delta["sample"], "word_added": delta["word_added"],
                            "word_removed": delta["word_removed"],
                            "deadline": hit.deadline.date if hit.deadline else None})
        local_index.store_hunt_doc(hunt_id, canon, digest, text[:6000])

    return {"hunt": hunt_row, "new": new_items, "new_count": len(new_items),
            "changed": changed, "changed_count": len(changed),
            "total": len(response.hits), "stats": response.stats.model_dump()}


@router.get("/saved")
async def list_saved() -> dict[str, Any]:
    with local_index.db() as conn:
        rows = [dict(r) for r in conn.execute("SELECT * FROM saved ORDER BY id DESC").fetchall()]
    return {"saved": rows}


@router.post("/saved")
async def save_item(payload: dict[str, Any]) -> dict[str, Any]:
    url = (payload.get("url") or "").strip()
    if not url:
        raise HTTPException(400, detail="url is required")
    canon = canonical_url(url)
    with local_index.db() as conn:
        try:
            conn.execute(
                "INSERT INTO saved (url, canonical, title, provider, kind, file_ext, deadline, "
                "depth, note, query, created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?) "
                "ON CONFLICT(canonical) DO UPDATE SET note = excluded.note",
                (url, canon, payload.get("title") or url, payload.get("provider") or "",
                 payload.get("kind") or "page", payload.get("file_ext"),
                 payload.get("deadline"), int(payload.get("depth") or 0),
                 payload.get("note") or "", payload.get("query") or "", local_index.now()))
        except Exception as exc:
            raise HTTPException(400, detail=str(exc)[:200]) from exc
    return {"saved": True, "url": url}


@router.delete("/saved/{item_id}")
async def delete_saved(item_id: int) -> dict[str, Any]:
    with local_index.db() as conn:
        conn.execute("DELETE FROM saved WHERE id = ?", (item_id,))
    return {"deleted": item_id}
