import test from 'node:test';
import assert from 'node:assert/strict';
import worker from '../contributions/worker.mjs';

const origin = 'https://heritage.example';
const filename = 'Ugrakshatriya_Pratinidhi_Vol_01.pdf';
const path = `/api/documents/${filename}`;
const upstreamURL = `https://github.com/rn5678/aguri-heritage-resources/releases/download/journals-v1/${filename}`;

async function mockedFetch(handler, run) {
  const original = globalThis.fetch;
  globalThis.fetch = handler;
  try { await run(); } finally { globalThis.fetch = original; }
}

test('public journal response streams the fixed PDF and forwards only range/validator headers', async () => {
  let pulls = 0, observed;
  const stream = new ReadableStream({ pull(controller) {
    pulls++;
    controller.enqueue(new TextEncoder().encode('%PDF-1.7'));
    controller.close();
  } }, { highWaterMark: 0 });
  await mockedFetch(async (url, options) => {
    observed = { url, options };
    return new Response(stream, { status: 206, headers: {
      'Content-Type': 'application/octet-stream', 'Content-Disposition': 'attachment',
      'Content-Length': '8', 'Content-Range': 'bytes 0-7/84100000', 'Accept-Ranges': 'bytes',
      ETag: '"fixture"', 'Last-Modified': 'Fri, 16 Oct 2026 00:00:00 GMT', 'Cache-Control': 'public, max-age=300'
    } });
  }, async () => {
    const response = await worker.fetch(new Request(origin + path + '?url=https://untrusted.example/', { headers: {
      Range: 'bytes=0-7', 'If-Range': '"fixture"', 'If-None-Match': '"previous"',
      'If-Modified-Since': 'Thu, 15 Oct 2026 00:00:00 GMT', 'If-Match': '"expected"',
      'If-Unmodified-Since': 'Fri, 16 Oct 2026 00:00:00 GMT',
      Authorization: 'Bearer never-forward', Cookie: 'private=never-forward', Referer: origin + '/review'
    } }), {});
    assert.equal(pulls, 0, 'The Worker does not buffer or consume the upstream PDF');
    assert.equal(observed.url, upstreamURL);
    assert.equal(observed.options.method, 'GET');
    assert.equal(observed.options.credentials, 'omit');
    assert.equal(observed.options.referrerPolicy, 'no-referrer');
    assert.equal(observed.options.headers.get('Range'), 'bytes=0-7');
    assert.equal(observed.options.headers.get('If-Range'), '"fixture"');
    for (const name of ['Authorization', 'Cookie', 'Referer']) assert.equal(observed.options.headers.has(name), false);
    assert.deepEqual([...observed.options.headers.keys()].sort(), ['accept', 'if-match', 'if-modified-since', 'if-none-match', 'if-range', 'if-unmodified-since', 'range']);
    assert.equal(response.status, 206);
    assert.equal(response.headers.get('Content-Type'), 'application/pdf');
    assert.equal(response.headers.get('Content-Disposition'), `inline; filename="${filename}"`);
    for (const [name, value] of Object.entries({ 'Content-Length': '8', 'Content-Range': 'bytes 0-7/84100000',
      'Accept-Ranges': 'bytes', ETag: '"fixture"', 'Last-Modified': 'Fri, 16 Oct 2026 00:00:00 GMT' }))
      assert.equal(response.headers.get(name), value);
    assert.equal(await response.text(), '%PDF-1.7');
    assert.equal(pulls, 1);
  });
});

test('journal HEAD and 304 preserve metadata and have no body', async () => {
  for (const status of [200, 304]) {
    await mockedFetch(async (url, options) => {
      assert.equal(url.endsWith('Vol_02.pdf'), true);
      assert.equal(options.method, status === 200 ? 'HEAD' : 'GET');
      return new Response(null, { status, headers: { ETag: '"volume-two"', 'Content-Length': '243000000',
        'Last-Modified': 'Fri, 16 Oct 2026 00:00:00 GMT', 'Cache-Control': 'public, max-age=300' } });
    }, async () => {
      const response = await worker.fetch(new Request(origin + path.replace('01.pdf', '02.pdf'),
        { method: status === 200 ? 'HEAD' : 'GET' }), {});
      assert.equal(response.status, status);
      assert.equal(response.body, null);
      assert.equal(response.headers.get('Content-Type'), 'application/pdf');
      assert.match(response.headers.get('Content-Disposition'), /^inline;/);
      assert.equal(response.headers.get('ETag'), '"volume-two"');
      assert.equal(response.headers.get('Content-Length'), '243000000');
      assert.equal(response.headers.get('Cache-Control'), 'public, max-age=300');
    });
  }
});

test('upstream 404 and 416 remain errors rather than being relabelled as PDFs', async () => {
  for (const status of [404, 416]) {
    await mockedFetch(async () => new Response('upstream error', { status, headers: {
      'Content-Type': 'text/plain', 'Content-Range': 'bytes */84100000', 'Retry-After': '60'
    } }), async () => {
      const response = await worker.fetch(new Request(origin + path), {});
      assert.equal(response.status, status);
      assert.equal(response.headers.get('Content-Type'), 'text/plain');
      assert.equal(response.headers.get('Content-Disposition'), null);
      assert.equal(response.headers.get('Content-Range'), 'bytes */84100000');
      assert.equal(await response.text(), 'upstream error');
    });
  }
});

test('journal routes reject other names/methods without fetching or needing contribution credentials', async () => {
  await mockedFetch(async () => { throw new Error('Unexpected upstream request'); }, async () => {
    for (const name of ['other.pdf', 'Ugrakshatriya_Pratinidhi_Vol_03.pdf', 'constructor', '__proto__']) {
      const response = await worker.fetch(new Request(origin + '/api/documents/' + name), {});
      assert.equal(response.status, 404);
    }
    const response = await worker.fetch(new Request(origin + path, { method: 'POST' }), {});
    assert.equal(response.status, 405);
    assert.equal(response.headers.get('Allow'), 'GET, HEAD');
    assert.equal((await worker.fetch(new Request(origin + '/api/review'), {})).status, 503,
      'The public document route does not bypass review configuration/authentication');
  });
});

test('journal network failures return a bounded public error without leaking internals', async () => {
  await mockedFetch(async () => { throw new Error('private upstream information'); }, async () => {
    for (const method of ['GET', 'HEAD']) {
      const response = await worker.fetch(new Request(origin + path, { method }), {});
      assert.equal(response.status, 502);
      assert.equal((await response.text()).includes('private upstream'), false);
      if (method === 'HEAD') assert.equal(response.body, null);
    }
  });
});
