from __future__ import annotations

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


def _find_root() -> Path:
    """Where the project root is, found rather than counted.

    In a checkout this file is <root>/apps/api/app/config.py, so the root is
    three levels up. In the container the package is copied to /app/app, so
    there are only two levels above it and `parents[3]` is an IndexError — which
    is exactly how the first Render deploy died, at import, before uvicorn bound
    a port.

    Walk up instead and stop at the first directory that looks like the root:
    the repo marker, or the launcher sitting beside the package.
    """
    here = Path(__file__).resolve()
    for parent in here.parents:
        if (parent / "apps" / "api" / "app" / "config.py").is_file():
            return parent                      # repo checkout
        if (parent / "index.html").is_file():
            return parent                      # container: /app/index.html + /app/app
    return here.parent.parent                  # last resort, never used


ROOT = _find_root()
DATA_DIR = ROOT / "data"


class Settings(BaseSettings):
    """Every value has a working default: Nighthawk runs with zero configuration."""

    model_config = SettingsConfigDict(env_prefix="NH_", env_file=".env", extra="ignore")

    app_name: str = "Nighthawk"
    data_dir: Path = DATA_DIR

    # network
    request_timeout: float = 9.0
    connect_timeout: float = 5.0
    provider_timeout: float = 11.0
    max_concurrency: int = 14
    user_agent: str = (
        "Nighthawk/1.0 (+https://github.com/regularshowrigby8-create/perplexity-connector; "
        "open-web discovery engine; contact via site)"
    )

    # limits
    rate_limit_per_min: int = 90
    max_domains_per_hunt: int = 6
    cdx_limit: int = 250
    provider_result_cap: int = 40

    # cache
    cache_ttl: int = 300
    cache_max: int = 400

    # optional credentials (never required)
    searxng_url: str = ""
    brave_api_key: str = ""
    tavily_api_key: str = ""
    exa_api_key: str = ""
    github_token: str = ""

    # baseline mesh is always on: it needs no network and no keys
    baseline_enabled: bool = True


settings = Settings()
settings.data_dir.mkdir(parents=True, exist_ok=True)
