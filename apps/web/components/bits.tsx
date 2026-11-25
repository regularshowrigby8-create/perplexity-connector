"use client";

import { type Hit, type Deadline } from "@/lib/api";
import { fileIcon, fmtDays, fmtMoney, fmtSize, hostOf } from "@/lib/format";

export function ThemeBanner({ variant = "full" }: { variant?: "full" | "compact" }) {
  if (variant === "compact") {
    return (
      <div className="theme-banner compact" role="note">
        <span className="theme-mark">!</span>
        <span>
          <b>Not a news feed.</b> Newest-first is an ordering, never a filter — the buried PDFs,
          listings and open calls that typical engines drop stay in these results.
        </span>
      </div>
    );
  }
  return (
    <div className="theme-banner" role="note">
      <span className="theme-mark">!</span>
      <div>
        <strong>This engine does not rank by popularity, and it does not filter like one.</strong>
        <p>
          Nighthawk exists for the material a mainstream results page demotes or drops entirely:
          the PDF in <span className="mono">/uploads/2019/03/</span>, the tender notice behind a
          portal search, the directory listing nobody linked, the spreadsheet in a data dump, the
          page deleted from the site. No freshness gate, no “helpful content” scorer, no
          domain-authority penalty — old, ugly, unlinked and machine-generated is the point.
          Results are ordered newest-first, to the second, straight from each source's own
          publication clock; anything undated follows rather than disappearing. Sort order can
          change; that filtering policy does not.
        </p>
      </div>
    </div>
  );
}

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

/** The publication clock, in the words a human would use for it. */
export function AgeBadge({ hit }: { hit: Hit }) {
  if (!hit.age_human) return null;
  const seconds = hit.age_seconds ?? Number.POSITIVE_INFINITY;
  const tone =
    seconds < 60 ? "fresh-live" : seconds < 3600 ? "fresh" : seconds < 86400 ? "cyan" : "muted";
  const firstSeen = hit.age_source === "first_seen";
  return (
    <span
      className={`pill ${tone}`}
      title={
        firstSeen
          ? "No publication date on the page — this is when Nighthawk first saw it"
          : `Published ${hit.published_at ?? hit.age_human}`
      }
    >
      {seconds < 60 && <span className="dot" />}
      {hit.age_human}
      {firstSeen ? " · first seen" : ""}
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
            <AgeBadge hit={hit} />
            {!hit.age_human && hit.published && (
              <span className="pill">{String(hit.published).slice(0, 10)}</span>
            )}
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
