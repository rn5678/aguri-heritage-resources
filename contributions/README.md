# Community contribution service

The bilingual site accepts stories, documents, corrections, and private rights
enquiries through a review queue. A contributor needs no account or email address. Each accepted
submission receives a private receipt token for checking its status and sending
up to 20 follow-up messages. Editors use a separate secret key. Changing a
review status never edits or publishes the website's articles.

The site's original content uses **All rights reserved**, with custom reuse and
contributor terms. New submissions must expressly accept the applicable terms
version. Story/document/correction consent is the limited permission described
in the contributor terms, not an open licence or a transfer of ownership.
Rights enquiries (permission, attribution, or removal requests) give permission
only for private handling and response; they grant no publication licence.

## Production setup

1. Create a Cloudflare D1 database and apply `contributions/schema.sql` to it.
   The schema is safe to apply repeatedly to this initial release's database.
   The 2026-10-04 rights/terms update needs **no database migration**: deploy
   the updated form and Worker together. Existing submissions and receipts
   remain valid without being relabelled as accepting new terms.
2. Bind the database to the Pages project as **`CONTRIBUTIONS_DB`**.
3. Configure **`EDITOR_KEY`** as a secret environment binding. Generate at least
   32 random bytes and encode them as hex or base64; the Worker rejects keys
   shorter than 32 characters. Keep the key in a password manager, never in
   published files, source control, URLs, browser storage, or screenshots.
4. Place `contributions/worker.mjs` in the publish root as **`_worker.js`**.
   The build/deploy process must copy only this server entry point; the schema,
   local database, test scripts, and this directory are not public assets.
5. Ensure the Pages project uses advanced-mode routing so the Worker receives
   `/api/*` requests. All non-API public pages and assets are passed through
   `env.ASSETS.fetch`. Redeploy after changing production bindings.
6. If using Turnstile, configure both **`TURNSTILE_SITE_KEY`** (public) and
   **`TURNSTILE_SECRET_KEY`** (secret). Add the production hostname to the
   widget. For the custom-domain migration, allow `aguri-heritage.in` and retain
   the existing `aguri-heritage.pages.dev` hostname while it is in use.
   Configuring only one disables contribution APIs. With neither set,
   the honeypot, upload validation, and rate limits still apply.

`GET /api/config` reports `available: false` until the database and valid secret
bindings are present. Other API routes then return 503. Config checks bindings,
not database connectivity; an unavailable or uninitialized database fails
closed when an operation is attempted. Never show a successful submission
until the server returns a receipt.

For production, keep the D1 database region, Cloudflare account access, backup
policy, and deletion requests under the project owner's control. Attachments,
email addresses, follow-ups, and internal notes are private editorial records.

## Local runtime and tests

Node 24 includes `node:sqlite`; no packages need to be installed. The exported
`LocalD1` class and `createLocalDatabase()` factory in `local-db.mjs` implement
the D1 operations used by the Worker. A file-backed instance persists local
submissions and applies the schema automatically; `:memory:` keeps tests
isolated. This adapter is for local development, not deployment.

Run the regression suite from the project root:

```sh
node --test scripts/test_contributions.mjs
```

The main project also provides `scripts/serve_contributions.mjs` for a local
site and API preview. Keep its database and editor key outside `site/` and
outside the public publish directory. Mutation requests made directly to the
Worker must include an `Origin` header matching the request URL origin.

## API contract

All API responses use `Cache-Control: no-store, private`, `nosniff`, `noindex`,
and a restrictive content security policy. Cross-origin API access is rejected;
no cross-origin sharing headers are emitted. Tokens are accepted only in the
`Authorization: Bearer …` header, never query parameters.

| Route | Authentication | Purpose |
| --- | --- | --- |
| `GET /api/config` | None | Availability, upload limits, optional Turnstile site key |
| `POST /api/contributions` | None | Multipart submission; returns private receipt |
| `GET /api/contributions/:id` | Receipt token | Type, title, status, dates, public note, published article link |
| `POST /api/contributions/:id/reply` | Receipt token | JSON `{message}` follow-up |
| `GET /api/review` | Editor key | Filter by `status`, literal text `q`, and opaque `before` cursor |
| `GET /api/review/:id` | Editor key | User-supplied details, consent evidence, attachment metadata, audit history, replies |
| `PATCH /api/review/:id` | Editor key | Optimistic status/note update with current `version` |
| `GET /api/review/:id/files/:fileId` | Editor key | Authenticated attachment download |

