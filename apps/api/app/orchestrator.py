"""Fan-out, fusion and ranking across every engine, with streaming."""
from __future__ import annotations

import asyncio
import hashlib
import json
import time
from typing import Any, Awaitable, Callable

import httpx

from . import exact, freshness, intent as query_intent, local_index, near_dup, quality, registry
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

# kinds that name a real artefact we could have "just discovered"; portals and
# generated search links are excluded because they have no upload time at all.
LAUNCHER_KINDS = {"portal", "dork"}

UNDATED_KINDS_SAFE = {"page", "document", "file", "dataset", "opportunity", "application",
                      "archive", "release", "commit", "repo", "paper", "image", "media",
                      "video", "spreadsheet", "presentation", "code", "package"}

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
              terms: list[str] | None = None, phrase: exact.Phrase | None = None,
              unrestricted: bool = True) -> Hit | None:
    url = (raw.url or "").strip()
    if not url.startswith(("http://", "https://")):
        return None
    ext, kind, mime, domain = fingerprint(url)
    if raw.kind:
        kind = raw.kind if kind == "page" else kind
    title = quality.repair(raw.title or url)
    snippet = quality.normalise(raw.snippet)
    meta = raw.meta or {}
    published_dt = (freshness.parse(raw.published)
                    or freshness.parse(meta.get("published_at"))
                    or freshness.parse(meta.get("published")))
    first_seen_dt = freshness.parse(meta.get("first_seen")) or freshness.utcnow()
    # Publication time when the page states one; otherwise *our* clock: the moment
    # this engine first saw it. Both are honest, and the badge says which.
    # Generated entries (a portal's search URL) have no clock of their own and are
    # left undated rather than dressed up as something new.
    has_own_clock = bool(published_dt) or raw.kind in UNDATED_KINDS_SAFE
    age_source = "published" if published_dt else ("first_seen" if has_own_clock else None)
    stamp = freshness.describe((published_dt or first_seen_dt) if has_own_clock else None)
    deadline: Deadline | None = None
    if raw.deadline:
        deadline = find_deadline(snippet, explicit=raw.deadline)
    elif snippet:
        deadline = find_deadline(snippet)
    text = f"{title} {snippet}"
    noise = bool(raw.url and provider.layer != "portal" and NOISE.search(raw.url))
    if noise and not unrestricted:
        return None  # only when the caller asked for the filtered view
    coverage = 0.0
    if terms:
        haystack = f"{title} {snippet} {url}".lower()
        matched = sum(1 for term in terms if term and term in haystack)
        coverage = matched / max(1, len(terms))
    hit = Hit(
        url=url, title=title or url, snippet=truncate(snippet, 360),
        provider=provider.id, provider_name=provider.name, kind=kind, file_ext=ext,
        mime=mime, domain=domain, deadline=deadline,
        depth=depth_score(url, ext, raw.archive, text),
        archive=raw.archive, portal=raw.kind == "portal",
        tags=list(dict.fromkeys([*raw.tags, *opportunity_tags(text)])),
        meta=dict(meta),
        published=raw.published or (published_dt.date().isoformat() if published_dt else None),
        published_at=(stamp["published_at"] if published_dt else None),
        age_seconds=stamp["age_seconds"],
        age_human=stamp["age_human"], freshness=stamp["freshness"],
        first_seen=(first_seen_dt.isoformat() if has_own_clock else None),
        age_source=age_source,
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
    assessment = quality.assess(url, title, snippet, text=text, terms=terms)
    hit.quality = round(assessment.score, 3)
    hit.quality_flags = list(assessment.flags)
    hit.language = assessment.language or None
    hit.meta["quality_flags"] = list(assessment.flags)
    if quality.is_spam(assessment):
        hit.meta["spam"] = True
    boost *= 0.6 + 0.4 * assessment.score        # junk ranks low, never disappears
    boost *= 1.0 + 0.55 * hit.freshness          # recency is a signal, not a gate

    # Generated portal/dork links are entry points, not documents: they have no
    # text of their own, so claiming a verbatim match would be a fiction.
    exact.annotate(hit, None if hit.kind in LAUNCHER_KINDS else phrase)
    hit.noise = noise
    if noise:
        hit.meta["noise"] = True
    if hit.exact:
        boost *= 1.45                            # the literal phrase outweighs a near miss

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


def stamp_of(hit: Hit):
    """The best clock a hit has: publication time, else when we first saw it."""
    return (freshness.parse(hit.published_at)
            or freshness.parse(hit.published)
            or freshness.parse(hit.first_seen))


def refresh_ages(hits: list[Hit], now=None) -> None:
    """Recompute ages at response time so the UI can say *4 seconds ago*."""
    now = now or freshness.utcnow()
    for hit in hits:
        published = freshness.parse(hit.published_at) or freshness.parse(hit.published)
        stamp = published or (freshness.parse(hit.first_seen) if hit.age_source != "none" else None)
        described = freshness.describe(stamp, now)
        hit.age_seconds = described["age_seconds"]
        hit.age_human = described["age_human"]
        hit.freshness = described["freshness"]
        if published:
            hit.published_at = described["published_at"]
            hit.age_source = "published"
        elif stamp:
            hit.age_source = "first_seen"
        else:
            hit.age_source = None


def verbatim_key(hit: Hit) -> tuple:
    """Word-for-word first: literal match, then how far apart the words are."""
    proximity = hit.proximity if hit.proximity is not None else 10**6
    return (0 if hit.exact else 1, proximity)


def rank(hits: list[Hit], sort: str, verbatim: bool = True) -> list[Hit]:
    now = freshness.utcnow()
    if sort == "depth":
        hits.sort(key=lambda h: (h.junk, -h.depth, -h.score))
    elif sort == "deadline":
        hits.sort(key=lambda h: (h.junk, h.deadline is None,
                                 abs(h.deadline.days_left) if h.deadline else 10**6, -h.score))
    elif sort == "newest":
        # undated results are sorted last, never removed — ordering, not a filter
        def newest_key(hit: Hit):
            # Three bands, because a clock can lie: dated in the past (the newest
            # of those first, to the second), dated in the future (a wrong clock —
            # it used to sort *above* everything, pushing 16-second-old results
            # below records stamped ten months ahead), then undated. Nothing is
            # removed; the bands only decide order.
            stamp = stamp_of(hit)
            age = freshness.age_seconds(stamp, now)
            tier = (*verbatim_key(hit),) if verbatim else ()
            if age is None:
                return (hit.junk, *tier, 2, 0.0, -hit.score, -hit.depth)
            if age < 0:
                return (hit.junk, *tier, 1, float(-age), -hit.score, -hit.depth)
            return (hit.junk, *tier, 0, float(age), -hit.score, -hit.depth)

        hits.sort(key=newest_key)
    else:
        key = (lambda h: (h.junk, *verbatim_key(h), -h.score, -h.depth)) if verbatim             else (lambda h: (h.junk, -h.score, -h.depth))
        hits.sort(key=key)
        hits = diversify(hits) if not verbatim else hits
    refresh_ages(hits, now)
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

    # What is being asked for, before anything is crawled: a file type ("apk",
    # "pdf report") and/or a host ("mediafire"). A type word becomes the one
    # filter the engine has; a host word becomes an aim, not a filter.
    asked = query_intent.parse(req.q)
    search_text = asked.query if asked.wants_files else req.q
    if not search_text.strip():
        search_text = " ".join(asked.matched) or req.q
    file_types = list(dict.fromkeys([*(req.file_types or []), *asked.types]))
    plan = build_plan(search_text, req.lens, req.site, file_types)
    expanded = expand_terms(plan.terms, plan.lens)
    terms = [t for t in plan.terms.lower().replace(":", " ").split() if len(t) > 2][:8]
    domains = portal_domains(plan.terms, plan.lens, plan.site, cap=settings.max_domains_per_hunt)
    verbatim_text = asked.query if asked.wants_files else req.q
    # A bare type ("apk") is a browse, not a phrase: there is nothing to match
    # word for word, so no verbatim claim is made about it.
    phrase = (exact.Phrase.parse(verbatim_text)
              if req.match == "exact" and verbatim_text.strip() else None)
    providers, waiting = select_providers(req, explicit=bool(req.providers))
    if asked.wants_files and not req.providers:
        # the file hosts are the only engines that look inside MediaFire, APKPure
        # or archive.org's software collection — dispatch them whenever the query
        # names a file type or a host
        have = {p.id for p in providers}
        providers = [*providers, *[p for p in registry.file_hosts() if p.id not in have]]
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
                          limit=25 if req.limit == 0 else max(8, min(req.limit, 50)),
                          domains=domains)
        # 119 engines fan out at once; the semaphore keeps sockets sane without
        # turning the hunt into a queue that hides the fast sources behind the slow.
        gate = asyncio.Semaphore(32)

        async def _gated(provider: Provider):
            async with gate:
                return await _run_provider(provider, ctx)

        # The clock. Waiting for all 119 engines meant one slow host set the
        # latency of the whole hunt (11 s provider timeout, so that is what a
        # search could cost before it showed anything). Now the fast ones answer
        # and the stragglers are reported as "slow" — cut off, not hidden.
        budget_ms = req.budget_ms or settings.hunt_budget_ms
        deadline = time.perf_counter() + max(0.2, budget_ms / 1000.0)
        tasks = [asyncio.create_task(_gated(p)) for p in providers]
        owner = {task: provider for task, provider in zip(tasks, providers)}
        collected: list[Hit] = []
        statuses: list[dict[str, Any]] = [
            {"id": p.id, "name": p.name, "status": "needs_key", "count": 0, "ms": 0,
             "message": "credentials not set"} for p in waiting
        ]
        dropped = 0
        pending: set[asyncio.Task] = set(tasks)
        while pending:
            left = deadline - time.perf_counter()
            if left <= 0:
                break
            done, pending = await asyncio.wait(pending, timeout=left,
                                               return_when=asyncio.FIRST_COMPLETED)
            if not done:
                break
            for finished in done:
                provider = owner[finished]
                try:
                    provider, raws, ms, error = finished.result()
                except asyncio.CancelledError:
                    continue
                except Exception as exc:          # a provider that raised is still reported
                    statuses.append({"id": provider.id, "name": provider.name,
                                     "status": "error", "count": 0, "ms": 0,
                                     "message": f"{type(exc).__name__}: {exc}"[:160]})
                    continue
                batch: list[Hit] = []
                for index, raw in enumerate(raws):
                    hit = build_hit(raw, provider, index + 1, plan.lens, terms, phrase,
                                    req.unrestricted)
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
                    preview = rank(batch, req.sort)[:12]
                    await emit({"type": "results", "final": False,
                                "provider": provider.id, "provider_name": provider.name,
                                "hits": [h.model_dump() for h in preview]})
                elif emit:
                    await emit({"type": "provider", **statuses[-1]})

        slow = 0
        if pending:
            for task in pending:
                provider = owner[task]
                task.cancel()
                slow += 1
                statuses.append({"id": provider.id, "name": provider.name, "status": "slow",
                                 "count": 0, "ms": budget_ms,
                                 "message": f"still working when the {budget_ms} ms budget ran out"})
            await asyncio.gather(*pending, return_exceptions=True)

    fused = merge_hits(collected)
    before = len(fused)
    collapsed = 0
    if req.unrestricted:
        # near-duplicate detection still runs — it just reports instead of deleting
        try:
            _kept, collapsed = near_dup.cluster([hit.model_copy(deep=True) for hit in fused])
        except Exception:
            collapsed = 0
        for hit in fused:
            hit.near_dupes = 0
    else:
        fused, collapsed = near_dup.cluster(fused)
        for hit in fused:
            hit.near_dupes = int((hit.meta or {}).get("near_dupes") or 0)
    _ = before

    spam = [hit for hit in fused if hit.meta.get("spam")]
    if req.unrestricted:
        for hit in spam:
            hit.junk = True
        dropped_spam = 0            # nothing is dropped; junk is labelled and sorted last
    else:
        fused = [hit for hit in fused if not hit.meta.get("spam")]
        dropped_spam = len(spam)

    # Portal entry points are not documents and have no upload time; they are
    # kept outside the limit so the newest-first tail cannot evict them.
    if req.only_exact:
        fused = [hit for hit in fused if hit.exact]

    # The typed filter, and only the typed filter: "apk" means APKs. Everything
    # else the engine believes about not removing results still holds.
    type_dropped = 0
    if asked.types:
        fused, type_dropped = query_intent.filter_by_type(fused, asked.types)
    host_lifted = 0
    if asked.hosts:
        fused, host_lifted = query_intent.boost_hosts(fused, asked.hosts)

    launchers = [hit for hit in fused if hit.kind in LAUNCHER_KINDS] if req.sort == "newest" else []
    if launchers:
        fused = [hit for hit in fused if hit.kind not in LAUNCHER_KINDS]

    fused = rank(fused, req.sort, verbatim=bool(phrase))
    if asked.hosts:
        # after ranking too, so a named host leads the newest-first order instead
        # of being buried under it
        fused, _ = query_intent.boost_hosts(fused, asked.hosts)
    truncated = bool(req.limit) and len(fused) > req.limit
    if truncated:
        fused = fused[: req.limit]
    if launchers:
        fused = [*fused, *rank(launchers, req.sort, verbatim=False)[:5]]

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
        dropped_spam=dropped_spam,
        fresh_seconds=sum(1 for h in fused if h.age_seconds is not None and h.age_seconds < 60),
        fresh_minutes=sum(1 for h in fused if h.age_seconds is not None and 60 <= h.age_seconds < 3600),
        fresh_hours=sum(1 for h in fused if h.age_seconds is not None and 3600 <= h.age_seconds < 86400),
        fresh_days=sum(1 for h in fused if h.age_seconds is not None and 86400 <= h.age_seconds < 604800),
        dated=sum(1 for h in fused if h.age_source == "published"),
        undated=sum(1 for h in fused if h.age_source != "published"),
        newest_age_seconds=next((h.age_seconds for h in fused if h.age_seconds is not None), None),
        newest_age_human=next((h.age_human for h in fused if h.age_seconds is not None), None),
        dropped_noise=int(dropped),
        verbatim=sum(1 for h in fused if h.exact),
        near_verbatim=sum(1 for h in fused if not h.exact and h.proximity is not None),
        not_verbatim=sum(1 for h in fused if h.proximity is None),
        copies_reported=int(collapsed),
        junk_retained=sum(1 for h in fused if h.junk),
        noise_retained=sum(1 for h in fused if h.noise),
        truncated=truncated,
        took_ms=int((time.perf_counter() - started) * 1000),
        cached=False,
        budget_ms=int(budget_ms),
        slow_providers=int(slow),
    )
    intent_meta = asked.as_meta()
    intent_meta.update({
        "search_text": plan.terms,
        "removed_by_type": int(type_dropped),
        "host_matches": int(host_lifted),
        "file_host_engines": [p.id for p in registry.file_hosts()]
        if asked.wants_files and not req.providers else [],
    })
    response = HuntResponse(query=plan.terms, lens=plan.lens, site=plan.site, hits=fused,
                            providers=statuses, facets=facets(fused), stats=stats,
                            plays=[p.dork for p in plan.plays], expanded=expanded,
                            sort=req.sort, as_of=freshness.utcnow().isoformat(),
                            match=req.match, only_exact=req.only_exact,
                            unrestricted=req.unrestricted, intent=intent_meta)
    _cache[key] = (time.time(), response)
    if len(_cache) > settings.cache_max:
        for stale in sorted(_cache, key=lambda k: _cache[k][0])[:50]:
            _cache.pop(stale, None)
    if emit:
        await emit({"type": "done", **response.model_dump()})
    return response
