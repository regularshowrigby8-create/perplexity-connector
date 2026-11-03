/**
 * Smoke test for a running connector instance.
 * Usage: BASE=http://127.0.0.1:3210 KEY=<CONNECTOR_API_KEY> node test/smoke.mjs
 * Speaks raw MCP over Streamable HTTP (initialize → tools/list → a few tools/call).
 */
const BASE = process.env.BASE || 'http://127.0.0.1:3210';
const KEY = process.env.KEY || '';

let nextId = 1;
async function rpc(method, params, { notify = false } = {}) {
  const id = notify ? undefined : nextId++;
  const res = await fetch(`${BASE}/mcp`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      Accept: 'application/json, text/event-stream',
      ...(KEY ? { Authorization: `Bearer ${KEY}` } : {}),
    },
    body: JSON.stringify({ jsonrpc: '2.0', id, method, params }),
  });
  const ct = res.headers.get('content-type') || '';
  const text = await res.text();
  let msg;
  if (ct.includes('text/event-stream')) {
    const dataLine = text.split('\n').find((l) => l.startsWith('data:'));
    msg = dataLine ? JSON.parse(dataLine.slice(5)) : null;
  } else {
    msg = text ? JSON.parse(text) : null;
  }
  return { status: res.status, msg };
}

function assert(cond, label) {
  if (!cond) {
    console.error(`FAIL: ${label}`);
    process.exitCode = 1;
  } else {
    console.log(`ok: ${label}`);
  }
}

async function callTool(name, args) {
  const { status, msg } = await rpc('tools/call', { name, arguments: args });
  if (status !== 200 || msg?.error) throw new Error(`tools/call ${name} failed: ${JSON.stringify(msg?.error || status)}`);
  const text = msg.result?.content?.[0]?.text ?? '';
  return { isError: msg.result?.isError, text };
}

const { status, msg } = await rpc('initialize', {
  protocolVersion: '2025-06-18',
  capabilities: {},
  clientInfo: { name: 'smoke-test', version: '0.0.1' },
});
assert(status === 200 && msg?.result?.serverInfo?.name, `initialize → serverInfo (${JSON.stringify(msg?.result?.serverInfo)})`);
await rpc('notifications/initialized', {}, { notify: true });

const list = await rpc('tools/list', {});
const tools = list.msg?.result?.tools ?? [];
console.log(`tools registered (${tools.length}):`, tools.map((t) => t.name).join(', '));
assert(tools.length >= 15, 'at least 15 tools registered');

const me = await callTool('get_me', {});
assert(!me.isError, 'get_me ok');
console.log('  get_me →', me.text.slice(0, 200));

const sr = await callTool('search_repositories', { query: 'perplexity-connector in:name user:regularshowrigby8-create', per_page: 3 });
assert(!sr.isError, 'search_repositories ok');
const srJson = JSON.parse(sr.text);
assert(srJson.total_count >= 1, 'search_repositories finds this repo');
console.log('  search_repositories → total_count =', srJson.total_count);

const fc = await callTool('get_file_contents', { owner: 'regularshowrigby8-create', repo: 'perplexity-connector', path: 'README.md' });
assert(!fc.isError && fc.text.includes('perplexity'), 'get_file_contents README.md ok');
console.log('  get_file_contents →', fc.text.slice(0, 120).replace(/\n/g, ' '), '...');

const sc = await callTool('search_code', { query: 'repo:regularshowrigby8-create/perplexity-connector connector', per_page: 3 });
assert(!sc.isError, 'search_code ok');
console.log('  search_code →', sc.text.slice(0, 200).replace(/\n/g, ' '));

const br = await callTool('list_branches', { owner: 'regularshowrigby8-create', repo: 'perplexity-connector' });
assert(!br.isError, 'list_branches ok');
console.log('  list_branches →', br.text.slice(0, 200).replace(/\n/g, ' '));

// auth check (only meaningful when KEY is set)
if (KEY) {
  const res = await fetch(`${BASE}/mcp`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', Accept: 'application/json, text/event-stream' },
    body: JSON.stringify({ jsonrpc: '2.0', id: 99, method: 'initialize', params: { protocolVersion: '2025-06-18', capabilities: {}, clientInfo: { name: 'x', version: '0' } } }),
  });
  assert(res.status === 401, 'request without API key is rejected with 401');
}

console.log(process.exitCode ? 'SMOKE TEST: FAILURES' : 'SMOKE TEST: ALL OK');
