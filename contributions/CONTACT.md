# Contact page — production, 1 November 2026

The English `/contact` and Bengali `/bn/contact` pages use the existing design,
language switch, search, footer and Cloudflare Worker. Both are published and operational.
The form takes name, reply email, subject and a message of up to 5,000 characters.
No attachments are accepted. Messages are private contact enquiries, not grants
of permission to publish or add material to the heritage collection.

## Production delivery

The owner approved Resend delivery to a private server-configured inbox. The
verified sending domain is `notify.aguri-heritage.in`, using
`contact@notify.aguri-heritage.in`. The sending-only API key is restricted to this
domain. The receiving address and both provider/Turnstile secrets are encrypted
Pages bindings and are not in the public frontend or source files.

The account is on Resend Transactional Free (3,000/month, 100/day), with no paid
commitment. The managed Turnstile widget permits only `aguri-heritage.in`.

Production requires all of these server bindings. Do not put secret values in
HTML, JavaScript, source files, browser storage, screenshots or this document:

- Existing `CONTRIBUTIONS_DB` and `EDITOR_KEY` (used for limits and keyed hashes).
- `CONTACT_HOSTNAMES`: exact comma-separated permitted hostnames, no wildcard.
- `CONTACT_TURNSTILE_SITE_KEY`: public contact widget key.
- `CONTACT_TURNSTILE_SECRET_KEY`: secret for that widget.
- `CONTACT_DELIVERY_PROVIDER`: `resend`, only if the owner selects that service.
- `CONTACT_RESEND_API_KEY`: provider secret with appropriate sending scope.
- `CONTACT_FROM_EMAIL`: verified sender address; never a visitor-supplied address.
- `CONTACT_TO_EMAIL`: the owner's chosen fixed recipient address.

The additive `contact_requests` table was created once through the approved
Cloudflare D1 dashboard route and verified. The table stores
only UUID, keyed payload hash, pending/sent status and timestamp. Names, email
addresses and message contents are not stored in that table. Message contents
are transmitted to the selected email provider and receiving inbox after CAPTCHA
validation. No retention duration or reply deadline is promised on the public
page. The owner can define operational retention/deletion policies separately.

## Mandatory bot verification and abuse controls

`GET /api/contact/config` exposes only availability and the public sitekey.
Missing delivery or CAPTCHA configuration, known dummy keys, non-HTTPS requests
or an unlisted hostname leave the service unavailable. A failed or missing
verification never falls back to an unprotected submission.

`POST /api/contact` checks same-origin, JSON size, exact allowed fields, lengths,
email/header safety, required private-contact consent and an empty honeypot.
It permits ten attempts per IP per hour and one hundred new verified contacts
per day globally, using the existing private rate-limit table. Raw IP addresses
are not stored; only Cloudflare's trusted connecting-IP header is used.

The server calls Turnstile Siteverify, requires strict `success === true`, an
exact matching hostname and action `contact`, and fails closed on timeout,
malformed data, non-success HTTP status or mismatch. Both provider fetches use
Workers-supported `redirect: manual`; all redirect responses are rejected without
forwarding credentials. Tokens are single-use;
the client resets verification after each attempt while preserving text on errors.

Provider mail uses a fixed recipient/sender and plain text, with the visitor's
validated address only in Reply-To. UUID plus payload hashes and the provider's
idempotency key protect retries. An uncertain attempt older than 23 hours is
not resent automatically. A success means the provider accepted the message;
it is not proof of final inbox delivery. Delivery failures keep text on screen.

## Local preview and tests

The local-only preview harness uses official public Turnstile test keys and
mock mail, clearly labelled as a test. It is not production-ready or a real
message-delivery test. The production Worker has no test-mode bypass.
Do not publish the preview harness, test keys/configuration or preview screenshots
as proof of production CAPTCHA validation.

Run `node --test scripts/test_contact.mjs` and the existing contribution, push,
page-view and homepage-language regressions. For a site preview, build in an
isolated copy to preserve unrelated saved drafts. The final report records the
exact checked candidate files, screenshot paths and test results.

References:
- https://developers.cloudflare.com/turnstile/get-started/server-side-validation/
- https://developers.cloudflare.com/turnstile/troubleshooting/testing/
- https://developers.cloudflare.com/turnstile/reference/supported-languages/
- https://resend.com/docs/api-reference/emails/send-email
- https://resend.com/docs/dashboard/emails/idempotency-keys

## Activation evidence

Production deployment `91960f10-4b4a-4993-b14c-9a5a63eed5e8` completed on
1 November 2026. All 143 automated tests and the static site check passed.
One authorized message passed real Turnstile server verification and arrived in
the selected inbox at 11:03:21 UTC, with SPF, DKIM and DMARC passing. No additional
test messages were sent. English/Bengali navigation and desktop/mobile layouts
were checked. Private operational evidence is in the Codex task output folder,
not the published site. The final runtime fix changed only `_worker.js`; 1,005
other published files remained identical.
