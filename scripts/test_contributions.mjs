import test from 'node:test';
import assert from 'node:assert/strict';
import worker from '../contributions/worker.mjs';
import { createLocalDatabase } from '../contributions/local-db.mjs';

const ORIGIN = 'https://heritage.example';
const KEY = 'test-editor-secret-with-more-than-32-characters-only';
const png = new Uint8Array([137,80,78,71,13,10,26,10,0,0,0,0]);
const makeEnv = () => ({
  EDITOR_KEY: KEY, CONTRIBUTIONS_DB: createLocalDatabase(),
  ASSETS: { async fetch(request) {
    const path = new URL(request.url).pathname;
    if (['/history.html','/bn/history.html','/history','/bn/history'].includes(path)) return new Response('<html><body data-page="history"><main>Article</main></body></html>', { headers: { 'Content-Type': 'text/html' } });
    if (path === '/soft404.html') return new Response('<html><body data-page="index">Fallback</body></html>', { headers: { 'Content-Type': 'text/html' } });
    return new Response('Not found', { status: 404 });
  } },
});
function form(overrides = {}, attachments = []) {
  const data = new FormData();
  for (const [key, value] of Object.entries({ client_id: crypto.randomUUID(), type: 'story', title: 'Village history', description: 'A family account, with details still to verify.', contributor_name: 'Test contributor', email: 'person@example.test', place: 'Bardhaman', date_text: 'circa 1940', language: 'en', consent: 'yes', terms_version: '2026-10-04', credit: 'no', attachment_rights: attachments.length ? 'yes' : '', website: '', ...overrides })) {
    if (value !== undefined) data.set(key, value);
  }
  for (const file of attachments) data.append('attachments', file);
  return data;
}
async function call(env, path, { method = 'GET', token, body, headers = {}, origin = ORIGIN, ip = '192.0.2.5' } = {}) {
  const head = new Headers(headers);
  if (origin != null) head.set('Origin', origin);
  if (token) head.set('Authorization', `Bearer ${token}`);
  if (ip) head.set('CF-Connecting-IP', ip);
  if (body && !(body instanceof FormData) && typeof body === 'object' && !(body instanceof ReadableStream)) { body = JSON.stringify(body); head.set('Content-Type', 'application/json'); }
  const request = new Request(`${ORIGIN}${path}`, { method, headers: head, body, ...(body instanceof ReadableStream ? { duplex: 'half' } : {}) });
  const response = await worker.fetch(request, env);
  const data = response.headers.get('Content-Type')?.includes('application/json') ? await response.json() : null;
  return { response, data };
}
async function submit(env, overrides = {}, attachments = [], options = {}) {
  return call(env, '/api/contributions', { method: 'POST', body: form(overrides, attachments), ...options });
}
async function count(env, table) { return (await env.CONTRIBUTIONS_DB.prepare(`SELECT count(*) AS n FROM ${table}`).first()).n; }

test('configuration fails closed and API rejects foreign origins without CORS', async () => {
  let result = await call({}, '/api/config');
  assert.equal(result.response.status, 200); assert.equal(result.data.available, false);
  result = await call({}, '/api/contributions', { method: 'POST', body: form() });
  assert.equal(result.response.status, 503);
  const env = makeEnv();
  result = await call(env, '/api/config'); assert.equal(result.data.available, true);
  assert.deepEqual(result.data.uploads, { max_files: 3, max_file_bytes: 1500000 });
  for (const extra of [{ TURNSTILE_SECRET_KEY: 'secret' }, { TURNSTILE_SITE_KEY: 'site' }]) {
    result = await call({ ...env, ...extra }, '/api/config'); assert.equal(result.data.available, false);
    result = await submit({ ...env, ...extra }); assert.equal(result.response.status, 503);
  }
  for (const path of ['/api/config', '/api/review']) {
    result = await call(env, path, { origin: 'https://foreign.example' });
    assert.equal(result.response.status, 403); assert.equal(result.response.headers.get('Access-Control-Allow-Origin'), null);
  }
  result = await submit(env, {}, [], { origin: null }); assert.equal(result.response.status, 403);
  result = await call(env, '/api/config', { origin: null, headers: { 'Sec-Fetch-Site': 'cross-site' } }); assert.equal(result.response.status, 403);
  env.CONTRIBUTIONS_DB.close();
});

