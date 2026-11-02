import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import worker, { encryptPushPayload, vapidAuthorization } from '../contributions/worker.mjs';
import { createLocalDatabase } from '../contributions/local-db.mjs';

const ORIGIN = 'https://heritage.example';
const KEY = 'test-editor-secret-with-more-than-32-characters-only';
const b64u = b => Buffer.from(b).toString('base64url');
const unb64u = s => new Uint8Array(Buffer.from(s, 'base64url'));

// RFC 8291, Appendix A: the published example must be reproduced exactly.
test('RFC 8291 aes128gcm test vector', async () => {
  const asPublic = 'BP4z9KsN6nGRTbVYI_c7VJSPQTBtkgcy27mlmlMoZIIgDll6e3vCYLocInmYWAmS6TlzAC8wEqKK6PBru3jl7A8';
  const asPrivate = 'yfWPiYE-n46HLnH0KqZOF1fJJU3MYrct3AELtAQ-oRw';
  const pub = unb64u(asPublic);
  const jwk = { kty: 'EC', crv: 'P-256', d: asPrivate, x: b64u(pub.slice(1, 33)), y: b64u(pub.slice(33)), ext: true };
  const privateKey = await crypto.subtle.importKey('jwk', jwk, { name: 'ECDH', namedCurve: 'P-256' }, true, ['deriveBits']);
  const publicKey = await crypto.subtle.importKey('raw', pub, { name: 'ECDH', namedCurve: 'P-256' }, true, []);
  const out = await encryptPushPayload('When I grow up, I want to be a watermelon',
    'BCVxsr7N_eNgVRqvHtD0zTZsEc6-VV-JvLexhqUzORcxaOzi6-AYWXvTBHm4bjyPjs7Vd8pZGH6SRpkNtoIAiw4', 'BTBZMqHH6r4Tts7J_aSIgg',
    { salt: unb64u('DGv6ra1nlYgDCS1FRnbzlw'), serverKeys: { privateKey, publicKey } });
  assert.equal(b64u(out), 'DGv6ra1nlYgDCS1FRnbzlwAAEABBBP4z9KsN6nGRTbVYI_c7VJSPQTBtkgcy27mlmlMoZIIgDll6e3vCYLocInmYWAmS6TlzAC8wEqKK6PBru3jl7A_yl95bQpu6cVPTpK4Mqgkf1CXztLVBSt2Ks3oZwbuwXPXLWyouBWLVWGNWQexSgSxsj_Qulcy4a-fN');
});

async function vapidEnv() {
  const pair = await crypto.subtle.generateKey({ name: 'ECDSA', namedCurve: 'P-256' }, true, ['sign', 'verify']);
  const jwk = await crypto.subtle.exportKey('jwk', pair.privateKey);
  const raw = new Uint8Array(await crypto.subtle.exportKey('raw', pair.publicKey));
  return { VAPID_PUBLIC_KEY: b64u(raw), VAPID_PRIVATE_KEY: jwk.d, VAPID_SUBJECT: 'mailto:editor@heritage.example', verifyKey: pair.publicKey };
}

test('VAPID authorisation is a valid ES256 token for the push service origin', async () => {
  const env = await vapidEnv();
  const header = await vapidAuthorization('https://fcm.googleapis.com/fcm/send/abc', env, Date.UTC(2026, 9, 6));
  const [, token, key] = header.match(/^vapid t=([^,]+), k=(.+)$/);
  assert.equal(key, env.VAPID_PUBLIC_KEY);
  const [h, c, s] = token.split('.');
  assert.deepEqual(JSON.parse(Buffer.from(h, 'base64url')), { typ: 'JWT', alg: 'ES256' });
  const claims = JSON.parse(Buffer.from(c, 'base64url'));
  assert.equal(claims.aud, 'https://fcm.googleapis.com'); assert.equal(claims.sub, env.VAPID_SUBJECT);
  assert.equal(claims.exp, Date.UTC(2026, 9, 6) / 1000 + 43200);
  assert.ok(await crypto.subtle.verify({ name: 'ECDSA', hash: 'SHA-256' }, env.verifyKey, unb64u(s), new TextEncoder().encode(`${h}.${c}`)));
});

