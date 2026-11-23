"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { api } from "@/lib/api";
import { fileIcon } from "@/lib/format";

type MetaRow = { url: string; title: string; snippet: string; provider: string; file_ext: string | null; depth: number; deadline: string | null; times_seen?: number };
type DocRow = { url: string; title: string; snippet: string; engine: string; chars: number };
type Stats = { documents: number; files: number; domains: number; hunts: number; saved: number };

export default function VaultPage() {
  const [q, setQ] = useState("");
  const [mode, setMode] = useState<"both" | "meta" | "fulltext">("both");
  const [meta, setMeta] = useState<MetaRow[]>([]);
  const [docs, setDocs] = useState<DocRow[]>([]);
  const [stats, setStats] = useState<Stats | null>(null);
  const [busy, setBusy] = useState(false);

  const search = useCallback(async (query: string, searchMode: "both" | "meta" | "fulltext") => {
    setBusy(true);
    try {
      const data = await api<{ meta: MetaRow[]; fulltext: DocRow[]; stats: Stats }>(
        `/api/v1/vault?q=${encodeURIComponent(query)}&mode=${searchMode}&limit=40`,
      );
      setMeta(data.meta);
      setDocs(data.fulltext);
      setStats(data.stats);
    } finally {
      setBusy(false);
    }
  }, []);

  useEffect(() => { search("", "both").catch(() => undefined); }, [search]);

  return (
    <main className="wrap" style={{ paddingTop: 26 }}>
      <div className="section-head" style={{ marginBottom: 10 }}>
        <h1 style={{ fontSize: 30, margin: 0, letterSpacing: "-0.03em" }}>The vault</h1>
        <span className="rule" />
        <span className="tiny">sqlite fts5 · whoosh · tantivy</span>
      </div>
      <p className="lede" style={{ maxWidth: 820 }}>
        Everything the crawler and the engines have ever touched is mirrored here — URLs, metadata
        and the extracted full text of every PDF, spreadsheet and archive. It works with the network
        unplugged.
      </p>

      <div className="stats-grid" style={{ marginTop: 18 }}>
        <div className="stat"><div className="n lime">{stats?.documents ?? 0}</div><div className="l">documents</div></div>
        <div className="stat"><div className="n cyan">{stats?.files ?? 0}</div><div className="l">files</div></div>
        <div className="stat"><div className="n">{stats?.domains ?? 0}</div><div className="l">domains</div></div>
        <div className="stat"><div className="n amber">{stats?.hunts ?? 0}</div><div className="l">watchers</div></div>
        <div className="stat"><div className="n">{stats?.saved ?? 0}</div><div className="l">saved items</div></div>
      </div>

      <div className="search-panel" style={{ marginTop: 18 }}>
        <div className="search-row">
          <div className="search-input-wrap">
            <span className="glyph">⌕</span>
            <input className="search-input" value={q} onChange={(e) => setQ(e.target.value)}
              onKeyDown={(e) => { if (e.key === "Enter") search(q, mode); }}
              placeholder="search inside every file the crawler has read" />
          </div>
          <select className="chip" style={{ padding: "10px 12px" }} value={mode}
            onChange={(e) => setMode(e.target.value as typeof mode)}>
            <option value="both">metadata + full text</option>
            <option value="fulltext">full text only</option>
            <option value="meta">metadata only</option>
          </select>
          <button className="btn btn-primary" onClick={() => search(q, mode)} disabled={busy}>
            {busy ? <span className="spin" /> : "Search"}
          </button>
        </div>
      </div>

      {(docs.length > 0 || meta.length > 0) && (
        <p className="tiny" style={{ marginTop: 18 }}>
          {docs.length} deep matches · {meta.length} metadata matches
          {q && <> for “{q}”</>}
        </p>
      )}

      {docs.length > 0 && (
        <>
          <div className="section-head" style={{ marginTop: 8 }}>
            <h2 style={{ fontSize: 16 }}>Inside the documents</h2><span className="rule" />
          </div>
          {docs.map((row) => (
            <a className="result" key={row.url + row.snippet.slice(0, 20)} href={row.url} target="_blank" rel="noreferrer"
              style={{ display: "block" }}>
              <div className="result-top">
                <span className="result-icon">▤</span>
                <div className="result-main">
                  <div className="result-title">{row.title}</div>
                  <div className="result-url">{row.url}</div>
                  <p className="result-snip" dangerouslySetInnerHTML={{
                    __html: row.snippet.replace(/\[([^\]]+)\]/g, "<mark>$1</mark>"),
                  }} />
                  <div className="result-meta">
                    <span className="pill cyan">{row.engine}</span>
                    <span className="pill">{row.chars.toLocaleString()} chars</span>
                  </div>
                </div>
              </div>
            </a>
          ))}
        </>
      )}

      {meta.length > 0 && (
        <>
          <div className="section-head" style={{ marginTop: 22 }}>
            <h2 style={{ fontSize: 16 }}>Metadata index</h2><span className="rule" />
          </div>
          {meta.map((row) => (
            <a className="file-row" key={row.url} href={row.url} target="_blank" rel="noreferrer">
              <span className="file-ext">{row.file_ext ?? fileIcon(row.file_ext) ?? "url"}</span>
              <span style={{ minWidth: 0, flex: 1 }}>
                <span className="file-name" style={{ display: "block" }}>{row.title}</span>
                <span className="file-sub" style={{ display: "block" }}>
                  {row.provider} · depth {row.depth}{row.deadline ? ` · ${row.deadline}` : ""} · {row.snippet.slice(0, 90)}
                </span>
              </span>
            </a>
          ))}
        </>
      )}

      {!busy && docs.length === 0 && meta.length === 0 && (
        <div className="empty">
          {q ? <>No local matches for “{q}”.</> : <>The vault is empty.</>}
          <div style={{ marginTop: 12 }}>
            <Link className="btn btn-primary" href="/crawl">Run the practice crawl</Link>
          </div>
          <p className="tiny" style={{ marginTop: 14 }}>
            The demo target gives you PDFs, a CSV, JSON, a ZIP and a robots-disallowed page to chew on.
          </p>
        </div>
      )}
    </main>
  );
}
