"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import { ALL_FILE_TYPES, LENSES } from "@/lib/format";
import type { Lens } from "@/lib/api";

type Props = {
  initialQuery?: string;
  initialLens?: Lens;
  compact?: boolean;
};

export function SearchPanel({ initialQuery = "", initialLens = "all", compact = false }: Props) {
  const router = useRouter();
  const [q, setQ] = useState(initialQuery);
  const [lens, setLens] = useState<Lens>(initialLens);
  const [site, setSite] = useState("");
  const [types, setTypes] = useState<string[]>([]);
  const [sort, setSort] = useState("relevance");
  const [adv, setAdv] = useState(false);
  const [busy, setBusy] = useState(false);

  function go(mode: "hunt" | "crawl") {
    if (!q.trim() || busy) return;
    setBusy(true);
    const params = new URLSearchParams({ q: q.trim(), lens });
    if (site.trim()) params.set("site", site.trim());
    if (types.length) params.set("types", types.join(","));
    if (sort !== "relevance") params.set("sort", sort);
    router.push(`/${mode}?${params.toString()}`);
  }

  return (
    <section className="search-panel">
      <div className="search-row">
        <div className="search-input-wrap">
          <span className="glyph">⌕</span>
          <input
            className="search-input"
            placeholder="climate grants for coastal towns in Kenya"
            value={q}
            onChange={(e) => setQ(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter") go("hunt");
            }}
            autoFocus={!compact}
            aria-label="Search query"
          />
          <span className="tiny" style={{ whiteSpace: "nowrap" }}>⏎ hunt</span>
        </div>
        <button className="btn btn-primary" onClick={() => go("hunt")} disabled={busy || !q.trim()}>
          {busy ? <span className="spin" /> : "Hunt"}
        </button>
        {!compact && (
          <button className="btn btn-ghost" onClick={() => go("crawl")} disabled={!q.trim()}
            title="Take the query straight into the crawler">
            Crawl instead
          </button>
        )}
      </div>

      <div className="lens-row">
        {LENSES.map((item) => (
          <button key={item.id} className="lens" data-on={lens === item.id}
            onClick={() => setLens(item.id as Lens)} title={item.hint}>
            {item.label}
          </button>
        ))}
        <button className="adv-toggle" onClick={() => setAdv(!adv)}>
          {adv ? "− filters" : "+ filters"}
        </button>
      </div>

      {adv && (
        <div className="advanced">
          <div className="field">
            <label>Limit to site</label>
            <input value={site} onChange={(e) => setSite(e.target.value)}
              placeholder="grants.gov (optional)" />
          </div>
          <div className="field">
            <label>Sort</label>
            <select value={sort} onChange={(e) => setSort(e.target.value)}>
              <option value="relevance">Relevance (fused RRF)</option>
              <option value="depth">Depth (most buried first)</option>
              <option value="deadline">Closing soonest</option>
              <option value="newest">Newest</option>
            </select>
          </div>
          <div className="field" style={{ gridColumn: "1 / -1" }}>
            <label>File types</label>
            <div className="chip-row">
              {ALL_FILE_TYPES.map((t) => (
                <button key={t} className="chip" data-on={types.includes(t)}
                  onClick={() => setTypes(types.includes(t) ? types.filter((x) => x !== t) : [...types, t])}>
                  .{t}
                </button>
              ))}
            </div>
          </div>
        </div>
      )}
    </section>
  );
}
