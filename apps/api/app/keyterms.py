"""Keyphrase extraction and query expansion.

Imported from:
  * LIAAD/yake        — unsupervised single-document keyphrase extraction (YAKE)
  * boudinfl/pke       — the family of statistical keyphrase extractors
  * searxng/searxng    — synonym expansion of the query before fan-out

Purpose here is narrow and practical: tag every result with the phrases that actually
identify it, and widen the query with the vocabulary each lens expects.
"""
from __future__ import annotations

import re

_STOP = set("""
a an the and or but if then than that this these those of in on at to for from by with without
about into over under again further once here there when where why how all any both each few
more most other some such no nor not only own same so too very can will just should now
is are was were be been being have has had do does did doing would could may might must
""".split())

# Lens vocabulary — siblings of the words a user is likely to type.
THESAURUS: dict[str, tuple[str, ...]] = {
    "opportunities": ("grant", "call for proposals", "tender", "funding", "fellowship",
                      "scholarship", "open call", "expression of interest"),
    "applications": ("application form", "apply", "admissions", "call for applications",
                     "eligibility", "guidelines"),
    "files": ("pdf", "report", "annex", "guidelines", "spreadsheet", "download"),
    "datasets": ("dataset", "open data", "csv", "indicator", "statistics", "microdata"),
    "exposed": ("index of", "backup", "directory listing", "upload", "archive"),
}

_yake = None


def _yake_extractor():
    global _yake
    if _yake is None:
        try:
            import yake

            _yake = yake.KeywordExtractor(lan="en", n=3, dedupLim=0.85, top=12, features=None)
        except Exception:
            _yake = False
    return _yake


def keyphrases(text: str, limit: int = 8) -> list[str]:
    """Unsupervised keyphrases, cheapest engine first."""
    text = re.sub(r"\s+", " ", text or "").strip()
    if len(text) < 40:
        return []
    extractor = _yake_extractor()
    if extractor:
        try:
            found = extractor.extract_keywords(text[:20000])
            out: list[str] = []
            for phrase, _score in found:
                phrase = phrase.strip().lower()
                if 3 <= len(phrase) <= 60 and phrase not in out and any(ch.isalpha() for ch in phrase):
                    out.append(phrase)
                if len(out) >= limit:
                    break
            if out:
                return out
        except Exception:
            pass
    # Fallback: frequency of 1–2-grams, stopword filtered.
    words = [w for w in re.findall(r"[a-zA-Z][a-zA-Z0-9-]{2,}", text.lower()) if w not in _STOP]
    counts: dict[str, int] = {}
    for i, word in enumerate(words):
        counts[word] = counts.get(word, 0) + 1
        if i + 1 < len(words):
            bigram = f"{word} {words[i + 1]}"
            counts[bigram] = counts.get(bigram, 0) + 1
    ranked = sorted(counts.items(), key=lambda kv: (-kv[1], -len(kv[0])))
    return [phrase for phrase, count in ranked if count > 1][:limit] or [w for w, _ in ranked[:limit]]


def expand_terms(query: str, lens: str, limit: int = 6) -> list[str]:
    """Add sibling vocabulary for this lens, never repeating what the user typed."""
    low = (query or "").lower()
    present = set(re.findall(r"[a-z]{3,}", low))
    out: list[str] = []
    for term in THESAURUS.get(lens, ()):
        words = set(re.findall(r"[a-z]{3,}", term))
        if words and words <= present:
            continue
        if term in low:
            continue
        out.append(term)
        if len(out) >= limit:
            break
    return out
