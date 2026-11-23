export type Lens = "all" | "opportunities" | "files" | "applications" | "exposed" | "datasets";

export type Deadline = {
  date: string;
  days_left: number;
  phrase: string;
  urgency: "closed" | "today" | "soon" | "upcoming" | "later";
};

export type Hit = {
  url: string;
  title: string;
  snippet: string;
  provider: string;
  provider_name: string;
  kind: string;
  file_ext: string | null;
  mime: string | null;
  domain: string;
  published: string | null;
  deadline: Deadline | null;
  depth: number;
  score: number;
  tags: string[];
  archive: boolean;
  portal: boolean;
  sources: { provider: string; name: string; rank: number; url: string }[];
  meta: Record<string, unknown>;
};

export type ProviderStatus = {
  id: string;
  name: string;
  status: "ok" | "error" | "empty" | "needs_key";
  count: number;
  ms: number;
  message: string;
};

export type HuntResponse = {
  query: string;
  lens: string;
  site: string | null;
  hits: Hit[];
  providers: ProviderStatus[];
  facets: Record<string, { value: string; count: number }[]>;
  stats: {
    hits: number;
    unique: number;
    providers_ok: number;
    providers_failed: number;
    files: number;
    opportunities: number;
    closing_soon: number;
    took_ms: number;
    cached: boolean;
  };
  plays: string[];
};

export type HuntParams = {
  q: string;
  lens?: Lens;
  site?: string | null;
  file_types?: string[];
  providers?: string[];
  limit?: number;
  sort?: "relevance" | "depth" | "deadline" | "newest";
  fresh?: boolean;
};

export async function api<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(path, {
    ...init,
    headers: { "content-type": "application/json", ...(init?.headers ?? {}) },
    cache: "no-store",
  });
  if (!res.ok) {
    const text = await res.text().catch(() => "");
    throw new Error(`${res.status} ${res.statusText}${text ? ` — ${text.slice(0, 200)}` : ""}`);
  }
  return res.json() as Promise<T>;
}

export type StreamEvent = Record<string, unknown> & { type: string };

export async function streamSSE(
  path: string,
  body: unknown,
  onEvent: (event: StreamEvent) => void,
  signal?: AbortSignal,
): Promise<void> {
  const res = await fetch(path, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify(body),
    signal,
  });
  if (!res.ok || !res.body) {
    const text = await res.text().catch(() => "");
    throw new Error(`${res.status} ${res.statusText} ${text.slice(0, 300)}`);
  }
  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  for (;;) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const parts = buffer.split("\n\n");
    buffer = parts.pop() ?? "";
    for (const part of parts) {
      const line = part.split("\n").find((l) => l.startsWith("data:"));
      if (!line) continue;
      const payload = line.slice(5).trim();
      if (!payload) continue;
      try {
        onEvent(JSON.parse(payload) as StreamEvent);
      } catch {
        /* ignore keep-alives */
      }
    }
  }
}
