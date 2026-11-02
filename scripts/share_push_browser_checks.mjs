// Browser checks for the share button and opt-in notifications.
// Serves the built site and the real API handler (with a local SQLite D1 stand-in)
// on 127.0.0.1, then drives Chromium at desktop and mobile sizes.
import http from 'node:http';
import { readFile, stat } from 'node:fs/promises';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import assert from 'node:assert/strict';
import { chromium } from 'playwright';
import worker from '../contributions/worker.mjs';
import { createLocalDatabase } from '../contributions/local-db.mjs';

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const site = path.join(root, 'site');
const out = process.env.SHOT_DIR || path.join(root, 'shots');
const CANON = new URL(JSON.parse(await readFile(path.join(root, 'content/site-config.json'), 'utf8')).url).origin;
const mime = { '.html': 'text/html; charset=utf-8', '.js': 'text/javascript', '.css': 'text/css', '.webp': 'image/webp', '.jpg': 'image/jpeg', '.png': 'image/png', '.svg': 'image/svg+xml', '.ttf': 'font/ttf', '.json': 'application/json' };
const b64u = b => Buffer.from(b).toString('base64url');

async function makeEnv(withPush) {
  const db = createLocalDatabase();
  db.exec(await readFile(path.join(root, 'contributions/schema.sql'), 'utf8'));
  const env = { EDITOR_KEY: 'x'.repeat(40), CONTRIBUTIONS_DB: db };
  if (withPush) {
    const pair = await crypto.subtle.generateKey({ name: 'ECDSA', namedCurve: 'P-256' }, true, ['sign']);
    Object.assign(env, { VAPID_PUBLIC_KEY: b64u(await crypto.subtle.exportKey('raw', pair.publicKey)),
      VAPID_PRIVATE_KEY: (await crypto.subtle.exportKey('jwk', pair.privateKey)).d, VAPID_SUBJECT: 'mailto:editor@example.test' });
  }
  env.ASSETS = { async fetch(request) {
    let p = decodeURIComponent(new URL(request.url).pathname);
    if (p.endsWith('/')) p += 'index.html';
    let file = path.join(site, p);
    try { await stat(file); } catch { file += '.html'; }
    try { return new Response(await readFile(file), { headers: { 'Content-Type': mime[path.extname(file)] || 'application/octet-stream' } }); }
    catch { return new Response('Not found', { status: 404 }); }
  } };
  return env;
}
function serve(env, port) {
  return new Promise(resolve => {
    const server = http.createServer(async (req, res) => {
      const chunks = []; for await (const c of req) chunks.push(c);
      const body = chunks.length ? Buffer.concat(chunks) : undefined;
      const response = await worker.fetch(new Request(`http://127.0.0.1:${port}${req.url}`, { method: req.method, headers: req.headers, body: ['GET', 'HEAD'].includes(req.method) ? undefined : body }), env);
      res.writeHead(response.status, Object.fromEntries(response.headers));
      res.end(Buffer.from(await response.arrayBuffer()));
    });
    server.listen(port, '127.0.0.1', () => resolve(server));
  });
}

const pushEnv = await makeEnv(true), plainEnv = await makeEnv(false);
const s1 = await serve(pushEnv, 8791), s2 = await serve(plainEnv, 8792);
const BASE = 'http://127.0.0.1:8791', PLAIN = 'http://127.0.0.1:8792';
const browser = await chromium.launch({ executablePath: '/opt/pw-browsers/chromium', headless: true });
const log = [], issues = [];
const watch = page => { page.on('pageerror', e => issues.push(`${page.url()}: ${e.message}`)); page.on('console', m => { if (m.type() === 'error' && !/favicon|404/.test(m.text())) issues.push(`${page.url()}: ${m.text()}`); }); };

