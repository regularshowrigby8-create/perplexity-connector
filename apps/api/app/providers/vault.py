"""Local engines: the vault and its full-text document index."""
from __future__ import annotations

from .. import local_index
from .base import HuntContext, Provider, RawHit


class Vault(Provider):
    id, name, family, layer = "vault", "Nighthawk Vault", "local", "core"
    description = "Everything this instance has ever surfaced — SQLite FTS5 + BM25."
    lenses = ("all", "files", "opportunities", "applications", "datasets", "exposed")
    homepage = "/vault"
    needs_network = False
    weight = 1.1

    async def hunt(self, ctx: HuntContext) -> list[RawHit]:
        rows = local_index.search_vault(ctx.plan.terms, limit=ctx.limit)
        return [RawHit(url=r["url"], title=r["title"], snippet=r["snippet"],
                       kind=r.get("kind") or "page", tags=("vault",))
                for r in rows]


class VaultFullText(Provider):
    id, name, family, layer = "vault_docs", "Vault Deep Text", "local", "core"
    description = "Full-text search inside every file the crawler has extracted."
    lenses = ("all", "files", "opportunities", "datasets")
    homepage = "/vault"
    needs_network = False
    weight = 1.35

    async def hunt(self, ctx: HuntContext) -> list[RawHit]:
        rows = local_index.search_docs(ctx.plan.terms, limit=ctx.limit)
        return [RawHit(url=r["url"], title=r["title"], snippet=r["snippet"],
                       kind="document", tags=("fulltext", r.get("engine") or ""))
                for r in rows]