Multipart fields:

| Field | Rule |
| --- | --- |
| `client_id` | UUID, reused unchanged only when retrying the same submission |
| `type` | `story`, `document`, `correction`, or private `rights` enquiry |
| `title` | Required; at most 160 characters |
| `description` | Required; at most 12,000 characters |
| `contributor_name` | Optional; at most 160 characters |
| `email` | Optional; at most 254 characters |
| `place`, `credit` | Place at most 160 characters; credit `yes` or `no` (blank becomes `no`) |
| `date_text` | Optional; at most 100 characters |
| `source_url` | Optional HTTP(S) source; at most 2,000 characters |
| `source_page` | Optional same-site page path/URL; at most 2,000 characters |
| `language` | `en` or `bn` |
| `consent` | Must be `yes`; acceptance applies to the selected submission type |
| `terms_version` | New submissions must send `2026-10-04`; stale/missing versions return `terms_version_required` |
| `attachment_rights` | Must be `yes` with attachments; for rights enquiries this acknowledges private evidence handling, not a publication grant |
| `website` | Honeypot; must be empty |
| `attachments` | Up to three JPEG, PNG, WebP, PDF or UTF-8 TXT files |
| `cf-turnstile-response` | Required only when Turnstile is configured |

Named public credit requires a nonempty contributor name. `credit=no` means
the editor may use the name privately to review the contribution but should
publish it anonymously if publication is otherwise permitted. Rights enquiries
always store `credit=no` and must remain private, regardless of this field.
`source_page` identifies the existing article being
corrected; `source_url` may point to an external supporting source.

The initial history record stores server-written JSON with `kind` equal to
`terms-acceptance`, the accepted `terms_version`, `purpose` (`contribution` or
`rights-enquiry`), original API `type`, server acceptance timestamp, and form
language. It is committed atomically with the submission and files. No API can
edit that record. Editor detail exposes it separately as `consent_info`:

```json
{"status":"recorded","terms_version":"2026-10-04","purpose":"contribution","accepted_at":"2026-10-04T00:00:00.000Z","language":"en"}
```

Legacy records expose `status: "legacy"` and null values for all other consent
evidence fields. Their existing `consent=yes` field is **not** evidence of
accepting the current terms, and editors must not assume expanded permissions.
The initial JSON note is omitted from the displayed history because the same
evidence is returned in `consent_info`; later editor history is unchanged.

For compatibility with the existing database's type constraint, a rights enquiry
uses storage type `correction` plus its authoritative initial history record
identifying API type `rights` and purpose `rights-enquiry`. Every API read
surface restores `rights`; publication checks read the same initial record.
Raw database exports must interpret this evidence too and must never treat
every stored correction as a publication contribution. Keep this record intact
when backing up, restoring, or exporting submissions. No schema rebuild or
production data rewrite is needed for this update.

Each file is limited to 1,500,000 bytes. The full multipart body is limited to
5,000,000 bytes by a streaming reader, even if Content-Length is missing or
incorrect. The file contents must match their declared MIME type; filenames
are normalized and sanitized. Each file has a separate D1 BLOB row under
2 MB. Files are never served inline. Signature checks are not malware scanning;
an editor should treat submitted documents as untrusted files.

Status values are `received`, `under_review`, `needs_information`, `approved`,
`published`, and `declined`. An update takes `status`, `public_note`,
`internal_note`, `published_url`, and the latest integer `version`. A stale
version returns 409 without changing the contribution or its history. Both
notes are limited to 5,000 characters. Public receipt responses never include
contact details, internal notes, attachment metadata, or reply contents.

