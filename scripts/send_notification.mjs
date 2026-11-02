#!/usr/bin/env node
// Send one opt-in notification campaign through the site's own service.
//   AGURI_EDITOR_KEY=... node scripts/send_notification.mjs push/messages/<file>.json            (dry run)
//   AGURI_EDITOR_KEY=... node scripts/send_notification.mjs push/messages/<file>.json --send     (send)
// Options: --site https://aguri-heritage.in  --allow-frequent
// The configured production site is the default; --site can target the legacy host.
// The editor key is read from the environment so it never lands in shell history files or the repository.
import { readFile } from 'node:fs/promises';

const args = process.argv.slice(2);
const file = args.find(a => !a.startsWith('--'));
const flag = name => args.includes(name);
const option = (name, fallback) => { const i = args.indexOf(name); return i >= 0 ? args[i + 1] : fallback; };
const config = JSON.parse(await readFile(new URL('../content/site-config.json', import.meta.url), 'utf8'));
const site = new URL(option('--site', config.url)).origin;
const key = process.env.AGURI_EDITOR_KEY;
if (!file || !key) {
  console.error('Usage: AGURI_EDITOR_KEY=… node scripts/send_notification.mjs <message.json> [--send] [--site URL] [--allow-frequent]');
  process.exit(2);
}
const message = JSON.parse(await readFile(file, 'utf8'));
const body = { ...message, dry_run: !flag('--send'), allow_frequent: flag('--allow-frequent') };
async function post() {
  const response = await fetch(site + '/api/push/send', { method: 'POST', body: JSON.stringify(body),
    headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${key}`, Origin: site } });
  const data = await response.json().catch(() => ({}));
  if (!response.ok) { console.error(`Refused (${response.status}): ${data.error || ''} ${data.message || ''}`); process.exit(1); }
  return data;
}
let result = await post();
if (result.dry_run) {
  console.log(`DRY RUN — nothing was sent.\nCampaign: ${result.campaign}\nAudience: ${result.audience}\nSubscribers who would receive it: ${result.subscribers}`);
  console.log(JSON.stringify(result.preview, null, 2));
  console.log('\nRe-run with --send to deliver it.');
  process.exit(0);
}
let totals = { sent: 0, removed: 0, failed: 0 };
for (let round = 1; ; round++) {
  for (const k of Object.keys(totals)) totals[k] += result[k];
  console.log(`Batch ${round}: sent ${result.sent}, expired ${result.removed}, failed ${result.failed}, remaining ${result.remaining}`);
  if (!result.remaining || (result.sent + result.removed + result.failed) === 0) break;
  result = await post();
}
console.log(`Done. Sent ${totals.sent}; removed ${totals.removed} expired subscriptions; ${totals.failed} failed (retry later with the same file; nobody receives a message twice).`);
