"""Local hybrid index: SQLite FTS5 + Whoosh + Tantivy + BM25 fused into one ranker.

This is the part of the monster that lives inside the box. Every hit Nighthawk
surfaces is written to a local vault (files, metadata, snippets) and can be
re-searched offline, re-ranked, and fused with live provider scores.
"""
from __future__ import annotations

import json
import math
import re
import sqlite3
import threading
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, Iterator

from .config import settings

_lock = threading.Lock()
_db_path = settings.data_dir / "nighthawk.db"
_whoosh_dir = settings.data_dir / "whoosh"
_tantivy_dir = settings.data_dir / "tantivy"

STOP = {
    "the", "a", "an", "and", "or", "of", "to", "in", "for", "on", "with", "is", "are",
    "at", "by", "from", "as", "be", "this", "that", "it", "its",
}


@contextmanager
def db() -> Iterator[sqlite3.Connection]:
    conn = sqlite3.connect(_db_path, timeout=20)
    conn.row_factory = sqlite3.Row
    try:
        conn.execute("PRAGMA journal_mode=WAL")
        _ensure_schema(conn)
        yield conn
        conn.commit()
    finally:
        conn.close()


_SCHEMA = """
            CREATE TABLE IF NOT EXISTS vault (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                url TEXT NOT NULL,
                canonical TEXT NOT NULL,
                title TEXT NOT NULL,
                snippet TEXT,
                provider TEXT,
                kind TEXT,
                file_ext TEXT,
                domain TEXT,
                deadline TEXT,
                depth INTEGER DEFAULT 0,
                first_seen TEXT,
                last_seen TEXT,
                times_seen INTEGER DEFAULT 1,
                payload TEXT
            );
            CREATE UNIQUE INDEX IF NOT EXISTS vault_canonical ON vault(canonical);
            CREATE INDEX IF NOT EXISTS vault_ext ON vault(file_ext);

            CREATE VIRTUAL TABLE IF NOT EXISTS vault_fts USING fts5(
                title, snippet, url, content='vault', content_rowid='id',
                tokenize='porter unicode61'
            );

            CREATE TRIGGER IF NOT EXISTS vault_ai AFTER INSERT ON vault BEGIN
                INSERT INTO vault_fts(rowid, title, snippet, url)
                VALUES (new.id, new.title, new.snippet, new.url);
            END;
            CREATE TRIGGER IF NOT EXISTS vault_ad AFTER DELETE ON vault BEGIN
                INSERT INTO vault_fts(vault_fts, rowid, title, snippet, url)
                VALUES ('delete', old.id, old.title, old.snippet, old.url);
            END;
            CREATE TRIGGER IF NOT EXISTS vault_au AFTER UPDATE ON vault BEGIN
                INSERT INTO vault_fts(vault_fts, rowid, title, snippet, url)
                VALUES ('delete', old.id, old.title, old.snippet, old.url);
                INSERT INTO vault_fts(rowid, title, snippet, url)
                VALUES (new.id, new.title, new.snippet, new.url);
            END;

            CREATE TABLE IF NOT EXISTS hunts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                query TEXT NOT NULL,
                lens TEXT NOT NULL DEFAULT 'all',
                site TEXT,
                created_at TEXT NOT NULL,
                last_run_at TEXT,
                last_count INTEGER DEFAULT 0
            );
            CREATE TABLE IF NOT EXISTS hunt_seen (
                hunt_id INTEGER NOT NULL,
                canonical TEXT NOT NULL,
                first_seen TEXT NOT NULL,
                PRIMARY KEY (hunt_id, canonical)
            );
            CREATE TABLE IF NOT EXISTS saved (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                url TEXT NOT NULL,
                canonical TEXT NOT NULL,
                title TEXT NOT NULL,
                provider TEXT,
                kind TEXT,
                file_ext TEXT,
                deadline TEXT,
                depth INTEGER DEFAULT 0,
                note TEXT DEFAULT '',
                query TEXT DEFAULT '',
                created_at TEXT NOT NULL
            );
            CREATE UNIQUE INDEX IF NOT EXISTS saved_canonical ON saved(canonical);
            CREATE TABLE IF NOT EXISTS hunt_docs (
                hunt_id INTEGER NOT NULL,
                canonical TEXT NOT NULL,
                hash TEXT,
                excerpt TEXT,
                updated_at TEXT,
                PRIMARY KEY (hunt_id, canonical)
            );
            CREATE TABLE IF NOT EXISTS runs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                query TEXT, lens TEXT, providers INTEGER, hits INTEGER,
                took_ms INTEGER, created_at TEXT
            );
            CREATE TABLE IF NOT EXISTS docs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                canonical TEXT NOT NULL UNIQUE,
                url TEXT NOT NULL,
                title TEXT,
                text TEXT,
                engine TEXT,
                chars INTEGER DEFAULT 0,
                created_at TEXT
            );
            CREATE VIRTUAL TABLE IF NOT EXISTS docs_fts USING fts5(
                title, text, content='docs', content_rowid='id',
                tokenize='porter unicode61'
            );
            CREATE TRIGGER IF NOT EXISTS docs_ai AFTER INSERT ON docs BEGIN
                INSERT INTO docs_fts(rowid, title, text) VALUES (new.id, new.title, new.text);
            END;
            CREATE TRIGGER IF NOT EXISTS docs_ad AFTER DELETE ON docs BEGIN
                INSERT INTO docs_fts(docs_fts, rowid, title, text)
                VALUES ('delete', old.id, old.title, old.text);
            END;
            CREATE TRIGGER IF NOT EXISTS docs_au AFTER UPDATE ON docs BEGIN
                INSERT INTO docs_fts(docs_fts, rowid, title, text)
                VALUES ('delete', old.id, old.title, old.text);
                INSERT INTO docs_fts(rowid, title, text) VALUES (new.id, new.title, new.text);
            END;
            """


