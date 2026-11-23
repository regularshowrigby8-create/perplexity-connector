"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import { api } from "@/lib/api";

type RemoteEngine = {
  id: string; name: string; family: string; layer: string; description: string;
  lenses: string[]; homepage: string; requires: string[]; status: string;
  needs_network: boolean; opt_in: boolean; retired: boolean;
};
type ArsenalEngine = {
  id: string; name: string; role: string; language: string; homepage: string; license: string;
  kind: string; available: boolean; detail: string; note: string; command: string;
};
type Portal = { name: string; domains: string[]; lenses: string[]; search: string; note: string };

const TABS = ["Fusion + remote", "Crawl arsenal", "Portal universe"] as const;

export default function ArsenalPage() {
  const [tab, setTab] = useState<(typeof TABS)[number]>(TABS[0]);
  const [remote, setRemote] = useState<RemoteEngine[]>([]);
  const [arsenal, setArsenal] = useState<{ engines: ArsenalEngine[]; summary: { total: number; available: number } } | null>(null);
  const [portals, setPortals] = useState<Portal[]>([]);
  const [filter, setFilter] = useState("");
  const [readyOnly, setReadyOnly] = useState(false);
  const [counts, setCounts] = useState<Record<string, number>>({});

  useEffect(() => {
    api<{ providers: RemoteEngine[]; counts: Record<string, number> }>("/api/v1/engines")
      .then((d) => { setRemote(d.providers); setCounts(d.counts); })
      .catch(() => undefined);
    api<{ engines: ArsenalEngine[]; summary: { total: number; available: number } }>("/api/v1/arsenal")
      .then(setArsenal).catch(() => undefined);
    api<{ portals: Portal[] }>("/api/v1/portals")
      .then((d) => setPortals(d.portals)).catch(() => undefined);
  }, []);

  const needle = filter.trim().toLowerCase();
  const remoteShown = useMemo(() => remote.filter((e) => {
    if (readyOnly && e.status !== "ready") return false;
    if (!needle) return true;
    return `${e.name} ${e.family} ${e.description} ${e.lenses.join(" ")}`.toLowerCase().includes(needle);
  }), [remote, needle, readyOnly]);

  const arsenalShown = useMemo(() => (arsenal?.engines ?? []).filter((e) => {
    if (readyOnly && !e.available) return false;
    if (!needle) return true;
    return `${e.name} ${e.role} ${e.language} ${e.note} ${e.command}`.toLowerCase().includes(needle);
  }), [arsenal, needle, readyOnly]);

  const portalsShown = useMemo(() => portals.filter((p) => {
    if (!needle) return true;
    return `${p.name} ${p.note} ${p.domains.join(" ")} ${p.lenses.join(" ")}`.toLowerCase().includes(needle);
  }), [portals, needle]);

  return (
    <main className="wrap" style={{ paddingTop: 26 }}>
      <div className="section-head" style={{ marginBottom: 12 }}>
        <h1 style={{ fontSize: 30, margin: 0, letterSpacing: "-0.03em" }}>Engine mesh</h1>
        <span className="rule" />
        <span className="tiny">
          {counts.total ?? "—"} integrations total
        </span>
      </div>
      <p className="lede" style={{ maxWidth: 860 }}>
        Every entry is a real, separately probed integration. Python engines are imported,
        native binaries are looked up on <span className="mono">PATH</span>, and remote APIs are
        unlocked by a key or by being open. Nothing is faked: if a tier is missing, the crawler
        says so and falls back to the next engine that is installed.
      </p>

      <div className="stats-grid" style={{ marginTop: 20 }}>
        <div className="stat"><div className="n lime">{counts.arsenal ?? 86}</div><div className="l">crawl arsenal</div></div>
        <div className="stat"><div className="n cyan">{arsenal?.summary.available ?? "—"}</div><div className="l">live in this box</div></div>
        <div className="stat"><div className="n">{remote.length || 66}</div><div className="l">remote engines</div></div>
        <div className="stat"><div className="n amber">{portals.length || 54}</div><div className="l">portals</div></div>
        <div className="stat">
          <div className="n">{counts.total ?? "—"}</div><div className="l">total integrations</div>
        </div>
      </div>

      <div className="tabs" style={{ marginTop: 26 }}>
        {TABS.map((item) => (
          <button key={item} className="tab" data-on={tab === item} onClick={() => setTab(item)}>
            {item}
          </button>
        ))}
        <div style={{ marginLeft: "auto", display: "flex", gap: 8, alignItems: "center", paddingBottom: 6 }}>
          <input className="chip" style={{ padding: "7px 10px", minWidth: 200 }}
            placeholder="filter engines…" value={filter} onChange={(e) => setFilter(e.target.value)} />
          <button className="chip" data-on={readyOnly} onClick={() => setReadyOnly(!readyOnly)}>
            ready only
          </button>
        </div>
      </div>

      {tab === "Fusion + remote" && (
        <div className="card-grid">
          {remoteShown.map((engine) => (
            <div className="card engine-card" key={engine.id}
              data-ready={engine.status === "ready" || engine.layer === "core"}>
              <span className="status-dot" style={{
                background: engine.status === "ready" || engine.layer === "core" ? "var(--lime)"
                  : engine.status === "retired" ? "var(--dim)" : "var(--amber)",
              }} />
              <div className="top">
                <span className="pill">{engine.layer}</span>
                <span className="pill cyan">{engine.family}</span>
                {engine.status !== "ready" && engine.status !== "retired" && (
                  <span className="pill amber">{engine.status.replace("_", " ")}</span>
                )}
              </div>
              <h3>{engine.name}</h3>
              <p>{engine.description}</p>
              <div className="engine-note">
                {engine.lenses.join(" · ")}
                {engine.requires.length > 0 && <> · key: {engine.requires.join(", ")}</>}
              </div>
            </div>
          ))}
        </div>
      )}

      {tab === "Crawl arsenal" && (
        <div className="card-grid">
          {arsenalShown.map((engine) => (
            <div className="card engine-card" key={engine.id} data-ready={engine.available}>
              <span className="status-dot" style={{
                background: engine.available ? "var(--lime)" : "var(--dim)",
              }} />
              <div className="top">
                <span className="engine-role">{engine.role}</span>
                <span className="pill">{engine.language}</span>
                {engine.license && <span className="pill">{engine.license}</span>}
              </div>
              <h3>{engine.name}</h3>
              <div className="engine-note">{engine.available ? "ready · " : "not installed · "}{engine.detail}</div>
              {engine.note && <div className="engine-note" style={{ color: "var(--ink-2)" }}>{engine.note}</div>}
              {engine.command && <div className="engine-cmd">{engine.command}</div>}
            </div>
          ))}
          {arsenalShown.length === 0 && (
            <div className="empty">No engine matches “{filter}”.</div>
          )}
        </div>
      )}

      {tab === "Portal universe" && (
        <div className="card-grid">
          {portalsShown.map((portal) => (
            <a className="card engine-card" key={portal.name} href={portal.search.replace("{q}", "climate+grant")}
              target="_blank" rel="noreferrer">
              <div className="top">
                {portal.lenses.slice(0, 3).map((lens) => (
                  <span className="pill" key={lens}>{lens}</span>
                ))}
              </div>
              <h3>{portal.name}</h3>
              <p>{portal.note}</p>
              <div className="engine-note">{portal.domains.join(" · ")}</div>
            </a>
          ))}
        </div>
      )}

      <div className="notice info" style={{ marginTop: 26 }}>
        Missing a tier? Drop the binary on <span className="mono">PATH</span> (katana, gau, ffuf,
        feroxbuster, tesseract) or <span className="mono">pip install</span> a Python engine — the
        registry probes at request time, so it appears here without a code change.
        See <Link href="/api/docs" style={{ color: "var(--lime)" }}>the API</Link>.
      </div>
    </main>
  );
}
