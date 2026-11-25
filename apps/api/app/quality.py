"""Cleanliness and accuracy signals, applied before anything is ranked.

Breadth means nothing if half the set is parked domains, cookie walls and
keyword-stuffed doorway pages. This module scores every candidate and repairs
the text, so ranking works on real content.

Imported from:
  * rspeer/python-ftfy        — mojibake repair ("SÃ£o Paulo" → "São Paulo")
  * jfilter/clean-text        — unicode/whitespace/phone normalisation
  * searxng/searxng           — engine-level "this result is junk" heuristics
  * trafilatura / jusText     — link-density and text-length thresholds
  * py3langid (MIT)           — language label, never a language filter
  * scrapers/dateparser       — date-shape sanity checks
  * Common Crawl quality work — the "thin page" / boilerplate ratio idea
  * Google's doorway-page policy (public documentation) — the spam patterns
  * Adblock/uBlock filter lists — parked-domain and parking-page markers

Deliberate non-goal: nothing here demotes a result for being old, unlinked,
plain-text or machine-generated. Those are the results Nighthawk exists for.
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field

SPAM_PATTERNS = re.compile(
    r"\b(viagra|cialis|casino|betting bonus|free spins|escort service|porn|xxx|"
    r"essay writing service|buy assignment|cheap essay|payday loan|"
    r"crypto pump|bitcoin doubles|binary options|forex signals|"
    r"replica watches|cheap jerseys|seo backlinks|buy backlinks|"
    r"hacked|cracked apk|nulled script)\b", re.I)
PARKED_PATTERNS = re.compile(
    r"(this domain (is|may be) for sale|buy this domain|domain has expired|"
    r"parked (free|domain)|sedo\.com|hugedomains|afternic|"
    r"future home of something quite cool|default web page|"
    r"website is under construction|coming soon)", re.I)
WALL_PATTERNS = re.compile(
    r"(enable javascript|cookies? (are|must be) (required|enabled)|"
    r"sign in to (continue|view)|log ?in to continue|"
    r"you must be logged in|subscribe to (read|continue)|"
    r"verify you are human|checking your browser|attention required)", re.I)
ERROR_PATTERNS = re.compile(
    r"(404 not found|page not found|the page you (are|were) looking for|"
    r"access denied|403 forbidden|502 bad gateway|503 service unavailable|"
    r"this (page|content) (is )?no longer available|file not found)", re.I)
DOORWAY_PATTERNS = re.compile(
    r"(we have \d{2,} (pages|articles) about|related searches|"
    r"best \w+ in \w+ \| best \w+ in|click here to (enter|continue))", re.I)
BOILERPLATE = re.compile(
    r"(all rights reserved|privacy policy|terms (of|and) (use|conditions)|"
    r"cookie (policy|settings)|accept all cookies|sign up for our newsletter|"
    r"follow us on (facebook|twitter|x|linkedin)|share this article)", re.I)

STOPWORDS = set("""the a an and or but if then than that this these those of to in on at by for
with from as is are was were be been being it its it's into about over under between during
after before above below up down out off again further once here there when where why how all
any both each few more most other some such no nor not only own same so too very can will just
don should now you your we our they their he she his her i my me""".split())

CURRENCY = re.compile(r"[$€£¥₹₦₽₩]|\b(usd|eur|gbp|zar|kes|ngn|inr|cad|aud|chf|sek|nok)\b", re.I)
NUMBER = re.compile(r"\b\d[\d,.]*\b")
WORD = re.compile(r"[A-Za-z][A-Za-z'\-]{1,}")


@dataclass
class Quality:
    score: float = 1.0
    spam: bool = False
    flags: list[str] = field(default_factory=list)
    language: str = ""

    def as_meta(self) -> dict:
        return {"quality": round(self.score, 3), "quality_flags": list(self.flags),
                "language": self.language}


# ------------------------------------------------------------------------ repair

def repair(text: str | None) -> str:
    """Fix mojibake and stray control characters, keep real punctuation."""
    if not text:
        return ""
    out = text
    try:
        import ftfy

        out = ftfy.fix_text(out, normalization="NFC")
    except Exception:
        pass
    out = unicodedata.normalize("NFC", out)
    out = out.replace("\u200b", "").replace("\ufeff", "")
    return re.sub(r"[ \t\u00a0]+", " ", out).strip()


def normalise(text: str | None, keep_urls: bool = True) -> str:
    """Collapse whitespace and strip noise characters without eating content."""
    text = repair(text)
    if not text:
        return ""
    if not keep_urls:
        text = re.sub(r"https?://\S+", " ", text)
    text = re.sub(r"\s*\n\s*", "\n", text)
    text = re.sub(r"[ ]{2,}", " ", text)
    return text.strip()


# ------------------------------------------------------------------------ signals

def language_of(text: str) -> str:
    """Language label via py3langid. Returns "" when the sample is too small."""
    sample = (text or "").strip()
    if len(sample) < 80:
        return ""
    try:
        import py3langid as langid

        ranked = langid.rank(sample[:2000])
        if not ranked:
            return ""
        best, best_score = ranked[0]
        runner_up = ranked[1][1] if len(ranked) > 1 else best_score - 99
        # rank() returns log-probabilities; a clear margin is the confidence signal
        return best if (best_score - runner_up) > 1.0 else ""
    except Exception:
        return ""


def stopword_ratio(text: str) -> float:
    words = [w.lower() for w in WORD.findall(text or "")]
    if len(words) < 12:
        return 0.0
    return sum(1 for w in words if w in STOPWORDS) / len(words)


def link_density(text: str) -> float:
    if not text:
        return 0.0
    words = max(1, len(WORD.findall(text)))
    links = len(re.findall(r"https?://\S+", text))
    return min(1.0, links / words * 12)


def keyword_stuffing(title: str) -> float:
    tokens = [t.lower() for t in WORD.findall(title or "")]
    if len(tokens) < 4:
        return 0.0
    unique = len(set(tokens))
    return round(1 - unique / len(tokens), 3)


def gibberish(text: str) -> bool:
    words = WORD.findall(text or "")[:120]
    if len(words) < 10:
        return False
    long_consonants = sum(
        1 for w in words if re.search(r"[bcdfghjklmnpqrstvwxz]{6,}", w.lower()))
    return long_consonants / len(words) > 0.25


def _hits(pattern: re.Pattern[str], *parts: str) -> list[str]:
    blob = " ".join(part or "" for part in parts)
    return [m.group(0).lower() for m in pattern.finditer(blob)][:4]


def assess(url: str, title: str, snippet: str, text: str | None = None,
           terms: list[str] | None = None) -> Quality:
    """Score one candidate 0..1 and say why. ``spam`` means "drop it"."""
    title = repair(title)
    snippet = repair(snippet)
    body = text if text is not None else snippet
    blob = f"{title} {snippet} {body[:4000]}"
    quality = Quality()
    flags: list[str] = []

    if PARKED_PATTERNS.search(blob):
        flags.append("parked")
        quality.score -= 0.85
        quality.spam = True
    wall = _hits(WALL_PATTERNS, title, snippet[:400])
    if wall:
        flags.append("login-wall")
        quality.score -= 0.5
    errors = _hits(ERROR_PATTERNS, title, snippet[:300])
    if errors:
        flags.append("error-page")
        quality.score -= 0.6
        quality.spam = True
    if SPAM_PATTERNS.search(blob):
        flags.append("spam")
        quality.score -= 0.7
        quality.spam = True
    if DOORWAY_PATTERNS.search(blob[:2000]):
        flags.append("doorway")
        quality.score -= 0.3

    stuffing = keyword_stuffing(title)
    if stuffing >= 0.34:
        flags.append("keyword-stuffing")
        quality.score -= 0.2

    words = len(WORD.findall(body))
    if words < 12 and len(snippet) < 80:
        flags.append("thin")
        quality.score -= 0.25
    if words >= 40 and BOILERPLATE.search(body):
        flags.append("boilerplate")
        quality.score -= 0.08

    if gibberish(body):
        flags.append("gibberish")
        quality.score -= 0.35

    if title and title.upper() == title and len(title) > 25:
        flags.append("shouting")
        quality.score -= 0.05

    ratio = stopword_ratio(body)
    if words >= 40 and ratio < 0.06:
        flags.append("low-prose")
        quality.score -= 0.1

    density = link_density(body)
    if density > 0.55:
        flags.append("link-farm")
        quality.score -= 0.15

    quality.language = language_of(body) if body else ""

    if terms:
        haystack = blob.lower()
        if not any(term in haystack for term in terms):
            flags.append("off-topic")
            quality.score -= 0.1

    quality.score = max(0.0, min(1.0, quality.score))
    quality.flags = flags
    return quality


def is_spam(quality: Quality, threshold: float = 0.28) -> bool:
    """Drop only clear junk. An undated, ugly, unlinked page is never spam."""
    return quality.spam and quality.score <= threshold
