import type { VercelRequest, VercelResponse } from '@vercel/node';
import { flags, SERVER_NAME } from '../src/server.js';
import { githubTokenConfigured } from '../src/github.js';

export const config = { api: { bodyParser: false } };

export default function handler(_req: VercelRequest, res: VercelResponse) {
  const f = flags();
  res.status(200).json({
    ok: true,
    service: SERVER_NAME,
    mcp: '/mcp',
    githubTokenConfigured: githubTokenConfigured(),
    readOnlyMode: f.readOnly,
    destructiveToolsEnabled: f.destructive,
    time: new Date().toISOString(),
  });
}
