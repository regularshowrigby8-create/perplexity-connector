"""Launchers: portal deep links and operator-grade dork hand-off."""
from __future__ import annotations

from ..extract import pretty_name
from ..plays import dork_launch_links
from ..portals import portal_hits
from .base import HuntContext, Provider, RawHit


class Portals(Provider):
    id, name, family, layer = "portals", "Portal Universe", "launcher", "portal"
    description = "60+ hand-picked opportunity, document and dataset portals, pre-queried."
    lenses = ("all", "opportunities", "files", "applications", "datasets", "exposed")
    homepage = "/engines"
    needs_network = False
    weight = 0.45

    async def hunt(self, ctx: HuntContext) -> list[RawHit]:
        out = []
        for portal, url in portal_hits(ctx.plan.terms, ctx.lens, limit=12):
            note = portal.note or ", ".join(portal.lenses)
            out.append(RawHit(url=url, title=f"{portal.name} — {ctx.plan.terms}",
                              snippet=f"{note} · lens: {'/'.join(portal.lenses)}",
                              kind="portal", tags=("portal", *portal.lenses)))
        return out


class DorkLauncher(Provider):
    id, name, family, layer = "dorklaunch", "Dork Hand-off", "launcher", "portal"
    description = "Hands the composed operator query to engines that allow it."
    lenses = ("all", "exposed", "files", "opportunities")
    homepage = "/engines"
    needs_network = False
    weight = 0.4

    async def hunt(self, ctx: HuntContext) -> list[RawHit]:
        dork = ctx.plan.plays[0].dork if ctx.plan.plays else ctx.plan.query
        out = []
        for engine, url in dork_launch_links(dork):
            out.append(RawHit(url=url, title=f"{engine}: {dork[:90]}",
                              snippet=f"Open this dork on {engine}",
                              kind="dork", tags=("dork", engine.lower())))
        return out