def _ensure_schema(conn: sqlite3.Connection, force: bool = False) -> None:
    """Create tables when they are missing — the vault must survive a wipe.

    Users delete the data directory, containers start with an empty volume, and
    a long-lived process can outlive its own database file. Checking the schema
    on every connection costs one index lookup and removes a whole class of
    ``no such table`` failures.
    """
    if not force:
        row = conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='vault'").fetchone()
        if row is not None:
            return
    conn.executescript(_SCHEMA)
    _ensure_columns(conn)


def init() -> None:
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    with db() as conn:
        _ensure_schema(conn, force=True)


def _ensure_columns(conn: sqlite3.Connection | None = None) -> None:
    """Small in-place migrations; the vault must survive upgrades."""
    wanted = {"docs": {"hash": "TEXT"}, "vault": {"rich": "INTEGER NOT NULL DEFAULT 0"}}

    def migrate(target: sqlite3.Connection) -> None:
        for table, columns in wanted.items():
            existing = {row[1] for row in target.execute(f"PRAGMA table_info({table})")}
            for column, kind in columns.items():
                if column not in existing:
                    target.execute(f"ALTER TABLE {table} ADD COLUMN {column} {kind}")

    if conn is not None:
        migrate(conn)
        return
    with db() as fresh:
        migrate(fresh)


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _terms(text: str) -> list[str]:
    return [t for t in re.split(r"[^a-z0-9]+", (text or "").lower()) if len(t) > 1 and t not in STOP]


RICH_FIELDS = ("funder", "amount", "currency", "location", "structured", "schema_type",
               "size", "sniffed", "mime", "keyphrases", "near_dupes", "published_at",
               "first_seen", "age_source", "language", "quality")


