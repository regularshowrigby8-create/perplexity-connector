export const LENSES = [
  { id: "all", label: "Everything", hint: "all engines" },
  { id: "opportunities", label: "Opportunities", hint: "grants, tenders, calls" },
  { id: "files", label: "Buried files", hint: "pdf, xls, csv, dumps" },
  { id: "applications", label: "Applications", hint: "forms, portals, packs" },
  { id: "exposed", label: "Exposed", hint: "listings, backups, configs" },
  { id: "datasets", label: "Datasets", hint: "open data, tables" },
] as const;

export const ALL_FILE_TYPES = [
  "pdf", "docx", "xlsx", "csv", "pptx", "json", "xml", "zip", "sql", "env", "bak", "log",
  "sqlite", "db", "geojson", "rss", "txt", "md",
];

export function fmtMs(ms: number): string {
  if (ms < 1000) return `${Math.round(ms)}ms`;
  return `${(ms / 1000).toFixed(1)}s`;
}

export function fmtDays(days: number): string {
  if (days === 0) return "closes today";
  if (days < 0) return `closed ${Math.abs(days)}d ago`;
  if (days === 1) return "closes tomorrow";
  return `${days}d left`;
}

export function hostOf(url: string): string {
  try {
    return new URL(url).hostname.replace(/^www\./, "");
  } catch {
    return url;
  }
}

export function fmtMoney(amount: string | null, currency: string | null): string {
  if (!amount) return "";
  const value = Number(String(amount).replace(/[^0-9.]/g, ""));
  const pretty = Number.isFinite(value) && value > 0
    ? value.toLocaleString("en-US", { maximumFractionDigits: 0 })
    : amount;
  return currency ? `${currency} ${pretty}` : pretty;
}

export function fmtSize(bytes: number | null): string {
  if (!bytes) return "";
  const units = ["B", "KB", "MB", "GB"];
  let value = bytes;
  let unit = 0;
  while (value >= 1024 && unit < units.length - 1) {
    value /= 1024;
    unit += 1;
  }
  return `${value < 10 && unit > 0 ? value.toFixed(1) : Math.round(value)}${units[unit]}`;
}

export function fileIcon(ext: string | null): string {
  if (!ext) return "◇";
  if (["pdf"].includes(ext)) return "▤";
  if (["xls", "xlsx", "csv", "tsv", "ods"].includes(ext)) return "▦";
  if (["doc", "docx", "odt", "rtf", "txt", "md"].includes(ext)) return "▥";
  if (["zip", "7z", "tar", "gz", "rar"].includes(ext)) return "▣";
  if (["json", "xml", "yml", "yaml", "env", "ini", "conf", "sql", "db", "sqlite", "bak", "log"].includes(ext)) return "⌗";
  if (["ppt", "pptx"].includes(ext)) return "▧";
  return "◇";
}

export function copy(text: string): Promise<void> {
  return navigator.clipboard?.writeText(text) ?? Promise.resolve();
}
