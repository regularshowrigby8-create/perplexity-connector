/**
 * Minimal GitHub REST API client used by the connector tools.
 * Authenticates with a personal access token held server-side (GITHUB_TOKEN).
 * Nothing here is ever sent to Perplexity — the token never leaves this server.
 */

const API_BASE = (process.env.GITHUB_API_URL || 'https://api.github.com').replace(/\/+$/, '');

export class GitHubError extends Error {
  constructor(
    public status: number,
    message: string,
    public details?: unknown,
  ) {
    super(message);
    this.name = 'GitHubError';
  }
}

export function githubTokenConfigured(): boolean {
  return Boolean(process.env.GITHUB_TOKEN || process.env.GITHUB_PERSONAL_ACCESS_TOKEN);
}

function token(): string {
  const t = process.env.GITHUB_TOKEN || process.env.GITHUB_PERSONAL_ACCESS_TOKEN;
  if (!t) {
    throw new GitHubError(
      500,
      'Server misconfiguration: GITHUB_TOKEN is not set. Add a GitHub personal access token ' +
        'as the GITHUB_TOKEN environment variable (e.g. a Vercel env var) and redeploy.',
    );
  }
  return t;
}

export interface GhQuery {
  [key: string]: string | number | boolean | undefined;
}

/** Perform an authenticated GitHub REST API call. Throws GitHubError on non-2xx. */
export async function gh<T = any>(
  method: 'GET' | 'POST' | 'PATCH' | 'PUT' | 'DELETE',
  path: string,
  body?: unknown,
  query?: GhQuery,
): Promise<T> {
  let url = API_BASE + path;
  if (query) {
    const usp = new URLSearchParams();
    for (const [k, v] of Object.entries(query)) {
      if (v !== undefined && v !== '') usp.set(k, String(v));
    }
    const qs = usp.toString();
    if (qs) url += (url.includes('?') ? '&' : '?') + qs;
  }

  const res = await fetch(url, {
    method,
    headers: {
      Authorization: `Bearer ${token()}`,
      Accept: 'application/vnd.github+json',
      'X-GitHub-Api-Version': '2022-11-28',
      'User-Agent': 'perplexity-github-connector/1.0',
      ...(body !== undefined ? { 'Content-Type': 'application/json' } : {}),
    },
    body: body !== undefined ? JSON.stringify(body) : undefined,
  });

  if (res.status === 204) return undefined as T;

  const text = await res.text();
  let data: unknown;
  try {
    data = text ? JSON.parse(text) : undefined;
  } catch {
    data = text;
  }

  if (!res.ok) {
    const msg =
      (data as { message?: string })?.message ||
      (typeof data === 'string' ? data : '') ||
      res.statusText;
    const remaining = res.headers.get('x-ratelimit-remaining');
    const hint =
      remaining === '0'
        ? ` Rate limit exhausted (resets at ${new Date(
            Number(res.headers.get('x-ratelimit-reset') || 0) * 1000,
          ).toISOString()}); wait and retry.`
        : '';
    throw new GitHubError(res.status, `GitHub API error ${res.status} on ${method} ${path}: ${msg}.${hint}`, data);
  }
  return data as T;
}

export const b64encode = (s: string): string => Buffer.from(s, 'utf8').toString('base64');

export function decodeContent(content: string, encoding: string): string {
  if (encoding === 'base64') return Buffer.from(content.replace(/\s/g, ''), 'base64').toString('utf8');
  return content;
}

/** Pick a subset of fields from a repo object for compact tool output. */
export function slimRepo(r: Record<string, unknown>) {
  return {
    full_name: r.full_name,
    description: r.description,
    private: r.private,
    default_branch: r.default_branch,
    html_url: r.html_url,
    stargazers_count: r.stargazers_count,
    forks_count: r.forks_count,
    open_issues_count: r.open_issues_count,
    language: r.language,
    pushed_at: r.pushed_at,
    updated_at: r.updated_at,
    permissions: r.permissions,
  };
}
