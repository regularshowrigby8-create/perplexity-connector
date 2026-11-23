"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { SearchPanel } from "@/components/search-panel";
import { api } from "@/lib/api";

type Health = {
  engines_remote: number;
  engines_arsenal: number;
  arsenal_ready: number;
  portals: number;
  vault: { documents: number; files: number; domains: number };
};

const SAMPLES = [
  "climate grants for coastal towns in Kenya",
  "tender solar mini-grid procurement 2026",
  "call for proposals youth food security",
  "index of files backup sql",
  "scholarships for women in data science",
  "open data electricity access csv",
];

const LAYERS = [
  { name: "Fusion crawler", role: "primary", desc: "Own frontier, own fetch, no ceilings.", tone: "lime" },
  { name: "Archive indexes", role: "buried", desc: "Common Crawl + Wayback CDX, straight.", tone: "violet" },
  { name: "Opportunity APIs", role: "structured", desc: "Grants.gov, ReliefWeb, EU SEDIA.", tone: "amber" },
  { name: "Scholarly mesh", role: "documents", desc: "OpenAlex, arXiv, DOAJ, PubMed.", tone: "cyan" },
];

export default function HomePage() {
  const [health, setHealth] = useState<Health | null>(null);

  useEffect(() => {
    api<Health>("/api/v1/health").then(setHealth).catch(() => undefined);
  }, []);

  return (
    <main>
      <section className="hero">
        <div className="wrap hero-in">
          <span className="eyebrow">
            <span className="dot" />
            86-engine crawl arsenal · {(health?.engines_remote ?? 66) + 1} remote engines · zero keys
          </span>
          <h1 className="title">
            Find what search<br />
            <span className="grad">engines bury.</span>
          </h1>
          <p className="lede">
            Nighthawk is a <b>fusion crawler</b> that walks the web itself, reads raw crawl archives,
            and queries every structured engine it can reach — then extracts, indexes and ranks the
            <b> hosted files, open calls and portals</b> that a normal results page never shows you.
          </p>

          <SearchPanel />

          <div style={{ display: "flex", gap: 8, flexWrap: "wrap", marginTop: 14 }}>
            <span className="tiny" style={{ alignSelf: "center" }}>try:</span>
            {SAMPLES.map((sample) => (
              <Link key={sample} className="pill" href={`/hunt?q=${encodeURIComponent(sample)}`}>
                {sample}
              </Link>
            ))}
          </div>
        </div>
      </section>

      <section className="wrap section">
        <div className="stats-grid">
          <div className="stat"><div className="n lime">{health?.engines_arsenal ?? 86}</div><div className="l">arsenal engines</div></div>
          <div className="stat"><div className="n cyan">{health?.arsenal_ready ?? "—"}</div><div className="l">live in this box</div></div>
          <div className="stat"><div className="n">{(health?.engines_remote ?? 66) + 1}</div><div className="l">remote engines</div></div>
          <div className="stat"><div className="n amber">{health?.portals ?? 54}</div><div className="l">hand-picked portals</div></div>
          <div className="stat"><div className="n">{health?.vault.files ?? 0}</div><div className="l">files in vault</div></div>
          <div className="stat"><div className="n">{health?.vault.domains ?? 0}</div><div className="l">domains mapped</div></div>
        </div>
      </section>

      <section className="wrap section" style={{ paddingTop: 6 }}>
        <div className="section-head">
          <h2>Four layers, one ranked stream</h2>
          <span className="rule" />
          <Link className="tiny" href="/arsenal">inspect every engine →</Link>
        </div>
        <div className="card-grid">
          {LAYERS.map((layer) => (
            <div className="card" key={layer.name}>
              <div className="top">
                <span className={`pill ${layer.tone}`}>{layer.role}</span>
              </div>
              <h3>{layer.name}</h3>
              <p>{layer.desc}</p>
            </div>
          ))}
        </div>
      </section>

      <section className="wrap section" style={{ paddingTop: 6 }}>
        <div className="section-head">
          <h2>Two ways in</h2>
          <span className="rule" />
        </div>
        <div className="card-grid">
          <Link href="/hunt?q=climate%20grants%20africa&lens=opportunities" className="card">
            <div className="top"><span className="pill lime">federated</span></div>
            <h3>Hunt across everything</h3>
            <p>
              One query fans out to every reachable engine, fuses the results with reciprocal-rank
              fusion, extracts deadlines, and dedupes by canonical URL. Use it when you want breadth.
            </p>
          </Link>
          <Link href="/crawl" className="card">
            <div className="top"><span className="pill cyan">unrestricted</span></div>
            <h3>Point the crawler at a target</h3>
            <p>
              Give it a domain or a query. It harvests seeds from SERPs, sitemaps and archives,
              walks the frontier, opens PDFs, spreadsheets and dumps, and indexes their full text.
            </p>
          </Link>
          <Link href="/vault" className="card">
            <div className="top"><span className="pill violet">local</span></div>
            <h3>Search what you found</h3>
            <p>
              Every file Nighthawk touches lands in the vault — SQLite FTS5, Whoosh and Tantivy
              merged into one local index. Search inside the documents, not just their titles.
            </p>
          </Link>
        </div>
      </section>

      <section className="wrap section" style={{ paddingTop: 0 }}>
        <div className="notice info">
          No API keys required. The crawler respects <span className="mono">robots.txt</span> by default
          and you can turn that off for targets you own. Everything it finds stays on this machine.
        </div>
      </section>
    </main>
  );
}