test('anonymous submissions and canonical public article paths work; named credit needs a name', async () => {
  const env = makeEnv();
  const created = await submit(env, { contributor_name: '', credit: '', source_page: '/history' });
  assert.equal(created.response.status, 201);
  let result = await call(env, `/api/review/${created.data.id}`, { method: 'PATCH', token: KEY, body: { status: 'published', published_url: '/history', version: 1 } });
  assert.equal(result.response.status, 200, JSON.stringify(result.data));
  result = await submit(env, { contributor_name: '', credit: 'yes' }); assert.equal(result.response.status, 400);
  result = await submit(env, { source_page: 'https://foreign.example/history' }); assert.equal(result.response.status, 400);
  env.CONTRIBUTIONS_DB.close();
});

test('submission, private receipt, attachments, reply, editor review and optimistic conflicts', async () => {
  const env = makeEnv();
  const created = await submit(env, { contributor_name: 'প্রদীপ', language: 'bn', credit: 'yes' }, [new File([png], '../family.png', { type: 'image/png' })]);
  assert.equal(created.response.status, 201, JSON.stringify(created.data));
  const { id, token } = created.data;
  assert.ok(id); assert.equal(token.length, 64);
  assert.match(created.response.headers.get('Cache-Control'), /no-store/);
  assert.match(created.response.headers.get('X-Robots-Tag'), /noindex/);
  assert.equal(await count(env, 'contributions'), 1); assert.equal(await count(env, 'contribution_files'), 1);
  let result = await call(env, `/api/contributions/${id}`, { token });
  assert.equal(result.response.status, 200);
  assert.deepEqual(Object.keys(result.data).sort(), ['id','type','title','status','created_at','updated_at','public_note','published_url'].sort());
  result = await call(env, `/api/contributions/${id}`, { token: 'wrong' }); assert.equal(result.response.status, 404);
  result = await call(env, '/api/review', { token: KEY });
  assert.equal(result.data.items.length, 1); assert.equal(result.data.counts.received, 1);
  assert.equal(result.data.items[0].email, undefined); assert.equal(result.data.items[0].client_id, undefined);
  result = await call(env, `/api/review/${id}`, { token: KEY });
  assert.equal(result.data.submission.credit, 'yes'); assert.equal(result.data.submission.attachment_rights, 'yes');
  assert.equal(result.data.submission.token_hash, undefined);
  assert.deepEqual(result.data.consent_info, { status: 'recorded', terms_version: '2026-10-04', purpose: 'contribution', accepted_at: created.data.created_at, language: 'bn' });
  assert.equal(result.data.history[0].note, '');
  assert.equal(result.data.attachments[0].name, 'family.png');
  let file = await call(env, `/api/review/${id}/files/${result.data.attachments[0].id}`, { token: KEY });
  assert.match(file.response.headers.get('Content-Disposition'), /^inline;/);
  assert.equal(file.response.headers.get('Content-Type'), 'image/png');
  assert.equal(file.response.headers.get('X-Content-Type-Options'), 'nosniff');
  assert.deepEqual(new Uint8Array(await file.response.arrayBuffer()), png);
  result = await call(env, `/api/review/${id}`, { method: 'PATCH', token: KEY, body: { status: 'needs_information', public_note: 'Which village?', internal_note: 'Private note', version: 1 } });
  assert.equal(result.response.status, 200); assert.equal(result.data.version, 2);
  result = await call(env, `/api/review/${id}`, { method: 'PATCH', token: KEY, body: { status: 'approved', version: 1 } });
  assert.equal(result.response.status, 409); assert.equal(await count(env, 'contribution_history'), 2);
  result = await call(env, `/api/contributions/${id}`, { token });
  assert.equal(result.data.public_note, 'Which village?'); assert.equal(result.data.internal_note, undefined);
  result = await call(env, `/api/contributions/${id}/reply`, { method: 'POST', token, body: { message: 'It is Khirgram.' } });
  assert.equal(result.response.status, 201);
  result = await call(env, `/api/review/${id}`, { token: KEY });
  assert.equal(result.data.replies[0].message, 'It is Khirgram.'); assert.equal(result.data.submission.version, 3);
  assert.equal(result.data.history.length, 2);
  result = await call(env, `/api/review/${id}`, { method: 'PATCH', token: KEY, body: { status: 'published', published_url: '/history.html', public_note: 'Thank you', version: 3 } });
  assert.equal(result.response.status, 200);
  result = await call(env, `/api/contributions/${id}`, { token });
  assert.equal(result.data.status, 'published'); assert.equal(result.data.published_url, '/history.html');
  env.CONTRIBUTIONS_DB.close();
});

