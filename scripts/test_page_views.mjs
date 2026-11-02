import test from 'node:test';
import assert from 'node:assert/strict';
import { mkdtempSync, readFileSync, rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import worker from '../contributions/worker.mjs';
import { createLocalDatabase } from '../contributions/local-db.mjs';

const ORIGIN = 'https://heritage.example';
const PUBLIC = new Set(['/', '/bn/', '/history', '/bn/history', '/contribute', '/bn/contribute', '/rights', '/contributor-terms']);
const html = page => new Response(`<html><body><p data-page-views="${page}">Page views</p></body></html>`, { headers: { 'Content-Type': 'text/html; charset=utf-8' } });
function makeEnv(t, filename) {
  const env = { CONTRIBUTIONS_DB: createLocalDatabase(filename), assetCalls: [], ASSETS: {
    async fetch(request) {
      const page = new URL(request.url).pathname;
      env.assetCalls.push(page);
      assert.equal(request.method, 'GET');
      assert.equal(request.headers.get('Authorization'), null);
      assert.equal(request.headers.get('CF-Connecting-IP'), null);
      // Unknown routes deliberately return a plausible soft-404 home page.
      return html(PUBLIC.has(page) ? page : '/');
    },
  } };
  t?.after(() => env.CONTRIBUTIONS_DB.close());
  return env;
}
async function call(env, page = '/history', options = {}) {
  const { method = 'POST', origin = ORIGIN, headers = {}, body, query } = options;
  const head = new Headers(headers);
  if (origin !== null) head.set('Origin', origin);
  let payload;
  if (!['GET', 'HEAD'].includes(method)) {
    head.set('Content-Type', head.get('Content-Type') || 'application/json');
    payload = body ?? JSON.stringify({ page });
  }
  const search = query ?? (method === 'GET' ? `?page=${encodeURIComponent(page)}` : '');
  const response = await worker.fetch(new Request(`${ORIGIN}/api/page-views${search}`, { method, headers: head, body: payload }), env);
  return { response, data: await response.json() };
}
async function rows(env, table = 'page_views') {
  return (await env.CONTRIBUTIONS_DB.prepare(`SELECT * FROM ${table}`).all()).results.map(row => ({ ...row }));
}

test('public totals work without editor or Turnstile configuration; GET does not create or increment', async t => {
  const env = makeEnv(t);
  let result = await call(env, '/history', { method: 'GET', origin: null });
  assert.equal(result.response.status, 200);
  assert.deepEqual(result.data, { page: '/history', views: 0 });
  assert.deepEqual(await rows(env), []);
  result = await call(env);
  assert.deepEqual(result.data, { page: '/history', views: 1 });
  const before = await rows(env);
  for (let n = 0; n < 4; n++) assert.deepEqual((await call(env, '/history', { method: 'GET' })).data, result.data);
  assert.deepEqual(await rows(env), before);
  env.TURNSTILE_SECRET_KEY = 'unpaired-test-secret';
  assert.equal((await call(env)).data.views, 2);
  assert.match(result.response.headers.get('Cache-Control'), /no-store/);
  assert.match(result.response.headers.get('X-Robots-Tag'), /noindex/);
  assert.equal(result.response.headers.get('Set-Cookie'), null);
  assert.equal(result.response.headers.get('Access-Control-Allow-Origin'), null);
});

test('home/article aliases share canonical totals while English and Bengali remain independent', async t => {
  const env = makeEnv(t);
  const groups = [
    ['/', '/index', '/index.html', '/index/', '/index.html/'],
    ['/bn/', '/bn', '/bn/index', '/bn/index.html', '/bn/index/'],
    ['/history', '/history.html', '/history/', '/history.html/'],
    ['/bn/history', '/bn/history.html', '/bn/history/', '/bn/history.html/'],
  ];
  for (const aliases of groups) {
    for (const [index, alias] of aliases.entries()) {
      const result = await call(env, alias);
      assert.equal(result.response.status, 200, alias);
      assert.deepEqual(result.data, { page: aliases[0], views: index + 1 });
    }
    assert.equal((await call(env, aliases.at(-1), { method: 'GET' })).data.views, aliases.length);
  }
  for (const page of ['/contribute', '/bn/contribute', '/rights', '/contributor-terms'])
    assert.deepEqual((await call(env, page)).data, { page, views: 1 });
  assert.equal((await rows(env)).length, 8);
});

test('rejects malformed, external, encoded, administrative and error-page keys without writes', async t => {
  const env = makeEnv(t);
  const invalid = ['', null, 7, {}, 'history', 'https://heritage.example/history', '//foreign.example/history',
    '/history?x=1', '/history#section', '/%68istory', '/bn%2Fhistory', '/history%00', '/history\\',
    '/history more', '/history\n', '/history/../rights', '/history//', '/bn//history', '/a/b', '/api/config',
    '/review', '/bn/review.html', '/404', '/bn/404/', '/editor', '/admin', '/History'];
  for (const page of invalid) {
    const result = await call(env, page);
    assert.equal(result.response.status, 400, JSON.stringify(page));
  }
  assert.deepEqual(env.assetCalls, []);
  assert.deepEqual(await rows(env), []);
});

test('valid-looking unknown pages and missing or mismatched markers cannot create counts', async t => {
  const env = makeEnv(t);
  for (const method of ['GET', 'POST']) {
    assert.equal((await call(env, '/unknown', { method })).response.status, 404);
    assert.equal((await call(env, '/bn/unknown', { method })).response.status, 404);
  }
  env.ASSETS.fetch = async () => new Response('<html><body>Existing page without counter</body></html>', { headers: { 'Content-Type': 'text/html' } });
  assert.equal((await call(env)).response.status, 404);
  env.ASSETS.fetch = async () => new Response('<p data-page-views="/history"></p><p data-page-views="/history"></p>', { headers: { 'Content-Type': 'text/html' } });
  assert.equal((await call(env)).response.status, 404);
  env.ASSETS.fetch = async () => new Response('data-page-views="/history"', { headers: { 'Content-Type': 'text/plain' } });
  assert.equal((await call(env)).response.status, 404);
  assert.deepEqual(await rows(env), []);
});

test('asset redirects are bounded and limited to aliases of the same public page', async t => {
  const env = makeEnv(t);
  const called = [];
  env.ASSETS.fetch = async request => {
    const path = new URL(request.url).pathname;
    called.push(path);
    return path === '/history' ? new Response(null, { status: 302, headers: { Location: '/history.html' } }) : html('/history');
  };
  assert.equal((await call(env)).data.views, 1);
  assert.deepEqual(called, ['/history', '/history.html']);
  for (const location of ['https://foreign.example/history', '/rights', '/history?private=1', '/history#part']) {
    env.ASSETS.fetch = async () => new Response(null, { status: 302, headers: { Location: location } });
    assert.equal((await call(env)).response.status, 404);
  }
  let loops = 0;
  env.ASSETS.fetch = async () => { loops++; return new Response(null, { status: 302, headers: { Location: '/history' } }); };
  assert.equal((await call(env)).response.status, 404);
  assert.equal(loops, 3);
  assert.deepEqual(await rows(env), [{ page: '/history', views: 1 }]);
});

test('same-origin mutations only, supported methods only and bounded exact-shape payloads', async t => {
  const env = makeEnv(t);
  for (const options of [{ origin: null }, { origin: 'https://foreign.example' }, { headers: { 'Sec-Fetch-Site': 'cross-site' } }])
    assert.equal((await call(env, '/history', options)).response.status, 403);
  assert.equal((await call(env, '/history', { method: 'GET', origin: 'https://foreign.example' })).response.status, 403);
  for (const method of ['PUT', 'DELETE', 'PATCH', 'OPTIONS', 'HEAD']) {
    const result = await call(env, '/history', { method });
    assert.equal(result.response.status, 405);
    assert.equal(result.response.headers.get('Allow'), 'GET, POST');
  }
  for (const query of ['', '?other=x', '?page=%2Fhistory&page=%2Frights', '?page=%2Fhistory&other=x'])
    assert.equal((await call(env, '/history', { method: 'GET', query })).response.status, 400);
  assert.equal((await call(env, '/history', { query: '?page=/history' })).response.status, 400);
  for (const body of ['{}', '{"page":"/history","ip":"discard-me"}', '[]', 'invalid json'])
    assert.equal((await call(env, '/history', { body })).response.status, 400);
  assert.equal((await call(env, '/history', { headers: { 'Content-Type': 'text/plain' } })).response.status, 415);
  assert.equal((await call(env, '/history', { body: JSON.stringify({ page: '/' + 'x'.repeat(1100) }) })).response.status, 413);
  assert.deepEqual(await rows(env), []);
});

test('concurrent loads increment atomically and store no visitor or rate-limit identities', async t => {
  const env = makeEnv(t);
  const responses = await Promise.all(Array.from({ length: 64 }, (_, i) => call(env, '/history', {
    headers: { 'CF-Connecting-IP': `192.0.2.${i + 1}`, 'User-Agent': `test-agent-${i}`, Cookie: `visitor=${i}` },
  })));
  assert.ok(responses.every(result => result.response.status === 200));
  assert.deepEqual(responses.map(result => result.data.views).sort((a, b) => a - b), Array.from({ length: 64 }, (_, i) => i + 1));
  assert.deepEqual(await rows(env), [{ page: '/history', views: 64 }]);
  assert.deepEqual(await rows(env, 'contribution_rate_limits'), []);
  const columns = (await env.CONTRIBUTIONS_DB.prepare('PRAGMA table_info(page_views)').all()).results;
  assert.deepEqual(columns.map(column => column.name), ['page', 'views']);
});

test('missing bindings and storage errors fail closed without leaking details', async t => {
  const env = makeEnv(t);
  for (const other of [{}, { ASSETS: env.ASSETS }, { CONTRIBUTIONS_DB: env.CONTRIBUTIONS_DB }])
    assert.equal((await call(other)).response.status, 503);
  const broken = { ...env, CONTRIBUTIONS_DB: { prepare() { throw new Error('private-sql-or-binding-secret'); } } };
  let result = await call(broken);
  assert.equal(result.response.status, 503);
  assert.equal(JSON.stringify(result.data).includes('private-sql-or-binding-secret'), false);
});

test('first valid GET initializes only the counter table without inserting a view; invalid pages do not initialize', async t => {
  const env = makeEnv(t);
  env.CONTRIBUTIONS_DB.exec('DROP TABLE page_views');
  const tableExists = async () => Boolean(await env.CONTRIBUTIONS_DB.prepare("SELECT name FROM sqlite_master WHERE type='table' AND name='page_views'").first());
  const before = await env.CONTRIBUTIONS_DB.prepare("SELECT name,sql FROM sqlite_master WHERE name<>'page_views' ORDER BY name").all();
  for (const method of ['GET', 'POST']) {
    assert.equal((await call(env, '/history?invalid=1', { method })).response.status, 400);
    assert.equal((await call(env, '/unknown', { method })).response.status, 404);
    assert.equal((await call(env, '/review', { method })).response.status, 400);
    assert.equal(await tableExists(), false);
  }
  const result = await call(env, '/history', { method: 'GET' });
  assert.equal(result.response.status, 200);
  assert.deepEqual(result.data, { page: '/history', views: 0 });
  assert.equal(await tableExists(), true);
  assert.deepEqual(await rows(env), []);
  assert.deepEqual(await env.CONTRIBUTIONS_DB.prepare("SELECT name,sql FROM sqlite_master WHERE name<>'page_views' AND name<>'sqlite_autoindex_page_views_1' ORDER BY name").all(), before);
});

test('concurrent cold requests initialize once per D1 binding and lose no increments', async t => {
  for (let binding = 0; binding < 2; binding++) {
    const env = makeEnv(t);
    env.CONTRIBUTIONS_DB.exec('DROP TABLE page_views');
    const prepare = env.CONTRIBUTIONS_DB.prepare;
    let initializationCalls = 0;
    env.CONTRIBUTIONS_DB.prepare = sql => {
      const statement = prepare(sql);
      if (!sql.startsWith('CREATE TABLE IF NOT EXISTS page_views')) return statement;
      initializationCalls++;
      const migration = readFileSync(new URL('../contributions/migrations/2026-10-09-page-views.sql', import.meta.url), 'utf8');
      assert.equal(sql, migration.slice(migration.indexOf('CREATE TABLE')).trim());
      return { async run() { await new Promise(resolve => setTimeout(resolve, 5)); return statement.run(); } };
    };
    const results = await Promise.all(Array.from({ length: 32 }, () => call(env)));
    assert.ok(results.every(result => result.response.status === 200));
    assert.deepEqual(results.map(result => result.data.views).sort((a, b) => a - b), Array.from({ length: 32 }, (_, i) => i + 1));
    assert.equal(initializationCalls, 1);
    assert.deepEqual((await call(env, '/history', { method: 'GET' })).data, { page: '/history', views: 32 });
    assert.equal((await call(env)).data.views, 33);
    assert.equal(initializationCalls, 1);
  }
});

test('failed schema initialization is shared, reveals no details and retries successfully', async t => {
  const env = makeEnv(t);
  env.CONTRIBUTIONS_DB.exec('DROP TABLE page_views');
  const prepare = env.CONTRIBUTIONS_DB.prepare;
  let initializationCalls = 0;
  env.CONTRIBUTIONS_DB.prepare = sql => {
    if (!sql.startsWith('CREATE TABLE IF NOT EXISTS page_views')) return prepare(sql);
    initializationCalls++;
    if (initializationCalls === 1) return { async run() {
      await new Promise(resolve => setTimeout(resolve, 5));
      throw new Error('private-schema-or-binding-secret');
    } };
    return prepare(sql);
  };
  const failures = await Promise.all(Array.from({ length: 12 }, () => call(env)));
  assert.equal(initializationCalls, 1);
  for (const result of failures) {
    assert.equal(result.response.status, 503);
    assert.equal(JSON.stringify(result.data).includes('private-schema-or-binding-secret'), false);
  }
  assert.equal(await prepare("SELECT name FROM sqlite_master WHERE name='page_views'").first(), null);
  assert.deepEqual((await call(env, '/history', { method: 'GET' })).data, { page: '/history', views: 0 });
  assert.equal(initializationCalls, 2);
  assert.deepEqual(await rows(env), []);
  assert.equal((await call(env)).data.views, 1);
  assert.equal(initializationCalls, 2);
});

test('migration is additive/repeatable and totals survive reopening the database', async () => {
  const directory = mkdtempSync(join(tmpdir(), 'aguri-page-view-tests-'));
  const filename = join(directory, 'test.sqlite');
  let env;
  try {
    env = makeEnv(null, filename);
    assert.equal((await call(env)).data.views, 1);
    const migration = readFileSync(new URL('../contributions/migrations/2026-10-09-page-views.sql', import.meta.url), 'utf8');
    env.CONTRIBUTIONS_DB.exec(migration);
    env.CONTRIBUTIONS_DB.exec(migration);
    assert.deepEqual(await rows(env), [{ page: '/history', views: 1 }]);
    env.CONTRIBUTIONS_DB.close(); env = null;
    env = makeEnv(null, filename);
    assert.deepEqual((await call(env, '/history', { method: 'GET' })).data, { page: '/history', views: 1 });
    assert.equal((await call(env)).data.views, 2);
    assert.equal((await env.CONTRIBUTIONS_DB.prepare('SELECT used_bytes FROM contribution_storage WHERE id=1').first()).used_bytes, 0);
  } finally {
    env?.CONTRIBUTIONS_DB.close();
    rmSync(directory, { recursive: true, force: true });
  }
});
