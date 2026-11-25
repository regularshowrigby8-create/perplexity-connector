"""Continuous crawling — one site in, and it never stops.

The rest of the engine is request-shaped: a hunt runs, answers, and is over. This
module is the opposite. You name a site once and a background worker keeps
walking it, round after round, for as long as the process lives: new pages get
fetched, changed pages get read again, and everything found lands in the same
local index a normal crawl writes to. Nothing is thrown away between rounds.

Design notes, so the behaviour is not a surprise:

* One round = one real `FusionCrawler` pass over one origin. The continuous part
  is the loop and the bookkeeping, not a second crawler implementation — every
  arsenal engine, every robots check and every extractor a one-off crawl uses is
  used here too.
* Rounds rotate. With several sites running, each round takes the next origin in
  turn, so no site is starved.
* The pause between rounds is a real pause (`delay` seconds, default 20). A
  crawler that hammers a site is not "continuous", it is a denial of service.
* Stopping is cooperative: the worker checks its flag every couple of seconds,
  so Stop answers immediately instead of waiting for a slow round to finish.
* State is per-process and in memory. On a free host that sleeps after idle
  minutes the worker goes quiet with it; that is stated in the notes rather than
  pretended away.
"""
from __future__ import annotations

import asyncio
import time
from typing import Any
from urllib.parse import urlsplit

from pydantic import BaseModel, Field

from . import local_index
from .crawl import CrawlRequest, FusionCrawler, normalize_seed

MAX_ERRORS = 20


class ContinuousRequest(BaseModel):
    """What to keep crawling, and how hard."""

    seeds: list[str] = Field(default_factory=list)
    delay: float = Field(default=20.0, ge=0, le=3600)
    pages_per_round: int = Field(default=25, ge=1, le=200)
    same_host: bool = True
    respect_robots: bool = True
    query: str = ""


def _origin(url: str) -> str:
    parts = urlsplit(url)
    if not parts.scheme or not parts.netloc:
        return ""
    return f"{parts.scheme}://{parts.netloc}"


