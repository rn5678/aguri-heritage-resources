# Google-authenticated page comments — development candidate

This feature is **not enabled or deployed by this branch**. It extends the existing
Cloudflare Pages Worker and D1 database; it does not require Firebase, a new cloud
hosting project, or access to Gmail. Google authenticates commenters. Aguri Heritage
stores and moderates their comments. Signing in is not a guarantee against spam.

## Product scope

- Anyone can read approved comments. Google sign-in is required to post, report,
  view one's pending comments, or delete one's own comments.
- New comments are plain text, at most 2,000 characters, and pending until an
  editor approves them. Rejected/hidden/pending comments are not publicly listed.
- The public display name comes from the signed-in Google account. Never expose
  account email, Google subject identifier, session tokens or private moderation
  notes in public responses. Inform users before they agree to publish.
- English and Bengali versions of the same content share a stable page key and
  discussion. Comments are not automatically translated.
- Comments belong below public HTML content, not inside downloaded PDFs. Review,
  contact, submission and error pages are excluded. Existing no-login private
  contributions and their receipts remain separate.
- If comments are disabled or unavailable, articles remain readable. Google login
  code should load only after a reader chooses to sign in.

## Deployment prerequisites — owner review required

1. Review the comment publication/privacy wording and assign an editor to the
   moderation queue. Decide retention and handling of reports/deletion requests.
   Do not claim the existing contribution terms automatically cover comments.
2. In the Google Auth Platform, create or select a **web** OAuth client for this
   website with the owner's approval. Configure branding, support address,
   homepage/privacy links and authorized origins. Use the canonical
   `https://aguri-heritage.in` origin and explicitly approved local test origins;
   do not authorize arbitrary preview hosts. Basic identity is sufficient.
3. Confirm Cloudflare account usage/headroom, export a protected D1 backup, and
   review/apply the additive comments schema migration. No existing contributions,
   files, receipts, push subscriptions or page views should be rewritten.
4. Configure the comment client ID and session secret as specified in the
   implementation. Keep secrets in Cloudflare secret bindings, never GitHub
   source, URLs, browser storage or screenshots. Creating OAuth access or changing
   credential configuration is a separate approval step, not done by a build.
5. Keep `COMMENTS_ENABLED` unset until the migration, configuration, review and
   live sign-in checks are ready. The implementation must fail closed if required
   bindings are missing. Never enable a partially configured authentication path.
6. Follow `hosting/PIPELINE.md`: local checks, reviewed branch, required PR checks,
   authorized merge and verified deployment. The deployment tool fingerprints
   bindings; configuration changes must be planned separately rather than hidden
   in an ordinary publish operation. Do not bypass its drift protections.

## Security requirements

Google credentials must be verified server-side against Google's signing keys,
expected client ID, issuer, lifetime and login nonce. An email/name supplied by
JavaScript is not authentication. Only a verified stable subject identifies an
account. Session cookies must be Secure, HttpOnly, host-only and SameSite, with
bounded lifetime. Mutations require same-origin checks and CSRF protection.

Use bounded requests and database queries, bound SQL values, plain-text rendering,
account/IP limits, pagination, and no token logging. Moderator access remains
separate from commenter authentication. A Google login must not grant editor
rights. Review private moderation notes and report contents as untrusted text.

## Verification and release evidence

Run the full existing CI-equivalent checks with `python3 scripts/ci_build.py`,
including all Python and Node suites, source portability, generated page/link
checks and deployment-folder validation. Stage reviewed source before that
script, because it asserts builds leave tracked source unchanged.

Before enabling for readers, verify with real authorized Google accounts on the
canonical domain: Chrome and Safari desktop/mobile, popup cancellation, blocked
third-party cookies/FedCM behavior, expired session, logout, foreign-origin and
CSRF rejection, pending versus public visibility, moderation, author deletion,
reporting, throttling, and bilingual shared discussion. Local/mock identity tests
are not evidence that Google's production consent configuration works.

Measure existing contribution/contact/push regressions and confirm generated
public assets contain no database, secrets or private records. Disable comments
first for rollback; a code rollback must not drop new tables or erase comments.

## Cost and privacy

The current account plan and remaining allowance have not been verified in this
assessment. Usage includes Worker requests and D1 reads/writes/storage; indexing,
pagination and bounded text keep it small. Do not promise zero cost. Review the
account's limits before enabling, and add operational monitoring without silently
creating paid resources. Google receives authentication interaction when users
choose sign-in; disclose that alongside public comment display and deletion.

## References

- [Google Identity Services setup](https://developers.google.com/identity/gsi/web/guides/get-google-api-clientid)
- [Verify Google ID tokens on the server](https://developers.google.com/identity/gsi/web/guides/verify-google-id-token)
- [Cloudflare D1 pricing](https://developers.cloudflare.com/d1/platform/pricing/)
- [Existing contribution service](README.md)
- [GitHub publishing procedure](../hosting/PIPELINE.md)

## Configuration and API contract

The feature requires `COMMENTS_ENABLED=true`, the existing `CONTRIBUTIONS_DB`,
`ASSETS` and `EDITOR_KEY`, a web `GOOGLE_CLIENT_ID`, and a separately generated
`COMMENTS_SESSION_SECRET` of at least 32 characters (different from the editor
key). The client ID is public configuration, not a secret. The session secret is
server-only. Disabling the flag is a feature kill switch, not data deletion.

- `GET /api/comments/config`: availability, public client ID, length and terms version.
- `GET /api/comments/auth/nonce`: short-lived Google login challenge.
- `POST /api/comments/auth/google`: verify the Google credential and challenge;
  establish a one-hour session. No refresh/access token or mailbox access is needed.
- `GET /api/comments/me`, `POST /api/comments/auth/logout`: current session/logout.
- `GET /api/comments?page=KEY`: paginated approved comments.
- `GET /api/comments/mine?page=KEY`: the signed-in author's comments, including pending items.
- `POST /api/comments`: page, plain-text body, stable retry UUID, explicit consent,
  and the current terms version. Reusing a retry ID with changed content fails.
- `DELETE /api/comments/ID`: author-only deletion.
- `POST /api/comments/ID/report`: private editorial report from a signed-in user.
- `GET /api/comments/review`, `PATCH /api/comments/review/ID`: editor-only moderation.

Authenticated user mutations require the session's `X-CSRF-Token`. The existing
editor bearer key remains in memory only and must never be embedded in public
comment JavaScript. API routes are same-origin and return private/no-store
responses. Comments in the first version are not server-rendered or a substitute
for editorial article content/search indexing.

The additive migration file is `migrations/2026-11-09-comments.sql`; the same
schema is included in `schema.sql` for new/local databases. Existing databases
need the migration before enablement. Changing `COMMENTS_SESSION_SECRET`
invalidates sessions without changing stable author identity. Moderator writes
require the current comment `version`; stale decisions return a conflict rather
than overwriting another editor's decision. Review rows include private reports.

## Development verification boundaries

`node --test scripts/test_comments.mjs` uses generated RSA signatures and a local
mock of Google's fixed JWKS response; it exercises the real token verifier, not
an authentication bypass. `scripts/comments_browser_checks.cjs` is an optional
Playwright/Chromium suite whose Google and API traffic is fully mocked. It is
not production provider validation. In the development runtime used for this
branch, Chromium could not launch because socket creation was denied, so that
browser suite has not been executed there. Run it in a capable local environment
before release, as well as the real Google sign-in checks above. No production
Google accounts, cookies, comments or Cloudflare configuration were changed.
