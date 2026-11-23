"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { api, type Hit } from "@/lib/api";

type Hunt = {
  id: number; name: string; query: string; lens: string; site: string | null;
  created_at: string; last_run_at: string | null; last_count: number; seen?: number;
};

export default function HuntsPage() {
  const [hunts, setHunts] = useState<Hunt[]>([]);
  const [query, setQuery] = useState("");
  const [name, setName] = useState("");
  const [lens, setLens] = useState("all");
  const [busy, setBusy] = useState<number | null>(null);
  const [newItems, setNewItems] = useState<Record<number, Hit[]>>({});
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(() => {
    api<{ hunts: Hunt[] }>("/api/v1/hunts").then((d) => setHunts(d.hunts)).catch((e) => setError(e.message));
  }, []);

  useEffect(load, [load]);

  async function create() {
    if (!query.trim()) return;
    try {
      await api("/api/v1/hunts", {
        method: "POST",
        body: JSON.stringify({ query, name: name || query, lens }),
      });
      setQuery(""); setName("");
      load();
    } catch (err) {
      setError((err as Error).message);
    }
  }

  async function run(id: number) {
    setBusy(id);
    try {
      const data = await api<{ new: Hit[]; new_count: number }>(`/api/v1/hunts/${id}/run`, { method: "POST" });
      setNewItems((prev) => ({ ...prev, [id]: data.new }));
      load();
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(null);
    }
  }

  async function remove(id: number) {
    await api(`/api/v1/hunts/${id}`, { method: "DELETE" });
    load();
  }

  return (
    <main className="wrap" style={{ paddingTop: 26 }}>
      <div className="section-head" style={{ marginBottom: 10 }}>
        <h1 style={{ fontSize: 30, margin: 0, letterSpacing: "-0.03em" }}>Watchers</h1>
        <span className="rule" />
        <span className="tiny">diff every run</span>
      </div>
      <p className="lede" style={{ maxWidth: 800 }}>
        Save a hunt and run it whenever you like. Nighthawk keeps a canonical-URL ledger per
        watcher, so a run only reports what is genuinely new since last time — new calls, new PDFs,
        new listings.
      </p>

      <div className="search-panel" style={{ marginTop: 18 }}>
        <div className="advanced" style={{ borderTop: "none", paddingTop: 0 }}>
          <div className="field">
            <label>Query</label>
            <input value={query} onChange={(e) => setQuery(e.target.value)}
              placeholder="tender solar mini-grid 2026" />
          </div>
          <div className="field">
            <label>Name</label>
            <input value={name} onChange={(e) => setName(e.target.value)} placeholder="optional label" />
          </div>
          <div className="field">
            <label>Lens</label>
            <select value={lens} onChange={(e) => setLens(e.target.value)}>
              {["all", "opportunities", "files", "applications", "exposed", "datasets"].map((l) => (
                <option key={l} value={l}>{l}</option>
              ))}
            </select>
          </div>
        </div>
        <div className="search-row" style={{ marginTop: 12 }}>
          <button className="btn btn-primary" onClick={create} disabled={!query.trim()}>Create watcher</button>
          <Link className="btn btn-ghost" href="/hunt">Back to hunting</Link>
        </div>
      </div>

      {error && <div className="notice" style={{ marginTop: 12 }}>{error}</div>}

      <div className="section-head" style={{ marginTop: 26 }}>
        <h2 style={{ fontSize: 16 }}>Your watchers</h2><span className="rule" />
        <span className="tiny">{hunts.length}</span>
      </div>

      {hunts.length === 0 && (
        <div className="empty">No watchers yet. Save a query above and run it on a schedule.</div>
      )}

      {hunts.map((hunt) => (
        <div className="result" key={hunt.id}>
          <div className="result-top">
            <span className="result-icon">◎</span>
            <div className="result-main">
              <div className="result-title">{hunt.name}</div>
              <div className="result-url">
                {hunt.query} · {hunt.lens}{hunt.site ? ` · site:${hunt.site}` : ""} · created {hunt.created_at.slice(0, 10)}
              </div>
              <div className="result-meta">
                <span className="pill">{hunt.seen ?? 0} seen</span>
                {hunt.last_run_at && <span className="pill cyan">last run {hunt.last_run_at.slice(0, 16).replace("T", " ")}</span>}
                {hunt.last_count > 0 && <span className="pill lime">{hunt.last_count} hits</span>}
              </div>
              {(newItems[hunt.id]?.length ?? 0) > 0 && (
                <div style={{ marginTop: 10 }}>
                  <div className="tiny" style={{ color: "var(--lime)" }}>
                    {newItems[hunt.id].length} new since last run
                  </div>
                  {newItems[hunt.id].slice(0, 6).map((hit) => (
                    <a key={hit.url} href={hit.url} target="_blank" rel="noreferrer" className="file-row">
                      <span className="file-ext">{hit.file_ext ?? "url"}</span>
                      <span style={{ minWidth: 0, flex: 1 }}>
                        <span className="file-name" style={{ display: "block" }}>{hit.title}</span>
                        <span className="file-sub" style={{ display: "block" }}>{hit.domain} · depth {hit.depth}</span>
                      </span>
                    </a>
                  ))}
                </div>
              )}
            </div>
            <div style={{ display: "flex", gap: 6 }}>
              <button className="btn btn-sm" onClick={() => run(hunt.id)} disabled={busy === hunt.id}>
                {busy === hunt.id ? <span className="spin" style={{ borderTopColor: "var(--lime)" }} /> : "Run"}
              </button>
              <button className="btn btn-sm btn-ghost" onClick={() => remove(hunt.id)}>Delete</button>
            </div>
          </div>
        </div>
      ))}
    </main>
  );
}