// A browser-side subscription with real keys, so the test can decrypt what the worker sends.
async function browser(endpoint) {
  const pair = await crypto.subtle.generateKey({ name: 'ECDH', namedCurve: 'P-256' }, true, ['deriveBits']);
  const auth = crypto.getRandomValues(new Uint8Array(16));
  const p256dh = new Uint8Array(await crypto.subtle.exportKey('raw', pair.publicKey));
  return { pair, auth, json: { endpoint, keys: { p256dh: b64u(p256dh), auth: b64u(auth) } }, p256dh };
}
async function hkdf(salt, ikm, info, n) {
  const k = await crypto.subtle.importKey('raw', ikm, 'HKDF', false, ['deriveBits']);
  return new Uint8Array(await crypto.subtle.deriveBits({ name: 'HKDF', hash: 'SHA-256', salt, info }, k, n * 8));
}
// Independent receiver-side decryption written from RFC 8291 section 3.
async function decrypt(body, b) {
  body = new Uint8Array(body);
  const salt = body.slice(0, 16), idlen = body[20], asPublic = body.slice(21, 21 + idlen), cipher = body.slice(21 + idlen);
  const asKey = await crypto.subtle.importKey('raw', asPublic, { name: 'ECDH', namedCurve: 'P-256' }, false, []);
  const shared = new Uint8Array(await crypto.subtle.deriveBits({ name: 'ECDH', public: asKey }, b.pair.privateKey, 256));
  const te = new TextEncoder();
  const info = new Uint8Array([...te.encode('WebPush: info\0'), ...b.p256dh, ...asPublic]);
  const ikm = await hkdf(b.auth, shared, info, 32);
  const cek = await hkdf(salt, ikm, te.encode('Content-Encoding: aes128gcm\0'), 16);
  const nonce = await hkdf(salt, ikm, te.encode('Content-Encoding: nonce\0'), 12);
  const key = await crypto.subtle.importKey('raw', cek, 'AES-GCM', false, ['decrypt']);
  const plain = new Uint8Array(await crypto.subtle.decrypt({ name: 'AES-GCM', iv: nonce }, key, cipher));
  assert.equal(plain.at(-1), 2);
  return JSON.parse(new TextDecoder().decode(plain.slice(0, -1)));
}

async function makeEnv() {
  const db = createLocalDatabase();
  db.exec(readFileSync(new URL('../contributions/schema.sql', import.meta.url), 'utf8'));
  const v = await vapidEnv();
  return { EDITOR_KEY: KEY, CONTRIBUTIONS_DB: db, VAPID_PUBLIC_KEY: v.VAPID_PUBLIC_KEY, VAPID_PRIVATE_KEY: v.VAPID_PRIVATE_KEY, VAPID_SUBJECT: v.VAPID_SUBJECT };
}
async function call(env, path, { method = 'GET', token, body, origin = ORIGIN, ip = '192.0.2.9' } = {}) {
  const headers = new Headers({ Origin: origin, 'CF-Connecting-IP': ip });
  if (token) headers.set('Authorization', `Bearer ${token}`);
  if (body) { headers.set('Content-Type', 'application/json'); body = JSON.stringify(body); }
  const response = await worker.fetch(new Request(ORIGIN + path, { method, headers, body }), env);
  return { status: response.status, data: await response.json() };
}
const message = { en: { title: 'New article: Family histories', body: 'How Burdwan studies discuss Aguri families.', url: '/history.html#enterprise-and-social-mobility' },
  bn: { title: 'নতুন লেখা: পারিবারিক ইতিহাস', body: 'বর্ধমান-গবেষণায় আগুরী পরিবারের কথা।', url: '/bn/history.html' } };

test('notification service stays unavailable until every binding is configured', async () => {
  let r = await call({}, '/api/push/config'); assert.equal(r.data.available, false); assert.equal(r.data.public_key, undefined);
  const env = await makeEnv();
  r = await call({ ...env, VAPID_SUBJECT: 'not-a-contact' }, '/api/push/config'); assert.equal(r.data.available, false);
  r = await call({ ...env, VAPID_SUBJECT: 'x' }, '/api/push/subscribe', { method: 'POST', body: {} }); assert.equal(r.status, 503);
  r = await call(env, '/api/push/config'); assert.equal(r.data.available, true); assert.equal(r.data.public_key, env.VAPID_PUBLIC_KEY);
  r = await call(env, '/api/push/config', { origin: 'https://foreign.example' }); assert.equal(r.status, 403);
});

