"use client";

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useCallback, useEffect, useMemo, useRef, useState } from "react";
import { ResultCard, ThemeBanner } from "@/components/bits";
import { SearchPanel } from "@/components/search-panel";
import { api, streamSSE, type Hit, type HuntResponse, type Lens, type ProviderStatus } from "@/lib/api";
import { LENSES, fmtMs, hostOf } from "@/lib/format";

type Meta = {
  plan?: { query: string; lens: string; site?: string | null; suggested_lens?: string | null;
    file_types?: string[]; plays?: { id: string; label: string; dork: string }[] };
  domains?: string[];
  providers?: string[];
};

function label(lens: string) {
  return LENSES.find((l) => l.id === lens)?.label ?? lens;
}

function HuntView() {
  const params = useSearchParams();
  const router = useRouter();
  const q = params.get("q") ?? "";
  const lens = (params.get("lens") ?? "all") as Lens;
  const site = params.get("site");
  const types = params.get("types");
  const sort = (params.get("sort") ?? "newest") as "relevance" | "depth" | "deadline" | "newest";
  const match = (params.get("match") ?? "exact") as "exact" | "loose";
  const onlyExact = params.get("only") === "1";

  const [hits, setHits] = useState<Hit[]>([]);
  const [final, setFinal] = useState<HuntResponse | null>(null);
  const [providers, setProviders] = useState<Record<string, ProviderStatus>>({});
  const [meta, setMeta] = useState<Meta>({});
  const [running, setRunning] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [saved, setSaved] = useState<Record<string, boolean>>({});
  const [toast, setToast] = useState<string | null>(null);
  const [filters, setFilters] = useState<{ domain?: string; ext?: string; provider?: string }>({});
  const [whyOpen, setWhyOpen] = useState(false);
  const abort = useRef<AbortController | null>(null);

  useEffect(() => {
    if (!q) return;
    abort.current?.abort();
    const controller = new AbortController();
    abort.current = controller;
    setHits([]);
    setFinal(null);
    setProviders({});
    setMeta({});
    setRunning(true);
    setError(null);

    streamSSE(
      "/api/v1/hunt/stream",
      {
        q, lens, site: site ?? null, file_types: types ? types.split(",") : [], sort, limit: 0,
        match, only_exact: onlyExact, unrestricted: true,
      },
      (event) => {
        if (event.type === "meta") {
          setMeta({ plan: event.plan as Meta["plan"], domains: event.domains as string[],
            providers: event.providers as string[] });
        } else if (event.type === "results") {
          const incoming = (event.hits ?? []) as Hit[];
          setHits((prev) => {
            const seen = new Set(prev.map((h) => h.url));
            return [...prev, ...incoming.filter((h) => !seen.has(h.url))];
          });
        } else if (event.type === "provider") {
          const status = event as unknown as ProviderStatus;
          setProviders((prev) => ({ ...prev, [status.id]: status }));
        } else if (event.type === "done") {
          const payload = event as unknown as HuntResponse;
          setFinal(payload);
          setHits(payload.hits);
          setProviders(Object.fromEntries(payload.providers.map((p) => [p.id, p])));
          setRunning(false);
        } else if (event.type === "error") {
          setError(String(event.message ?? "engine error"));
          setRunning(false);
        }
      },
      controller.signal,
    ).catch((err: Error) => {
      if (err.name !== "AbortError") {
        setError(err.message);
        setRunning(false);
      }
    });

    return () => controller.abort();
  }, [q, lens, site, types, sort, match, onlyExact]);

  useEffect(() => {
    if (!toast) return;
    const timer = setTimeout(() => setToast(null), 2200);
    return () => clearTimeout(timer);
  }, [toast]);

  const shown = useMemo(() => {
    if (!final) return hits;
    return hits.filter(
      (hit) =>
        (!filters.domain || hit.domain === filters.domain) &&
        (!filters.ext || (hit.file_ext ?? "page") === filters.ext) &&
        (!filters.provider || hit.provider_name === filters.provider),
    );
  }, [hits, final, filters]);

  const toggleSave = useCallback(async (hit: Hit) => {
    if (saved[hit.url]) return;
    try {
      await api("/api/v1/saved", {
        method: "POST",
        body: JSON.stringify({
          url: hit.url, title: hit.title, provider: hit.provider_name, kind: hit.kind,
          file_ext: hit.file_ext, deadline: hit.deadline?.date, depth: hit.depth, query: q,
        }),
      });
      setSaved((prev) => ({ ...prev, [hit.url]: true }));
      setToast("saved to watchlist");
    } catch (err) {
      setToast((err as Error).message);
    }
  }, [q, saved]);

  function factLine(hit: Hit): string {
    return [
      hit.funder ? `funder: ${hit.funder}` : "",
      hit.amount ? `amount: ${[hit.currency, hit.amount].filter(Boolean).join(" ")}` : "",
      hit.location ? `location: ${hit.location}` : "",
      hit.structured ? `type: ${hit.structured}` : "",
    ].filter(Boolean).join(" · ");
  }

  function exportHits(kind: "json" | "md") {
    const data = final?.hits ?? hits;
    if (!data.length) return;
    let blob: Blob;
    if (kind === "json") {
      blob = new Blob([JSON.stringify({ query: q, lens, hits: data }, null, 2)], { type: "application/json" });
    } else {
      const lines = [
        `# ${q} — ${label(lens)}`,
        "",
        `Generated ${new Date().toISOString()} · ${data.length} results · nighthawk`,
        "",
        ...data.map((h, i) =>
          `${i + 1}. [${h.title}](${h.url})\n   ${h.file_ext ? `\`.${h.file_ext}\` · ` : ""}depth ${h.depth}` +
          `${h.deadline ? ` · ${h.deadline.date} (${h.deadline.days_left}d)` : ""} · ${h.provider_name}` +
          `${factLine(h) ? `\n   ${factLine(h)}` : ""}\n   ${h.snippet}`),
      ];
      blob = new Blob([lines.join("\n")], { type: "text/markdown" });
    }
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `nighthawk-${kind === "json" ? "results.json" : "report.md"}`;
    a.click();
    URL.revokeObjectURL(url);
  }

  function crawlDomains() {
    const domains = Array.from(new Set((final?.hits ?? hits).slice(0, 12).map((h) => hostOf(h.url)))).slice(0, 4);
    const seedParam = domains.map((d) => `https://${d}`).join(",");
    router.push(`/crawl?seeds=${encodeURIComponent(seedParam)}&q=${encodeURIComponent(q)}`);
  }

  const runningIds = meta.providers ?? [];
  const facetBlocks: [string, string][] = [
    ["domain", "domains"],
    ["file_ext", "file types"],
    ["provider", "engines"],
  ];

  return (
    <main className="wrap" style={{ paddingTop: 22 }}>
      <SearchPanel initialQuery={q} initialLens={lens} compact />

      <div className="results-layout">
        <aside className="rail">
          <div className="rail-block">
            <header><span>Hunt plan</span><span>{meta.plan?.lens ?? lens}</span></header>
            <div className="body" style={{ gap: 8 }}>
              <p className="tiny" style={{ margin: "2px 6px", lineHeight: 1.5, color: "var(--muted)" }}>
                {meta.plan?.file_types?.length ?? 0} file types · {(meta.domains ?? []).length} archive targets
              </p>
              {(meta.plan?.plays ?? []).map((play) => (
                <div key={play.id} style={{ padding: "4px 6px" }}>
                  <div className="tiny" style={{ color: "var(--lime)" }}>{play.label}</div>
                  <div className="mono" style={{ fontSize: 10.5, color: "var(--dim)", wordBreak: "break-word" }}>
                    {play.dork.slice(0, 150)}{play.dork.length > 150 ? "…" : ""}
                  </div>
                </div>
              ))}
              {meta.plan?.suggested_lens && meta.plan.suggested_lens !== lens && (
                <Link className="facet" href={`/hunt?q=${encodeURIComponent(q)}&lens=${meta.plan.suggested_lens}`}>
                  <span className="v">Switch to {label(meta.plan.suggested_lens)}</span><span className="c">→</span>
                </Link>
              )}
            </div>
          </div>

          {final && facetBlocks.map(([key, title]) => {
            const values = (final.facets[key] ?? []).slice(0, 10);
            if (!values.length) return null;
            return (
              <div className="rail-block" key={key}>
                <header><span>{title}</span><span>{values.length}</span></header>
                <div className="body">
                  {values.map((value) => {
                    const active =
                      (key === "domain" && filters.domain === value.value) ||
                      (key === "file_ext" && filters.ext === value.value) ||
                      (key === "provider" && filters.provider === value.value);
                    return (
                      <button key={value.value} className="facet" data-on={active}
                        onClick={() => setFilters((prev) => {
                          const current =
                            key === "domain" ? prev.domain : key === "file_ext" ? prev.ext : prev.provider;
                          const next = current === value.value ? undefined : value.value;
                          return key === "domain" ? { ...prev, domain: next }
                            : key === "file_ext" ? { ...prev, ext: next }
                              : { ...prev, provider: next };
                        })}>
                        <span className="v">{value.value}</span>
                        <span className="c">{value.count}</span>
                      </button>
                    );
                  })}
                </div>
              </div>
            );
          })}

          <div className="rail-block">
            <header><span>Engine stream</span><span>{running ? "live" : "settled"}</span></header>
            <div className="body" style={{ gap: 1 }}>
              {Object.values(providers)
                .sort((a, b) => {
                  const rank = (s: string) => (s === "ok" ? 0 : s === "empty" ? 1 : s === "needs_key" ? 2 : 3);
                  return rank(a.status) - rank(b.status) || b.count - a.count;
                })
                .slice(0, 24).map((provider) => (
                <div key={provider.id} className="facet" style={{ cursor: "default" }}>
                  <span className="v" style={{ display: "flex", gap: 6, alignItems: "center" }}>
                    <span className={`dot ${provider.status === "ok" ? "ok"
                      : provider.status === "error" ? "err" : "idle"}`} />
                    {provider.name}
                  </span>
                  <span className="c">
                    {provider.status === "needs_key" ? "key"
                      : `${provider.count || ""}${provider.ms ? ` ${fmtMs(provider.ms)}` : ""}`}
                  </span>
                </div>
              ))}
              {!Object.keys(providers).length && running &&
                runningIds.slice(0, 20).map((id) => (
                  <div key={id} className="facet" style={{ cursor: "default" }}>
                    <span className="v" style={{ display: "flex", gap: 6, alignItems: "center" }}>
                      <span className="dot" style={{ background: "var(--cyan)", animation: "pulse 1.4s infinite" }} />
                      {id}
                    </span>
                    <span className="c">…</span>
                  </div>
                ))}
            </div>
          </div>
        </aside>

        <section>
          <ThemeBanner variant="compact" />
          <div className="result-toolbar">
            <div>
              <h1>{q || "No query"}</h1>
              <div className="meta">
                {label(lens)} · {running ? "hunting…" : `${shown.length} shown · ${final?.stats.unique ?? 0} unique`}
                {final && ` · ${final.stats.providers_ok} engines ok`}
                {final?.stats.providers_failed ? ` · ${final.stats.providers_failed} unreachable` : ""}
                {final && ` · ${fmtMs(final.stats.took_ms)}`}
                {final?.stats.cached && " · cached"}
                {final && final.stats.newest_age_human
                  ? ` · newest ${final.stats.newest_age_human}` : ""}
              </div>
            </div>
            <div className="toolbar-right">
              <button
                className="btn btn-sm"
                data-on={match === "exact"}
                title={match === "exact"
                  ? "Word for word: the literal phrase, in order. Nothing is expanded, stemmed or approximated."
                  : "Any of the words — the old keyword behaviour"}
                onClick={() => {
                  const next = new URLSearchParams(params.toString());
                  next.set("match", match === "exact" ? "loose" : "exact");
                  router.replace(`/hunt?${next.toString()}`);
                }}
              >
                {match === "exact" ? "verbatim" : "any word"}
              </button>
              <button
                className="btn btn-sm"
                data-on={onlyExact}
                title="Show only results containing the phrase word for word. Off by default — nothing is hidden unless you ask."
                onClick={() => {
                  const next = new URLSearchParams(params.toString());
                  if (onlyExact) next.delete("only"); else next.set("only", "1");
                  router.replace(`/hunt?${next.toString()}`);
                }}
              >
                {onlyExact ? "verbatim only ✓" : "verbatim only"}
              </button>
              <select className="chip" value={sort} style={{ padding: "6px 8px" }}
                onChange={(e) => {
                  const next = new URLSearchParams(params.toString());
                  next.set("sort", e.target.value);
                  router.replace(`/hunt?${next.toString()}`);
                }}>
                <option value="newest">newest first</option>
                <option value="relevance">relevance</option>
                <option value="depth">most buried</option>
                <option value="deadline">closing soonest</option>
              </select>
              <button className="btn btn-sm" onClick={() => setWhyOpen(!whyOpen)}>why these?</button>
              <button className="btn btn-sm" onClick={crawlDomains} title="Crawl the top hosts">
                crawl hosts
              </button>
              <button className="btn btn-sm" onClick={() => exportHits("md")}>export .md</button>
              <button className="btn btn-sm" onClick={() => exportHits("json")}>json</button>
            </div>
          </div>

          {final && (
            <div className="fresh-strip">
              <span className="tick"><b>{final.stats.fresh_seconds}</b> under a minute</span>
              <span className="tick"><b>{final.stats.fresh_minutes}</b> this hour</span>
              <span className="tick"><b>{final.stats.fresh_hours}</b> today</span>
              <span className="tick"><b>{final.stats.fresh_days}</b> this week</span>
              <span className="tick" title="results containing the query word for word">
                <b>{final.stats.verbatim}</b> verbatim
              </span>
              <span className="tick" title="every query word present, in order, with words in between">
                <b>{final.stats.near_verbatim}</b> near
              </span>
              {final.stats.not_verbatim > 0 && (
                <span className="tick" title="kept because nothing is removed — the phrase is not on the page">
                  <b>{final.stats.not_verbatim}</b> not verbatim
                </span>
              )}
              {final.stats.junk_retained > 0 && (
                <span className="tick" title="parked domains, login walls, error pages — labelled and sorted last, never deleted">
                  <b>{final.stats.junk_retained}</b> junk kept
                </span>
              )}
              <span className="tick">
                newest: <b>{final.stats.newest_age_human ?? "undated"}</b>
              </span>
            </div>
          )}

          {final && (final.expanded?.length > 0 || final.stats.duplicates_collapsed > 0) && (
            <div className="expand-row">
              {final.expanded?.length > 0 && (
                <>
                  <span className="tiny">expanded:</span>
                  {final.expanded.slice(0, 8).map((term) => (
                    <Link key={term} className="pill cyan"
                      href={`/hunt?q=${encodeURIComponent(`${q} ${term}`)}&lens=${lens}`}>
                      + {term}
                    </Link>
                  ))}
                </>
              )}
              {final.stats.duplicates_collapsed > 0 && (
                <span className="pill violet" title="near-identical pages and copies folded by MinHash + LSH">
                  {final.stats.duplicates_collapsed} near-duplicates folded
                </span>
              )}
              {final.stats.dropped_noise > 0 && (
                <span className="pill" title="login walls, carts and cookie pages removed">
                  {final.stats.dropped_noise} noise dropped
                </span>
              )}
            </div>
          )}

          {running && (
            <div className="stream-strip">
              {Array.from({ length: 14 }).map((_, i) => (
                <span key={i} className="src-chip" data-state="running">engine {i + 1}</span>
              ))}
            </div>
          )}

          {whyOpen && (
            <div className="notice info" style={{ marginTop: 12 }}>
              <b>Fusion recipe:</b> each engine contributes <span className="mono">weight ÷ (40 + rank)</span>.
              Files get a type boost, deadlines inside 30 days get up to +45%, and the depth score
              (archive-only, deep paths, upload dirs, non-mainstream hosts) adds up to +40%.
              Duplicates collapse to one canonical URL and list every engine that agreed.
              Near-identical copies (MinHash + LSH, then a token-set pass) fold into the richest
              record, and a record with a funder, an amount and a closing date outranks everything.
            </div>
          )}

          {error && (
            <div className="notice" style={{ marginTop: 12 }}>
              {error}
            </div>
          )}

          {running && hits.length === 0 && (
            <>
              <div className="skeleton" /><div className="skeleton" /><div className="skeleton" />
            </>
          )}

          {shown.map((hit, index) => (
            <ResultCard
              key={`${hit.url}-${index}`}
              hit={hit}
              index={index}
              saved={Boolean(saved[hit.url])}
              onSave={() => toggleSave(hit)}
              onCrawl={() => router.push(`/crawl?seeds=${encodeURIComponent(`https://${hostOf(hit.url)}`)}&q=${encodeURIComponent(hit.title.slice(0, 60))}`)}
              onCopy={() => {
                navigator.clipboard?.writeText(hit.url);
                setToast("link copied");
              }}
            />
          ))}

          {!running && shown.length === 0 && !error && (
            <div className="empty">
              <p style={{ marginTop: 0 }}>Nothing came back for this hunt.</p>
              <p className="mono" style={{ fontSize: 12 }}>
                Try the crawler on a specific host, widen the lens, or check
                <Link href="/arsenal" style={{ color: "var(--lime)" }}> engine status</Link>.
              </p>
            </div>
          )}

          {!running && shown.length > 0 && (
            <p className="tiny" style={{ marginTop: 18 }}>
              {shown.filter((h) => h.file_ext).length} files ·{" "}
              {shown.filter((h) => h.deadline && h.deadline.days_left >= 0).length} live deadlines ·{" "}
              {shown.filter((h) => h.archive).length} archive-only ·{" "}
              {shown.filter((h) => h.sources.length > 1).length} multi-engine consensus ·{" "}
              {shown.filter((h) => h.amount).length} with amounts ·{" "}
              {shown.filter((h) => h.funder).length} with named funders
            </p>
          )}
        </section>
      </div>

      {toast && <div className="toast">{toast}</div>}
    </main>
  );
}

export default function HuntPage() {
  return (
    <Suspense fallback={<main className="wrap" style={{ paddingTop: 22 }}><div className="skeleton" /></main>}>
      <HuntView />
    </Suspense>
  );
}
