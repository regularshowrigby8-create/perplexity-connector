import { McpServer } from '@modelcontextprotocol/sdk/server/mcp.js';
import { registerTools } from './tools.js';
import { githubTokenConfigured } from './github.js';

export const SERVER_NAME = 'perplexity-github-connector';
export const SERVER_VERSION = '1.0.0';

export function flags() {
  return {
    readOnly: process.env.GITHUB_READ_ONLY === 'true',
    destructive: process.env.ENABLE_DESTRUCTIVE_TOOLS === 'true',
  };
}

export function createServer(): McpServer {
  const f = flags();
  const server = new McpServer(
    { name: SERVER_NAME, version: SERVER_VERSION },
    {
      instructions: [
        'This connector gives you direct access to a GitHub account via its REST API (authenticated server-side by a personal access token).',
        'Typical flow: search_repositories/search_code/search_issues to find things, then get_repository/list_contents/get_file_contents to read code,',
        'and create_branch/commit_files/create_or_update_file/create_pull_request/create_issue etc. to make changes.',
        'commit_files can commit many files at once to any branch (e.g. main). delete_file removes a file; destructive repo deletion is disabled unless the server enables it.',
        'Always confirm the owner/repo before write operations, and prefer a feature branch + pull request over pushing straight to main.',
        githubTokenConfigured()
          ? `GitHub token is configured (read-only mode: ${f.readOnly}).`
          : 'WARNING: GITHUB_TOKEN is not set on the server — all calls will fail until it is configured.',
      ].join('\n'),
    },
  );
  registerTools(server, f);
  return server;
}