test('new submissions require the current terms and retain immutable acceptance evidence on retries', async () => {
  const env = makeEnv();
  for (const terms_version of [undefined, '', '2026-01-01']) {
    const rejected = await submit(env, { terms_version });
    assert.equal(rejected.response.status, 400); assert.equal(rejected.data.error, 'terms_version_required');
  }
  assert.equal(await count(env, 'contributions'), 0); assert.equal(await count(env, 'contribution_history'), 0);
  const client_id = crypto.randomUUID(), created = await submit(env, { client_id });
  assert.equal(created.response.status, 201);
  const initial = await env.CONTRIBUTIONS_DB.prepare('SELECT note,created_at FROM contribution_history WHERE contribution_id=?').bind(created.data.id).first();
  assert.deepEqual(JSON.parse(initial.note), { kind: 'terms-acceptance', terms_version: '2026-10-04', purpose: 'contribution', type: 'story', accepted_at: created.data.created_at, language: 'en' });
  assert.equal(initial.created_at, created.data.created_at);
  assert.equal((await submit(env, { client_id })).response.status, 200);
  for (const terms_version of [undefined, '2026-01-01']) {
    assert.equal((await submit(env, { client_id, terms_version })).data.error, 'submission_conflict');
  }
  assert.equal(await count(env, 'contributions'), 1); assert.equal(await count(env, 'contribution_history'), 1);
  const after = await env.CONTRIBUTIONS_DB.prepare('SELECT note FROM contribution_history WHERE contribution_id=?').bind(created.data.id).first();
  assert.equal(after.note, initial.note);
  env.CONTRIBUTIONS_DB.close();
});

test('rights enquiries have private handling evidence and cannot be approved, published, or given publication links', async () => {
  const env = makeEnv(), client_id = crypto.randomUUID();
  const file = new File([png], 'rights-evidence.png', { type: 'image/png' });
  const created = await submit(env, { client_id, type: 'rights', language: 'bn', credit: 'yes' }, [file]);
  assert.equal(created.response.status, 201, JSON.stringify(created.data)); assert.equal(created.data.type, 'rights');
  const { id, token } = created.data;
  let result = await call(env, `/api/review/${id}`, { token: KEY });
  assert.equal(result.data.submission.type, 'rights'); assert.equal(result.data.submission.credit, 'no');
  assert.deepEqual(result.data.consent_info, { status: 'recorded', terms_version: '2026-10-04', purpose: 'rights-enquiry', accepted_at: created.data.created_at, language: 'bn' });
  assert.equal(result.data.attachments.length, 1);
  result = await call(env, '/api/review', { token: KEY });
  assert.equal(result.data.items[0].type, 'rights'); assert.equal(result.data.items[0].acceptance_note, undefined);
  result = await call(env, `/api/contributions/${id}`, { token });
  assert.equal(result.data.type, 'rights'); assert.equal(result.data.consent_info, undefined);
  result = await submit(env, { client_id, type: 'rights', language: 'bn', credit: 'yes' }, [file]);
  assert.equal(result.response.status, 200); assert.equal(result.data.type, 'rights');
  for (const body of [
    { status: 'approved' }, { status: 'published', published_url: '/history' }, { status: 'under_review', published_url: '/history' },
  ]) {
    result = await call(env, `/api/review/${id}`, { method: 'PATCH', token: KEY, body: { ...body, version: 1 } });
    assert.equal(result.response.status, 400); assert.equal(result.data.error, 'private_enquiry');
  }
  assert.equal(await count(env, 'contribution_history'), 1);
  let version = 1;
  for (const status of ['under_review', 'needs_information', 'declined']) {
    result = await call(env, `/api/review/${id}`, { method: 'PATCH', token: KEY, body: { status, public_note: 'Private reply to this enquiry.', version } });
    assert.equal(result.response.status, 200); version = result.data.version;
  }
  result = await call(env, `/api/contributions/${id}/reply`, { method: 'POST', token, body: { message: 'Additional context for the enquiry.' } });
  assert.equal(result.response.status, 201);
  result = await call(env, `/api/review/${id}`, { token: KEY });
  assert.equal(result.data.submission.type, 'rights'); assert.equal(result.data.consent_info.purpose, 'rights-enquiry');
  assert.equal(result.data.history[0].note, ''); assert.equal(result.data.replies.length, 1);
  env.CONTRIBUTIONS_DB.close();
});

