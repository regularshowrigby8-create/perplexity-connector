"use client";

import { type Hit, type Deadline } from "@/lib/api";
import { fileIcon, fmtDays, fmtMoney, fmtSize, hostOf } from "@/lib/format";

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

function Facts({ hit }: { hit: Hit }) {
  const money = fmtMoney(hit.amount, hit.currency);
  const rows = [
    hit.funder ? { label: "funder", value: hit.funder, tone: "amber" } : null,
    money ? { label: hit.schema_type ? hit.schema_type.toLowerCase() : "amount", value: money, tone: "lime" } : null,
    hit.location ? { label: "location", value: hit.location, tone: "cyan" } : null,
    hit.structured ? { label: "structured", value: hit.structured, tone: "violet" } : null,
  ].filter(Boolean) as { label: string; value: string; tone: string }[];
  if (!rows.length) return null;
  return (
    <div className="facts">
      {rows.map((row) => (
        <span key={`${row.label}-${row.value}`} className={`fact ${row.tone}`}>
          <span className="fact-l">{row.label}</span>
          <span className="fact-v">{row.value}</span>
        </span>
      ))}
    </div>
  );
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
          <Facts hit={hit} />
          {hit.snippet && <p className="result-snip">{hit.snippet}</p>}
          {hit.keyphrases?.length > 0 && (
            <div className="phrases">
              {hit.keyphrases.slice(0, 4).map((phrase) => (
                <span key={phrase} className="phrase">{phrase}</span>
              ))}
            </div>
          )}
          <div className="result-meta">
            <ExtBadge ext={hit.file_ext} />
            <Depth value={hit.depth} />
            {hit.deadline && <DeadlineChip deadline={hit.deadline} />}
            {hit.archive && <span className="pill violet"><span className="dot" />archive</span>}
            {hit.portal && <span className="pill">portal</span>}
            {hit.kind === "dork" && <span className="pill violet">dork</span>}
            {hit.size ? <span className="pill">{fmtSize(hit.size)}</span> : null}
            {hit.sniffed ? (
              <span className="pill lime" title="extension did not match the magic bytes">
                magic: {hit.sniffed}
              </span>
            ) : null}
            {hit.near_dupes > 0 && (
              <span className="pill violet" title="near-identical copies folded into this result">
                +{hit.near_dupes} folded
              </span>
            )}
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
