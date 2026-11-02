import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import worker from '../contributions/worker.mjs';

const ORIGIN = 'https://aguri-heritage.in';
const WB = { country: 'IN', regionCode: 'WB', region: 'West Bengal' };
const ENGLISH = '<html lang="en"><body>English homepage</body></html>';
const STATIC_CACHE = 'public, max-age=14400';

// ASSETS responses may have immutable headers. Reject in-place mutation while
// retaining the iterable Headers contract used to clone them safely.
function immutableCacheableResponse(request) {
  const response = new Response(request.method === 'HEAD' ? null : ENGLISH, {
    headers: { 'Content-Type': 'text/html; charset=utf-8', 'Cache-Control': STATIC_CACHE,
      'Vary': 'Accept-Encoding', 'ETag': '"static-english"' },
  });
  const headers = response.headers;
  Object.defineProperty(response, 'headers', { value: new Proxy(headers, {
    get(target, name) {
      if (['set', 'append', 'delete'].includes(name)) return () => { throw new TypeError('Immutable ASSETS headers'); };
      const value = Reflect.get(target, name, target);
      return typeof value === 'function' ? value.bind(target) : value;
    },
  }) });
  return response;
}

function environment() {
  const env = { calls: [], responses: [], ASSETS: { async fetch(request) {
    env.calls.push(request);
    const response = immutableCacheableResponse(request);
    env.responses.push(response);
    return response;
  } } };
  return env;
}

function request(path = '/', { cf, cookie, method = 'GET' } = {}) {
  const req = new Request(ORIGIN + path, { method, headers: cookie ? { Cookie: cookie } : {} });
  if (cf !== undefined) Object.defineProperty(req, 'cf', { value: cf });
  return req;
}

function noCache(response) {
  assert.equal(response.headers.get('Cache-Control'), 'private, no-store, max-age=0');
  assert.equal(response.headers.get('CDN-Cache-Control'), 'no-store');
  assert.equal(response.headers.get('Cloudflare-CDN-Cache-Control'), 'no-store');
  assert.match(response.headers.get('Vary'), /(?:^|,\s*)Cookie(?:,|$)/);
}

function preference(response, language) {
  assert.equal(response.headers.get('Set-Cookie'),
    `aguri_language=${language}; Max-Age=31536000; Path=/; Secure; SameSite=Lax`);
  assert.doesNotMatch(response.headers.get('Set-Cookie'), /Domain=/i);
}

for (const [name, cf, bengali] of [
  ['West Bengal ISO suffix', WB, true],
  ['full ISO defensive variant', { country: 'IN', regionCode: 'IN-WB' }, true],
  ['normalized code', { country: 'IN', regionCode: ' wb ' }, true],
  ['region name with absent code', { country: 'IN', region: 'West Bengal' }, true],
  ['region name with null code', { country: 'IN', regionCode: null, region: 'West Bengal' }, true],
  ['Karnataka', { country: 'IN', regionCode: 'KA', region: 'Karnataka' }, false],
  ['Delhi', { country: 'IN', regionCode: 'DL' }, false],
  ['conflicting known state code', { country: 'IN', regionCode: 'KA', region: 'West Bengal' }, false],
  ['Bangladesh', { country: 'BD', regionCode: 'WB', region: 'West Bengal' }, false],
  ['United States', { country: 'US', regionCode: 'TX' }, false],
  ['country without state', { country: 'IN' }, false],
  ['unknown country', { country: 'XX', regionCode: 'WB' }, false],
  ['missing metadata', undefined, false],
  ['null metadata', null, false],
  ['empty metadata', {}, false],
  ['state without country', { regionCode: 'WB' }, false],
  ['malformed metadata', 'West Bengal', false],
  ['unknown state code', { country: 'IN', regionCode: '??' }, false],
  ['unknown region name', { country: 'IN', region: 'Unknown' }, false],
]) {
  test(`geolocation: ${name}`, async () => {
    const env = environment();
    const response = await worker.fetch(request('/', { cf }), env);
    assert.equal(response.status, bengali ? 302 : 200);
    assert.equal(response.headers.get('Location'), bengali ? ORIGIN + '/bn/' : null);
    assert.equal(env.calls.length, bengali ? 0 : 1);
    if (!bengali) assert.equal(await response.text(), ENGLISH);
    noCache(response);
    assert.equal(response.headers.get('Set-Cookie'), null, 'geolocation is not a manual preference');
  });
}

