/**
 * Registers the GitHub toolset on an MCP server.
 *
 * Read tools are always available. Write tools are skipped when GITHUB_READ_ONLY=true.
 * Destructive tools (delete_repository) additionally require ENABLE_DESTRUCTIVE_TOOLS=true.
 */
import { McpServer } from '@modelcontextprotocol/sdk/server/mcp.js';
import { z } from 'zod';
import { gh, GitHubError, b64encode, decodeContent, slimRepo } from './github.js';

export interface ToolFlags {
  readOnly: boolean;
  destructive: boolean;
}

const MAX_FILE_CHARS = 100_000;

function ok(data: unknown) {
  return { content: [{ type: 'text' as const, text: JSON.stringify(data, null, 2) }] };
}

function fail(err: unknown) {
  const msg = err instanceof Error ? err.message : String(err);
  return { isError: true as const, content: [{ type: 'text' as const, text: msg }] };
}

const ownerRepo = {
  owner: z.string().min(1).describe('GitHub username or organization, e.g. "octocat"'),
  repo: z.string().min(1).describe('Repository name, e.g. "hello-world"'),
};

const perPage = {
  per_page: z.number().int().min(1).max(100).default(10).describe('Results per page (1-100)'),
};

const READ_ONLY_HINT = { readOnlyHint: true, openWorldHint: true } as const;
const WRITE_HINT = { readOnlyHint: false, destructiveHint: true, openWorldHint: true } as const;
const SAFE_WRITE_HINT = { readOnlyHint: false, destructiveHint: false, openWorldHint: true } as const;
const DESTRUCTIVE_HINT = { readOnlyHint: false, destructiveHint: true, idempotentHint: false, openWorldHint: true } as const;

