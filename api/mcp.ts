import type { VercelRequest, VercelResponse } from '@vercel/node';
import { app } from '../src/http.js';

// Let express read the raw request stream (we parse JSON ourselves in the /mcp route).
export const config = { api: { bodyParser: false } };

export default function handler(req: VercelRequest, res: VercelResponse) {
  return app(req as never, res as never);
}