def _payload_of(hit) -> dict:
    payload = {"tags": getattr(hit, "tags", []), "published": getattr(hit, "published", None),
               "archive": getattr(hit, "archive", False),
               "meta": getattr(hit, "meta", {}) or {},
               **{key: getattr(hit, key, None) for key in RICH_FIELDS}}
    if getattr(hit, "age_source", None) != "published":
        # never launder "we just discovered it" into "it was published now"
        payload["published_at"] = None
    return payload


def payload_richness(payload: dict) -> int:
    """Rank records by how much *specific* detail they carry.

    A hunt re-surfaces the same URL through weaker engines (full-text snippet,
    portal link). Those must never overwrite the crawl's structured record.
    """
    score = 0
    for key in ("funder", "amount", "currency", "location", "structured", "schema_type"):
        if payload.get(key):
            score += 2
    if payload.get("size"):
        score += 1
    if payload.get("keyphrases"):
        score += 1
    if payload.get("tags"):
        score += 1
    return score


def upsert_hits(hits: Iterable) -> int:
    """Persist every surfaced hit into the local vault (dedupe by canonical URL)."""
    from .extract import canonical_url

    added = 0
    stamp = now()
    with _lock, db() as conn:
        for h in hits:
            try:
                canon = canonical_url(h.url)
                payload = json.dumps(_payload_of(h), default=str)
                richness = payload_richness(_payload_of(h))
                cur = conn.execute(
                    """INSERT INTO vault (url, canonical, title, snippet, provider, kind, file_ext,
                                          domain, deadline, depth, first_seen, last_seen, times_seen,
                                          payload, rich)
                       VALUES (?,?,?,?,?,?,?,?,?,?,?,?,1,?,?)
                       ON CONFLICT(canonical) DO UPDATE SET
                         last_seen=excluded.last_seen,
                         times_seen=vault.times_seen+1,
                         title=CASE WHEN excluded.rich > vault.rich THEN excluded.title
                                    ELSE vault.title END,
                         snippet=CASE WHEN excluded.rich > vault.rich
                                        OR length(excluded.snippet) > length(vault.snippet)
                                      THEN excluded.snippet ELSE vault.snippet END,
                         deadline=CASE WHEN excluded.rich > vault.rich THEN excluded.deadline
                                       ELSE COALESCE(vault.deadline, excluded.deadline) END,
                         kind=CASE WHEN excluded.rich > vault.rich THEN excluded.kind
                                   ELSE vault.kind END,
                         file_ext=COALESCE(vault.file_ext, excluded.file_ext),
                         payload=CASE WHEN excluded.rich >= vault.rich THEN excluded.payload
                                      ELSE vault.payload END,
                         rich=MAX(vault.rich, excluded.rich),
                         depth=MAX(vault.depth, excluded.depth)""",
                    (h.url, canon, h.title, h.snippet, h.provider, h.kind, h.file_ext,
                     h.domain, h.deadline.date if getattr(h, "deadline", None) else None,
                     int(getattr(h, "depth", 0)), stamp, stamp, payload, richness),
                )
                added += cur.rowcount
            except sqlite3.Error:
                continue
    return added


def _payload_meta(payload: str | None) -> dict:
    """Structured fields stored with a vault row, flattened for re-hydration."""
    try:
        data = json.loads(payload or "{}")
    except (ValueError, AttributeError):
        return {}
    if not isinstance(data, dict):
        return {}
    out = dict(data.get("meta") or {})
    for key in ("funder", "amount", "currency", "location", "structured", "size",
                "schema_type", "sniffed", "mime", "keyphrases", "near_dupes",
                "published_at", "first_seen", "age_source", "language", "quality"):
        if data.get(key):
            out[key] = data[key]
    return out