export function registerTools(server: McpServer, flags: ToolFlags): void {
  const wrap =
    <A extends Record<string, z.ZodTypeAny>>(fn: (args: z.infer<z.ZodObject<A>>) => Promise<unknown>) =>
    async (args: z.infer<z.ZodObject<A>>) => {
      try {
        return ok(await fn(args));
      } catch (err) {
        return fail(err instanceof GitHubError ? `${err.message}` : err);
      }
    };

  // ---------------------------------------------------------------- account
  server.registerTool(
    'get_me',
    {
      title: 'Who am I (GitHub)',
      description:
        'Returns the authenticated GitHub user behind this connector (login, plan, counts). Use to verify which account the connector acts as.',
      inputSchema: {},
      annotations: READ_ONLY_HINT,
    },
    wrap(async () => {
      const u = await gh<any>('GET', '/user');
      return {
        login: u.login,
        name: u.name,
        type: u.type,
        plan: u.plan,
        public_repos: u.public_repos,
        private_repos: u.private_repos ?? null,
        html_url: u.html_url,
      };
    }),
  );

  server.registerTool(
    'list_my_repositories',
    {
      title: 'List my repositories',
      description: 'Lists repositories of the authenticated account (all repos it can see, incl. private if the token allows).',
      inputSchema: {
        type: z.enum(['all', 'owner', 'member']).default('all').describe('Filter: all, owned, or member-of'),
        per_page: perPage.per_page,
      },
      annotations: READ_ONLY_HINT,
    },
    wrap(async ({ type, per_page }) => {
      const repos = await gh<any[]>('GET', '/user/repos', undefined, { type, per_page, sort: 'updated' });
      return { total: repos.length, repositories: repos.map(slimRepo) };
    }),
  );

  // ---------------------------------------------------------------- search
  server.registerTool(
    'search_repositories',
    {
      title: 'Search GitHub repositories',
      description: 'Search repositories on GitHub. Query uses GitHub search syntax, e.g. "mcp server language:typescript stars:>1000".',
      inputSchema: { query: z.string().min(1).describe('GitHub repository search query'), ...perPage },
      annotations: READ_ONLY_HINT,
    },
    wrap(async ({ query, per_page }) => {
      const d = await gh<any>('GET', '/search/repositories', undefined, { q: query, per_page });
      return { total_count: d.total_count, items: d.items.map(slimRepo) };
    }),
  );

  server.registerTool(
    'search_code',
    {
      title: 'Search code on GitHub',
      description:
        'Search code across GitHub (requires the token to have code-search access). Query syntax e.g. "registerTool repo:modelcontextprotocol/servers language:typescript". Results include file path and repo; fetch content with get_file_contents.',
      inputSchema: { query: z.string().min(1).describe('GitHub code search query'), ...perPage },
      annotations: READ_ONLY_HINT,
    },
    wrap(async ({ query, per_page }) => {
      const d = await gh<any>('GET', '/search/code', undefined, { q: query, per_page });
      return {
        total_count: d.total_count,
        items: d.items.map((i: any) => ({
          name: i.name,
          path: i.path,
          html_url: i.html_url,
          repository: i.repository?.full_name,
          score: i.score,
        })),
      };
    }),
  );

  server.registerTool(
    'search_issues',
    {
      title: 'Search issues & PRs on GitHub',
      description: 'Search issues and pull requests across GitHub, e.g. "is:pr is:open label:bug repo:facebook/react".',
      inputSchema: { query: z.string().min(1), ...perPage },
      annotations: READ_ONLY_HINT,
    },
    wrap(async ({ query, per_page }) => {
      const d = await gh<any>('GET', '/search/issues', undefined, { q: query, per_page });
      return {
        total_count: d.total_count,
        items: d.items.map((i: any) => ({
          number: i.number, title: i.title, state: i.state, html_url: i.html_url,
          repository: (i.repository_url as string)?.split('/repos/')[1], user: i.user?.login,
          labels: (i.labels as { name: string }[] | undefined)?.map((l) => l.name),
        })),
      };
    }),
  );

  server.registerTool(
    'search_commits',
    {
      title: 'Search commits on GitHub',
      description: 'Search commit history across GitHub, e.g. "repo:torvalds/linux fix typo".',
      inputSchema: { query: z.string().min(1), ...perPage },
      annotations: READ_ONLY_HINT,
    },
    wrap(async ({ query, per_page }) => {
      const d = await gh<any>('GET', '/search/commits', undefined, { q: query, per_page });
      return {
        total_count: d.total_count,
        items: d.items.map((i: any) => ({
          sha: i.sha, html_url: i.html_url, message: i.commit?.message,
          author: i.commit?.author?.name, repository: i.repository?.full_name,
        })),
      };
    }),
  );

  // ---------------------------------------------------------------- repos / files
  server.registerTool(
    'get_repository',
    {
      title: 'Get repository info',
      description: 'Get metadata for a repository: description, default branch, visibility, permissions, counts.',
      inputSchema: { ...ownerRepo },
      annotations: READ_ONLY_HINT,
    },
    wrap(async ({ owner, repo }) => slimRepo(await gh('GET', `/repos/${owner}/${repo}`))),
  );

  server.registerTool(
    'list_contents',
    {
      title: 'List directory contents',
      description: 'List files/folders of a repository path (root if path omitted). Optionally at a branch/tag/commit ref.',
      inputSchema: { ...ownerRepo, path: z.string().default('').describe('Directory path, "" or omit for root'), ref: z.string().optional().describe('Branch, tag or commit SHA') },
      annotations: READ_ONLY_HINT,
    },
    wrap(async ({ owner, repo, path, ref }) => {
      const p = path.replace(/^\/+/, '');
      const d = await gh<Record<string, unknown> | Record<string, unknown>[]>('GET', `/repos/${owner}/${repo}/contents/${p}`, undefined, { ref });
      if (Array.isArray(d)) return { path: p || '/', entries: d.map((e) => ({ name: e.name, path: e.path, type: e.type, size: e.size, sha: e.sha, html_url: e.html_url })) };
      return { type: 'file', name: d.name, path: d.path, size: d.size, html_url: d.html_url };
    }),
  );

  server.registerTool(
    'get_file_contents',
    {
      title: 'Read a file from a repo',
      description:
        'Read a single file (decoded to text, truncated at ~100k chars) or list a directory. Use after search_code to read the matched files.',
      inputSchema: { ...ownerRepo, path: z.string().min(1).describe('File path, e.g. "src/index.ts"'), ref: z.string().optional().describe('Branch, tag or commit SHA (default: default branch)') },
      annotations: READ_ONLY_HINT,
    },
    wrap(async ({ owner, repo, path, ref }) => {
      const d = await gh<any>('GET', `/repos/${owner}/${repo}/contents/${path.replace(/^\/+/, '')}`, undefined, { ref });
      if (Array.isArray(d)) {
        return { type: 'directory', entries: d.map((e: Record<string, unknown>) => ({ name: e.name, path: e.path, type: e.type, size: e.size, sha: e.sha })) };
      }
      if (d.type === 'file') {
        const raw = decodeContent(String(d.content ?? ''), String(d.encoding ?? 'base64'));
        const truncated = raw.length > MAX_FILE_CHARS;
        return {
          type: 'file', path: d.path, size: d.size, encoding: 'utf-8',
          truncated,
          content: truncated ? raw.slice(0, MAX_FILE_CHARS) + `\n\n[... truncated at ${MAX_FILE_CHARS} chars; ask to fetch a smaller range or the raw blob ...]` : raw,
          html_url: d.html_url,
        };
      }
      return { type: d.type, path: d.path, html_url: d.html_url, note: String(d.content ?? '') };
    }),
  );

  server.registerTool(
    'list_branches',
    {
      title: 'List branches',
      description: 'List branches of a repository.',
      inputSchema: { ...ownerRepo, ...perPage },
      annotations: READ_ONLY_HINT,
    },
    wrap(async ({ owner, repo, per_page }) => {
      const d = await gh<any[]>('GET', `/repos/${owner}/${repo}/branches`, undefined, { per_page });
      return d.map((b) => ({ name: b.name, protected: b.protected, commit_sha: b.commit?.sha }));
    }),
  );

  server.registerTool(
    'list_commits',
    {
      title: 'List commits',
      description: 'List recent commits of a repository, optionally on a branch/SHA or touching a path.',
      inputSchema: { ...ownerRepo, sha: z.string().optional().describe('Branch or commit SHA to start from'), path: z.string().optional(), ...perPage },
      annotations: READ_ONLY_HINT,
    },
    wrap(async ({ owner, repo, sha, path, per_page }) => {
      const d = await gh<any[]>('GET', `/repos/${owner}/${repo}/commits`, undefined, { sha, path, per_page });
      return d.map((c) => ({ sha: c.sha, message: c.commit?.message, author: c.commit?.author?.name, date: c.commit?.author?.date, html_url: c.html_url }));
    }),
  );

  // ---------------------------------------------------------------- issues / PRs (read)
  server.registerTool(
    'list_issues',
    {
      title: 'List issues',
      description: 'List issues of a repository (PRs are excluded by GitHub on this endpoint).',
      inputSchema: { ...ownerRepo, state: z.enum(['open', 'closed', 'all']).default('open'), labels: z.string().optional().describe('Comma-separated label names'), ...perPage },
      annotations: READ_ONLY_HINT,
    },
    wrap(async ({ owner, repo, state, labels, per_page }) => {
      const d = await gh<any[]>('GET', `/repos/${owner}/${repo}/issues`, undefined, { state, labels, per_page });
      return d.map((i) => ({
        number: i.number, title: i.title, state: i.state, html_url: i.html_url, user: i.user?.login,
        labels: (i.labels as { name: string }[] | undefined)?.map((l) => l.name), comments: i.comments,
      }));
    }),
  );

  server.registerTool(
    'get_issue',
    {
      title: 'Get an issue',
      description: 'Get one issue with its body.',
      inputSchema: { ...ownerRepo, issue_number: z.number().int().min(1) },
      annotations: READ_ONLY_HINT,
    },
    wrap(async ({ owner, repo, issue_number }) => {
      const i = await gh<any>('GET', `/repos/${owner}/${repo}/issues/${issue_number}`);
      return { number: i.number, title: i.title, state: i.state, body: i.body, user: i.user?.login, html_url: i.html_url, labels: (i.labels as { name: string }[] | undefined)?.map((l) => l.name) };
    }),
  );

  server.registerTool(
    'list_pull_requests',
    {
      title: 'List pull requests',
      description: 'List pull requests of a repository.',
      inputSchema: { ...ownerRepo, state: z.enum(['open', 'closed', 'all']).default('open'), head: z.string().optional(), base: z.string().optional(), ...perPage },
      annotations: READ_ONLY_HINT,
    },
    wrap(async ({ owner, repo, state, head, base, per_page }) => {
      const d = await gh<any[]>('GET', `/repos/${owner}/${repo}/pulls`, undefined, { state, head, base, per_page });
      return d.map((p) => ({ number: p.number, title: p.title, state: p.state, head: p.head?.ref, base: p.base?.ref, user: p.user?.login, html_url: p.html_url, merged: p.merged_at }));
    }),
  );

  server.registerTool(
    'get_pull_request',
    {
      title: 'Get a pull request',
      description: 'Get one pull request with body, head/base and merge status.',
      inputSchema: { ...ownerRepo, pull_number: z.number().int().min(1) },
      annotations: READ_ONLY_HINT,
    },
    wrap(async ({ owner, repo, pull_number }) => {
      const p = await gh<any>('GET', `/repos/${owner}/${repo}/pulls/${pull_number}`);
      return { number: p.number, title: p.title, state: p.state, body: p.body, head: p.head?.ref, base: p.base?.ref, user: p.user?.login, mergeable: p.mergeable, merged: p.merged_at, html_url: p.html_url };
    }),
  );

  server.registerTool(
    'list_pull_request_files',
    {
      title: 'List files changed in a PR',
      description: 'List the files changed by a pull request, with patch snippets when small.',
      inputSchema: { ...ownerRepo, pull_number: z.number().int().min(1), ...perPage },
      annotations: READ_ONLY_HINT,
    },
    wrap(async ({ owner, repo, pull_number, per_page }) => {
      const d = await gh<any[]>('GET', `/repos/${owner}/${repo}/pulls/${pull_number}/files`, undefined, { per_page });
      return d.map((f) => ({ filename: f.filename, status: f.status, additions: f.additions, deletions: f.deletions, patch: f.patch }));
    }),
  );

  // ---------------------------------------------------------------- write tools
  if (!flags.readOnly) {
    server.registerTool(
      'create_repository',
      {
        title: 'Create repository',
        description: 'Create a new repository on the authenticated account.',
        inputSchema: {
          name: z.string().min(1),
          description: z.string().optional(),
          private: z.boolean().default(false),
          auto_init: z.boolean().default(true).describe('Initialize with a README'),
        },
        annotations: SAFE_WRITE_HINT,
      },
      wrap(async (args) => slimRepo(await gh('POST', '/user/repos', args))),
    );

    server.registerTool(
      'create_fork',
      {
        title: 'Fork a repository',
        description: 'Fork any repository you can read into your account (or an organization). This is how you "import" someone else\'s repo to work on it.',
        inputSchema: { ...ownerRepo, organization: z.string().optional().describe('Fork into this org instead of your user account') },
        annotations: SAFE_WRITE_HINT,
      },
      wrap(async ({ owner, repo, organization }) => {
        const f = await gh<any>('POST', `/repos/${owner}/${repo}/forks`, organization ? { organization } : {});
        return slimRepo(f);
      }),
    );

    server.registerTool(
      'create_branch',
      {
        title: 'Create a branch',
        description: 'Create a new branch from another ref (defaults to the repository default branch).',
        inputSchema: { ...ownerRepo, branch: z.string().min(1).describe('New branch name'), from_ref: z.string().optional().describe('Source branch/SHA (default: default branch)') },
        annotations: SAFE_WRITE_HINT,
      },
      wrap(async ({ owner, repo, branch, from_ref }) => {
        const repoInfo = await gh<any>('GET', `/repos/${owner}/${repo}`);
        const src = from_ref || String(repoInfo.default_branch || 'main');
        const ref = await gh<{ object: { sha: string } }>('GET', `/repos/${owner}/${repo}/git/ref/heads/${encodeURIComponent(src)}`);
        const created = await gh('POST', `/repos/${owner}/${repo}/git/refs`, { ref: `refs/heads/${branch}`, sha: ref.object.sha });
        return { branch, from: src, ref: created.ref, sha: created.object.sha };
      }),
    );

    server.registerTool(
      'create_or_update_file',
      {
        title: 'Create or update a single file',
        description:
          'Create or update one file via the contents API (commits directly to `branch`, or the default branch). Provide `sha` of the existing blob when updating an existing file. Content is plain text (server base64-encodes it).',
        inputSchema: {
          ...ownerRepo,
          path: z.string().min(1).describe('File path, e.g. "docs/notes.md"'),
          content: z.string().describe('Full new file content as plain text'),
          message: z.string().min(1).describe('Commit message'),
          branch: z.string().optional().describe('Target branch (default: repo default branch). Use to push straight to main if you have permission.'),
          sha: z.string().optional().describe('Blob SHA of the file being replaced (required by GitHub when the file exists)'),
        },
        annotations: WRITE_HINT,
      },
      wrap(async ({ owner, repo, path, content, message, branch, sha }) => {
        const d = await gh<any>('PUT', `/repos/${owner}/${repo}/contents/${path.replace(/^\/+/, '')}`, {
          message, content: b64encode(content), branch, sha,
        });
        return { path, commit: d.commit?.sha, html_url: d.content?.html_url };
      }),
    );

    server.registerTool(
      'delete_file',
      {
        title: 'Delete a file',
        description: 'Delete a file from a branch by committing the removal. Requires the blob `sha` of the file (get it from list_contents/get_file_contents).',
        inputSchema: {
          ...ownerRepo,
          path: z.string().min(1),
          message: z.string().min(1).describe('Commit message'),
          sha: z.string().min(1).describe('Blob SHA of the file to delete'),
          branch: z.string().optional(),
        },
        annotations: WRITE_HINT,
      },
      wrap(async ({ owner, repo, path, message, sha, branch }) => {
        const d = await gh<any>('DELETE', `/repos/${owner}/${repo}/contents/${path.replace(/^\/+/, '')}`, { message, sha, branch });
        return { path, commit: d.commit?.sha };
      }),
    );

    server.registerTool(
      'commit_files',
      {
        title: 'Commit multiple files at once (push)',
        description:
          'Create one commit with many file changes on any branch (including main) using the Git Data API: blobs → tree → commit → ref update. Set branch="main" to push directly to main (only if allowed). `force` overwrites non-fast-forward history — use with care. Entries with delete=true remove files.',
        inputSchema: {
          ...ownerRepo,
          branch: z.string().min(1).describe('Target branch, e.g. "main" or "feat/x"'),
          message: z.string().min(1).describe('Commit message'),
          files: z
            .array(
              z.object({
                path: z.string().min(1).describe('Repo-relative file path'),
                content: z.string().optional().describe('New file content (plain text). Omit when delete=true.'),
                delete: z.boolean().default(false).describe('Delete this path instead of writing it'),
              }),
            )
            .min(1)
            .describe('Files to write/delete in this commit'),
          force: z.boolean().default(false).describe('Force-update the branch ref (overwrites history if not fast-forward)'),
          create_if_missing: z.boolean().default(false).describe('Create the branch from the default branch if it does not exist yet'),
        },
        annotations: WRITE_HINT,
      },
      wrap(async ({ owner, repo, branch, message, files, force, create_if_missing }) => {
        // 1. resolve base commit
        let baseSha: string;
        let refExists = true;
        try {
          const ref = await gh<{ object: { sha: string } }>('GET', `/repos/${owner}/${repo}/git/ref/heads/${encodeURIComponent(branch)}`);
          baseSha = ref.object.sha;
        } catch (err) {
          if (err instanceof GitHubError && err.status === 404 && create_if_missing) {
            refExists = false;
            const info = await gh<any>('GET', `/repos/${owner}/${repo}`);
            const def = await gh<{ object: { sha: string } }>('GET', `/repos/${owner}/${repo}/git/ref/heads/${encodeURIComponent(String(info.default_branch || 'main'))}`);
            baseSha = def.object.sha;
          } else throw err;
        }
        // 2. base tree
        const baseCommit = await gh<{ tree: { sha: string } }>('GET', `/repos/${owner}/${repo}/git/commits/${baseSha}`);
        // 3. blobs
        const tree: Record<string, unknown>[] = [];
        for (const f of files) {
          if (f.delete) {
            tree.push({ path: f.path, mode: '100644', type: 'blob', sha: null });
          } else {
            const blob = await gh<{ sha: string }>('POST', `/repos/${owner}/${repo}/git/blobs`, { content: f.content ?? '', encoding: 'utf-8' });
            tree.push({ path: f.path, mode: '100644', type: 'blob', sha: blob.sha });
          }
        }
        // 4. tree + commit
        const newTree = await gh<{ sha: string }>('POST', `/repos/${owner}/${repo}/git/trees`, { base_tree: baseCommit.tree.sha, tree });
        const commit = await gh<{ sha: string }>('POST', `/repos/${owner}/${repo}/git/commits`, { message, tree: newTree.sha, parents: [baseSha] });
        // 5. update ref
        const refPath = `refs/heads/${branch}`;
        const updated = refExists
          ? await gh('PATCH', `/repos/${owner}/${repo}/git/refs/heads/${encodeURIComponent(branch)}`, { sha: commit.sha, force })
          : await gh('POST', `/repos/${owner}/${repo}/git/refs`, { ref: refPath, sha: commit.sha });
        return { branch, commit: commit.sha, ref: updated.ref, files: files.map((f: { path: string }) => f.path), forced: force };
      }),
    );

    server.registerTool(
      'create_pull_request',
      {
        title: 'Create a pull request',
        description: 'Open a PR from `head` branch into `base` branch (same repo; use "user:branch" for cross-fork heads).',
        inputSchema: {
          ...ownerRepo,
          title: z.string().min(1),
          head: z.string().min(1).describe('Source branch (or "owner:branch" for forks)'),
          base: z.string().min(1).describe('Target branch, e.g. "main"'),
          body: z.string().optional(),
          draft: z.boolean().default(false),
        },
        annotations: SAFE_WRITE_HINT,
      },
      wrap(async ({ owner, repo, title, head, base, body, draft }) => {
        const p = await gh<any>('POST', `/repos/${owner}/${repo}/pulls`, { title, head, base, body, draft });
        return { number: p.number, title: p.title, html_url: p.html_url, state: p.state };
      }),
    );

    server.registerTool(
      'merge_pull_request',
      {
        title: 'Merge a pull request',
        description: 'Merge an open PR. merge_method: merge | squash | rebase.',
        inputSchema: {
          ...ownerRepo,
          pull_number: z.number().int().min(1),
          merge_method: z.enum(['merge', 'squash', 'rebase']).default('squash'),
          commit_message: z.string().optional(),
        },
        annotations: WRITE_HINT,
      },
      wrap(async ({ owner, repo, pull_number, merge_method, commit_message }) => {
        const d = await gh<any>('PUT', `/repos/${owner}/${repo}/pulls/${pull_number}/merge`, { merge_method, commit_message });
        return { merged: d.merged, sha: d.sha, message: d.message };
      }),
    );

    server.registerTool(
      'create_issue',
      {
        title: 'Create an issue',
        description: 'Create an issue in a repository.',
        inputSchema: { ...ownerRepo, title: z.string().min(1), body: z.string().optional(), labels: z.array(z.string()).optional() },
        annotations: SAFE_WRITE_HINT,
      },
      wrap(async ({ owner, repo, title, body, labels }) => {
        const i = await gh<any>('POST', `/repos/${owner}/${repo}/issues`, { title, body, labels });
        return { number: i.number, title: i.title, html_url: i.html_url, state: i.state };
      }),
    );

    server.registerTool(
      'update_issue',
      {
        title: 'Update an issue',
        description: 'Update title/body/labels or close/reopen an issue (state: open|closed).',
        inputSchema: {
          ...ownerRepo,
          issue_number: z.number().int().min(1),
          title: z.string().optional(),
          body: z.string().optional(),
          state: z.enum(['open', 'closed']).optional(),
          labels: z.array(z.string()).optional(),
        },
        annotations: SAFE_WRITE_HINT,
      },
      wrap(async ({ owner, repo, issue_number, ...rest }) => {
        const i = await gh<any>('PATCH', `/repos/${owner}/${repo}/issues/${issue_number}`, rest);
        return { number: i.number, title: i.title, state: i.state, html_url: i.html_url };
      }),
    );

    server.registerTool(
      'create_issue_comment',
      {
        title: 'Comment on an issue or PR',
        description: 'Add a comment to an issue or pull request (same endpoint on GitHub).',
        inputSchema: { ...ownerRepo, issue_number: z.number().int().min(1), body: z.string().min(1) },
        annotations: SAFE_WRITE_HINT,
      },
      wrap(async ({ owner, repo, issue_number, body }) => {
        const c = await gh<any>('POST', `/repos/${owner}/${repo}/issues/${issue_number}/comments`, { body });
        return { id: c.id, html_url: c.html_url };
      }),
    );
  }

  // ---------------------------------------------------------------- destructive
  if (!flags.readOnly && flags.destructive) {
    server.registerTool(
      'delete_repository',
      {
        title: 'DELETE a repository (irreversible)',
        description:
          'Permanently deletes a repository owned by the token user. ONLY available when the server runs with ENABLE_DESTRUCTIVE_TOOLS=true. Type the full "owner/repo" name in `confirm` to proceed.',
        inputSchema: {
          ...ownerRepo,
          confirm: z.string().describe('Must exactly equal "owner/repo" to confirm deletion'),
        },
        annotations: DESTRUCTIVE_HINT,
      },
      wrap(async ({ owner, repo, confirm }) => {
        if (confirm !== `${owner}/${repo}`) throw new GitHubError(400, `Confirmation mismatch: type "${owner}/${repo}" in confirm to delete this repository.`);
        await gh('DELETE', `/repos/${owner}/${repo}`);
        return { deleted: `${owner}/${repo}` };
      }),
    );
  }
}
