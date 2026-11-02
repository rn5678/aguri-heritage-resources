# Opt-in notifications

Readers can choose to be notified when something substantial is published: a new article, a major research update or a new family profile. The feature is built into the existing Cloudflare Pages worker and D1 database. It adds **no paid service, no third-party script and no tracking**.

## How it works

| Part | File | Role |
| --- | --- | --- |
| Footer opt-in block | `build.py`, `assets/push.js`, `assets/style.css` | Hidden unless the browser supports web push *and* `/api/push/config` reports the service available. Nothing is registered or requested until the reader presses **Turn on notifications**; only then does the browser show its permission prompt. The same button turns notifications off and deletes the record. |
| Service worker | `push/sw.js` → copied to `site/sw.js` | Registered only after opt-in. Shows the message and opens the linked same-site page. It does not cache or intercept pages. |
| API | `contributions/worker.mjs` | `GET /api/push/config`, `POST /api/push/subscribe`, `POST /api/push/unsubscribe` (public, same-origin, rate-limited); `POST /api/push/send` and `GET /api/push/stats` (editor key). Messages are encrypted (RFC 8291) and signed with the site's VAPID key (RFC 8292) inside the worker. |
| Storage | `contributions/schema.sql` | `push_subscriptions` (endpoint, two public keys, language, dates, failure count), `push_campaigns`, `push_deliveries`. No name, email, IP address, user agent or reading history. |
| Sending | `scripts/send_notification.mjs` | Dry run by default; sends in batches of 40 until done. |
| Explanation for readers | About page, `#notifications` (both languages) | What readers receive, what is stored, how to turn it off, iPhone/iPad limitation. |

### Safeguards against duplicate or excessive messages

- Every campaign has an ID you choose (for example `family-histories-2026-10`). Each subscriber receives a campaign at most once; re-running the same file only completes unfinished batches.
- Re-using an ID with different text is refused.
- A new campaign within **24 hours** of the previous one is refused unless `--allow-frequent` is given (intended only for correcting an error in a message).
- The browser shows each campaign under one tag, so a repeated delivery replaces rather than duplicates the notification.
- Push services keep an undelivered message for at most 7 days (`TTL`), and a newer message with the same topic replaces an older undelivered one.
- Endpoints that the push service reports as gone (404/410) are deleted at once; endpoints that fail five times in a row are deleted.

## One-time activation (needs the project owner)

Nothing below has been done. It changes production settings, so it needs your approval.

1. **Generate keys** on your computer: `node scripts/generate_vapid_keys.mjs`. Save both values in your password manager.
2. **Database**: apply the updated `contributions/schema.sql` to the existing `aguri-heritage-contributions` D1 database (it only adds three tables with `CREATE TABLE IF NOT EXISTS`; existing contribution data is untouched).
3. **Cloudflare Pages → Settings → Variables and Secrets (Production)**:
   - `VAPID_PUBLIC_KEY` — plain text variable, the public value.
   - `VAPID_PRIVATE_KEY` — **Secret**, the private value. Never put it in files, URLs or chat.
   - `VAPID_SUBJECT` — plain text, a contact such as `mailto:you@example.com`. Push services use it to reach the sender if there is a problem; it is not shown to readers.
   - `CONTRIBUTIONS_DB` and `EDITOR_KEY` are already required by the contribution service.
4. **Rebuild and publish** as usual (`python3 build.py`, `python3 scripts/check_site.py`, `python3 scripts/prepare_cloudflare.py …`, upload `hosting/cloudflare/site`). The upload already contains `sw.js` and the updated `_worker.js`.
5. **Check**: `https://aguri-heritage.in/api/push/config` should return `"available": true` with a `public_key`. Then turn notifications on from your own browser and send yourself a test campaign (below) before announcing the feature.

Until step 3 is complete the footer block stays hidden and the API returns `available: false`, so publishing the code first is safe.

## Publishing workflow

The sending tool reads the production origin `https://aguri-heritage.in` from `content/site-config.json`; that configuration was published on 9 October 2026. Normal DNS/HTTPS resolution and the migration redirects were verified on 10 October 2026. The optional notification service remains inactive until its activation steps are completed. To target the existing host intentionally, pass `--site https://aguri-heritage.pages.dev`; migration redirects exclude `/api/` routes. Browser notification permissions and subscriptions are origin-specific; readers need to opt in on the new domain.

1. Publish the new article or update and confirm the page is live.
2. Copy `push/messages/example-family-histories.json` to a new file. Give it a new `campaign` ID; write a title (max 80 characters), a body (max 180) and a same-site `url` for each language. Leave a language out to send the other language's text to everyone; set `audience` to `en` or `bn` to reach only one edition's subscribers.
3. Dry run (nothing is sent; shows the audience size and the exact text):
   `AGURI_EDITOR_KEY='…' node scripts/send_notification.mjs push/messages/<file>.json`
4. Send: add `--send`. The script reports sent, expired and failed counts per batch. If it stops part-way, run the same command again.
5. Check totals at any time with `GET /api/push/stats` (editor key), or keep the script output.

Suggested editorial rule: notify only for new articles, substantial research updates and newly published family profiles; at most a few a month. Do not send promotional campaigns without a separate decision.

## Browser support and limits

- **Chrome, Edge, Firefox, Opera, Samsung Internet (desktop and Android)**: supported.
- **Safari on macOS** (Ventura or later): supported.
- **iPhone and iPad** (iOS/iPadOS 16.4 or later): supported only after the reader adds the site to the Home Screen and opens it from there. The footer explains this to iPhone/iPad visitors instead of showing a button.
- In-app browsers (for example inside some messaging apps) and private/incognito windows often do not support push; the block stays hidden.
- A reader who blocks notifications in browser settings sees an explanation; the site cannot override that choice.
- The offline copy opened from `site/index.html` cannot use notifications (browsers require HTTPS); sharing still works there.

## Costs and third parties

- Cloudflare Pages Functions and D1 free tiers cover this use. Each send request handles up to 40 subscribers to stay under the free plan's 50 outbound requests per invocation; the script simply makes more requests.
- Messages are delivered by the push service built into each reader's browser (Google Firebase Cloud Messaging for Chrome/Edge/Android, Mozilla for Firefox, Apple for Safari, Microsoft WNS for some Edge versions). These services receive only the encrypted message and the push address. No account, SDK or payment is needed.
- No paid service was purchased and no live campaign has been sent.

## Testing

- `node --test scripts/test_push.mjs` — RFC 8291 test vector reproduced exactly; VAPID token verified; subscribe/unsubscribe validation; encrypted delivery decrypted independently; once-only delivery, expired-endpoint removal, campaign conflict and 24-hour spacing.
- `node scripts/share_push_browser_checks.mjs` (needs Playwright and Chromium) — opt-in flow in Chromium, real service-worker push display, permission refusal, hidden block when unconfigured or opened from a file, and the share button.
- Not tested: delivery through real push services (needs production keys and a public HTTPS site), and real iPhone/Safari devices. Do this after activation with your own devices.
