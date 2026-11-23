"use client";

import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { Suspense, useEffect, useMemo, useRef, useState } from "react";
import { streamSSE, type Hit } from "@/lib/api";
import { fmtMs } from "@/lib/format";

type LogLine = { kind: string; text: string; url?: string; at: string };

const SERP_OPTIONS = ["duckduckgo", "mojeek", "marginalia", "bing", "brave", "startpage", "google"];

function isFile(hit: Hit) {
  return Boolean(hit.file_ext);
}

function CrawlView() {
  const params = useSearchParams();
  const [seeds, setSeeds] = useState(params.get("seeds") ?? "");
  const [query, setQuery] = useState(params.get("q") ?? "");
  const [depth, setDepth] = useState(2);
  const [maxPages, setMaxPages] = useState(40);
  const [maxFiles, setMaxFiles] = useState(80);
  const [concurrency, setConcurrency] = useState(8);
  const [robots, setRobots] = useState(true);
  const [sitemaps, setSitemaps] = useState(true);
  const [extract, setExtract] = useState(true);
  const [sameHost, setSameHost] = useState(true);
  const [serps, setSerps] = useState<string[]>(["duckduckgo", "mojeek", "marginalia", "bing"]);
  const [running, setRunning] = useState(false);
  const [logs, setLogs] = useState<LogLine[]>([]);
  const [files, setFiles] = useState<Hit[]>([]);
  const [stats, setStats] = useState<Record<string, unknown> | null>(null);
  const [error, setError] = useState<string | null>(null);
  const abort = useRef<AbortController | null>(null);
  const logRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    if (logRef.current) logRef.current.scrollTop = logRef.current.scrollHeight;
  }, [logs]);

  const counters = useMemo(() => {
    const engines = (stats?.engines as Record<string, number>) ?? {};
    return {
      pages: Number(stats?.pages ?? 0),
      files: Number(stats?.files ?? 0),
      docs: Number(stats?.docs_indexed ?? 0),
      bytes: Number(stats?.bytes ?? 0),
      blocked: Number(stats?.blocked_by_robots ?? 0),
      errors: Number(stats?.errors ?? 0),
      engines: Object.entries(engines).slice(0, 8),
    };
  }, [stats]);

  function pushLog(kind: string, text: string, url?: string) {
    setLogs((prev) => [...prev.slice(-500), { kind, text, url, at: new Date().toLocaleTimeString() }]);
  }

  async function start() {
    if (running) return;
    setRunning(true);
    setLogs([]);
    setFiles([]);
    setStats(null);
    setError(null);
    pushLog("status", "warming up the arsenal");
    const controller = new AbortController();
    abort.current = controller;
    const payload = {
      query,
      seeds: seeds.split(/[\n,]/).map((s) => s.trim()).filter(Boolean),
      depth,
      max_pages: maxPages,
      max_files: maxFiles,
      concurrency,
      respect_robots: robots,
      same_host: sameHost,
      use_sitemaps: sitemaps,
      use_archive: false,
      serp_engines: serps,
      extract_files: extract,
      fetch_engine: "httpx",
    };

    try {
      await streamSSE("/api/v1/crawl/stream", payload, (event) => {
        const type = String(event.type);
        if (type === "status") {
          pushLog("status", String(event.message ?? ""));
        } else if (type === "seeds") {
          pushLog("seeds", `${event.total} seeds planned`);
          for (const seed of (event.list as { url: string; source: string }[] ?? []).slice(0, 12)) {
            pushLog("seeds", `${seed.source} → ${seed.url}`, seed.url);
          }
        } else if (type === "serp") {
          const status = event.status === "error" ? "error" : "serp";
          pushLog(status, `${event.engine}: ${event.found ?? 0} candidates${event.message ? ` (${event.message})` : ""}`);
        } else if (type === "sitemap") {
          pushLog("sitemap", `${event.urls} urls from ${event.url}`, String(event.url));
        } else if (type === "robots") {
          pushLog("robots", `${event.host}: ${event.rules} rule lines`);
        } else if (type === "page") {
          pushLog("page", `${String(event.title ?? "").slice(0, 90)} · ${event.links} links · ${event.text_engine}`,
            String(event.url));
        } else if (type === "pagehit") {
          const hit = event.hit as Hit;
          pushLog("file", `${hit.kind === "opportunity" ? "CALL" : "PAGE"} · ${hit.title}${hit.deadline ? ` · closes ${hit.deadline.date}` : ""}`, hit.url);
          setFiles((prev) => (prev.some((f) => f.url === hit.url) ? prev : [...prev, hit]));
        } else if (type === "listing") {
          pushLog("listing", `directory listing detected: ${event.title}`, String(event.url));
        } else if (type === "file") {
          const hit = event.hit as Hit;
          pushLog("file", `${(hit.file_ext ?? "file").toUpperCase()} · ${hit.title}`, hit.url);
          if (isFile(hit)) setFiles((prev) => (prev.some((f) => f.url === hit.url) ? prev : [...prev, hit]));
        } else if (type === "blocked") {
          pushLog("blocked", `robots.txt disallows ${event.url}`, String(event.url));
        } else if (type === "error") {
          pushLog("error", `${event.message} — ${event.url ?? ""}`);
          setError(String(event.message ?? "crawl error"));
        } else if (type === "progress") {
          setStats((prev) => ({ ...(prev ?? {}), pages: event.pages, files: event.files,
            docs_indexed: event.docs }));
        } else if (type === "done") {
          setStats(event.stats as Record<string, unknown>);
          const finalFiles = (event.files as Hit[]) ?? [];
          if (finalFiles.length) setFiles(finalFiles);
          pushLog("done", `crawl complete in ${fmtMs(Number((event.stats as Record<string, number>)?.walls_ms ?? 0))}`);
          setRunning(false);
        }
      }, controller.signal);
    } catch (err) {
      if ((err as Error).name !== "AbortError") {
        setError((err as Error).message);
        pushLog("error", (err as Error).message);
      }
    } finally {
      setRunning(false);
    }
  }

  function stop() {
    abort.current?.abort();
    setRunning(false);
    pushLog("status", "aborted by operator");
  }

  function practice() {
    setSeeds("http://127.0.0.1:8000/demo/index.html");
    setQuery("climate grant");
    pushLog("status", "practice target loaded — press start");
  }

  return (
    <main className="wrap" style={{ paddingTop: 26 }}>
      <div className="section-head" style={{ marginBottom: 10 }}>
        <h1 style={{ fontSize: 30, margin: 0, letterSpacing: "-0.03em" }}>Fusion crawler</h1>
        <span className="rule" />
        <span className="tiny">primary engine · no ceilings</span>
      </div>
      <p className="lede" style={{ maxWidth: 820 }}>
        Give it seeds or a query. It harvests candidates from SERPs, sitemaps and archive indexes,
        then walks the frontier with whatever fetchers, parsers and extractors are installed —
        opening PDFs, spreadsheets and archives, and indexing their full text locally.
      </p>

      <div className="console-layout">
        <div>
          <div className="search-panel" style={{ marginTop: 18 }}>
            <div className="field">
              <label>Seeds · one per line, or a domain</label>
              <textarea rows={3} value={seeds} onChange={(e) => setSeeds(e.target.value)}
                placeholder={"https://example.org\nhttps://example.org/files/\nexample.org"} />
            </div>
            <div className="advanced" style={{ borderTop: "none", paddingTop: 12 }}>
              <div className="field">
                <label>Query (for SERP + sitemap seeding)</label>
                <input value={query} onChange={(e) => setQuery(e.target.value)}
                  placeholder="climate grants kenya" />
              </div>
              <div className="field">
                <label>Depth</label>
                <input type="number" min={0} max={6} value={depth}
                  onChange={(e) => setDepth(Number(e.target.value))} />
              </div>
              <div className="field">
                <label>Max pages</label>
                <input type="number" min={1} max={800} value={maxPages}
                  onChange={(e) => setMaxPages(Number(e.target.value))} />
              </div>
              <div className="field">
                <label>Max files</label>
                <input type="number" min={1} max={800} value={maxFiles}
                  onChange={(e) => setMaxFiles(Number(e.target.value))} />
              </div>
              <div className="field">
                <label>Concurrency</label>
                <input type="number" min={1} max={32} value={concurrency}
                  onChange={(e) => setConcurrency(Number(e.target.value))} />
              </div>
            </div>

            <div className="field" style={{ marginTop: 12 }}>
              <label>SERP seeders (unrestricted mode)</label>
              <div className="chip-row">
                {SERP_OPTIONS.map((engine) => (
                  <button key={engine} className="chip" data-on={serps.includes(engine)}
                    onClick={() => setSerps(serps.includes(engine)
                      ? serps.filter((x) => x !== engine) : [...serps, engine])}>
                    {engine}
                  </button>
                ))}
              </div>
            </div>

            <div className="chip-row" style={{ marginTop: 12 }}>
              <button className="chip" data-on={robots} onClick={() => setRobots(!robots)}>respect robots.txt</button>
              <button className="chip" data-on={sitemaps} onClick={() => setSitemaps(!sitemaps)}>sitemaps</button>
              <button className="chip" data-on={sameHost} onClick={() => setSameHost(!sameHost)}>same host</button>
              <button className="chip" data-on={extract} onClick={() => setExtract(!extract)}>extract + index files</button>
            </div>

            <div className="search-row" style={{ marginTop: 14 }}>
              <button className="btn btn-primary" onClick={start} disabled={running}>
                {running ? <><span className="spin" /> crawling</> : "Start crawl"}
              </button>
              <button className="btn" onClick={stop} disabled={!running}>Stop</button>
              <button className="btn btn-ghost" onClick={practice}>Load practice target</button>
              <Link className="btn btn-ghost" href="/vault">Open vault →</Link>
            </div>
            {error && <div className="notice" style={{ marginTop: 12 }}>{error}</div>}
            {!robots && (
              <div className="notice" style={{ marginTop: 12 }}>
                robots.txt enforcement is off — only do this for targets you own or have written
                permission to crawl.
              </div>
            )}
          </div>

          <div className="terminal" style={{ marginTop: 16 }}>
            <div className="terminal-bar">
              <span className="led r" /><span className="led y" /><span className="led g" />
              <span style={{ marginLeft: 8 }}>nighthawk://crawler</span>
              <span style={{ marginLeft: "auto" }}>{running ? "live" : "idle"}</span>
            </div>
            {running && <div className="scanline" />}
            <div className="terminal-body" ref={logRef}>
              {logs.length === 0 && (
                <div className="log-line"><span className="log-k status">status</span>
                  <span className="log-m dim">waiting for a target…</span></div>
              )}
              {logs.map((line, index) => (
                <div className="log-line" key={index}>
                  <span className="log-t">{line.at}</span>
                  <span className={`log-k ${line.kind}`}>{line.kind}</span>
                  <span className="log-m">
                    {line.url ? <a href={line.url} target="_blank" rel="noreferrer">{line.text}</a> : line.text}
                  </span>
                </div>
              ))}
            </div>
          </div>
        </div>

        <aside>
          <div className="mini-stats">
            <div className="mini-stat"><div className="n">{counters.pages}</div><div className="l">pages</div></div>
            <div className="mini-stat"><div className="n" style={{ color: "var(--lime)" }}>{counters.files}</div><div className="l">files</div></div>
            <div className="mini-stat"><div className="n" style={{ color: "var(--cyan)" }}>{counters.docs}</div><div className="l">indexed</div></div>
            <div className="mini-stat"><div className="n">{(counters.bytes / 1024).toFixed(0)}</div><div className="l">KB in</div></div>
            <div className="mini-stat"><div className="n" style={{ color: "var(--amber)" }}>{counters.blocked}</div><div className="l">robots blocks</div></div>
            <div className="mini-stat"><div className="n" style={{ color: "var(--red)" }}>{counters.errors}</div><div className="l">errors</div></div>
          </div>

          {counters.engines.length > 0 && (
            <div className="rail-block" style={{ marginTop: 14 }}>
              <header><span>Engines that fired</span><span>{counters.engines.length}</span></header>
              <div className="body">
                {counters.engines.map(([engine, count]) => (
                  <div className="facet" key={engine} style={{ cursor: "default" }}>
                    <span className="v">{engine}</span><span className="c">{count}</span>
                  </div>
                ))}
              </div>
            </div>
          )}

          <div className="section-head" style={{ marginTop: 20 }}>
            <h2 style={{ fontSize: 15 }}>Discovered files</h2>
            <span className="rule" />
            <span className="tiny">{files.length}</span>
          </div>
          {files.slice(0, 60).map((hit) => (
            <a className="file-row" key={hit.url} href={hit.url} target="_blank" rel="noreferrer">
              <span className="file-ext">{hit.file_ext ?? "file"}</span>
              <span style={{ minWidth: 0, flex: 1 }}>
                <span className="file-name" style={{ display: "block" }}>{hit.title}</span>
                <span className="file-sub" style={{ display: "block" }}>
                  depth {hit.depth}{hit.deadline ? ` · closes ${hit.deadline.date}` : ""} · {hit.snippet.slice(0, 60)}
                </span>
              </span>
            </a>
          ))}
          {files.length === 0 && (
            <p className="tiny" style={{ marginTop: 10 }}>
              files appear here as the crawler opens them — run the practice target to see it work
            </p>
          )}
        </aside>
      </div>
    </main>
  );
}

export default function CrawlPage() {
  return (
    <Suspense fallback={<main className="wrap" style={{ paddingTop: 26 }}><div className="skeleton" /></main>}>
      <CrawlView />
    </Suspense>
  );
}