test('legacy receipts, files, replies and retries remain available without accepting new terms', async () => {
  const env = makeEnv(), client_id = crypto.randomUUID(), file = new File([png], 'old-photo.png', { type: 'image/png' });
  const created = await submit(env, { client_id }, [file]), { id, token } = created.data;
  // Recreate the original unversioned release's exact persisted payload hash
  // and empty initial history note, without changing its receipt or files.
  const row = await env.CONTRIBUTIONS_DB.prepare('SELECT * FROM contributions WHERE id=?').bind(id).first();
  const data = Object.fromEntries(['type','title','description','contributor_name','email','place','date_text','source_url','credit','source_page','language','consent','attachment_rights'].map(key => [key, row[key]]));
  const sha256 = async value => Buffer.from(await crypto.subtle.digest('SHA-256', typeof value === 'string' ? new TextEncoder().encode(value) : value)).toString('hex');
  const legacyHash = await sha256(JSON.stringify({ ...data, files: [{ name: 'old-photo.png', type: 'image/png', size: png.length, hash: await sha256(png) }] }));
  await env.CONTRIBUTIONS_DB.prepare('UPDATE contributions SET payload_hash=? WHERE id=?').bind(legacyHash, id).run();
  await env.CONTRIBUTIONS_DB.prepare("UPDATE contribution_history SET note='' WHERE contribution_id=?").bind(id).run();
  let result = await call(env, `/api/review/${id}`, { token: KEY });
  const legacyConsent = { status: 'legacy', terms_version: null, purpose: null, accepted_at: null, language: null };
  assert.deepEqual(result.data.consent_info, legacyConsent); assert.equal(result.data.attachments.length, 1);
  result = await call(env, `/api/contributions/${id}`, { token }); assert.equal(result.response.status, 200);
  for (const terms_version of [undefined, '2026-10-04']) {
    result = await submit(env, { client_id, terms_version }, [file]); assert.equal(result.response.status, 200); assert.equal(result.data.id, id);
  }
  result = await submit(env, { client_id, description: 'Changed legacy content' }, [file]); assert.equal(result.response.status, 409);
  result = await call(env, `/api/contributions/${id}/reply`, { method: 'POST', token, body: { message: 'Legacy follow-up' } }); assert.equal(result.response.status, 201);
  const pretendAcceptance = JSON.stringify({ kind: 'terms-acceptance', terms_version: '2026-10-04', purpose: 'rights-enquiry', type: 'rights', accepted_at: created.data.created_at, language: 'en' });
  result = await call(env, `/api/review/${id}`, { method: 'PATCH', token: KEY, body: { status: 'under_review', public_note: pretendAcceptance, version: 2 } }); assert.equal(result.response.status, 200);
  result = await call(env, `/api/review/${id}`, { token: KEY });
  assert.deepEqual(result.data.consent_info, legacyConsent); assert.equal(result.data.submission.type, 'story');
  assert.equal(result.data.replies.length, 1); assert.equal(result.data.history[0].note, '');
  assert.equal(await count(env, 'contributions'), 1); assert.equal(await count(env, 'contribution_files'), 1);
  env.CONTRIBUTIONS_DB.close();
});