for (const [name, cookie, cf, language] of [
  ['saved English overrides West Bengal', 'aguri_language=en', WB, 'en'],
  ['saved Bengali overrides other country', 'aguri_language=bn', { country: 'US' }, 'bn'],
  ['saved Bengali overrides unknown geography', 'aguri_language=bn', undefined, 'bn'],
  ['cookie amid other cookies', 'session=other; aguri_language=en; theme=dark', WB, 'en'],
  ['invalid value falls back', 'aguri_language=fr', WB, 'bn'],
  ['different cookie name is ignored', 'not_aguri_language=en', WB, 'bn'],
  ['prefix cookie name is ignored', 'aguri_language_other=en', WB, 'bn'],
  ['malformed cookie does not match', 'aguri_language=en=bn', WB, 'bn'],
  ['empty cookie value is ignored', 'aguri_language=', { country: 'US' }, 'en'],
]) {
  test(`cookie: ${name}`, async () => {
    const response = await worker.fetch(request('/', { cookie, cf }), environment());
    assert.equal(response.status, language === 'bn' ? 302 : 200);
    noCache(response);
    assert.equal(response.headers.get('Set-Cookie'), null);
  });
}

for (const [path, cookie, cf, language] of [
  ['/?lang=en', 'aguri_language=bn', WB, 'en'],
  ['/?lang=bn', 'aguri_language=en', { country: 'US' }, 'bn'],
  ['/index.html?lang=en', 'aguri_language=bn', WB, 'en'],
  ['/index.html?lang=bn', 'aguri_language=en', undefined, 'bn'],
]) {
  test(`explicit manual homepage override: ${path}`, async () => {
    const response = await worker.fetch(request(path, { cookie, cf }), environment());
    assert.equal(response.status, language === 'bn' ? 302 : 200);
    preference(response, language);
    noCache(response);
  });
}

test('unrecognized language query leaves cookie/geography selection intact', async () => {
  for (const path of ['/?lang=fr', '/?lang=', '/?LANG=en']) {
    const response = await worker.fetch(request(path, { cf: WB }), environment());
    assert.equal(response.status, 302);
    assert.equal(response.headers.get('Set-Cookie'), null);
    assert.equal(new URL(response.headers.get('Location')).search, new URL(ORIGIN + path).search);
  }
});

for (const path of ['/?utm_source=a%20b&scan=12&word=%E0%A6%AC&x=1&x=2', '/index.html?utm_source=a+b&scan=12&x=%2F', '/?lang=bn&scan=12']) {
  test(`Bengali redirect preserves original query exactly: ${path}`, async () => {
    const response = await worker.fetch(request(path, { cf: WB }), environment());
    const target = new URL(response.headers.get('Location'));
    assert.equal(target.pathname, '/bn/');
    assert.equal(target.search, new URL(ORIGIN + path).search);
  });
}

test('English asset passthrough preserves request/query and clones immutable headers', async () => {
  const env = environment();
  const req = request('/?utm_source=a%20b&scan=12&x=%2F', { cf: { country: 'US' } });
  const response = await worker.fetch(req, env);
  assert.equal(env.calls[0], req);
  assert.equal(env.responses[0].headers.get('Cache-Control'), STATIC_CACHE);
  assert.equal(env.responses[0].headers.get('Vary'), 'Accept-Encoding');
  assert.equal(response.headers.get('Content-Type'), 'text/html; charset=utf-8');
  assert.equal(response.headers.get('ETag'), '"static-english"');
  assert.equal(response.headers.get('Vary'), 'Accept-Encoding, Cookie');
  noCache(response);
});

test('Pages canonical index.html redirect retains explicit English override without cookies or loops', async () => {
  const env = { calls: [], ASSETS: { async fetch(req) {
    env.calls.push(req.url);
    const url = new URL(req.url);
    if (url.pathname === '/index.html') {
      url.pathname = '/';
      // Response.redirect has native immutable headers.
      return Response.redirect(url.href, 308);
    }
    return immutableCacheableResponse(req);
  } } };
  const initial = '/index.html?lang=en&scan=12&x=%2F';
  const canonical = await worker.fetch(request(initial, { cf: WB }), env);
  assert.equal(canonical.status, 308);
  assert.equal(canonical.headers.get('Location'), ORIGIN + '/?lang=en&scan=12&x=%2F');
  preference(canonical, 'en');
  noCache(canonical);
  const target = new URL(canonical.headers.get('Location'));
  const final = await worker.fetch(request(target.pathname + target.search, { cf: WB }), env);
  assert.equal(final.status, 200);
  assert.equal(final.headers.get('Location'), null);
  noCache(final);
  assert.equal(env.calls.length, 2);
});

for (const cf of [WB, { country: 'US' }]) {
  test(`HEAD is bodyless and selects ${cf === WB ? 'Bengali' : 'English'}`, async () => {
    const response = await worker.fetch(request('/', { cf, method: 'HEAD' }), environment());
    assert.equal(response.status, cf === WB ? 302 : 200);
    assert.equal(await response.text(), '');
    noCache(response);
  });
}

