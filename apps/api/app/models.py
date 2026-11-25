from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

Lens = Literal["all", "opportunities", "files", "applications", "exposed", "datasets"]


class ProviderRef(BaseModel):
    provider: str
    name: str
    rank: int = 0
    url: str


class Deadline(BaseModel):
    date: str
    days_left: int
    phrase: str = ""
    urgency: Literal["closed", "today", "soon", "upcoming", "later"]


class Hit(BaseModel):
    url: str
    title: str
    snippet: str = ""
    provider: str
    provider_name: str
    kind: str = "page"
    file_ext: str | None = None
    mime: str | None = None
    domain: str = ""
    published: str | None = None
    deadline: Deadline | None = None
    depth: int = 0
    score: float = 0.0
    tags: list[str] = Field(default_factory=list)
    archive: bool = False
    portal: bool = False
    funder: str | None = None
    amount: str | None = None
    currency: str | None = None
    location: str | None = None
    structured: str | None = None
    schema_type: str | None = None
    size: int | None = None
    sniffed: str | None = None
    keyphrases: list[str] = Field(default_factory=list)
    near_dupes: int = 0
    sources: list[ProviderRef] = Field(default_factory=list)
    meta: dict[str, Any] = Field(default_factory=dict)


class HuntRequest(BaseModel):
    q: str = Field(min_length=1, max_length=400)
    lens: Lens = "all"
    site: str | None = Field(default=None, max_length=253)
    file_types: list[str] = Field(default_factory=list)
    providers: list[str] = Field(default_factory=list)
    limit: int = Field(default=40, ge=5, le=200)
    sort: Literal["relevance", "depth", "deadline", "newest"] = "relevance"
    fresh: bool = False
    # session-supplied optional credentials — used for this request only, never stored
    keys: dict[str, str] = Field(default_factory=dict)


class ProviderInfo(BaseModel):
    id: str
    name: str
    family: str
    description: str
    lenses: list[str]
    homepage: str
    requires: list[str] = Field(default_factory=list)
    needs_network: bool = True
    rate_note: str = ""
    configured: bool = True


class HuntStats(BaseModel):
    hits: int = 0
    unique: int = 0
    providers_ok: int = 0
    providers_failed: int = 0
    files: int = 0
    opportunities: int = 0
    closing_soon: int = 0
    duplicates_collapsed: int = 0
    dropped_noise: int = 0
    took_ms: int = 0
    cached: bool = False


class HuntResponse(BaseModel):
    query: str
    lens: str
    site: str | None = None
    hits: list[Hit]
    providers: list[dict[str, Any]]
    facets: dict[str, list[dict[str, Any]]]
    stats: HuntStats
    plays: list[str] = Field(default_factory=list)
    expanded: list[str] = Field(default_factory=list)


class ScoutRequest(BaseModel):
    domain: str = Field(min_length=3, max_length=253)
    sitemaps: bool = True
    directories: bool = True
    archives: bool = True
    subdomains: bool = False
    file_types: list[str] = Field(default_factory=list)
    limit: int = Field(default=120, ge=10, le=400)


class ScoutResponse(BaseModel):
    domain: str
    files: list[Hit]
    probes: list[dict[str, Any]]
    stats: dict[str, Any]


class Hunt(BaseModel):
    id: int
    name: str
    query: str
    lens: str
    site: str | None = None
    created_at: str
    last_run_at: str | None = None
    last_count: int = 0


class SavedItem(BaseModel):
    id: int
    url: str
    title: str
    provider: str = ""
    kind: str = "page"
    file_ext: str | None = None
    deadline: str | None = None
    note: str = ""
    query: str = ""
    created_at: str
