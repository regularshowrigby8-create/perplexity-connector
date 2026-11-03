/**
 * OPTIONAL end-to-end WRITE test. Mutates a throwaway branch on a repo.
 * Usage: BASE=http://127.0.0.1:3210 KEY=<key> OWNER=... REPO=... BRANCH=smoke-write node test/write.mjs
 * Deletes the branch afterwards via the REST API (needs the same token locally).
 */
const BASE = process.env.BASE || 'http://127.0.0.1:3210';
const KEY = process.env.KEY || '';
const OWNER = process.env.OWNER || 'regularshowrigby8-create';
const REPO = process.env.REPO || 'perplexity-connector';
const BRANCH = process.env.BRANCH || 'smoke-write-test';

let nextId = 1;
async function rpc(method, params) {
  const res = await fetch(`${BASE}/mcp`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', Accept: 'application/json, text/event-stream', ...(KEY ? { Authorization: `Bearer ${KEY}` } : {}) },
    body: JSON.stringify({ jsonrpc: '2.0', id: nextId++, method, params }),
  });
  return { status: res.status, msg: JSON.parse(await res.text()) };
}
async function callTool(name, args) {
  const { msg } = await rpc('tools/call', { name, arguments: args });
  const text = msg.result?.content?.[0]?.text ?? '';
  if (msg.error || msg.result?.isError) throw new Error(`${name}: ${text || JSON.stringify(msg.error)}`);
  return JSON.parse(text);
}

await rpc('initialize', { protocolVersion: '2025-06-18', capabilities: {}, clientInfo: { name: 'write-test', version: '0' } });

const br = await callTool('create_branch', { owner: OWNER, repo: REPO, branch: BRANCH });
console.log('create_branch →', JSON.stringify(br));

const commit = await callTool('commit_files', {
  owner: OWNER, repo: REPO, branch: BRANCH, message: 'smoke: write test',
  files: [{ path: 'smoke.txt', content: 'hello from perplexity-github-connector\n' }, { path: 'docs/deep/nested.txt', content: 'nested ok\n' }],
});
console.log('commit_files →', JSON.stringify(commit));

const read = await callTool('get_file_contents', { owner: OWNER, repo: REPO, path: 'docs/deep/nested.txt', ref: BRANCH });
if (!read.content.includes('nested ok')) throw new Error('read-back mismatch: ' + JSON.stringify(read));
console.log('get_file_contents read-back → OK');

const upd = await callTool('create_or_update_file', {
  owner: OWNER, repo: REPO, path: 'smoke.txt', branch: BRANCH, message: 'smoke: update',
  content: 'updated content\n', sha: undefined,
});
console.log('create_or_update_file →', JSON.stringify(upd));

console.log('WRITE TEST: ALL OK (branch left in place — delete it with: gh api -X DELETE repos/' + OWNER + '/' + REPO + '/git/refs/heads/' + BRANCH + ')');