Rights enquiries cannot move to `approved` or `published`, or have any
`published_url`, even through a direct authenticated API request. Use
`under_review`, `needs_information`, or `declined` to handle these private
messages. A `public_note` is visible only to the holder of that private receipt;
the name does not mean the note is published on the website.

To mark an item published, first add the accepted material to a public article
and deploy it. Then provide the existing same-site article URL, such as
`/history` or `/bn/history.html`. The Worker checks that `ASSETS` serves a real
HTML article whose `body[data-page]` matches that path, rejecting missing
articles, fallback pages, administrative pages, and external URLs.

## Reliability and abuse controls

- A D1 batch atomically creates the contribution, all attachment rows, and the
  initial history entry. Capacity failure rolls everything back.
- Editor history is recorded by a database trigger in the update transaction.
  Follow-ups atomically increment the record version so an editor must reload
  before overwriting a record changed by new information.
- The same `client_id` and identical content return the original receipt.
  Changed content with an already-used reference returns 409. Concurrent
  retries cannot create duplicate submissions or attachments.
- The accepted terms version is part of new payload hashes. A changed or
  omitted version on a retry of a versioned submission returns 409. Identical
  legacy retries still return the original receipt, including when the updated
  form supplies a terms version, without writing new acceptance evidence or
  extending old permissions. New unversioned submissions are rejected.
- Receipt tokens are HMAC-derived from `EDITOR_KEY` and the UUID, and only
  token hashes are stored. Existing receipts still work after rotating the
  editor key. Retrying an old upload after rotation needs its original receipt
  token as bearer authentication; without it, the service asks the contributor
  to use the original receipt rather than issuing a different one.
- Submission attempts: 10 per IP per hour. New accepted-submission attempts:
  100 globally per day. Receipt reads/auth attempts: 120 per IP per hour.
  Follow-ups: 10 per IP per hour and 20 per submission in total. Failed editor
  logins: 10 per IP per hour; a valid editor key remains usable.
- IP identities are HMAC-hashed with the editor secret before storage. The
  service trusts only Cloudflare's `CF-Connecting-IP` header, not arbitrary
  forwarded-IP headers. Counters use atomic upserts, and old counter rows are
  cleaned after successful submissions. The daily limit counts attempts after
  validation, including a capacity failure or a concurrent retry race.
- A database-enforced 200,000,000-byte attachment capacity prevents concurrent
  uploads from exceeding the cap. There is no public deletion API; deleting a
  contribution as an authorized database maintenance operation cascades to its
  attachments, history and replies and releases attachment capacity.
- Secrets and raw SQL/database errors never appear in API responses. Queries
  bind all user values rather than interpolating them into SQL.

Cloudflare references: [D1 batch transactions](https://developers.cloudflare.com/d1/worker-api/d1-database/),
[prepared statements](https://developers.cloudflare.com/d1/worker-api/prepared-statements/),
and [Turnstile server validation](https://developers.cloudflare.com/turnstile/get-started/server-side-validation/).


## Notification routes (added 6 October 2026)

The same worker serves opt-in web push notifications under `/api/push/*`. They require `VAPID_PUBLIC_KEY`, `VAPID_PRIVATE_KEY` (Secret) and `VAPID_SUBJECT` in addition to `CONTRIBUTIONS_DB` and `EDITOR_KEY`, and the three push tables in `schema.sql`. See `push/README.md`. Tests: `node --test scripts/test_push.mjs`.

## Private Contact Us form — unpublished draft

The separate `/api/contact` draft uses mandatory Turnstile verification and
fixed-recipient mail delivery. It does not add enquiries to the public-content
review queue or accept publication permissions. It remains disabled without
complete contact-specific server bindings. No live resources have been changed.
See [CONTACT.md](CONTACT.md) before enabling it; the owner must select the
receiving inbox, sender and delivery provider.

## Google-authenticated page comments — development only

A separate, disabled-by-default comments feature is being prepared for public
HTML pages. It does not change anonymous private contribution submissions or
editor receipt handling. See [COMMENTS.md](COMMENTS.md) for scope, setup gates,
privacy, post-publication removal and verification requirements. Do not enable it merely by
publishing this branch; Google configuration and the additive database migration
require separate review.
