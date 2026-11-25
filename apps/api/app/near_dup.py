"""Near-duplicate clustering for result sets and extracted documents.

Imported from:
  * ekzhu/datasketch — MinHash + LSH parameters (num_perm=128, threshold-driven bands)
  * 1e0ng/simhash, seomoz/simhash-py — 64-bit simhash + hamming fallback
  * adbar/trafilatura (MIN_DUPLICATE_LENGTH=50) — never compare very short texts

The output is not "these are duplicates, deleted" — every cluster keeps its best member
and reports how many near-copies were folded into it, so consensus stays visible.
"""
from __future__ import annotations

import hashlib
import re
import unicodedata
from collections import defaultdict

from .urlnorm import registrable

MIN_DUPLICATE_LENGTH = 50      # imported threshold
NUM_PERM = 128                 # datasketch default
SHINGLE = 4

_WORD = re.compile(r"\w+", re.UNICODE)


def normalize_text(text: str) -> str:
    text = unicodedata.normalize("NFKC", text or "").lower()
    return " ".join(_WORD.findall(text))


def _shingles(text: str, size: int = SHINGLE) -> set[str]:
    words = normalize_text(text).split()
    if len(words) < size:
        return {" ".join(words)} if words else set()
    return {" ".join(words[i:i + size]) for i in range(len(words) - size + 1)}


def _simhash(text: str) -> int:
    tokens = normalize_text(text).split()
    if not tokens:
        return 0
    weights: dict[str, int] = defaultdict(int)
    for token in tokens:
        weights[token] += 1
    vector = [0] * 64
    for token, weight in weights.items():
        digest = int(hashlib.blake2b(token.encode(), digest_size=8).hexdigest(), 16)
        for bit in range(64):
            vector[bit] += weight if (digest >> bit) & 1 else -weight
    out = 0
    for bit in range(64):
        if vector[bit] > 0:
            out |= 1 << bit
    return out


def _hamming(a: int, b: int) -> int:
    return bin(a ^ b).count("1")


def cluster(records: list, text_of=..., key_of=..., max_bandwidth: int = 3) -> tuple[list, int]:
    """Collapse near-duplicates in a list of objects.

    `text_of(record)` must yield the comparable text, `key_of(record)` a stable identity.
    Returns (kept_records, collapsed_count); each kept record gets `meta['near_dupes']`.
    """
    if text_of is ...:
        text_of = lambda r: f"{getattr(r, 'title', '')} {getattr(r, 'snippet', '')}"
    if key_of is ...:
        key_of = lambda r: getattr(r, "url", "")

    candidates = [r for r in records if len(normalize_text(text_of(r))) >= MIN_DUPLICATE_LENGTH]
    if len(candidates) < 2:
        return records, 0

    parent = {id(r): id(r) for r in records}

    def find(x: int) -> int:
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(a: int, b: int) -> None:
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[rb] = ra

    used_lsh = False
    try:
        from datasketch import MinHash, MinHashLSH

        lsh = MinHashLSH(threshold=0.74, num_perm=NUM_PERM)
        signatures: dict[int, object] = {}
        for record in candidates:
            signature = MinHash(num_perm=NUM_PERM)
            shingles = _shingles(text_of(record))
            if not shingles:
                continue
            for shingle in shingles:
                signature.update(shingle.encode("utf-8"))
            signatures[id(record)] = signature
            try:
                lsh.insert(str(id(record)), signature)
            except ValueError:
                continue
        for record in candidates:
            signature = signatures.get(id(record))
            if signature is None:
                continue
            for other in lsh.query(signature):
                union(id(record), int(other))
        used_lsh = True
    except Exception:
        used_lsh = False

    # Second pass: fuzzy token matching for same-site paraphrase (rapidfuzz / dedupe.io idea).
    if "rapidfuzz" in globals() or True:
        try:
            from rapidfuzz import fuzz

            by_site: dict[str, list] = defaultdict(list)
            for record in candidates:
                by_site[registrable(getattr(record, "url", ""))].append(record)
            for site_records in by_site.values():
                if len(site_records) > 60:
                    continue
                for i, record_a in enumerate(site_records):
                    for record_b in site_records[i + 1:]:
                        if find(id(record_a)) == find(id(record_b)):
                            continue
                        ratio = fuzz.token_set_ratio(normalize_text(text_of(record_a))[:600],
                                                     normalize_text(text_of(record_b))[:600])
                        if ratio >= 92:
                            union(id(record_a), id(record_b))
        except Exception:
            pass

    if not used_lsh:
        hashes = [(r, _simhash(text_of(r))) for r in candidates]
        for i, (record_a, hash_a) in enumerate(hashes):
            for record_b, hash_b in hashes[i + 1:]:
                if _hamming(hash_a, hash_b) <= 3:
                    union(id(record_a), id(record_b))

    groups: dict[int, list] = defaultdict(list)
    for record in records:
        groups[find(id(record))].append(record)

    kept: list = []
    collapsed = 0
    for group in groups.values():
        if len(group) == 1:
            kept.append(group[0])
            continue
        group.sort(key=lambda r: (-_specificity(r), -float(getattr(r, "score", 0) or 0),
                                  -len(str(getattr(r, "snippet", "") or ""))))
        best = group[0]
        meta = getattr(best, "meta", None)
        if isinstance(meta, dict):
            meta["near_dupes"] = len(group) - 1
            meta["near_dup_urls"] = [getattr(r, "url", "") for r in group[1:6]]
        collapsed += len(group) - 1
        for other in group[1:]:
            sources = getattr(best, "sources", None)
            if isinstance(sources, list):
                for source in getattr(other, "sources", []) or []:
                    if all(s.provider != source.provider for s in sources):
                        sources.append(source)
            best.depth = max(int(getattr(best, "depth", 0)), int(getattr(other, "depth", 0)))
            if getattr(other, "deadline", None) and not getattr(best, "deadline", None):
                best.deadline = other.deadline
            for field in ("funder", "amount", "currency", "location", "structured",
                          "schema_type", "sniffed", "size"):
                if getattr(best, field, None) in (None, "", 0) and getattr(other, field, None):
                    try:
                        setattr(best, field, getattr(other, field))
                    except (AttributeError, ValueError):
                        pass
        kept.append(best)
    return kept, collapsed


def _specificity(record) -> int:
    """How *useful* a record is, not just how high it scored.

    A page that names the funder, the amount and the closing date beats a
    near-identical PDF that only carries the date — so when a duplicate cluster
    collapses, the richest member survives and inherits the others' fields.
    """
    fields = ("funder", "amount", "currency", "location", "structured", "schema_type")
    score = sum(2 for field in fields if getattr(record, field, None))
    if getattr(record, "deadline", None):
        score += 3
    if getattr(record, "kind", "") in ("opportunity", "grant"):
        score += 4
    elif getattr(record, "kind", "") == "document":
        score += 1
    return score


def fingerprint(text: str) -> str:
    """Stable content hash used by the change detector."""
    return hashlib.sha1(normalize_text(text).encode("utf-8")).hexdigest()