test('repeated neutral visits use the saved manual choice rather than the detected state', async () => {
  const env = environment();
  const first = await worker.fetch(request('/', { cf: WB }), env);
  assert.equal(first.status, 302);
  const manual = await worker.fetch(request('/?lang=en', { cf: WB }), env);
  preference(manual, 'en');
  const stored = manual.headers.get('Set-Cookie').split(';')[0];
  for (let n = 0; n < 3; n++) {
    const revisit = await worker.fetch(request('/', { cf: WB, cookie: stored }), env);
    assert.equal(revisit.status, 200);
    assert.equal(revisit.headers.get('Location'), null);
  }
});

test('cookies disabled: West Bengal English override stays English, while a later neutral visit detects afresh', async () => {
  const env = environment();
  for (let n = 0; n < 3; n++) {
    const manual = await worker.fetch(request('/?lang=en&utm_source=toggle', { cf: WB }), env);
    assert.equal(manual.status, 200);
    assert.equal(manual.headers.get('Location'), null);
  }
  const neutral = await worker.fetch(request('/', { cf: WB }), env);
  assert.equal(neutral.status, 302);
  const explicitBengali = await worker.fetch(request(new URL(neutral.headers.get('Location')).pathname, { cf: WB }), env);
  assert.equal(explicitBengali.status, 200);
  assert.equal(explicitBengali.headers.get('Location'), null);
  assert.equal(explicitBengali.headers.get('Set-Cookie'), null);
});

test('sequential visitors cannot share a negotiated or redirected response through the static cache', async () => {
  const env = environment();
  const visitors = [
    { cf: WB, expected: 302 },
    { cf: { country: 'US' }, expected: 200 },
    { cf: WB, cookie: 'aguri_language=en', expected: 200 },
    { cf: { country: 'US' }, cookie: 'aguri_language=bn', expected: 302 },
    { cf: undefined, expected: 200 },
  ];
  for (const { expected, ...options } of visitors) {
    const response = await worker.fetch(request('/', options), env);
    assert.equal(response.status, expected);
    noCache(response);
    assert.equal(response.headers.get('Set-Cookie'), null);
  }
  for (const asset of env.responses) assert.equal(asset.headers.get('Cache-Control'), STATIC_CACHE);
});

for (const path of ['/bn/', '/bn/index.html', '/bn/?lang=en&scan=4', '/history', '/history.html?scan=8', '/bn/history', '/bn/history.html', '/person-shib-shankar-chowdhury', '/bn/person-ganapati-panja', '/assets/app.js', '/assets/people/shib-shankar-chowdhury-artwork-960.webp']) {
  test(`explicit edition/article/asset stays static: ${path}`, async () => {
    const env = environment();
    const req = request(path, { cf: WB, cookie: 'aguri_language=en' });
    const response = await worker.fetch(req, env);
    assert.equal(response, env.responses[0], 'returns the original static response');
    assert.equal(env.calls[0], req);
    assert.equal(response.status, 200);
    assert.equal(response.headers.get('Location'), null);
    assert.equal(response.headers.get('Set-Cookie'), null);
    assert.equal(response.headers.get('Cache-Control'), STATIC_CACHE);
    assert.equal(response.headers.get('CDN-Cache-Control'), null);
    assert.equal(response.headers.get('Cloudflare-CDN-Cache-Control'), null);
  });
}

test('non-navigation methods at root are not geographically redirected', async () => {
  const env = environment();
  const req = request('/', { cf: WB, method: 'POST' });
  const response = await worker.fetch(req, env);
  assert.equal(response, env.responses[0]);
  assert.equal(response.headers.get('Location'), null);
  assert.equal(response.headers.get('Set-Cookie'), null);
});

test('existing config API still returns its own JSON response', async () => {
  const env = environment();
  const response = await worker.fetch(request('/api/config', { cf: WB, cookie: 'aguri_language=bn' }), env);
  assert.equal(response.status, 200);
  const data = await response.json();
  assert.equal(data.available, false);
  assert.equal(typeof data.uploads.max_files, 'number');
  assert.equal(env.calls.length, 0);
  assert.equal(response.headers.get('Location'), null);
  assert.equal(response.headers.get('Set-Cookie'), null);
});

test('preparer and publisher permit only existing API plus exact neutral-homepage invocation routes', () => {
  const prepare = readFileSync(new URL('./prepare_cloudflare.py', import.meta.url), 'utf8');
  const publish = readFileSync(new URL('./editor_publish.py', import.meta.url), 'utf8');
  assert.match(prepare, /'include':\s*\['\/api\/\*',\s*'\/',\s*'\/index\.html'\]/);
  assert.match(publish, /'include':\s*\['\/api\/\*',\s*'\/',\s*'\/index\.html'\]/);
  assert.doesNotMatch(prepare, /'include':\s*\['\/\*'\]/);
});
