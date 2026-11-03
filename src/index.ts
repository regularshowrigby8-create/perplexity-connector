/**
 * Entry point.
 *  - Default: stdio transport (for local MCP clients like Claude Desktop / `npx mcp-remote`).
 *  - MCP_HTTP=1 or PORT set: HTTP transport on 0.0.0.0:<PORT> (default 3000) — used locally and by Vercel.
 */
import { StdioServerTransport } from '@modelcontextprotocol/sdk/server/stdio.js';
import { createServer } from './server.js';
import { app } from './http.js';

async function main() {
  if (process.env.MCP_HTTP === '1' || process.env.PORT) {
    const port = Number(process.env.PORT || 3000);
    app.listen(port, '0.0.0.0', () => {
      console.log(`[perplexity-github-connector] HTTP (Streamable HTTP, stateless) listening on http://0.0.0.0:${port}/mcp`);
      console.log(`[perplexity-github-connector] health: http://0.0.0.0:${port}/health`);
    });
  } else {
    const server = createServer();
    const transport = new StdioServerTransport();
    await server.connect(transport);
    console.error('[perplexity-github-connector] running on stdio');
  }
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