test('idempotency preserves a single atomic record and detects payload changes, including attachments', async () => {
  const env = makeEnv(), client_id = crypto.randomUUID();
  const file = new File([png], 'photo.png', { type: 'image/png' });
  const first = await submit(env, { client_id }, [file]);
  const again = await submit(env, { client_id }, [file]);
  assert.equal(again.response.status, 200); assert.deepEqual(again.data, first.data);
  let result = await submit(env, { client_id, title: 'Different' }, [file]); assert.equal(result.response.status, 409);
  result = await submit(env, { client_id }, [new File([new Uint8Array([...png, 1])], 'photo.png', { type: 'image/png' })]); assert.equal(result.response.status, 409);
  assert.equal(await count(env, 'contributions'), 1); assert.equal(await count(env, 'contribution_files'), 1);
  env.EDITOR_KEY = 'rotated-key-that-is-also-more-than-32-characters';
  result = await call(env, `/api/contributions/${first.data.id}`, { token: first.data.token }); assert.equal(result.response.status, 200);
  result = await submit(env, { client_id }, [file]); assert.equal(result.data.error, 'receipt_key_changed');
  result = await submit(env, { client_id }, [file], { token: first.data.token }); assert.equal(result.response.status, 200); assert.equal(result.data.token, first.data.token);
  env.CONTRIBUTIONS_DB.close();
});

test('parallel idempotent submissions create one record and one set of files', async () => {
  const env = makeEnv(), client_id = crypto.randomUUID();
  const result = await Promise.all(Array.from({ length: 4 }, () => submit(env, { client_id }, [new File([png], 'p.png', { type: 'image/png' })])));
  assert.ok(result.every(item => [200,201].includes(item.response.status)), JSON.stringify(result.map(r => r.data)));
  assert.equal(new Set(result.map(item => item.data.id)).size, 1);
  assert.equal(await count(env, 'contributions'), 1); assert.equal(await count(env, 'contribution_history'), 1); assert.equal(await count(env, 'contribution_files'), 1);
  env.CONTRIBUTIONS_DB.close();
});

test('validation rejects unconsented, malformed, oversized and disguised uploads', async () => {
  const cases = [
    [{ consent: '' }, []], [{ website: 'spam' }, []], [{ title: 'x'.repeat(161) }, []], [{ source_url: 'javascript:alert(1)' }, []],
    [{ attachment_rights: '' }, [new File([png], 'p.png', { type: 'image/png' })]],
    [{}, [new File(['<html>bad</html>'], 'fake.png', { type: 'image/png' })]],
    [{}, [new File([png], 'p.pdf', { type: 'application/pdf' })]],
    [{}, [new File([new Uint8Array(1_500_001)], 'large.png', { type: 'image/png' })]],
    [{}, Array.from({ length: 4 }, () => new File([png], 'p.png', { type: 'image/png' }))],
    [{}, [new File([new Uint8Array([255,255,0])], 'binary.txt', { type: 'text/plain' })]],
  ];
  for (const [override, attachments] of cases) {
    const env = makeEnv();
    const result = await submit(env, override, attachments);
    assert.equal(result.response.status, 400, JSON.stringify(result.data)); assert.equal(await count(env, 'contributions'), 0);
    env.CONTRIBUTIONS_DB.close();
  }
  const env = makeEnv();
  const f = form(); f.append('title', 'duplicate');
  const result = await call(env, '/api/contributions', { method: 'POST', body: f });
  assert.equal(result.data.error, 'duplicate_field'); env.CONTRIBUTIONS_DB.close();
});

