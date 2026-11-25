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
    # freshness — every clock the web exposes, normalised to "how long ago"
    published_at: str | None = None
    age_seconds: int | None = None
    age_human: str | None = None
    freshness: float = 0.0
    first_seen: str | None = None
    age_source: str | None = None      # published | first_seen | none
    quality: float = 1.0
    quality_flags: list[str] = Field(default_factory=list)
    language: str | None = None
    # verbatim matching (exact.py) — the literal query, word for word
    exact: bool = False
    proximity: int | None = None       # extra words inside the literal window
    occurrences: int = 0
    match_span: list[int] | None = None
    match_where: str | None = None     # title | snippet | url
    # nothing is discarded; these say what would have been in a filtered engine
    copies: int = 0                    # near-duplicates reported, not removed
    words_hit: int = 0                 # how many of the query's own words this result contains
    off_topic: bool = False            # none of them — kept, sorted below everything that does
    junk: bool = False                 # parked / login wall / error — kept, sorted last
    noise: bool = False                # URL a mainstream engine would drop outright
    sources: list[ProviderRef] = Field(default_factory=list)
    meta: dict[str, Any] = Field(default_factory=dict)


class HuntRequest(BaseModel):
    q: str = Field(min_length=1, max_length=400)
    lens: Lens = "all"
    site: str | None = Field(default=None, max_length=253)
    file_types: list[str] = Field(default_factory=list)
    providers: list[str] = Field(default_factory=list)
    # 0 means "everything found". The caller's own display cap is their business.
    limit: int = Field(default=40, ge=0, le=1000)
    # "accuracy": how well it matches first (literal, then word distance), and
    # newest upload inside each band. "newest": upload date alone.
    sort: Literal["relevance", "depth", "deadline", "newest", "accuracy"] = "newest"
    # word-for-word by default: the literal phrase, in order, nothing added
    match: Literal["exact", "loose"] = "exact"
    # opt-in filter, off by default: results are never narrowed without being asked
    only_exact: bool = False
    # no dedup folding, no junk removal, no diversity penalty, no truncation
    unrestricted: bool = True
    # the demo site this engine ships with is practice material, not the web:
    # it is left out of an answer unless a test asks for it by name
    include_practice: bool = False
    # the 2-year window is the default for every search; a person who asks for
    # something older (a book from 2007) can lift it for that one search
    window_days: int | None = Field(default=None, ge=0, le=36500)
    fresh: bool = False
    # how long to wait for engines before answering with what has arrived;
    # 0 means "use the server's budget" (2.5 s by default)
    budget_ms: int = Field(default=0, ge=0, le=60000)
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
    # verbatim ledger
    verbatim: int = 0
    near_verbatim: int = 0
    not_verbatim: int = 0
    copies_reported: int = 0
    junk_retained: int = 0
    noise_retained: int = 0
    truncated: bool = False
    dropped_spam: int = 0
    # one hop out: the pages opened, the files and dates taken out of them,
    # and the pages that could not be read (slow, refused, not a page)
    hop_pages: int = 0
    hop_found: int = 0
    hop_skipped: int = 0
    # results that matched what was asked for — the file itself, or a page that
    # offers one — cut only because they are older than the window. Reported
    # because that is the cut most likely to hurt: a 2007 archive.org item is
    # still the book that was asked for.
    cut_older_matches: int = 0
    # freshness ledger — second granularity for the first minute
    fresh_seconds: int = 0      # < 60s
    fresh_minutes: int = 0      # < 60m
    fresh_hours: int = 0        # < 24h
    fresh_days: int = 0         # < 7d
    dated: int = 0
    undated: int = 0
    newest_age_seconds: int | None = None
    newest_age_human: str | None = None
    took_ms: int = 0
    cached: bool = False
    # the clock the answer was given against: engines still working when it
    # ran out are reported as "slow", never silently dropped
    budget_ms: int = 0
    slow_providers: int = 0
    # time spent after the last source answered (dedupe report, ranking, index)
    post_ms: int = 0
    copies_scanned: int = 0
    # the recency window: what it was, and how much it cut
    window_days: int = 0
    local_excluded: int = 0            # the practice site on this machine, left out of a real answer
    off_topic: int = 0                 # kept, but contains none of the query's words — sorted last
    cut_older: int = 0
    cut_future: int = 0
    undated_kept: int = 0


class HuntResponse(BaseModel):
    query: str
    lens: str
    site: str | None = None
    hits: list[Hit]
    providers: list[dict[str, Any]]
    facets: dict[str, list[dict[str, Any]]]
    stats: HuntStats
    plays: list[str] = Field(default_factory=list)
    sort: str = "newest"
    match: str = "exact"
    only_exact: bool = False
    unrestricted: bool = True
    # what the query was read as before anything was fetched
    understanding: dict[str, Any] | None = None
    as_of: str | None = None
    expanded: list[str] = Field(default_factory=list)
    # what the query asked for, read before crawling: file types, hosts, and what
    # the typed filter set aside. Empty when the query named no type or host.
    intent: dict[str, Any] = Field(default_factory=dict)


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