def index_document(canonical: str, url: str, title: str, text: str, engine: str) -> bool:
    """Store extracted full text so the vault becomes searchable from the inside."""
    text = (text or "").strip()
    if len(text) < 40:
        return False
    with _lock, db() as conn:
        try:
            conn.execute(
                """INSERT INTO docs (canonical, url, title, text, engine, chars, created_at)
                   VALUES (?,?,?,?,?,?,?)
                   ON CONFLICT(canonical) DO UPDATE SET
                     text=CASE WHEN length(excluded.text) > length(docs.text)
                               THEN excluded.text ELSE docs.text END,
                     chars=MAX(docs.chars, excluded.chars),
                     engine=excluded.engine""",
                (canonical, url, title, text[:400_000], engine, len(text), now()))
            return True
        except sqlite3.Error:
            return False


def _match_plan(terms: list[str]) -> str:
    """One broad OR query; term coverage is applied as a ranking pass instead.

    A raw OR lets "grant" or "kenya" dominate bm25 and bury the page that matches
    every word; a raw AND throws away good partial matches. So: retrieve broad,
    then rank by how many query terms each row actually covers.
    """
    return " OR ".join(f'"{t}"' for t in terms[:12])


def _coverage(text: str, terms: list[str]) -> float:
    haystack = (text or "").lower()
    if not terms:
        return 0.0
    return sum(1 for term in terms if term in haystack) / len(terms)


def _order_by_coverage(rows: list, terms: list[str], text_of, limit: int) -> list:
    """Full-coverage rows first, then partial, each group in bm25 order."""
    if not rows:
        return rows
    scored = [(row, _coverage(text_of(row), terms)) for row in rows]
    best = max(cov for _, cov in scored)
    if best >= 1.0:
        keep = [(row, cov) for row, cov in scored if cov >= 1.0]
    elif best >= 0.5:
        keep = [(row, cov) for row, cov in scored if cov >= 0.5]
    else:
        keep = scored
    if len(keep) < min(3, limit):
        keep = scored
    keep.sort(key=lambda pair: -pair[1])          # stable: bm25 order preserved
    return [row for row, _ in keep[:limit]]


def search_docs(query: str, limit: int = 40) -> list[dict]:
    """Full-text search inside extracted documents, enriched from the vault.

    The LEFT JOIN matters: a PDF found by the crawler has a rich vault record
    (funder, amount, schema type). Hydrating those fields here means the
    full-text engine returns complete records, not bare snippets.
    """
    terms = _terms(query)
    if not terms:
        return []
    out: list[dict] = []
    try:
        with db() as conn:
            rows = conn.execute(
                """SELECT d.url, d.title, d.engine, d.chars, bm25(docs_fts) AS rank,
                          snippet(docs_fts, 1, '[', ']', ' … ', 24) AS frag,
                          v.payload AS payload
                   FROM docs_fts
                   JOIN docs d ON d.id = docs_fts.rowid
                   LEFT JOIN vault v ON v.canonical = d.canonical
                   WHERE docs_fts MATCH ? ORDER BY rank LIMIT ?""",
                (_match_plan(terms), max(limit * 3, 40))).fetchall()
            rows = _order_by_coverage(
                rows, terms,
                lambda row: f"{row['title']} {row['frag']} {row['url']}", limit)
            for row in rows:
                out.append({
                    "url": row["url"], "title": row["title"] or row["url"],
                    "snippet": row["frag"], "engine": row["engine"], "chars": row["chars"],
                    "score": round(-row["rank"] * 10, 3),
                    "meta": _payload_meta(row["payload"]),
                })
    except sqlite3.Error:
        return []
    return out