test('stream size is bounded even without Content-Length', async () => {
  const env = makeEnv(); let cancelled = false, pulls = 0;
  const stream = new ReadableStream({ pull(controller) { pulls++; controller.enqueue(new Uint8Array(1_000_000)); }, cancel() { cancelled = true; } });
  const result = await call(env, '/api/contributions', { method: 'POST', body: stream, headers: { 'Content-Type': 'multipart/form-data; boundary=test' } });
  assert.equal(result.response.status, 413); assert.ok(cancelled); assert.ok(pulls < 9); assert.equal(await count(env, 'contributions'), 0);
  env.CONTRIBUTIONS_DB.close();
});

test('storage capacity rolls back submission, files, and history as one transaction', async () => {
  const env = makeEnv();
  await env.CONTRIBUTIONS_DB.prepare('UPDATE contribution_storage SET used_bytes=199999990 WHERE id=1').run();
  const result = await submit(env, {}, [new File([png], 'p.png', { type: 'image/png' })]);
  assert.equal(result.response.status, 503); assert.equal(result.data.error, 'storage_full');
  for (const table of ['contributions','contribution_files','contribution_history']) assert.equal(await count(env, table), 0);
  assert.equal((await env.CONTRIBUTIONS_DB.prepare('SELECT used_bytes FROM contribution_storage WHERE id=1').first()).used_bytes, 199999990);
  env.CONTRIBUTIONS_DB.close();
});

test('unpublished, external, private, missing and soft-404 URLs cannot be marked published', async () => {
  const env = makeEnv(), created = await submit(env), path = `/api/review/${created.data.id}`;
  for (const url of ['', 'https://foreign.example/history.html', '/review.html', '/missing.html', '/soft404.html', '/assets/file.pdf', '/history.html?preview=yes']) {
    const result = await call(env, path, { method: 'PATCH', token: KEY, body: { status: 'published', published_url: url, version: 1 } });
    assert.equal(result.response.status, 400, `${url}: ${JSON.stringify(result.data)}`);
  }
  assert.equal(await count(env, 'contribution_history'), 1); env.CONTRIBUTIONS_DB.close();
});

test('editor authentication is rate limited while legitimate editor access remains available', async () => {
  const env = makeEnv();
  for (let i = 0; i < 10; i++) assert.equal((await call(env, '/api/review', { token: 'bad' })).response.status, 401);
  assert.equal((await call(env, '/api/review', { token: 'bad' })).response.status, 429);
  assert.equal((await call(env, '/api/review', { token: KEY })).response.status, 200);
  const rates = await env.CONTRIBUTIONS_DB.prepare('SELECT bucket FROM contribution_rate_limits').all();
  assert.ok(rates.results.every(row => !row.bucket.includes('192.0.2.5')));
  env.CONTRIBUTIONS_DB.close();
});

test('public submissions have per-IP and global limits; wildcard search stays literal', async () => {
  const env = makeEnv();
  for (let i = 0; i < 10; i++) assert.equal((await submit(env, { title: i ? 'Ordinary title' : '100% family_record' })).response.status, 201);
  assert.equal((await submit(env)).response.status, 429);
  const searched = await call(env, '/api/review?q=%25', { token: KEY });
  assert.equal(searched.data.items.length, 1);
  const day = Math.floor(Date.now() / 1000 / 86400);
  await env.CONTRIBUTIONS_DB.prepare('UPDATE contribution_rate_limits SET count=100 WHERE bucket=?').bind(`submit-global:global:${day}`).run();
  const result = await submit(env, {}, [], { ip: '192.0.2.99' });
  assert.equal(result.response.status, 429); assert.equal(await count(env, 'contributions'), 10);
  env.CONTRIBUTIONS_DB.close();
});

