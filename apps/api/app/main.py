from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

import asyncio

from . import fixtures, local_index
from .crawl import CrawlRequest, FusionCrawler
from .api import router
from .config import settings


@asynccontextmanager
async def lifespan(app: FastAPI):
    local_index.init()
    demo_root = fixtures.build(8000)
    app.mount("/demo", StaticFiles(directory=str(demo_root), html=True), name="demo")

    async def prime() -> None:
        try:
            if local_index.vault_stats().get("documents", 0) == 0:
                await FusionCrawler(CrawlRequest(
                    seeds=["http://127.0.0.1:8000/demo/index.html"],
                    query="climate grant", depth=2, max_pages=14, max_files=16,
                    serp_engines=[], delay=0.0, label="vault-prime",
                )).run()
        except Exception:
            pass

    task = asyncio.create_task(prime())
    yield
    task.cancel()


app = FastAPI(
    title="Nighthawk API",
    description="One monster search engine: a fusion crawler, 60+ remote engines and an "
                "86-engine crawl arsenal, all fused into a single ranked stream.",
    version="1.0.0",
    lifespan=lifespan,
    docs_url="/api/docs",
    openapi_url="/api/openapi.json",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router)


@app.get("/api")
async def api_root() -> RedirectResponse:
    return RedirectResponse("/api/docs")


@app.get("/healthz")
async def healthz() -> JSONResponse:
    return JSONResponse({"ok": True, "app": settings.app_name})