def search_vault(query: str, limit: int = 40, file_ext: str | None = None) -> list[dict]:
    terms = _terms(query)
    if not terms:
        return []
    sql = ("SELECT v.*, bm25(vault_fts) AS rank FROM vault_fts "
           "JOIN vault v ON v.id = vault_fts.rowid WHERE vault_fts MATCH ?")
    if file_ext:
        sql += " AND v.file_ext = ?"
    sql += " ORDER BY rank LIMIT ?"
    out: list[dict] = []
    try:
        with db() as conn:
            params: list = [_match_plan(terms)]
            if file_ext:
                params.append(file_ext)
            params.append(max(limit * 3, 60))
            rows = conn.execute(sql, params).fetchall()
            rows = _order_by_coverage(
                rows, terms,
                lambda row: f"{row['title']} {row['snippet']} {row['url']}", limit)
            for row in rows:
                out.append({
                    "url": row["url"], "title": row["title"], "snippet": row["snippet"] or "",
                    "provider": row["provider"] or "vault", "provider_name": "Nighthawk Vault",
                    "kind": row["kind"] or "page", "file_ext": row["file_ext"],
                    "domain": row["domain"] or "", "depth": row["depth"] or 0,
                    "deadline": row["deadline"], "score": round(-row["rank"] * 10, 2),
                    "first_seen": row["first_seen"], "times_seen": row["times_seen"],
                    "meta": _payload_meta(row["payload"]),
                })
    except sqlite3.Error:
        return []
    return out


# ------------------------------------------------------------------ BM25 fusion

class _BM25:
    """Thin wrapper around rank_bm25 with a graceful fallback."""

    def __init__(self) -> None:
        self._corpus: list[list[str]] = []
        self._bm25 = None
        self._dirty = True
        self._lock = threading.Lock()
        self.available = True
        try:
            import rank_bm25  # noqa: F401
        except Exception:
            self.available = False

    def score(self, query: str, docs: list[str]) -> list[float]:
        if not self.available or not docs:
            return [0.0] * len(docs)
        try:
            from rank_bm25 import BM25Okapi

            tokenized = [_terms(d) for d in docs]
            if not any(tokenized):
                return [0.0] * len(docs)
            bm25 = BM25Okapi(tokenized)
            q = _terms(query) or ["_"]
            raw = bm25.get_scores(q)
            top = max(raw) if len(raw) else 0.0
            if top <= 0:
                return [0.0] * len(docs)
            return [float(s / top) for s in raw]
        except Exception:
            return [0.0] * len(docs)


_bm25 = _BM25()


def bm25_scores(query: str, docs: list[str]) -> list[float]:
    return _bm25.score(query, docs)


# --------------------------------------------------------------------- Whoosh

_whoosh_ok: bool | None = None
_whoosh_lock = threading.Lock()


def whoosh_scores(query: str, docs: list[str]) -> list[float]:
    """Ram-index the candidate set with Whoosh and return normalised BM25F scores."""
    global _whoosh_ok
    if _whoosh_ok is False or not docs:
        return [0.0] * len(docs)
    try:
        from whoosh import index
        from whoosh.analysis import StemmingAnalyzer
        from whoosh.fields import ID, TEXT, Schema
        from whoosh.qparser import MultifieldParser
        from whoosh.scoring import BM25F

        schema = Schema(key=ID(stored=True, unique=True), title=TEXT(analyzer=StemmingAnalyzer()),
                        body=TEXT(analyzer=StemmingAnalyzer()))
        with _whoosh_lock:
            import tempfile
            with tempfile.TemporaryDirectory() as tmp:
                ix = index.create_in(tmp, schema)
                writer = ix.writer()
                for i, doc in enumerate(docs):
                    text = doc or ""
                    writer.add_document(key=str(i), title=text[:180], body=text)
                writer.commit()
                out = [0.0] * len(docs)
                with ix.searcher(weighting=BM25F()) as searcher:
                    parser = MultifieldParser(["title", "body"], schema=ix.schema)
                    q = parser.parse(query or "*")
                    for hit in searcher.search(q, limit=len(docs)):
                        out[int(hit["key"])] = float(hit.score)
                top = max(out) if out else 0.0
                _whoosh_ok = True
                return [s / top if top > 0 else 0.0 for s in out]
    except Exception:
        _whoosh_ok = False
        return [0.0] * len(docs)


# -------------------------------------------------------------------- Tantivy

_tantivy_idx = None
_tantivy_ok: bool | None = None