test('reply count is bounded and failures are atomic', async () => {
  const env = makeEnv(), created = await submit(env), { id, token } = created.data;
  for (let i = 0; i < 20; i++) {
    const result = await call(env, `/api/contributions/${id}/reply`, { method: 'POST', token, body: { message: `Reply ${i}` }, ip: `192.0.2.${i + 10}` });
    assert.equal(result.response.status, 201);
  }
  const before = await env.CONTRIBUTIONS_DB.prepare('SELECT version FROM contributions WHERE id=?').bind(id).first();
  const result = await call(env, `/api/contributions/${id}/reply`, { method: 'POST', token, body: { message: 'Too many' }, ip: '192.0.2.100' });
  assert.equal(result.response.status, 429); assert.equal(result.data.error, 'reply_limit');
  assert.equal(await count(env, 'contribution_replies'), 20);
  assert.equal((await env.CONTRIBUTIONS_DB.prepare('SELECT version FROM contributions WHERE id=?').bind(id).first()).version, before.version);
  env.CONTRIBUTIONS_DB.close();
});

test('private server files are never served and internal errors reveal no SQL', async () => {
  const env = makeEnv();
  env.ASSETS.fetch = async () => new Response('private bytes');
  for (const path of ['/contributions/schema.sql', '/contributions/worker.mjs', '/_worker.js', '/%63ontributions/schema.sql', '/.dev.vars']) {
    assert.equal((await call(env, path)).response.status, 404);
  }
  env.CONTRIBUTIONS_DB.close();
  const result = await call(env, '/api/review', { token: KEY });
  assert.equal(result.response.status, 503); assert.equal(result.data.error, 'service_error');
  assert.doesNotMatch(JSON.stringify(result.data), /SELECT|sqlite|secret/);
});

test('review cursor is stable and skips no records sharing the same creation time', async () => {
  const env = makeEnv();
  for (let i = 0; i < 33; i++) assert.equal((await submit(env, { title: `Story ${i}` }, [], { ip: `198.51.100.${i}` })).response.status, 201);
  await env.CONTRIBUTIONS_DB.prepare('UPDATE contributions SET created_at=?').bind('2026-10-04T01:00:00.000Z').run();
  const first = await call(env, '/api/review', { token: KEY });
  assert.equal(first.data.items.length, 30); assert.ok(first.data.next_cursor);
  const second = await call(env, `/api/review?before=${encodeURIComponent(first.data.next_cursor)}`, { token: KEY });
  assert.equal(second.data.items.length, 3); assert.equal(second.data.next_cursor, null);
  assert.equal(new Set([...first.data.items, ...second.data.items].map(row => row.id)).size, 33);
  env.CONTRIBUTIONS_DB.close();
});

test('configured Turnstile verifies the token and hostname before storing a submission', async () => {
  const env = { ...makeEnv(), TURNSTILE_SITE_KEY: 'test-site', TURNSTILE_SECRET_KEY: 'test-secret' };
  const originalFetch = globalThis.fetch;
  let verification = { success: true, hostname: 'heritage.example' }, checks = 0;
  globalThis.fetch = async (url, options) => {
    checks++;
    assert.equal(url, 'https://challenges.cloudflare.com/turnstile/v0/siteverify');
    assert.equal(options.body.get('secret'), 'test-secret'); assert.equal(options.body.get('response'), 'test-token');
    return Response.json(verification);
  };
  try {
    let result = await call(env, '/api/config'); assert.equal(result.data.turnstile_site_key, 'test-site');
    result = await submit(env); assert.equal(result.response.status, 400); assert.equal(checks, 0);
    result = await submit(env, { 'cf-turnstile-response': 'test-token' }); assert.equal(result.response.status, 201);
    verification = { success: true, hostname: 'foreign.example' };
    result = await submit(env, { 'cf-turnstile-response': 'test-token' }); assert.equal(result.response.status, 400);
    verification = { success: false, hostname: 'heritage.example' };
    result = await submit(env, { 'cf-turnstile-response': 'test-token' }); assert.equal(result.response.status, 400);
    assert.equal(await count(env, 'contributions'), 1);
  } finally { globalThis.fetch = originalFetch; env.CONTRIBUTIONS_DB.close(); }
});
