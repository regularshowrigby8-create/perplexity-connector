"""Change detection for watchers.

Imported from:
  * dgtlmoon/changedetection.io — store a content hash per watched URL, diff on each run
  * difflib (stdlib)            — unified diff, bounded output
  * ajaxorg? no — the "watch the document, not the URL" lesson: a hit that keeps its URL
    but changes its body is the interesting event.

Every watcher run now reports: new URLs, changed documents (with added/removed line counts
and a sample diff), and unchanged ones. That is what turns a search into a monitoring tool.
"""
from __future__ import annotations

import difflib
import re
from typing import Any

MAX_DIFF_LINES = 60


def content_hash(text: str) -> str:
    from .near_dup import fingerprint

    return fingerprint(text or "")


def _lines(text: str) -> list[str]:
    clean = re.sub(r"[ \t]+", " ", text or "")
    return [line.strip() for line in clean.splitlines() if line.strip()]


def word_diff(old: str, new: str, limit: int = 12) -> dict[str, list[str]]:
    """Token-level delta — the only thing that reads well for one-line notices.

    Most opportunity pages are a single paragraph, so a line diff says "changed"
    and nothing else. Comparing word sequences surfaces the actual edit:
    "28 February" → "30 April", "90,000" → "120,000".
    """
    old_words = re.findall(r"\S+", old or "")
    new_words = re.findall(r"\S+", new or "")
    added: list[str] = []
    removed: list[str] = []
    matcher = difflib.SequenceMatcher(a=old_words, b=new_words, autojunk=False)
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag in ("replace", "delete"):
            removed.extend(old_words[i1:i2])
        if tag in ("replace", "insert"):
            added.extend(new_words[j1:j2])
    return {"added": [" ".join(added[:limit])] if added else [],
            "removed": [" ".join(removed[:limit])] if removed else []}


def diff(old: str, new: str, max_lines: int = MAX_DIFF_LINES) -> dict[str, Any]:
    old_lines, new_lines = _lines(old), _lines(new)
    added = removed = 0
    sample: list[str] = []
    for line in difflib.unified_diff(old_lines, new_lines, lineterm="", n=1):
        if line.startswith("+++") or line.startswith("---") or line.startswith("@@"):
            continue
        if line.startswith("+"):
            added += 1
        elif line.startswith("-"):
            removed += 1
        if len(sample) < max_lines:
            sample.append(line[:320])
    changed = bool(added or removed)
    words = word_diff(old, new) if changed else {"added": [], "removed": []}
    return {
        "changed": changed,
        "added": added,
        "removed": removed,
        "sample": "\n".join(sample[:max_lines]),
        "word_added": words["added"],
        "word_removed": words["removed"],
    }