def tantivy_add(hits: Iterable) -> None:
    """Mirror the vault into a Tantivy index for fast offline retrieval."""
    global _tantivy_idx, _tantivy_ok
    if _tantivy_ok is False:
        return
    try:
        import tantivy

        if _tantivy_idx is None:
            _tantivy_dir.mkdir(parents=True, exist_ok=True)
            builder = tantivy.SchemaBuilder()
            builder.add_text_field("url", stored=True)
            builder.add_text_field("title", stored=True, tokenizer_name="en_stem")
            builder.add_text_field("body", stored=True, tokenizer_name="en_stem")
            builder.add_text_field("provider", stored=True)
            schema = builder.build()
            _tantivy_idx = (tantivy.Index(schema, path=str(_tantivy_dir)), schema)
        idx, schema = _tantivy_idx
        writer = idx.writer()
        for h in hits:
            writer.add_document(tantivy.Document(
                url=getattr(h, "url", ""), title=getattr(h, "title", ""),
                body=getattr(h, "snippet", "") or "", provider=getattr(h, "provider", ""),
            ))
        writer.commit()
        idx.reload()
        _tantivy_ok = True
    except Exception:
        _tantivy_ok = False


def tantivy_search(query: str, limit: int = 40) -> list[dict]:
    global _tantivy_idx
    if _tantivy_ok is False or _tantivy_idx is None:
        return []
    try:
        idx, _ = _tantivy_idx
        idx.reload()
        searcher = idx.searcher()
        parsed = idx.parse_query(query, ["title", "body"])
        hits = searcher.search(parsed, limit)
        out = []
        for score, addr in hits.hits:
            doc = searcher.doc(addr)
            out.append({
                "url": doc.get_first("url"), "title": doc.get_first("title"),
                "snippet": doc.get_first("body"), "provider": doc.get_first("provider"),
                "score": round(float(score), 3),
            })
        return out
    except Exception:
        return []


def doc_text(canonical: str, limit: int = 200_000) -> str | None:
    try:
        with db() as conn:
            row = conn.execute("SELECT text FROM docs WHERE canonical = ?", (canonical,)).fetchone()
        return (row["text"] or "")[:limit] if row else None
    except sqlite3.Error:
        return None


def store_hunt_doc(hunt_id: int, canonical: str, hash_value: str, excerpt: str) -> None:
    with db() as conn:
        conn.execute(
            """INSERT INTO hunt_docs (hunt_id, canonical, hash, excerpt, updated_at)
               VALUES (?,?,?,?,?)
               ON CONFLICT(hunt_id, canonical) DO UPDATE SET
                 hash = excluded.hash, excerpt = excluded.excerpt,
                 updated_at = excluded.updated_at""",
            (hunt_id, canonical, hash_value, excerpt[:6000], now()))


def prior_hunt_doc(hunt_id: int, canonical: str) -> dict | None:
    with db() as conn:
        row = conn.execute(
            "SELECT hash, excerpt FROM hunt_docs WHERE hunt_id = ? AND canonical = ?",
            (hunt_id, canonical)).fetchone()
    return dict(row) if row else None


def vault_stats() -> dict:
    try:
        with db() as conn:
            total = conn.execute("SELECT COUNT(*) c FROM vault").fetchone()["c"]
            files = conn.execute("SELECT COUNT(*) c FROM vault WHERE file_ext IS NOT NULL").fetchone()["c"]
            domains = conn.execute("SELECT COUNT(DISTINCT domain) c FROM vault").fetchone()["c"]
            hunts = conn.execute("SELECT COUNT(*) c FROM hunts").fetchone()["c"]
            saved = conn.execute("SELECT COUNT(*) c FROM saved").fetchone()["c"]
        return {"documents": total, "files": files, "domains": domains, "hunts": hunts, "saved": saved}
    except sqlite3.Error:
        return {"documents": 0, "files": 0, "domains": 0, "hunts": 0, "saved": 0}