class ContinuousWorker:
    """The background loop and everything it has to say about itself."""

    def __init__(self) -> None:
        self.running: bool = False
        self.task: asyncio.Task | None = None
        self.origins: list[str] = []
        self.cursor: int = 0
        self.req: ContinuousRequest = ContinuousRequest()
        self.rounds: int = 0
        self.pages: int = 0
        self.files: int = 0
        self.skipped: int = 0
        self.current: str = ""
        self.current_since: float = 0.0
        self.last_round_ms: int = 0
        self.last_round_at: float = 0.0
        self.next_at: float = 0.0
        self.started_at: float = 0.0
        self.errors: list[dict[str, Any]] = []

    # ------------------------------------------------------------------ state

    def _note(self, message: str) -> None:
        self.errors.append({"at": int(time.time()), "message": message[:200]})
        del self.errors[:-MAX_ERRORS]

    def status(self) -> dict[str, Any]:
        vault = local_index.vault_stats()
        now = time.time()
        return {
            "running": self.running,
            "origins": list(self.origins),
            "rounds": self.rounds,
            "pages": self.pages,
            "files": self.files,
            "documents": vault.get("documents", 0),
            "current": self.current,
            "current_for_s": int(now - self.current_since) if self.current else 0,
            "delay_s": self.req.delay,
            "pages_per_round": self.req.pages_per_round,
            "same_host": self.req.same_host,
            "respect_robots": self.req.respect_robots,
            "last_round_ms": self.last_round_ms,
            "last_round_at": int(self.last_round_at) if self.last_round_at else 0,
            "next_in_s": max(0, int(self.next_at - now)) if self.running else 0,
            "started_at": int(self.started_at) if self.started_at else 0,
            "uptime_s": int(now - self.started_at) if self.started_at and self.running else 0,
            "errors": list(self.errors[-MAX_ERRORS:]),
            "notes": [
                "Each round is a real crawl of one site, using the same engines a one-off crawl uses.",
                "Rounds rotate between the sites you added, so none of them is starved.",
                "A round is capped at pages_per_round pages; the pause between rounds is delay_s seconds.",
                "Found pages land in the same local index (Your index) a normal crawl writes to.",
                "State lives in this process: it stops if the process restarts or the host sleeps.",
            ],
        }

    # ------------------------------------------------------------------ control

    async def start(self, req: ContinuousRequest) -> dict[str, Any]:
        for raw in req.seeds:
            url = normalize_seed(raw)
            if not url:
                continue
            origin = _origin(url) or url
            if origin not in self.origins:
                self.origins.append(origin)
        if req.seeds and not self.origins:
            raise ValueError("No usable site in that list — give it a full http(s) URL.")
        self.req = ContinuousRequest(
            seeds=list(self.origins), delay=req.delay,
            pages_per_round=req.pages_per_round, same_host=req.same_host,
            respect_robots=req.respect_robots, query=req.query,
        )
        if not self.origins:
            raise ValueError("Give it at least one site to walk.")
        if not self.running:
            self.running = True
            self.started_at = time.time()
            self.task = asyncio.create_task(self._loop())
        return self.status()

    def add_sites(self, raw_seeds: list[str]) -> dict[str, Any]:
        added: list[str] = []
        for raw in raw_seeds:
            url = normalize_seed(raw)
            origin = _origin(url or "")
            if origin and origin not in self.origins:
                self.origins.append(origin)
                added.append(origin)
        status = self.status()
        status["added"] = added
        return status

    async def stop(self) -> dict[str, Any]:
        was_running = self.running
        self.running = False
        task, self.task = self.task, None
        if task and not task.done():
            task.cancel()
            try:
                await asyncio.wait_for(asyncio.shield(task), timeout=8)
            except (asyncio.CancelledError, asyncio.TimeoutError):
                pass
            except Exception:
                pass
        self.current = ""
        self.next_at = 0.0
        status = self.status()
        status["was_running"] = was_running
        return status

    # -------------------------------------------------------------------- loop

    def _next_origin(self) -> str:
        if not self.origins:
            return ""
        origin = self.origins[self.cursor % len(self.origins)]
        self.cursor = (self.cursor + 1) % max(1, len(self.origins))
        return origin

    async def _round(self, seed: str) -> dict[str, Any]:
        crawler = FusionCrawler(CrawlRequest(
            seeds=[seed],
            query=self.req.query,
            depth=2,
            max_pages=self.req.pages_per_round,
            max_files=self.req.pages_per_round,
            respect_robots=self.req.respect_robots,
            same_host=self.req.same_host,
            serp_engines=[],
            use_sitemaps=True,
            use_archive=False,
            delay=0.3,
            label="continuous",
        ))
        try:
            return await crawler.run()
        finally:
            try:
                await crawler.client.aclose()
            except Exception:
                pass

    async def _loop(self) -> None:
        try:
            while self.running:
                seed = self._next_origin()
                if not seed:
                    await asyncio.sleep(2)
                    continue
                self.current = seed
                self.current_since = time.time()
                started = time.time()
                try:
                    report = await self._round(seed)
                    stats = report.get("stats") or {}
                    self.pages += int(stats.get("pages", 0) or 0)
                    self.files += int(stats.get("files", 0) or 0)
                except asyncio.CancelledError:
                    raise
                except Exception as exc:  # one bad round must not end the loop
                    self._note(f"{seed}: {type(exc).__name__}: {exc}")
                self.rounds += 1
                self.last_round_ms = int((time.time() - started) * 1000)
                self.last_round_at = time.time()
                self.current = ""
                # pause, but stay responsive to stop() while pausing
                end = time.time() + max(0.0, float(self.req.delay))
                self.next_at = end
                while self.running and time.time() < end:
                    await asyncio.sleep(min(2.0, max(0.05, end - time.time())))
        except asyncio.CancelledError:
            raise
        finally:
            self.running = False
            self.next_at = 0.0


worker = ContinuousWorker()
