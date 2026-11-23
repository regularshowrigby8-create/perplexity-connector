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
        yield conn
        conn.commit()
    finally:
        conn.close()


def init() -> None:
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    with db() as conn:
        conn.executescript(
            """
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
            CREATE TABLE IF NOT EXISTS runs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                query TEXT, lens TEXT, providers INTEGER, hits INTEGER,
                took_ms INTEGER, created_at TEXT
            );
            """
        )


with db() as conn:
        conn.executescript(
            """
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
        )


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


def search_docs(query: str, limit: int = 40) -> list[dict]:
    terms = _terms(query)
    if not terms:
        return []
    match = " OR ".join(f'"{t}"' for t in terms[:12])
    out: list[dict] = []
    try:
        with db() as conn:
            rows = conn.execute(
                """SELECT d.url, d.title, d.engine, d.chars, bm25(docs_fts) AS rank,
                          snippet(docs_fts, 1, '[', ']', ' … ', 24) AS frag
                   FROM docs_fts JOIN docs d ON d.id = docs_fts.rowid
                   WHERE docs_fts MATCH ? ORDER BY rank LIMIT ?""", (match, limit))
            for row in rows:
                out.append({
                    "url": row["url"], "title": row["title"] or row["url"],
                    "snippet": row["frag"], "engine": row["engine"], "chars": row["chars"],
                    "score": round(-row["rank"] * 10, 3),
                })
    except sqlite3.Error:
        return []
    return out


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _terms(text: str) -> list[str]:
    return [t for t in re.split(r"[^a-z0-9]+", (text or "").lower()) if len(t) > 1 and t not in STOP]


def upsert_hits(hits: Iterable) -> int:
    """Persist every surfaced hit into the local vault (dedupe by canonical URL)."""
    from .extract import canonical_url

    added = 0
    stamp = now()
    with _lock, db() as conn:
        for h in hits:
            try:
                canon = canonical_url(h.url)
                payload = json.dumps(
                    {"tags": getattr(h, "tags", []), "published": getattr(h, "published", None),
                     "archive": getattr(h, "archive", False)}, default=str
                )
                cur = conn.execute(
                    """INSERT INTO vault (url, canonical, title, snippet, provider, kind, file_ext,
                                          domain, deadline, depth, first_seen, last_seen, times_seen, payload)
                       VALUES (?,?,?,?,?,?,?,?,?,?,?,?,1,?)
                       ON CONFLICT(canonical) DO UPDATE SET
                         last_seen=excluded.last_seen,
                         times_seen=vault.times_seen+1,
                         snippet=CASE WHEN length(excluded.snippet) > length(vault.snippet)
                                      THEN excluded.snippet ELSE vault.snippet END,
                         deadline=COALESCE(vault.deadline, excluded.deadline),
                         depth=MAX(vault.depth, excluded.depth)""",
                    (h.url, canon, h.title, h.snippet, h.provider, h.kind, h.file_ext,
                     h.domain, h.deadline.date if getattr(h, "deadline", None) else None,
                     int(getattr(h, "depth", 0)), stamp, stamp, payload),
                )
                added += cur.rowcount
            except sqlite3.Error:
                continue
    return added


def search_vault(query: str, limit: int = 40, file_ext: str | None = None) -> list[dict]:
    terms = _terms(query)
    if not terms:
        return []
    match = " OR ".join(f'"{t}"' for t in terms[:12])
    sql = ("SELECT v.*, bm25(vault_fts) AS rank FROM vault_fts "
           "JOIN vault v ON v.id = vault_fts.rowid WHERE vault_fts MATCH ?")
    params: list = [match]
    if file_ext:
        sql += " AND v.file_ext = ?"
        params.append(file_ext)
    sql += " ORDER BY rank LIMIT ?"
    params.append(limit)
    out: list[dict] = []
    try:
        with db() as conn:
            for row in conn.execute(sql, params):
                out.append({
                    "url": row["url"], "title": row["title"], "snippet": row["snippet"] or "",
                    "provider": row["provider"] or "vault", "provider_name": "Nighthawk Vault",
                    "kind": row["kind"] or "page", "file_ext": row["file_ext"],
                    "domain": row["domain"] or "", "depth": row["depth"] or 0,
                    "deadline": row["deadline"], "score": round(-row["rank"] * 10, 2),
                    "first_seen": row["first_seen"], "times_seen": row["times_seen"],
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
