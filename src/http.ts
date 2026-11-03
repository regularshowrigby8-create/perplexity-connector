/**
 * HTTP layer: exposes the MCP server over Streamable HTTP in STATELESS mode
 * (no session id, JSON responses) so it runs on serverless platforms (Vercel)
 * where each request may hit a fresh instance.
 */
import express from 'express';
import { StreamableHTTPServerTransport } from '@modelcontextprotocol/sdk/server/streamableHttp.js';
import { createServer, flags, SERVER_NAME, SERVER_VERSION } from './server.js';
import { githubTokenConfigured } from './github.js';

const API_KEY = process.env.CONNECTOR_API_KEY || '';

export const app = express();
app.disable('x-powered-by');

// CORS — MCP web clients call this cross-origin.
app.use((req, res, next) => {
  res.setHeader('Access-Control-Allow-Origin', '*');
  res.setHeader('Access-Control-Allow-Methods', 'GET, POST, DELETE, OPTIONS');
  res.setHeader(
    'Access-Control-Allow-Headers',
    'Content-Type, Accept, Authorization, X-Api-Key, Mcp-Session-Id, Mcp-Protocol-Version, Last-Event-ID',
  );
  res.setHeader('Access-Control-Expose-Headers', 'Mcp-Session-Id');
  if (req.method === 'OPTIONS') return res.sendStatus(204);
  next();
});

// Optional bearer/API-key auth (Perplexity connector form: Authentication → API Key sends it as a Bearer token).
app.use((req, res, next) => {
  if (!API_KEY) return next();
  const auth = req.headers.authorization || '';
  const xk = req.headers['x-api-key'];
  if (auth === `Bearer ${API_KEY}` || xk === API_KEY) return next();
  return res.status(401).json({
    jsonrpc: '2.0',
    error: { code: -32001, message: 'Unauthorized. Use Authentication → API Key in the Perplexity connector form and paste your CONNECTOR_API_KEY.' },
    id: null,
  });
});

app.get('/', (_req, res) => {
  const f = flags();
  res.json({
    name: SERVER_NAME,
    version: SERVER_VERSION,
    mcpEndpoint: '/mcp',
    transport: 'Streamable HTTP (stateless, JSON responses)',
    auth: API_KEY ? 'API key required (Authorization: Bearer <CONNECTOR_API_KEY>)' : 'none',
    githubTokenConfigured: githubTokenConfigured(),
    readOnlyMode: f.readOnly,
    destructiveToolsEnabled: f.destructive,
    importIntoPerplexity:
      'perplexity.ai → Account settings → Connectors → + Custom connector → Remote → paste this origin + /mcp → Authentication: API Key (paste CONNECTOR_API_KEY) → Transport: Streamable HTTP → Add.',
  });
});

app.get('/health', (_req, res) => {
  const f = flags();
  res.json({
    ok: true,
    service: SERVER_NAME,
    githubTokenConfigured: githubTokenConfigured(),
    readOnlyMode: f.readOnly,
    destructiveToolsEnabled: f.destructive,
    time: new Date().toISOString(),
  });
});

const methodNotAllowed = (_req: express.Request, res: express.Response) =>
  res.status(405).json({
    jsonrpc: '2.0',
    error: { code: -32000, message: 'Stateless MCP server: send all MCP requests as POST to /mcp (GET/DELETE are not supported).' },
    id: null,
  });

app.get('/mcp', methodNotAllowed);
app.delete('/mcp', methodNotAllowed);

app.post('/mcp', express.json({ limit: '10mb' }), async (req, res) => {
  try {
    // Stateless pattern: a fresh server+transport per request (required on serverless).
    const server = createServer();
    const transport = new StreamableHTTPServerTransport({
      sessionIdGenerator: undefined, // stateless
      enableJsonResponse: true, // plain JSON responses — ideal for serverless + Perplexity
    });
    res.on('close', () => {
      transport.close().catch(() => {});
      server.close().catch(() => {});
    });
    await server.connect(transport);
    await transport.handleRequest(req, res, req.body);
  } catch (err) {
    console.error('MCP request failed:', err);
    if (!res.headersSent) {
      res.status(500).json({
        jsonrpc: '2.0',
        error: { code: -32603, message: `Internal server error: ${err instanceof Error ? err.message : String(err)}` },
        id: null,
      });
    }
  }
});
