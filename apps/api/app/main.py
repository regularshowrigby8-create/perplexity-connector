from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles

import asyncio

from . import fixtures, local_index
from .crawl import CrawlRequest, FusionCrawler
from .api import router
from .config import ROOT, public_port, settings


def launcher_path() -> Path | None:
    """Where index.html lives, wherever this is running.

    Next to the data dir (repo checkout, or /app in the container), next to the
    API package, then the container's own copy. First hit wins; no hit means the
    API is deployed without the page, which is fine — routes fall back to docs.
    """
    for candidate in (settings.data_dir.parent / "index.html", ROOT / "index.html",
                      Path("/app/index.html")):
        if candidate.is_file():
            return candidate
    return None


@asynccontextmanager
async def lifespan(app: FastAPI):
    local_index.init()
    demo_root = fixtures.build(public_port())
    app.mount("/demo", StaticFiles(directory=str(demo_root), html=True), name="demo")

    async def prime() -> None:
        try:
            if local_index.vault_stats().get("documents", 0) == 0:
                await FusionCrawler(CrawlRequest(
                    seeds=[f"http://127.0.0.1:{public_port()}/demo/index.html"],
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


@app.get("/", include_in_schema=False)
async def index() -> Response:
    """The launcher, when it ships beside the app (the Docker image does).

    One container then answers for the page *and* the crawler on one origin, so
    nothing in the page has to guess where the engine lives and no static host
    proxy is involved. Without the file this is just the API docs.
    """
    page = launcher_path()
    if page is None:
        return RedirectResponse("/api/docs")
    # no-store: a redeploy must show the new page, not the browser's copy of the
    # old one. "It is still the same error" is usually a cached launcher.
    return FileResponse(page, media_type="text/html",
                        headers={"Cache-Control": "no-store", "Pragma": "no-cache"})


@app.get("/launch", include_in_schema=False)
async def launch(download: bool = False) -> FileResponse:
    """Serve the standalone launcher page (or send it as a download)."""
    page = launcher_path()
    if page is None:
        raise HTTPException(status_code=404, detail="launcher not found")
    return FileResponse(
        page,
        media_type="text/html",
        filename="nighthawk-index.html" if download else None,
        headers={"Cache-Control": "no-store", "Pragma": "no-cache"},
    )


@app.get("/healthz")
async def healthz() -> JSONResponse:
    return JSONResponse({"ok": True, "app": settings.app_name})