test('subscribe validates push services and keys, and unsubscribe removes the record', async () => {
  const env = await makeEnv();
  const b = await browser('https://fcm.googleapis.com/fcm/send/reader-1');
  let r = await call(env, '/api/push/subscribe', { method: 'POST', body: { subscription: { ...b.json, endpoint: 'https://evil.example/collect' } } });
  assert.equal(r.status, 400); assert.equal(r.data.error, 'unsupported_push_service');
  r = await call(env, '/api/push/subscribe', { method: 'POST', body: { subscription: { ...b.json, keys: { p256dh: 'abc', auth: 'def' } } } });
  assert.equal(r.status, 400);
  r = await call(env, '/api/push/subscribe', { method: 'POST', body: { subscription: b.json, language: 'bn' } });
  assert.equal(r.status, 200);
  r = await call(env, '/api/push/subscribe', { method: 'POST', body: { subscription: b.json, language: 'bn' } }); // repeat is harmless
  let row = await env.CONTRIBUTIONS_DB.prepare('SELECT count(*) AS n, max(language) AS lang FROM push_subscriptions').first();
  assert.equal(row.n, 1); assert.equal(row.lang, 'bn');
  const rotated = await browser('https://fcm.googleapis.com/fcm/send/reader-1-rotated');
  r = await call(env, '/api/push/subscribe', { method: 'POST', body: { subscription: rotated.json, replaces: b.json.endpoint } });
  row = await env.CONTRIBUTIONS_DB.prepare('SELECT count(*) AS n, max(language) AS lang, max(endpoint) AS e FROM push_subscriptions').first();
  assert.equal(row.n, 1); assert.equal(row.lang, 'bn'); assert.equal(row.e, rotated.json.endpoint);
  r = await call(env, '/api/push/unsubscribe', { method: 'POST', body: { endpoint: rotated.json.endpoint } });
  assert.equal(r.status, 200);
  row = await env.CONTRIBUTIONS_DB.prepare('SELECT count(*) AS n FROM push_subscriptions').first(); assert.equal(row.n, 0);
  r = await call(env, '/api/push/unsubscribe', { method: 'POST', body: { endpoint: rotated.json.endpoint }, origin: null });
  assert.equal(r.status, 403);
});

test('sending requires the editor key, delivers encrypted messages once, removes expired endpoints and spaces campaigns', async (t) => {
  const env = await makeEnv();
  const readers = [];
  for (const [i, lang] of [[1, 'en'], [2, 'bn'], [3, 'en']]) {
    const b = await browser(`https://updates.push.services.mozilla.com/wpush/v2/reader-${i}`);
    await call(env, '/api/push/subscribe', { method: 'POST', body: { subscription: b.json, language: lang } });
    readers.push({ ...b, lang });
  }
  const deliveries = [];
  const realFetch = globalThis.fetch;
  globalThis.fetch = async (url, init) => {
    deliveries.push({ url, init });
    return new Response(null, { status: String(url).endsWith('reader-3') ? 410 : 201 });
  };
  t.after(() => { globalThis.fetch = realFetch; });
  let r = await call(env, '/api/push/send', { method: 'POST', body: { campaign: 'family-histories-2026-10', ...message } });
  assert.equal(r.status, 401);
  r = await call(env, '/api/push/send', { method: 'POST', token: KEY, body: { campaign: 'bad', ...message, en: { ...message.en, url: 'https://elsewhere.example/' } } });
  assert.equal(r.status, 400);
  r = await call(env, '/api/push/send', { method: 'POST', token: KEY, body: { campaign: 'family-histories-2026-10', ...message, dry_run: true } });
  assert.equal(r.data.dry_run, true); assert.equal(r.data.subscribers, 3); assert.equal(deliveries.length, 0);
  r = await call(env, '/api/push/send', { method: 'POST', token: KEY, body: { campaign: 'family-histories-2026-10', ...message } });
  assert.deepEqual([r.data.sent, r.data.removed, r.data.failed, r.data.remaining], [2, 1, 0, 0]);
  assert.equal(deliveries.length, 3);
  for (const d of deliveries) {
    assert.equal(d.init.headers['Content-Encoding'], 'aes128gcm'); assert.match(d.init.headers.Authorization, /^vapid t=/);
    const reader = readers.find(x => x.json.endpoint === d.url);
    const payload = await decrypt(d.init.body, reader);
    assert.equal(payload.lang, reader.lang); assert.equal(payload.title, message[reader.lang].title);
    assert.equal(payload.url, message[reader.lang].url);
    assert.equal(payload.tag, 'family-histories-2026-10');
  }
  const left = await env.CONTRIBUTIONS_DB.prepare('SELECT count(*) AS n FROM push_subscriptions').first(); assert.equal(left.n, 2);
  // Retrying the same campaign sends nothing new; reusing the ID for other text is refused.
  r = await call(env, '/api/push/send', { method: 'POST', token: KEY, body: { campaign: 'family-histories-2026-10', ...message } });
  assert.equal(r.data.sent, 0); assert.equal(deliveries.length, 3);
  r = await call(env, '/api/push/send', { method: 'POST', token: KEY, body: { campaign: 'family-histories-2026-10', en: { ...message.en, title: 'Different' } } });
  assert.equal(r.status, 409); assert.equal(r.data.error, 'campaign_conflict');
  // A second campaign inside 24 hours is refused unless explicitly allowed.
  r = await call(env, '/api/push/send', { method: 'POST', token: KEY, body: { campaign: 'another-update', ...message } });
  assert.equal(r.status, 409); assert.equal(r.data.error, 'too_soon');
  r = await call(env, '/api/push/send', { method: 'POST', token: KEY, body: { campaign: 'another-update', ...message, audience: 'bn', allow_frequent: true } });
  assert.equal(r.data.sent, 1);
  r = await call(env, '/api/push/stats', { token: KEY });
  assert.equal(r.data.campaigns.length, 2);
});
