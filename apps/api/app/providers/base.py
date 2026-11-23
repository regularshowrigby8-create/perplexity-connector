from __future__ import annotations

import html
import re
from dataclasses import dataclass, field
from typing import Any

import httpx

from ..config import settings
from ..plays import Plan


@dataclass
class RawHit:
    url: str
    title: str
    snippet: str = ""
    kind: str | None = None
    published: str | None = None
    deadline: str | None = None
    archive: bool = False
    tags: tuple[str, ...] = ()
    meta: dict[str, Any] = field(default_factory=dict)


@dataclass
class HuntContext:
    plan: Plan
    client: httpx.AsyncClient
    keys: dict[str, str]
    limit: int
    domains: list[str]

    @property
    def text(self) -> str:
        return self.plan.terms

    @property
    def lens(self) -> str:
        return self.plan.lens

    @property
    def site(self) -> str | None:
        return self.plan.site

    @property
    def file_types(self) -> list[str]:
        return self.plan.file_types


class Provider:
    id: str = "provider"
    name: str = "Provider"
    family: str = "web"
    layer: str = "remote"          # remote | archive | portal | core | launcher
    description: str = ""
    lenses: tuple[str, ...] = ("all",)
    homepage: str = ""
    requires: tuple[str, ...] = ()   # settings/env names that unlock this engine
    needs_network: bool = True
    rate_note: str = ""
    opt_in: bool = False             # only runs when explicitly selected
    retired: bool = False
    weight: float = 1.0

    # ---------------------------------------------------------------- availability
    def key(self, ctx: HuntContext, name: str) -> str:
        return (ctx.keys.get(name) or ctx.keys.get(self.id)
                or str(getattr(settings, name, "") or ""))

    def available(self, ctx: HuntContext) -> bool:
        if self.retired:
            return False
        return all(self.key(ctx, req) for req in self.requires)

    def status(self, ctx: HuntContext | None = None) -> str:
        if self.retired:
            return "retired"
        if self.layer == "core":
            return "local"
        if self.requires:
            has = all(str(getattr(settings, r, "") or "") for r in self.requires)
            return "ready" if has else "needs_key"
        return "ready"

    async def hunt(self, ctx: HuntContext) -> list[RawHit]:  # pragma: no cover - interface
        raise NotImplementedError


# ------------------------------------------------------------------- utilities

TAG_RE = re.compile(r"<[^>]+>")


def clean(text: str | None, limit: int = 420) -> str:
    if not text:
        return ""
    text = TAG_RE.sub(" ", text)
    text = html.unescape(text)
    text = re.sub(r"\s+", " ", text).strip()
    return text[:limit]


async def get_json(ctx: HuntContext, url: str, **kwargs: Any) -> Any:
    headers = kwargs.pop("headers", {})
    resp = await ctx.client.get(url, headers=headers, **kwargs)
    resp.raise_for_status()
    return resp.json()


async def post_json(ctx: HuntContext, url: str, **kwargs: Any) -> Any:
    headers = kwargs.pop("headers", {})
    resp = await ctx.client.post(url, headers=headers, **kwargs)
    resp.raise_for_status()
    return resp.json()


def domain_of(url: str) -> str:
    from ..extract import safe_domain

    return safe_domain(url)


def as_list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]
