"""Verbatim matching: the query has to appear, word for word.

No stemming, no synonyms, no query expansion, no fuzzy similarity, no "related
concepts". A result either contains the literal phrase or it does not — and when
it does not, we report *how far apart* the words are instead of quietly treating
a scattered keyword hit as a match.

``proximity`` is measured in words: 0 means the phrase is contiguous, 3 means
three extra words sat inside the smallest window that still contains every query
word in order.
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from urllib.parse import unquote

WORD = re.compile(r"\w+", re.UNICODE)
OPERATOR = re.compile(r"\b(?:site|filetype|ext|intitle|inurl|intext):\S+", re.I)


def _fold(text: str) -> str:
    return unicodedata.normalize("NFKC", text or "").casefold()


def tokens(text: str) -> list[tuple[str, int, int]]:
    """(word, start, end) for every word, with offsets into the original text."""
    return [(m.group(0), m.start(), m.end()) for m in WORD.finditer(text or "")]


@dataclass(frozen=True)
class Phrase:
    """The literal query. Operators are stripped; nothing is added."""

    raw: str
    tokens: tuple[str, ...]

    @classmethod
    def parse(cls, text: str) -> "Phrase":
        cleaned = OPERATOR.sub(" ", text or "")
        cleaned = re.sub(r'["\'“”‘’]', " ", cleaned)
        words = tuple(_fold(m.group(0)) for m in WORD.finditer(cleaned))
        return cls(raw=" ".join(words), tokens=words)

    def __bool__(self) -> bool:
        return bool(self.tokens)

    def __len__(self) -> int:
        return len(self.tokens)


@dataclass
class Match:
    verbatim: bool        # contiguous, in order
    slack: int            # extra words inside the smallest window (0 = verbatim)
    occurrences: int      # how many times the phrase appears contiguous
    first: int            # token index of the first hit
    start: int            # char offset of the best window
    end: int

    @property
    def proximity(self) -> int:
        return self.slack


def find(text: str, phrase: Phrase) -> Match | None:
    """Locate the phrase in text — literally if possible, otherwise measure the gap."""
    if not phrase or not text:
        return None
    words = tokens(text)
    if not words:
        return None
    folded = [_fold(word) for word, _start, _end in words]
    needle = list(phrase.tokens)
    size = len(needle)

    # 1. contiguous occurrences (the only thing that counts as a match)
    occurrences = 0
    first_index = -1
    first_span: tuple[int, int] | None = None
    if size <= len(folded):
        for index in range(len(folded) - size + 1):
            if folded[index:index + size] == needle:
                occurrences += 1
                if first_index < 0:
                    first_index = index
                    first_span = (words[index][1], words[index + size - 1][2])
    if occurrences:
        return Match(verbatim=True, slack=0, occurrences=occurrences, first=first_index,
                     start=first_span[0], end=first_span[1])

    # 2. in-order window: every query word present, order preserved, gap measured
    best: tuple[int, int, int, int] | None = None   # (slack, start_index, end_index, at)
    for start in range(len(folded)):
        if folded[start] != needle[0]:
            continue
        cursor = start
        at = 0
        while cursor < len(folded) and at < size:
            if folded[cursor] == needle[at]:
                at += 1
            cursor += 1
        if at == size:
            span = cursor - start
            candidate = (span - size, start, cursor - 1, start)
            if best is None or candidate < best:
                best = candidate
    if best is None:
        return None
    slack, start_index, end_index, at = best
    return Match(verbatim=False, slack=slack, occurrences=0, first=start_index,
                 start=words[start_index][1], end=words[end_index][2])


def annotate(hit, phrase: Phrase | None) -> None:
    """Stamp ``exact``/``proximity``/``match_span`` on a Hit, in place."""
    if not phrase:
        hit.exact = False
        hit.proximity = None
        hit.occurrences = 0
        hit.match_span = None
        hit.match_where = None
        return
    # title first: a title match is the strongest thing a result can say
    best: tuple[tuple, Match, str] | None = None
    for field, text in (("title", hit.title or ""),
                        ("snippet", hit.snippet or ""),
                        ("url", unquote(hit.url or ""))):
        found = find(text, phrase)
        if not found:
            continue
        priority = (0 if field == "title" else 1 if field == "snippet" else 2,
                    not found.verbatim, found.slack)
        if best is None or priority < best[0]:
            best = (priority, found, field)
    if best is None:
        hit.exact = False
        hit.proximity = None
        hit.occurrences = 0
        hit.match_span = None
        hit.match_where = None
        return
    _priority, found, field = best
    hit.exact = found.verbatim
    hit.proximity = found.slack
    hit.occurrences = found.occurrences
    hit.match_where = field
    hit.match_span = [found.start, found.end] if field != "url" else None
