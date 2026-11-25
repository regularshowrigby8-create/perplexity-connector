#!/usr/bin/env python3
"""Regenerate docs/ENGINES.md from the live registry.

The engine reference is a build artifact, not prose: every row is read from
app.registry.PROVIDERS and app.arsenal.ENGINES, so the document can never drift
from what the code actually dispatches.

    .venv/bin/python scripts/gen_engines_doc.py
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "apps" / "api"))

from app.arsenal import ENGINES, available_ids  # noqa: E402
from app.portals import PORTALS  # noqa: E402
from app.registry import PROVIDERS  # noqa: E402

OUT = ROOT / "docs" / "ENGINES.md"


def status_of(provider) -> str:
    try:
        return provider.status()
    except Exception:
        return "unknown"


def main() -> int:
    ready = available_ids()
    lines: list[str] = []
    lines.append("# Engine reference")
    lines.append("")
    lines.append(
        f"Generated from the live registry: **{len(PROVIDERS)} remote engines**, "
        f"**{len(ENGINES)} arsenal engines** ({len(ready)} resolved here), "
        f"**{len(PORTALS)} portals**, plus the fusion crawler.")
    lines.append("")
    lines.append("Regenerate with `.venv/bin/python scripts/gen_engines_doc.py`.")
    lines.append("")

    lines.append("## Remote engines")
    lines.append("")
    lines.append("| # | Engine | Layer | Family | Lenses | Credentials | Status |")
    lines.append("|---|---|---|---|---|---|---|")
    for index, provider in enumerate(PROVIDERS, 1):
        requires = ", ".join(provider.requires) or "—"
        lenses = ", ".join(provider.lenses)
        lines.append(
            f"| {index} | {provider.name} | {provider.layer} | {provider.family} | "
            f"{lenses} | {requires} | {status_of(provider)} |")
    lines.append("")

    lines.append("## Arsenal engines")
    lines.append("")
    lines.append("| # | Engine | Role | Language | Probe | State |")
    lines.append("|---|---|---|---|---|---|")
    for index, engine in enumerate(ENGINES, 1):
        state = "ready" if engine.id in ready else "missing"
        lines.append(
            f"| {index} | [{engine.name}]({engine.homepage}) | {engine.role} | "
            f"{engine.language} | `{engine.probe or '—'}` | {state} |")
    lines.append("")

    lines.append("## Portals")
    lines.append("")
    lines.append(f"{len(PORTALS)} hand-picked opportunity portals are searched as links, "
                 "so a hit on a portal page still carries the portal's own deadline.")
    lines.append("")
    for portal in PORTALS:
        site = portal.domains[0] if portal.domains else ""
        lines.append(f"- **{portal.name}** — {site} · {', '.join(portal.lenses)}")
    lines.append("")

    OUT.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"wrote {OUT.relative_to(ROOT)} — {len(PROVIDERS)} providers, "
          f"{len(ENGINES)} arsenal engines, {len(ready)} ready")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
