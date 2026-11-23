"use client";

import { type Hit, type Deadline } from "@/lib/api";
import { fileIcon, fmtDays, hostOf } from "@/lib/format";

export function Depth({ value }: { value: number }) {
  const filled = Math.max(1, Math.round((value / 100) * 5));
  return (
    <span className="depth" title={`Depth score ${value}/100 — how buried this result is`}>
      <span className="bars">
        {[0, 1, 2, 3, 4].map((i) => (
          <span key={i} className={`bar ${i < filled ? "on" : ""}`} />
        ))}
      </span>
      <span className="lbl">depth {value}</span>
    </span>
  );
}

export function DeadlineChip({ deadline }: { deadline: Deadline }) {
  const tone =
    deadline.urgency === "soon" || deadline.urgency === "today"
      ? "amber"
      : deadline.urgency === "closed"
        ? "red"
        : "cyan";
  return (
    <span className={`pill ${tone}`} title={`${deadline.phrase || "deadline"} — ${deadline.date}`}>
      <span className="dot" />
      {fmtDays(deadline.days_left)}
    </span>
  );
}

export function ExtBadge({ ext }: { ext: string | null }) {
  if (!ext) return null;
  return <span className="pill cyan">{ext.toUpperCase()}</span>;
}

export function ResultCard({
  hit,
  index,
  saved,
  onSave,
  onCrawl,
  onCopy,
}: {
  hit: Hit;
  index: number;
  saved: boolean;
  onSave: () => void;
  onCrawl: () => void;
  onCopy: () => void;
}) {
  return (
    <article className="result" style={{ animationDelay: `${Math.min(index, 12) * 22}ms` }}>
      <div className="result-top">
        <span className="result-icon">{fileIcon(hit.file_ext)}</span>
        <div className="result-main">
          <a className="result-title" href={hit.url} target="_blank" rel="noreferrer noopener">
            {hit.title}
          </a>
          <div className="result-url">{hostOf(hit.url)} · {hit.url.replace(/^https?:\/\//, "").slice(0, 110)}</div>
          {hit.snippet && <p className="result-snip">{hit.snippet}</p>}
          <div className="result-meta">
            <ExtBadge ext={hit.file_ext} />
            <Depth value={hit.depth} />
            {hit.deadline && <DeadlineChip deadline={hit.deadline} />}
            {hit.archive && <span className="pill violet"><span className="dot" />archive</span>}
            {hit.portal && <span className="pill">portal</span>}
            {hit.kind === "dork" && <span className="pill violet">dork</span>}
            {hit.provider_name && <span className="pill">{hit.provider_name}</span>}
            {hit.sources.length > 1 && (
              <span className="pill lime">+{hit.sources.length - 1} engines agree</span>
            )}
            {hit.published && <span className="pill">{String(hit.published).slice(0, 10)}</span>}
          </div>
        </div>
        <div className="result-actions">
          <button className="icon-btn" title="Copy link" onClick={onCopy}>⧉</button>
          <button
            className="icon-btn"
            title="Crawl this host"
            onClick={onCrawl}
          >↯</button>
          <button
            className="icon-btn"
            data-on={saved}
            title="Save to watchlist"
            onClick={onSave}
          >{saved ? "★" : "☆"}</button>
        </div>
      </div>
    </article>
  );
}