// 1. Desktop: fallback panel, correct links, copy, Escape.
{
  const context = await browser.newContext({ viewport: { width: 1440, height: 900 } });
  await context.grantPermissions(['clipboard-read', 'clipboard-write'], { origin: BASE });
  const page = await context.newPage(); watch(page);
  await page.goto(BASE + '/history.html');
  assert.equal(await page.evaluate(() => typeof navigator.share), 'undefined');
  const toggle = page.locator('.share-toggle');
  assert.ok(await toggle.isVisible()); assert.equal(await page.locator('.share-panel').isVisible(), false);
  await toggle.click();
  assert.equal(await toggle.getAttribute('aria-expanded'), 'true');
  assert.ok(await page.locator('.share-panel').isVisible());
  assert.equal(await page.evaluate(() => document.activeElement.dataset.share), 'whatsapp');
  const href = n => page.locator(`[data-share="${n}"]`).getAttribute('href');
  assert.equal(decodeURIComponent((await href('whatsapp')).split('text=')[1]), `The Aguris through history — ${CANON}/history`);
  assert.equal(decodeURIComponent((await href('facebook')).split('u=')[1]), `${CANON}/history`);
  assert.match(decodeURIComponent(await href('email')), new RegExp(`${CANON}/history$`));
  assert.equal(await page.locator('[data-share="whatsapp"]').getAttribute('rel'), 'noopener noreferrer');
  await page.screenshot({ path: `${out}/share-desktop-panel.png`, clip: { x: 0, y: 0, width: 1440, height: 900 } });
  await page.locator('[data-share="copy"]').click();
  await page.waitForFunction(() => document.querySelector('.share-status').textContent.length > 0);
  assert.equal(await page.locator('.share-status').innerText(), 'Link copied.');
  assert.equal(await page.evaluate(() => navigator.clipboard.readText()), `${CANON}/history`);
  await page.keyboard.press('Escape');
  assert.equal(await page.locator('.share-panel').isVisible(), false);
  assert.equal(await page.evaluate(() => document.activeElement.classList.contains('share-toggle')), true);
  // Outside click closes.
  await toggle.click(); await page.mouse.click(1300, 800); assert.equal(await page.locator('.share-panel').isVisible(), false);
  // Biography and Bengali pages share their own canonical address.
  await page.goto(BASE + '/person-hare-krishna-konar.html');
  assert.equal(await page.locator('.share').getAttribute('data-share-url'), `${CANON}/person-hare-krishna-konar`);
  assert.equal(await page.locator('meta[property="og:image"]').getAttribute('content'), `${CANON}/assets/social/person-hare-krishna-konar.jpg`);
  await page.goto(BASE + '/bn/history.html');
  assert.equal(await page.locator('.share-toggle').innerText(), 'শেয়ার করুন');
  assert.equal(await page.locator('.share').getAttribute('data-share-url'), `${CANON}/bn/history`);
  // Archive reader keeps its volume and scan.
  await page.goto(BASE + '/archives.html?volume=2&scan=5#reader');
  await page.locator('.share-toggle').click(); await page.locator('[data-share="copy"]').click();
  await page.waitForFunction(() => document.querySelector('.share-status').textContent.length > 0);
  assert.equal(await page.evaluate(() => navigator.clipboard.readText()), `${CANON}/archives?volume=2&scan=5`);
  // Pages without sharing.
  for (const p of ['/rights.html', '/contribute.html', '/review.html']) { await page.goto(BASE + p); assert.equal(await page.locator('.share').count(), 0, p); }
  log.push('Desktop 1440px: fallback panel, canonical links, copy, Escape/outside close, Bengali labels, archive deep link: pass');
  await context.close();
}
// 2. Mobile with a native share sheet.
{
  const context = await browser.newContext({ viewport: { width: 390, height: 844 }, isMobile: true, hasTouch: true, userAgent: 'Mozilla/5.0 (Linux; Android 14; Pixel 8) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/141.0 Mobile Safari/537.36' });
  await context.addInitScript(() => { window.__shared = []; navigator.share = async data => { window.__shared.push(data); if (window.__mode === 'abort') throw new DOMException('cancel', 'AbortError'); if (window.__mode === 'fail') throw new Error('x'); }; navigator.canShare = () => true; });
  const page = await context.newPage(); watch(page);
  await page.goto(BASE + '/person-benoy-choudhury.html');
  await page.locator('.share-toggle').tap();
  const shared = await page.evaluate(() => window.__shared);
  assert.equal(shared.length, 1); assert.equal(shared[0].url, `${CANON}/person-benoy-choudhury`); assert.ok(shared[0].title.length > 0);
  assert.equal(await page.locator('.share-panel').isVisible(), false);
  await page.evaluate(() => { window.__mode = 'abort'; }); await page.locator('.share-toggle').tap();
  assert.equal(await page.locator('.share-panel').isVisible(), false);
  await page.evaluate(() => { window.__mode = 'fail'; }); await page.locator('.share-toggle').tap();
  assert.ok(await page.locator('.share-panel').isVisible());
  await page.screenshot({ path: `${out}/share-mobile-fallback.png` });
  log.push('Mobile 390px: native share sheet used with canonical URL; cancel ignored; error falls back to panel: pass');
  await context.close();
}
// 3. Layout: no horizontal overflow at small widths with the panel open.
{
  const context = await browser.newContext(); const page = await context.newPage(); watch(page);
  for (const width of [320, 390, 768, 1440]) {
    await page.setViewportSize({ width, height: 800 });
    for (const p of ['/index.html', '/history.html', '/research.html', '/people.html', '/person-hare-krishna-konar.html', '/bn/person-hare-krishna-konar.html', '/bn/research.html', '/about.html']) {
      await page.goto(BASE + p); await page.locator('.share-toggle').click();
      const overflow = await page.evaluate(() => document.documentElement.scrollWidth > innerWidth + 1);
      if (overflow) issues.push(`${p} overflows at ${width}px with share panel open`);
      const box = await page.locator('.share-panel').boundingBox();
      if (box.x < 0 || box.x + box.width > width + 1) issues.push(`${p} share panel off-screen at ${width}px`);
    }
  }
  log.push('Layout at 320/390/768/1440px across 8 pages with panel open: checked');
  await context.close();
}
// 4. Without JavaScript the links remain usable.
{
  const context = await browser.newContext({ javaScriptEnabled: false }); const page = await context.newPage();
  await page.goto(BASE + '/history.html');
  assert.equal(await page.locator('.share-toggle').isVisible(), false);
  assert.ok(await page.locator('[data-share="whatsapp"]').isVisible());
  assert.equal(await page.locator('[data-notify]').isVisible(), false);
  log.push('No-JavaScript: plain share links visible, notification block hidden: pass');
  await context.close();
}
// 5. Notifications: opt-in, subscribe, push display, unsubscribe.
{
  const context = await browser.newContext({ viewport: { width: 1280, height: 900 } });
  await context.grantPermissions(['notifications'], { origin: BASE });
  // Headless Chromium cannot reach a real push service, so the browser-side
  // subscribe call is replaced with one holding real, valid encryption keys.
  await context.addInitScript(() => {
    if (!self.PushManager) return;
    const b64u = b => btoa(String.fromCharCode(...new Uint8Array(b))).replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '');
    let current = null;
    PushManager.prototype.getSubscription = async function () { return current; };
    PushManager.prototype.subscribe = async function (options) {
      window.__subscribeOptions = { userVisibleOnly: options.userVisibleOnly, keyLength: new Uint8Array(options.applicationServerKey).length };
      const pair = await crypto.subtle.generateKey({ name: 'ECDH', namedCurve: 'P-256' }, true, ['deriveBits']);
      const p256dh = b64u(await crypto.subtle.exportKey('raw', pair.publicKey)), auth = b64u(crypto.getRandomValues(new Uint8Array(16)));
      const endpoint = 'https://fcm.googleapis.com/fcm/send/browser-check-' + Math.random().toString(36).slice(2);
      current = { endpoint, toJSON: () => ({ endpoint, expirationTime: null, keys: { p256dh, auth } }), unsubscribe: async () => { current = null; return true; } };
      return current;
    };
  });
  const page = await context.newPage(); watch(page);
  await page.goto(BASE + '/bn/index.html');
  const block = page.locator('[data-notify]');
  await block.waitFor({ state: 'visible' });
  assert.equal(await page.evaluate(async () => (await navigator.serviceWorker.getRegistrations()).length), 0, 'no service worker before opting in');
  const button = page.locator('.notify-toggle');
  assert.equal(await button.innerText(), 'বিজ্ঞপ্তি চালু করুন');
  await block.scrollIntoViewIfNeeded(); await page.screenshot({ path: `${out}/notify-footer-bn.png`, clip: await block.boundingBox() });
  await button.click();
  await page.waitForFunction(() => document.querySelector('.notify-toggle').getAttribute('aria-pressed') === 'true');
  assert.deepEqual(await page.evaluate(() => window.__subscribeOptions), { userVisibleOnly: true, keyLength: 65 });
  let row = await pushEnv.CONTRIBUTIONS_DB.prepare('SELECT count(*) AS n, max(language) AS lang FROM push_subscriptions').first();
  assert.equal(row.n, 1); assert.equal(row.lang, 'bn');
  assert.equal(await button.innerText(), 'বিজ্ঞপ্তি বন্ধ করুন');
  // Deliver a push event to the real service worker and confirm what it displays.
  const sw = context.serviceWorkers()[0] || await context.waitForEvent('serviceworker');
  const shown = await sw.evaluate(async () => {
    const data = JSON.stringify({ title: 'নতুন লেখা', body: 'পারিবারিক ইতিহাস', url: '/bn/history.html', tag: 'check-1', lang: 'bn' });
    const event = new PushEvent('push', { data });
    self.dispatchEvent(event);
    await new Promise(r => setTimeout(r, 500));
    const list = await self.registration.getNotifications();
    return list.map(n => ({ title: n.title, body: n.body, tag: n.tag, lang: n.lang, url: n.data.url }));
  });
  assert.deepEqual(shown, [{ title: 'নতুন লেখা', body: 'পারিবারিক ইতিহাস', tag: 'check-1', lang: 'bn', url: '/bn/history.html' }]);
  await button.click();
  await page.waitForFunction(() => document.querySelector('.notify-toggle').getAttribute('aria-pressed') === 'false');
  row = await pushEnv.CONTRIBUTIONS_DB.prepare('SELECT count(*) AS n FROM push_subscriptions').first();
  assert.equal(row.n, 0);
  log.push('Notifications: hidden until config loads; no service worker before opt-in; subscribe stores language; push event displays localised notification; turning off deletes the record: pass');
  await context.close();
}
// 6. Permission refused: nothing stored.
{
  const context = await browser.newContext();
  await context.addInitScript(() => { Notification.requestPermission = async () => 'denied'; });
  const page = await context.newPage(); watch(page);
  await page.goto(BASE + '/index.html');
  await page.locator('.notify-toggle').click();
  await page.waitForFunction(() => document.querySelector('.notify-status').textContent.length > 0);
  assert.match(await page.locator('.notify-status').innerText(), /Nothing has been saved/);
  const row = await pushEnv.CONTRIBUTIONS_DB.prepare('SELECT count(*) AS n FROM push_subscriptions').first(); assert.equal(row.n, 0);
  log.push('Permission refused: clear message, nothing stored: pass');
  await context.close();
}
// 7. Service not configured, and local files: block stays hidden.
{
  const context = await browser.newContext(); const page = await context.newPage(); watch(page);
  await page.goto(PLAIN + '/index.html'); await page.waitForTimeout(500);
  assert.equal(await page.locator('[data-notify]').isVisible(), false);
  await page.goto('file://' + site + '/index.html'); await page.waitForTimeout(300);
  assert.equal(await page.locator('[data-notify]').isVisible(), false);
  assert.ok(await page.locator('.share-toggle').isVisible());
  log.push('Unconfigured server and file:// copy: notification block hidden; share still available: pass');
  await context.close();
}
await browser.close(); s1.close(); s2.close();
console.log(log.join('\n'));
if (issues.length) { console.log('ISSUES:\n' + [...new Set(issues)].join('\n')); process.exitCode = 1; }
