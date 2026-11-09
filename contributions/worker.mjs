// Cloudflare Pages advanced-mode worker. Copy this file to the publish root as
// _worker.js; never copy the schema, local database, or editor secret there.
const MAX_BODY = 5_000_000;
const MAX_FILE = 1_500_000;
const MAX_FILES = 3;
const INLINE_FILE_TYPES = new Set(['image/jpeg', 'image/png', 'image/webp', 'application/pdf', 'text/plain']);
const JOURNAL_DOCUMENTS = Object.freeze(Object.fromEntries([1, 2].map(number => {
  const name = `Ugrakshatriya_Pratinidhi_Vol_${String(number).padStart(2, '0')}.pdf`;
  return [`/api/documents/${name}`, `https://github.com/rn5678/aguri-heritage-resources/releases/download/journals-v1/${name}`];
})));
const TERMS_VERSION = '2026-10-04';
const STATUSES = ['received', 'under_review', 'needs_information', 'approved', 'published', 'declined'];
// The first history record is written atomically with the submission and cannot
// be edited through the API. Keeping acceptance there avoids a live DB migration.
const ACCEPTANCE_NOTE = '(SELECT note FROM contribution_history WHERE contribution_id=contributions.id ORDER BY rowid LIMIT 1)';
const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[1-8][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;
const encoder = new TextEncoder();
const SECURITY = {
  'Cache-Control': 'no-store, private',
  'X-Robots-Tag': 'noindex, nofollow, noarchive',
  'X-Content-Type-Options': 'nosniff',
  'Referrer-Policy': 'no-referrer',
  'Content-Security-Policy': "default-src 'none'; frame-ancestors 'none'",
};

class ApiError extends Error {
  constructor(status, code, message) { super(message); this.status = status; this.code = code; }
}
function fail(status, code, message) { throw new ApiError(status, code, message); }
function json(value, status = 200, extra = {}) {
  return new Response(JSON.stringify(value), { status, headers: { ...SECURITY, 'Content-Type': 'application/json; charset=utf-8', ...extra } });
}
function configured(env) {
  return !!env.CONTRIBUTIONS_DB && typeof env.EDITOR_KEY === 'string' && env.EDITOR_KEY.length >= 32
    && !!env.TURNSTILE_SECRET_KEY === !!env.TURNSTILE_SITE_KEY;
}
function stmt(env, sql, ...args) { const s = env.CONTRIBUTIONS_DB.prepare(sql); return args.length ? s.bind(...args) : s; }
function rows(result) { return result.results || []; }
function hex(bytes) { return [...new Uint8Array(bytes)].map(b => b.toString(16).padStart(2, '0')).join(''); }
async function digest(value) { return hex(await crypto.subtle.digest('SHA-256', typeof value === 'string' ? encoder.encode(value) : value)); }
async function hmac(secret, value) {
  const key = await crypto.subtle.importKey('raw', encoder.encode(secret), { name: 'HMAC', hash: 'SHA-256' }, false, ['sign']);
  return hex(await crypto.subtle.sign('HMAC', key, encoder.encode(value)));
}
async function equal(a, b) {
  const left = await digest(a), right = await digest(b);
  let difference = 0;
  for (let i = 0; i < left.length; i++) difference |= left.charCodeAt(i) ^ right.charCodeAt(i);
  return difference === 0;
}
function bearer(request) {
  const auth = request.headers.get('Authorization') || '';
  return auth.startsWith('Bearer ') && auth.length < 1024 ? auth.slice(7) : '';
}
function validateOrigin(request) {
  const origin = request.headers.get('Origin');
  const expected = new URL(request.url).origin;
  if ((origin && origin !== expected) || request.headers.get('Sec-Fetch-Site') === 'cross-site')
    fail(403, 'origin_rejected', 'Use this service from the heritage website.');
  if (!['GET', 'HEAD'].includes(request.method) && origin !== expected)
    fail(403, 'origin_required', 'A same-site Origin header is required.');
}
async function boundedBody(request, limit) {
  const length = request.headers.get('Content-Length');
  if (length && (!/^\d+$/.test(length) || Number(length) > limit)) fail(413, 'body_too_large', 'The request is too large.');
  const reader = request.body?.getReader();
  if (!reader) return new Uint8Array();
  let size = 0;
  const parts = [];
  try {
    for (;;) {
      const { done, value } = await reader.read();
      if (done) break;
      size += value.byteLength;
      if (size > limit) { await reader.cancel(); fail(413, 'body_too_large', 'The request is too large.'); }
      parts.push(value);
    }
  } finally { reader.releaseLock(); }
  const out = new Uint8Array(size);
  let at = 0;
  for (const part of parts) { out.set(part, at); at += part.byteLength; }
  return out;
}
async function jsonBody(request, limit = 40_000) {
  if (!(request.headers.get('Content-Type') || '').toLowerCase().startsWith('application/json'))
    fail(415, 'content_type', 'Send JSON for this request.');
  try {
    const data = JSON.parse(new TextDecoder('utf-8', { fatal: true }).decode(await boundedBody(request, limit)));
    if (!data || typeof data !== 'object' || Array.isArray(data)) fail(400, 'invalid_json', 'A JSON object is required.');
    return data;
  } catch (error) {
    if (error instanceof ApiError) throw error;
    fail(400, 'invalid_json', 'The request could not be read.');
  }
}
function field(data, name, max, required = false) {
  const value = data instanceof FormData ? data.get(name) : data[name];
  if (value == null && !required) return '';
  if (typeof value !== 'string') fail(400, 'invalid_field', `Check ${name}.`);
  const text = value.trim().normalize('NFC');
  if (text.length > max || (required && !text) || /[\u0000-\u0008\u000b\u000c\u000e-\u001f\u007f]/.test(text))
    fail(400, 'invalid_field', `Check ${name}; the limit is ${max} characters.`);
  return text;
}

// Aggregate page loads only: no visitor identifiers, IP buckets or event log.
const pageViewSchemaPromises = new WeakMap();
async function ensurePageViewSchema(env) {
  const database = env.CONTRIBUTIONS_DB;
  let pending = pageViewSchemaPromises.get(database);
  if (!pending) {
    // This feature owns only this additive table. Validation happens first;
    // concurrent first requests share initialization, and failures can retry.
    pending = Promise.resolve().then(async () => {
      const result = await stmt(env, `CREATE TABLE IF NOT EXISTS page_views (
  page TEXT PRIMARY KEY,
  views INTEGER NOT NULL DEFAULT 0 CHECK (views >= 0)
);`).run();
      if (result?.success === false) throw new Error('Page view initialization failed');
    }).catch(error => {
      if (pageViewSchemaPromises.get(database) === pending) pageViewSchemaPromises.delete(database);
      throw error;
    });
    pageViewSchemaPromises.set(database, pending);
  }
  await pending;
}

function pageViewPath(value) {
  if (typeof value !== 'string' || value.length > 180 || /[%?#\\\s]/.test(value))
    fail(400, 'invalid_page', 'Choose a public page on this website.');
  if (value === '/') return '/';
  if (value === '/bn' || value === '/bn/') return '/bn/';
  const match = value.match(/^\/(bn\/)?([a-z0-9]+(?:-[a-z0-9]+)*)(?:\.html)?\/?$/);
  if (!match || /^(?:review|404|editor|admin)$/.test(match[2]))
    fail(400, 'invalid_page', 'Choose a public page on this website.');
  const prefix = match[1] ? '/bn/' : '/';
  return prefix + (match[2] === 'index' ? '' : match[2]);
}

async function validateCountedPage(page, request, env) {
  const origin = new URL(request.url).origin;
  let target = new URL(page, origin);
  let response;
  for (let hop = 0; hop < 3; hop++) {
    response = await env.ASSETS.fetch(new Request(target, { method: 'GET', redirect: 'manual' }));
    if (![301, 302, 307, 308].includes(response.status)) break;
    const location = response.headers.get('Location');
    if (!location) fail(404, 'page_not_found', 'This public page could not be found.');
    const destination = new URL(location, target);
    if (destination.origin !== origin || destination.username || destination.password
        || destination.search || destination.hash || hop === 2
        || pageViewPath(destination.pathname) !== page)
      fail(404, 'page_not_found', 'This public page could not be found.');
    target = destination;
  }
  if (response.status !== 200 || !(response.headers.get('Content-Type') || '').toLowerCase().includes('text/html'))
    fail(404, 'page_not_found', 'This public page could not be found.');
  const html = new TextDecoder().decode(await boundedBody(response, MAX_BODY));
  const markers = [...html.matchAll(/<[a-z][^>]*\sdata-page-views\s*=\s*(["'])(.*?)\1[^>]*>/gi)];
  if (markers.length !== 1 || markers[0][2] !== page)
    fail(404, 'page_not_found', 'This public page could not be found.');
}

async function pageViews(request, env) {
  if (!['GET', 'POST'].includes(request.method))
    return json({ error: 'method_not_allowed', message: 'Use GET or POST for this service.' }, 405, { Allow: 'GET, POST' });
  if (!env.CONTRIBUTIONS_DB || !env.ASSETS)
    fail(503, 'service_unavailable', 'Page views are not available yet.');
  const url = new URL(request.url);
  let value;
  if (request.method === 'GET') {
    if ([...url.searchParams].length !== 1 || !url.searchParams.has('page'))
      fail(400, 'invalid_page', 'Choose a public page on this website.');
    value = url.searchParams.get('page');
  } else {
    if (url.search) fail(400, 'invalid_page', 'Choose a public page on this website.');
    const data = await jsonBody(request, 1024);
    if (Object.keys(data).length !== 1 || !Object.hasOwn(data, 'page'))
      fail(400, 'invalid_page', 'Choose a public page on this website.');
    value = data.page;
  }
  const page = pageViewPath(value);
  await validateCountedPage(page, request, env);
  await ensurePageViewSchema(env);
  if (request.method === 'GET') {
    const row = await stmt(env, 'SELECT views FROM page_views WHERE page=?', page).first();
    return json({ page, views: row?.views ?? 0 });
  }
  const row = await stmt(env, `INSERT INTO page_views(page,views) VALUES(?,1)
    ON CONFLICT(page) DO UPDATE SET views=page_views.views+1 RETURNING views`, page).first();
  return json({ page, views: row.views });
}

function webUrl(value, name, origin, allowPath = false) {
  if (!value) return '';
  let url;
  try { url = allowPath ? new URL(value, origin) : new URL(value); } catch { fail(400, 'invalid_url', `Check ${name}.`); }
  if (!['http:', 'https:'].includes(url.protocol) || url.username || url.password || /[\r\n\\]/.test(value))
    fail(400, 'invalid_url', `Check ${name}.`);
  return value;
}
async function limit(env, request, kind, count, seconds = 3600, global = false) {
  const now = Math.floor(Date.now() / 1000), window = Math.floor(now / seconds);
  // Only Cloudflare's trusted connection header is used; arbitrary forwarding
  // headers cannot rotate a caller's rate-limit identity. No raw IP is stored.
  const identity = global ? 'global' : await hmac(env.EDITOR_KEY, `ip:${request.headers.get('CF-Connecting-IP') || 'local'}`);
  const bucket = `${kind}:${identity}:${window}`;
  const result = await stmt(env, `INSERT INTO contribution_rate_limits(bucket,count,expires_at) VALUES(?,1,?)
    ON CONFLICT(bucket) DO UPDATE SET count=count+1 WHERE count < ? RETURNING count`, bucket, (window + 1) * seconds, count).first();
  if (!result) fail(429, 'rate_limited', 'Too many requests. Please try again later.');
}
async function editor(request, env) {
  if (await equal(bearer(request), env.EDITOR_KEY)) return;
  await limit(env, request, 'editor-failed', 10);
  fail(401, 'editor_auth_required', 'An editor key is required.');
}
async function receipt(request, env, id) {
  await limit(env, request, 'receipt', 120);
  const token = bearer(request);
  const row = await stmt(env, `SELECT *,${ACCEPTANCE_NOTE} AS acceptance_note FROM contributions WHERE id=?`, id).first();
  if (!row || !token || !(await equal(await digest(token), row.token_hash)))
    fail(404, 'receipt_not_found', 'The contribution or receipt could not be found.');
  return { ...row, type: submissionType(row) };
}
function publicRecord(row) {
  const { id, type, title, status, created_at, updated_at, public_note, published_url } = row;
  return { id, type, title, status, created_at, updated_at, public_note, published_url };
}
function acceptance(row) {
  try {
    const value = JSON.parse(row.acceptance_note);
    if (value.kind !== 'terms-acceptance' || !/^\d{4}-\d{2}-\d{2}$/.test(value.terms_version)
        || !['story', 'document', 'correction', 'rights'].includes(value.type)
        || value.purpose !== (value.type === 'rights' ? 'rights-enquiry' : 'contribution')
        || !['en', 'bn'].includes(value.language) || !/^\d{4}-\d{2}-\d{2}T[\d:.]+Z$/.test(value.accepted_at)) return null;
    return value;
  } catch { return null; }
}
function submissionType(row) { return acceptance(row)?.type || row.type; }
function consentInfo(row) {
  const value = acceptance(row);
  return value ? { status: 'recorded', terms_version: value.terms_version, purpose: value.purpose, accepted_at: value.accepted_at, language: value.language }
    : { status: 'legacy', terms_version: null, purpose: null, accepted_at: null, language: null };
}
function safeName(name, ext) {
  const base = String(name).split(/[\\/]/).pop().replace(/\.[^.]*$/, '').normalize('NFC')
    .replace(/[^\p{L}\p{N} ._-]/gu, '_').replace(/^\.+|\.+$/g, '').trim().slice(0, 100) || 'attachment';
  return `${base}.${ext}`;
}
async function fileRecord(file) {
  if (!file || typeof file.arrayBuffer !== 'function') fail(400, 'invalid_attachment', 'Choose a supported attachment.');
  if (file.size === 0 || file.size > MAX_FILE) fail(400, 'attachment_size', 'Each attachment must be between 1 byte and 1.5 MB.');
  const bytes = new Uint8Array(await file.arrayBuffer());
  const has = (...sig) => sig.every((byte, i) => bytes[i] === byte);
  let type, ext;
  if (has(0xff, 0xd8, 0xff)) { type = 'image/jpeg'; ext = 'jpg'; }
  else if (has(0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a)) { type = 'image/png'; ext = 'png'; }
  else if (bytes.length >= 12 && new TextDecoder().decode(bytes.slice(0, 4)) === 'RIFF' && new TextDecoder().decode(bytes.slice(8, 12)) === 'WEBP') { type = 'image/webp'; ext = 'webp'; }
  else if (has(0x25, 0x50, 0x44, 0x46, 0x2d)) { type = 'application/pdf'; ext = 'pdf'; }
  else if (file.type === 'text/plain' && /\.txt$/i.test(file.name)) {
    let text;
    try { text = new TextDecoder('utf-8', { fatal: true }).decode(bytes); } catch { fail(400, 'invalid_attachment', 'Text files must be UTF-8.'); }
    if (/[\u0000-\u0008\u000b\u000c\u000e-\u001f\u007f]/.test(text)) fail(400, 'invalid_attachment', 'This is not a plain text file.');
    type = 'text/plain'; ext = 'txt';
  } else fail(400, 'invalid_attachment', 'Attach JPEG, PNG, WebP, PDF, or UTF-8 TXT files.');
  if (file.type !== type) fail(400, 'attachment_type', 'The attachment contents and file type do not match.');
  return { id: crypto.randomUUID(), name: safeName(file.name, ext), type, size: bytes.length, bytes, hash: await digest(bytes) };
}
async function turnstile(form, request, env) {
  if (!env.TURNSTILE_SECRET_KEY) return;
  const token = field(form, 'cf-turnstile-response', 2048, true);
  const body = new URLSearchParams({ secret: env.TURNSTILE_SECRET_KEY, response: token });
  const ip = request.headers.get('CF-Connecting-IP');
  if (ip) body.set('remoteip', ip);
  let result;
  try {
    const response = await fetch('https://challenges.cloudflare.com/turnstile/v0/siteverify', { method: 'POST', body, signal: AbortSignal.timeout(10_000) });
    result = await response.json();
  } catch { fail(503, 'verification_unavailable', 'Verification is temporarily unavailable. Please try again.'); }
  if (!result.success || result.hostname !== new URL(request.url).hostname)
    fail(400, 'verification_failed', 'Please complete verification and try again.');
}
async function retryReceipt(row, payloadHash, legacyHash, token, request) {
  // A retry of a pre-versioned submission may come from the updated form. It
  // returns the original receipt without retroactively granting new rights.
  if (row.payload_hash !== payloadHash && (acceptance(row) || row.payload_hash !== legacyHash))
    fail(409, 'submission_conflict', 'This submission reference has already been used for different content.');
  if (!(await equal(await digest(token), row.token_hash))) {
    token = bearer(request);
    if (!token || !(await equal(await digest(token), row.token_hash)))
      fail(409, 'receipt_key_changed', 'This contribution was already received. Use your original receipt to check its status.');
  }
  return json({ id: row.id, type: submissionType(row), token, status: row.status, created_at: row.created_at });
}
async function submit(request, env) {
  await limit(env, request, 'submit', 10);
  const contentType = request.headers.get('Content-Type') || '';
  if (!contentType.toLowerCase().startsWith('multipart/form-data;')) fail(415, 'content_type', 'Use the contribution form to submit.');
  const bytes = await boundedBody(request, MAX_BODY);
  let form;
  try { form = await new Response(bytes, { headers: { 'Content-Type': contentType } }).formData(); }
  catch { fail(400, 'invalid_form', 'The contribution form could not be read.'); }
  const seen = new Set();
  for (const [key] of form) {
    if (key !== 'attachments' && seen.has(key)) fail(400, 'duplicate_field', 'The contribution form contains duplicate fields.');
    seen.add(key);
  }
  if (field(form, 'website', 2000)) fail(400, 'invalid_form', 'The contribution could not be accepted.');
  const clientId = field(form, 'client_id', 36, true).toLowerCase();
  if (!UUID.test(clientId)) fail(400, 'invalid_reference', 'A valid submission reference is required.');
  const data = {
    type: field(form, 'type', 16, true), title: field(form, 'title', 160, true), description: field(form, 'description', 12000, true),
    contributor_name: field(form, 'contributor_name', 160), email: field(form, 'email', 254), place: field(form, 'place', 160),
    date_text: field(form, 'date_text', 100), source_url: field(form, 'source_url', 2000), credit: field(form, 'credit', 160),
    source_page: field(form, 'source_page', 2000), language: field(form, 'language', 2, true), consent: field(form, 'consent', 3, true),
    attachment_rights: field(form, 'attachment_rights', 3),
  };
  const termsVersion = field(form, 'terms_version', 32);
  if (!['story', 'document', 'correction', 'rights'].includes(data.type) || !['en', 'bn'].includes(data.language) || data.consent !== 'yes')
    fail(400, 'invalid_field', 'Choose a submission type, language, and confirm the applicable terms.');
  if (data.email && (!/^[^\s@<>]+@[^\s@<>]+\.[^\s@<>]+$/.test(data.email))) fail(400, 'invalid_email', 'Check the email address.');
  webUrl(data.source_url, 'source_url');
  webUrl(data.source_page, 'source_page', new URL(request.url).origin, true);
  if (data.source_page && new URL(data.source_page, request.url).origin !== new URL(request.url).origin)
    fail(400, 'invalid_source_page', 'The correction must refer to a page on this website.');
  const uploads = form.getAll('attachments').filter(file => typeof file === 'string' || file.size || file.name);
  if (uploads.length > MAX_FILES) fail(400, 'attachment_count', 'Attach at most three files.');
  if (!['', 'yes', 'no'].includes(data.credit)) fail(400, 'invalid_credit', 'Choose whether your name may be credited.');
  data.credit = data.type !== 'rights' && data.credit === 'yes' ? 'yes' : 'no';
  if (data.credit === 'yes' && !data.contributor_name) fail(400, 'credit_name_required', 'Enter the name you would like credited.');
  if ((uploads.length && data.attachment_rights !== 'yes') || !['', 'yes'].includes(data.attachment_rights))
    fail(400, 'attachment_rights_required', 'Confirm the applicable attachment terms.');
  const files = [];
  for (const file of uploads) files.push(await fileRecord(file));
  const fileHashes = files.map(({ name, type, size, hash }) => ({ name, type, size, hash }));
  const legacyHash = await digest(JSON.stringify({ ...data, files: fileHashes }));
  const payloadHash = termsVersion ? await digest(JSON.stringify({ ...data, terms_version: termsVersion, files: fileHashes })) : legacyHash;
  const token = await hmac(env.EDITOR_KEY, `receipt:${clientId}`);
  const existingSubmission = () => stmt(env, `SELECT id,type,token_hash,payload_hash,status,created_at,${ACCEPTANCE_NOTE} AS acceptance_note FROM contributions WHERE client_id=?`, clientId).first();
  let existing = await existingSubmission();
  if (existing) return retryReceipt(existing, payloadHash, legacyHash, token, request);
  if (termsVersion !== TERMS_VERSION)
    fail(400, 'terms_version_required', 'Reload the form and review the current terms before submitting.');
  await turnstile(form, request, env);
  await limit(env, request, 'submit-global', 100, 86400, true);
  const id = crypto.randomUUID(), now = new Date().toISOString();
  // A rights enquiry is a private rights-related correction in the original
  // schema; the authoritative initial acceptance records its API type. Every
  // read surface and publication guard uses that record, not the storage alias.
  const stored = { ...data, type: data.type === 'rights' ? 'correction' : data.type };
  const fields = Object.keys(stored);
  const statements = [stmt(env, `INSERT INTO contributions(id,client_id,token_hash,payload_hash,${fields.join(',')},created_at,updated_at)
    VALUES(${Array(fields.length + 6).fill('?').join(',')})`, id, clientId, await digest(token), payloadHash, ...Object.values(stored), now, now)];
  for (const file of files) statements.push(stmt(env, 'INSERT INTO contribution_files(id,contribution_id,name,type,size,data) VALUES(?,?,?,?,?,?)',
    file.id, id, file.name, file.type, file.size, file.bytes.buffer));
  const acceptanceNote = JSON.stringify({ kind: 'terms-acceptance', terms_version: termsVersion, purpose: data.type === 'rights' ? 'rights-enquiry' : 'contribution', type: data.type, accepted_at: now, language: data.language });
  statements.push(stmt(env, 'INSERT INTO contribution_history(id,contribution_id,status,note,created_at) VALUES(?,?,?,?,?)', crypto.randomUUID(), id, 'received', acceptanceNote, now));
  try { await env.CONTRIBUTIONS_DB.batch(statements); }
  catch (error) {
    existing = await existingSubmission();
    if (existing) return retryReceipt(existing, payloadHash, legacyHash, token, request);
    if (String(error).includes('attachment_capacity')) fail(503, 'storage_full', 'Attachment storage is full. Please try again later or submit without files.');
    throw error;
  }
  // Expired rate records contain no raw IP addresses and are cleaned regularly.
  try { await stmt(env, 'DELETE FROM contribution_rate_limits WHERE expires_at < ?', Math.floor(Date.now() / 1000) - 86400).run(); }
  catch { /* Cleanup must not hide a successfully committed receipt. */ }
  return json({ id, type: data.type, token, status: 'received', created_at: now }, 201);
}
async function reply(request, env, id) {
  const row = await receipt(request, env, id);
  await limit(env, request, 'reply', 10);
  const data = await jsonBody(request);
  const message = field(data, 'message', 5000, true), now = new Date().toISOString();
  try {
    await env.CONTRIBUTIONS_DB.batch([
      stmt(env, 'INSERT INTO contribution_replies(id,contribution_id,message,created_at) VALUES(?,?,?,?)', crypto.randomUUID(), row.id, message, now),
      stmt(env, 'UPDATE contributions SET updated_at=?,version=version+1 WHERE id=?', now, row.id),
    ]);
  } catch (error) {
    if (String(error).includes('reply_limit')) fail(429, 'reply_limit', 'This receipt has reached its follow-up limit.');
    throw error;
  }
  return json({ ok: true, created_at: now }, 201);
}
function encodeCursor(row) { return btoa(JSON.stringify([row.created_at, row.id])); }
function decodeCursor(value) {
  try {
    const [date, id] = JSON.parse(atob(value));
    if (typeof date !== 'string' || !/^\d{4}-\d{2}-\d{2}T[\d:.]+Z$/.test(date) || !UUID.test(id)) throw new Error();
    return [date, id];
  } catch { fail(400, 'invalid_cursor', 'This list reference is invalid.'); }
}
async function reviewList(request, env) {
  const url = new URL(request.url), status = url.searchParams.get('status') || '', query = (url.searchParams.get('q') || '').trim();
  if (status && !STATUSES.includes(status)) fail(400, 'invalid_status', 'Choose a valid status.');
  if (query.length > 160) fail(400, 'invalid_query', 'Search must be 160 characters or fewer.');
  const conditions = [], args = [];
  if (status) { conditions.push('status=?'); args.push(status); }
  if (query) {
    conditions.push("(title LIKE ? ESCAPE '\\' OR contributor_name LIKE ? ESCAPE '\\' OR place LIKE ? ESCAPE '\\')");
    const pattern = `%${query.replace(/[\\%_]/g, '\\$&')}%`;
    args.push(pattern, pattern, pattern);
  }
  if (url.searchParams.get('before')) {
    const [date, id] = decodeCursor(url.searchParams.get('before'));
    conditions.push('(created_at < ? OR (created_at = ? AND id < ?))'); args.push(date, date, id);
  }
  const result = await stmt(env, `SELECT id,type,title,contributor_name,status,created_at,updated_at,version,${ACCEPTANCE_NOTE} AS acceptance_note FROM contributions
    ${conditions.length ? `WHERE ${conditions.join(' AND ')}` : ''} ORDER BY created_at DESC,id DESC LIMIT 31`, ...args).all();
  const items = rows(result).map(row => { const { acceptance_note, ...item } = row; return { ...item, type: submissionType(row) }; }), next = items.length > 30;
  if (next) items.pop();
  const counts = Object.fromEntries(STATUSES.map(status => [status, 0]));
  for (const row of rows(await stmt(env, 'SELECT status,count(*) AS count FROM contributions GROUP BY status').all())) counts[row.status] = row.count;
  return json({ items, next_cursor: next ? encodeCursor(items.at(-1)) : null, counts });
}
async function reviewDetail(env, id) {
  const row = await stmt(env, `SELECT *,${ACCEPTANCE_NOTE} AS acceptance_note FROM contributions WHERE id=?`, id).first();
  if (!row) fail(404, 'not_found', 'The contribution could not be found.');
  const { client_id, token_hash, payload_hash, acceptance_note, ...submission } = row;
  submission.type = submissionType(row);
  const result = await env.CONTRIBUTIONS_DB.batch([
    stmt(env, 'SELECT id,name,type,size FROM contribution_files WHERE contribution_id=? ORDER BY id', id),
    stmt(env, 'SELECT status,note,internal_note,created_at FROM contribution_history WHERE contribution_id=? ORDER BY rowid', id),
    stmt(env, 'SELECT message,created_at FROM contribution_replies WHERE contribution_id=? ORDER BY created_at,rowid', id),
  ]);
  const history = rows(result[1]);
  if (acceptance(row) && history.length) history[0] = { ...history[0], note: '' };
  return json({ submission, consent_info: consentInfo(row), attachments: rows(result[0]), history, replies: rows(result[2]) });
}
async function publication(value, request, env) {
  const origin = new URL(request.url).origin;
  webUrl(value, 'published_url', origin, true);
  let target = new URL(value, origin);
  if (target.origin !== origin || target.search || target.hash || !/^\/(?:bn\/)?[a-z0-9][a-z0-9-]*(?:\.html)?$/.test(target.pathname)
      || /\/(?:contribut[^/]*|review[^/]*|editor[^/]*|admin[^/]*|404)(?:\.html)?$/.test(target.pathname))
    fail(400, 'invalid_publication', 'Choose an existing public article on this website.');
  if (!env.ASSETS) fail(503, 'publication_unavailable', 'The public article could not be checked.');
  let response = await env.ASSETS.fetch(new Request(target, { method: 'GET', redirect: 'manual' }));
  // Pages may redirect .html to its extensionless canonical route.
  if ([301, 302, 307, 308].includes(response.status)) {
    const location = response.headers.get('Location');
    const destination = location ? new URL(location, target) : null;
    if (!destination || destination.origin !== origin || destination.pathname !== target.pathname.replace(/\.html$/, ''))
      fail(400, 'invalid_publication', 'The public article could not be found.');
    response = await env.ASSETS.fetch(new Request(destination, { method: 'GET', redirect: 'manual' }));
  }
  if (response.status !== 200 || !(response.headers.get('Content-Type') || '').includes('text/html'))
    fail(400, 'invalid_publication', 'The public article must exist before marking a contribution published.');
  const expectedPage = target.pathname.split('/').pop().replace(/\.html$/, '');
  const article = new TextDecoder().decode(await boundedBody(response, MAX_BODY));
  const page = article.match(/<body\b[^>]*\bdata-page=["']([^"']+)["']/i)?.[1];
  if (page !== expectedPage) fail(400, 'invalid_publication', 'The public article must exist before marking a contribution published.');
  return target.pathname;
}
async function reviewUpdate(request, env, id) {
  const data = await jsonBody(request), status = field(data, 'status', 24, true);
  if (!STATUSES.includes(status)) fail(400, 'invalid_status', 'Choose a valid status.');
  if (!Number.isSafeInteger(data.version) || data.version < 1) fail(400, 'invalid_version', 'Reload this contribution before saving.');
  const note = field(data, 'public_note', 5000), internal = field(data, 'internal_note', 5000);
  let published = field(data, 'published_url', 2000);
  const row = await stmt(env, `SELECT type,${ACCEPTANCE_NOTE} AS acceptance_note FROM contributions WHERE id=?`, id).first();
  if (!row) fail(404, 'not_found', 'The contribution could not be found.');
  if (submissionType(row) === 'rights' && (['approved', 'published'].includes(status) || published))
    fail(400, 'private_enquiry', 'Rights enquiries are private and cannot be approved for publication or linked as published.');
  if (status === 'published' && !published) fail(400, 'publication_required', 'Link the published article first.');
  if (published) published = await publication(published, request, env);
  const now = new Date().toISOString();
  // The database trigger writes the audit history in the same transaction as
  // this conditional update. A stale editor can never add a history entry.
  const result = await stmt(env, 'UPDATE contributions SET status=?,public_note=?,internal_note=?,published_url=?,updated_at=?,version=version+1 WHERE id=? AND version=?',
    status, note, internal, published, now, id, data.version).run();
  if (!result.meta?.changes) {
    if (!(await stmt(env, 'SELECT id FROM contributions WHERE id=?', id).first())) fail(404, 'not_found', 'The contribution could not be found.');
    fail(409, 'version_conflict', 'This contribution changed. Reload it before saving.');
  }
  return json({ id, status, version: data.version + 1, updated_at: now });
}
async function download(env, id, fileId) {
  const file = await stmt(env, 'SELECT name,type,size,data FROM contribution_files WHERE contribution_id=? AND id=?', id, fileId).first();
  if (!file) fail(404, 'not_found', 'The attachment could not be found.');
  const bytes = Array.isArray(file.data) ? new Uint8Array(file.data) : file.data;
  const disposition = INLINE_FILE_TYPES.has(file.type) ? 'inline' : 'attachment';
  return new Response(bytes, { headers: { ...SECURITY, 'Content-Type': file.type, 'Content-Length': String(file.size),
    'Content-Disposition': `${disposition}; filename="attachment.${file.name.split('.').pop()}"; filename*=UTF-8''${encodeURIComponent(file.name)}` } });
}

async function journalDocument(request, path) {
  const headers = new Headers({ 'X-Content-Type-Options': 'nosniff', 'Referrer-Policy': 'no-referrer' });
  if (!Object.hasOwn(JOURNAL_DOCUMENTS, path)) return new Response('Not found', { status: 404, headers });
  if (!['GET', 'HEAD'].includes(request.method)) {
    headers.set('Allow', 'GET, HEAD');
    return new Response('Method not allowed', { status: 405, headers });
  }
  // Only these two public documents can be fetched. Never forward credentials,
  // cookies, the reader's referrer, or a caller-supplied destination.
  const upstreamHeaders = new Headers({ Accept: 'application/pdf' });
  for (const name of ['Range', 'If-Range', 'If-None-Match', 'If-Modified-Since', 'If-Match', 'If-Unmodified-Since']) {
    if (request.headers.has(name)) upstreamHeaders.set(name, request.headers.get(name));
  }
  let upstream;
  try {
    upstream = await fetch(JOURNAL_DOCUMENTS[path], { method: request.method, headers: upstreamHeaders,
      redirect: 'follow', credentials: 'omit', referrerPolicy: 'no-referrer' });
  } catch (_) {
    return new Response(request.method === 'HEAD' ? null : 'The document is temporarily unavailable.', { status: 502, headers });
  }
  for (const name of ['Content-Type', 'Content-Length', 'Content-Range', 'Accept-Ranges', 'ETag', 'Last-Modified',
                       'Cache-Control', 'Expires', 'Vary', 'Retry-After']) {
    if (upstream.headers.has(name)) headers.set(name, upstream.headers.get(name));
  }
  if (upstream.ok || upstream.status === 304) {
    headers.set('Content-Type', 'application/pdf');
    headers.set('Content-Disposition', `inline; filename="${path.split('/').pop()}"`);
  }
  // Preserve range/conditional responses and stream the large PDF without
  // loading it into Worker memory. HEAD and 304 responses never get a body.
  return new Response(request.method === 'HEAD' || upstream.status === 304 ? null : upstream.body,
    { status: upstream.status, statusText: upstream.statusText, headers });
}


// ---------------------------------------------------------------------------
// Opt-in web push notifications.
// Readers subscribe only after pressing a button; the browser then asks for
// permission. Only the push endpoint, its two public encryption values, the
// reader's chosen language and dates are stored: no IP address, user agent or
// account. Messages are encrypted here (RFC 8291) and signed with the site's
// VAPID key (RFC 8292), so no third-party notification service is involved
// beyond the push service operated by the reader's own browser vendor.
const PUSH_HOSTS = [/^fcm\.googleapis\.com$/, /^updates\.push\.services\.mozilla\.com$/, /^push\.services\.mozilla\.com$/,
  /^[a-z0-9-]+\.notify\.windows\.com$/, /^web\.push\.apple\.com$/, /^[a-z0-9-]+\.push\.apple\.com$/, /^android\.googleapis\.com$/];
const PUSH_BATCH = 40; // below the Workers free-plan limit of 50 outbound requests per invocation
const PUSH_MIN_HOURS = 24; // default minimum spacing between campaigns
function b64u(bytes) {
  let text = '';
  for (const b of new Uint8Array(bytes)) text += String.fromCharCode(b);
  return btoa(text).replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '');
}
function unb64u(value) {
  if (typeof value !== 'string' || !/^[A-Za-z0-9_-]*$/.test(value)) throw new TypeError('base64url');
  const text = atob(value.replace(/-/g, '+').replace(/_/g, '/') + '==='.slice((value.length + 3) % 4));
  return Uint8Array.from(text, c => c.charCodeAt(0));
}
function concat(...parts) {
  const out = new Uint8Array(parts.reduce((n, p) => n + p.byteLength, 0));
  let at = 0;
  for (const p of parts) { out.set(new Uint8Array(p), at); at += p.byteLength; }
  return out;
}
async function hkdf(salt, ikm, info, length) {
  const key = await crypto.subtle.importKey('raw', ikm, 'HKDF', false, ['deriveBits']);
  return new Uint8Array(await crypto.subtle.deriveBits({ name: 'HKDF', hash: 'SHA-256', salt, info }, key, length * 8));
}
// RFC 8291 aes128gcm encryption. `salt` and `serverKeys` are injectable for the
// RFC test vector; production calls generate fresh values for every message.
export async function encryptPushPayload(payload, p256dh, authSecret, { salt, serverKeys } = {}) {
  const uaPublic = unb64u(p256dh), auth = unb64u(authSecret);
  if (uaPublic.length !== 65 || uaPublic[0] !== 4 || auth.length !== 16) throw new TypeError('subscription keys');
  salt = salt || crypto.getRandomValues(new Uint8Array(16));
  serverKeys = serverKeys || await crypto.subtle.generateKey({ name: 'ECDH', namedCurve: 'P-256' }, true, ['deriveBits']);
  const asPublic = new Uint8Array(await crypto.subtle.exportKey('raw', serverKeys.publicKey));
  const uaKey = await crypto.subtle.importKey('raw', uaPublic, { name: 'ECDH', namedCurve: 'P-256' }, false, []);
  const shared = new Uint8Array(await crypto.subtle.deriveBits({ name: 'ECDH', public: uaKey }, serverKeys.privateKey, 256));
  const ikm = await hkdf(auth, shared, concat(encoder.encode('WebPush: info\0'), uaPublic, asPublic), 32);
  const cek = await hkdf(salt, ikm, encoder.encode('Content-Encoding: aes128gcm\0'), 16);
  const nonce = await hkdf(salt, ikm, encoder.encode('Content-Encoding: nonce\0'), 12);
  const plain = concat(typeof payload === 'string' ? encoder.encode(payload) : payload, new Uint8Array([2]));
  if (plain.byteLength > 3993) throw new RangeError('payload too large');
  const key = await crypto.subtle.importKey('raw', cek, 'AES-GCM', false, ['encrypt']);
  const cipher = new Uint8Array(await crypto.subtle.encrypt({ name: 'AES-GCM', iv: nonce }, key, plain));
  const header = new Uint8Array(21);
  header.set(salt, 0);
  new DataView(header.buffer).setUint32(16, 4096);
  header[20] = 65;
  return concat(header, asPublic, cipher);
}
async function vapidKey(env) {
  const pub = unb64u(env.VAPID_PUBLIC_KEY);
  if (pub.length !== 65 || pub[0] !== 4) throw new TypeError('VAPID public key');
  return crypto.subtle.importKey('jwk', { kty: 'EC', crv: 'P-256', d: env.VAPID_PRIVATE_KEY,
    x: b64u(pub.slice(1, 33)), y: b64u(pub.slice(33, 65)), ext: true }, { name: 'ECDSA', namedCurve: 'P-256' }, false, ['sign']);
}
export async function vapidAuthorization(endpoint, env, now = Date.now()) {
  const header = b64u(encoder.encode(JSON.stringify({ typ: 'JWT', alg: 'ES256' })));
  const claims = b64u(encoder.encode(JSON.stringify({ aud: new URL(endpoint).origin, exp: Math.floor(now / 1000) + 12 * 3600, sub: env.VAPID_SUBJECT })));
  const signature = await crypto.subtle.sign({ name: 'ECDSA', hash: 'SHA-256' }, await vapidKey(env), encoder.encode(`${header}.${claims}`));
  return `vapid t=${header}.${claims}.${b64u(signature)}, k=${env.VAPID_PUBLIC_KEY}`;
}
function pushConfigured(env) {
  return !!env.CONTRIBUTIONS_DB && typeof env.EDITOR_KEY === 'string' && env.EDITOR_KEY.length >= 32
    && typeof env.VAPID_PUBLIC_KEY === 'string' && typeof env.VAPID_PRIVATE_KEY === 'string'
    && /^mailto:[^\s@]+@[^\s@]+$|^https:\/\/\S+$/.test(env.VAPID_SUBJECT || '');
}
function pushSubscription(data) {
  const sub = data.subscription;
  if (!sub || typeof sub !== 'object') fail(400, 'invalid_subscription', 'The browser subscription could not be read.');
  let endpoint;
  try { endpoint = new URL(sub.endpoint); } catch { fail(400, 'invalid_subscription', 'The browser subscription could not be read.'); }
  if (endpoint.protocol !== 'https:' || endpoint.username || endpoint.password || sub.endpoint.length > 1000
      || !PUSH_HOSTS.some(pattern => pattern.test(endpoint.hostname)))
    fail(400, 'unsupported_push_service', 'This browser’s push service is not supported.');
  const keys = sub.keys || {};
  try {
    if (unb64u(keys.p256dh).length !== 65 || unb64u(keys.auth).length !== 16) throw new Error();
  } catch { fail(400, 'invalid_subscription', 'The browser subscription could not be read.'); }
  return { endpoint: sub.endpoint, p256dh: keys.p256dh, auth: keys.auth };
}
async function pushSubscribe(request, env) {
  await limit(env, request, 'push-subscribe', 30);
  const data = await jsonBody(request, 4_000);
  const sub = pushSubscription(data);
  let language = data.language === 'bn' ? 'bn' : 'en';
  const now = new Date().toISOString(), id = await digest(sub.endpoint);
  // A browser-rotated subscription keeps the reader's earlier language choice.
  if (typeof data.replaces === 'string' && data.replaces.length <= 1000 && data.replaces !== sub.endpoint) {
    const oldId = await digest(data.replaces);
    const previous = await stmt(env, 'SELECT language FROM push_subscriptions WHERE id=?', oldId).first();
    if (previous) { language = previous.language; await stmt(env, 'DELETE FROM push_subscriptions WHERE id=?', oldId).run(); }
  }
  await stmt(env, `INSERT INTO push_subscriptions(id,endpoint,p256dh,auth,language,created_at,updated_at) VALUES(?,?,?,?,?,?,?)
    ON CONFLICT(id) DO UPDATE SET p256dh=excluded.p256dh, auth=excluded.auth, language=excluded.language, updated_at=excluded.updated_at, failures=0`,
    id, sub.endpoint, sub.p256dh, sub.auth, language, now, now).run();
  return json({ subscribed: true });
}
async function pushUnsubscribe(request, env) {
  await limit(env, request, 'push-unsubscribe', 60);
  const data = await jsonBody(request, 2_000);
  if (typeof data.endpoint !== 'string' || data.endpoint.length > 1000) fail(400, 'invalid_subscription', 'The browser subscription could not be read.');
  await stmt(env, 'DELETE FROM push_subscriptions WHERE id=?', await digest(data.endpoint)).run();
  return json({ subscribed: false });
}
function message(data, lang, origin) {
  const part = data[lang];
  if (!part) return null;
  const title = field(part, 'title', 80, true), body = field(part, 'body', 180, true);
  let url;
  try { url = new URL(field(part, 'url', 300, true), origin); } catch { fail(400, 'invalid_url', 'Check url.'); }
  if (url.origin !== origin || !/^\/(?:bn\/)?(?:[a-z0-9][a-z0-9-]*(?:\.html)?)?$/.test(url.pathname) || url.search)
    fail(400, 'invalid_url', 'Notifications may link only to a page on this website.');
  return { title, body, url: url.pathname + url.hash };
}
// Editors send in batches. Each campaign has a caller-chosen ID, so retrying a
// batch never sends a second copy, and campaigns are spaced to avoid excess.
async function pushSend(request, env) {
  const data = await jsonBody(request, 8_000);
  const id = field(data, 'campaign', 64, true);
  if (!/^[a-z0-9][a-z0-9-]{2,63}$/.test(id)) fail(400, 'invalid_campaign', 'Use a campaign ID of lowercase letters, numbers and hyphens.');
  const origin = new URL(request.url).origin;
  const content = { en: message(data, 'en', origin), bn: message(data, 'bn', origin) };
  if (!content.en && !content.bn) fail(400, 'missing_message', 'Provide an English or Bengali message.');
  const audience = ['all', 'en', 'bn'].includes(data.audience) ? data.audience : 'all';
  const now = new Date();
  let campaign = await stmt(env, 'SELECT * FROM push_campaigns WHERE id=?', id).first();
  if (!campaign) {
    const recent = await stmt(env, 'SELECT created_at FROM push_campaigns ORDER BY created_at DESC LIMIT 1').first();
    const hours = recent ? (now - new Date(recent.created_at)) / 3_600_000 : Infinity;
    if (hours < PUSH_MIN_HOURS && data.allow_frequent !== true)
      fail(409, 'too_soon', `The previous notification was sent less than ${PUSH_MIN_HOURS} hours ago.`);
    if (data.dry_run === true) {
      const audienceCount = await stmt(env, `SELECT count(*) AS n FROM push_subscriptions WHERE (?='all' OR language=?)`, audience, audience).first();
      return json({ dry_run: true, campaign: id, audience, subscribers: audienceCount.n, preview: content });
    }
    await stmt(env, 'INSERT INTO push_campaigns(id,payload,audience,created_at) VALUES(?,?,?,?)', id, JSON.stringify(content), audience, now.toISOString()).run();
    campaign = await stmt(env, 'SELECT * FROM push_campaigns WHERE id=?', id).first();
  } else if (campaign.payload !== JSON.stringify(content) || campaign.audience !== audience) {
    fail(409, 'campaign_conflict', 'This campaign ID was already used for a different message.');
  }
  const stored = JSON.parse(campaign.payload);
  const batch = rows(await stmt(env, `SELECT s.* FROM push_subscriptions s
    WHERE (?='all' OR s.language=?) AND NOT EXISTS (SELECT 1 FROM push_deliveries d WHERE d.campaign_id=? AND d.subscription_id=s.id)
    ORDER BY s.id LIMIT ?`, campaign.audience, campaign.audience, id, PUSH_BATCH).all());
  let sent = 0, removed = 0, failed = 0;
  for (const sub of batch) {
    const text = stored[sub.language] || stored.en || stored.bn;
    let outcome = 'failed';
    try {
      const body = await encryptPushPayload(JSON.stringify({ ...text, tag: id, lang: stored[sub.language] ? sub.language : (stored.en ? 'en' : 'bn') }), sub.p256dh, sub.auth);
      const response = await fetch(sub.endpoint, { method: 'POST', body, headers: {
        Authorization: await vapidAuthorization(sub.endpoint, env), 'Content-Encoding': 'aes128gcm',
        'Content-Type': 'application/octet-stream', TTL: '604800', Urgency: 'normal', Topic: id.replace(/-/g, '').slice(0, 32) } });
      if (response.status === 404 || response.status === 410) outcome = 'expired';
      else if (response.ok) outcome = 'sent';
    } catch { outcome = 'failed'; }
    await stmt(env, 'INSERT OR IGNORE INTO push_deliveries(campaign_id,subscription_id,outcome,created_at) VALUES(?,?,?,?)', id, sub.id, outcome, new Date().toISOString()).run();
    if (outcome === 'sent') { sent++; await stmt(env, 'UPDATE push_subscriptions SET failures=0, last_success_at=? WHERE id=?', new Date().toISOString(), sub.id).run(); }
    else if (outcome === 'expired') { removed++; await stmt(env, 'DELETE FROM push_subscriptions WHERE id=?', sub.id).run(); }
    else { failed++; await stmt(env, 'UPDATE push_subscriptions SET failures=failures+1 WHERE id=?', sub.id).run();
      await stmt(env, 'DELETE FROM push_subscriptions WHERE id=? AND failures>=5', sub.id).run(); }
  }
  const remaining = await stmt(env, `SELECT count(*) AS n FROM push_subscriptions s WHERE (?='all' OR s.language=?)
    AND NOT EXISTS (SELECT 1 FROM push_deliveries d WHERE d.campaign_id=? AND d.subscription_id=s.id)`, campaign.audience, campaign.audience, id).first();
  return json({ campaign: id, sent, removed, failed, remaining: remaining.n });
}
async function pushStats(env) {
  const total = await stmt(env, 'SELECT language, count(*) AS n FROM push_subscriptions GROUP BY language').all();
  const campaigns = await stmt(env, `SELECT c.id, c.audience, c.created_at,
    (SELECT count(*) FROM push_deliveries d WHERE d.campaign_id=c.id AND d.outcome='sent') AS sent,
    (SELECT count(*) FROM push_deliveries d WHERE d.campaign_id=c.id AND d.outcome<>'sent') AS not_sent
    FROM push_campaigns c ORDER BY c.created_at DESC LIMIT 20`).all();
  return json({ subscribers: rows(total), campaigns: rows(campaigns) });
}

// Only neutral homepage requests negotiate language. Explicit Bengali routes and
// article links never consult geolocation or the preference cookie.
const LANGUAGE_COOKIE = 'aguri_language';
function savedLanguage(request) {
  for (const part of (request.headers.get('Cookie') || '').split(';')) {
    const [name, ...value] = part.trim().split('=');
    if (name === LANGUAGE_COOKIE) {
      const language = value.join('=');
      if (language === 'en' || language === 'bn') return language;
    }
  }
  return null;
}
function westBengal(cf) {
  if (cf?.country !== 'IN') return false;
  // Cloudflare returns the ISO subdivision suffix (WB). Accept a full ISO
  // code defensively; use the documented name only when the code is absent.
  const code = typeof cf.regionCode === 'string' ? cf.regionCode.trim().toUpperCase() : '';
  return code === 'WB' || code === 'IN-WB' || (!code && cf.region === 'West Bengal');
}
async function homepageLanguage(request, env) {
  const url = new URL(request.url);
  const explicit = url.searchParams.get('lang');
  const manual = explicit === 'en' || explicit === 'bn' ? explicit : null;
  const language = manual || savedLanguage(request) || (westBengal(request.cf) ? 'bn' : 'en');
  let response;
  if (language === 'bn') {
    url.pathname = '/bn/';
    response = new Response(null, { status: 302, headers: { Location: url.href } });
  } else {
    response = env.ASSETS ? await env.ASSETS.fetch(request) : new Response('Not found', { status: 404 });
  }
  const headers = new Headers(response.headers);
  // Cover English passthrough as well as redirects. Never share a negotiated
  // result between visitors, and never cache a manual-choice Set-Cookie.
  headers.set('Cache-Control', 'private, no-store, max-age=0');
  headers.set('CDN-Cache-Control', 'no-store');
  headers.set('Cloudflare-CDN-Cache-Control', 'no-store');
  headers.set('Vary', [...new Set([...(headers.get('Vary') || '').split(',').map(v => v.trim()).filter(Boolean), 'Cookie'])].join(', '));
  if (manual) headers.append('Set-Cookie', `${LANGUAGE_COOKIE}=${manual}; Max-Age=31536000; Path=/; Secure; SameSite=Lax`);
  return new Response(request.method === 'HEAD' ? null : response.body, { status: response.status, statusText: response.statusText, headers });
}

// Contact mail is deliberately separate from publication contributions. It is
// disabled unless BOTH mandatory bot verification and fixed-recipient delivery
// are configured. No browser-controlled recipient, sender or HTML is accepted.
const CONTACT_EMAIL = /^[A-Za-z0-9.!#$%&'*+/=?^_`{|}~-]+@[A-Za-z0-9](?:[A-Za-z0-9.-]*[A-Za-z0-9])?\.[A-Za-z]{2,63}$/;
function contactConfigured(env, request) {
  const host = new URL(request.url).hostname;
  const hosts = typeof env.CONTACT_HOSTNAMES === 'string' ? env.CONTACT_HOSTNAMES.split(',').map(s => s.trim()) : [];
  const realKey = value => typeof value === 'string' && value.length >= 20 && !/^[123]x0{10}/.test(value) && !/\s/.test(value);
  return !!env.CONTRIBUTIONS_DB && typeof env.EDITOR_KEY === 'string' && env.EDITOR_KEY.length >= 32
    && new URL(request.url).protocol === 'https:' && host !== 'localhost' && host !== '127.0.0.1'
    && hosts.length > 0 && hosts.every(h => /^[a-z0-9]+(?:[.-][a-z0-9]+)*\.[a-z]{2,63}$/.test(h)) && hosts.includes(host)
    && realKey(env.CONTACT_TURNSTILE_SITE_KEY) && realKey(env.CONTACT_TURNSTILE_SECRET_KEY)
    && env.CONTACT_DELIVERY_PROVIDER === 'resend' && typeof env.CONTACT_RESEND_API_KEY === 'string' && env.CONTACT_RESEND_API_KEY.length >= 20
    && CONTACT_EMAIL.test(env.CONTACT_TO_EMAIL || '') && CONTACT_EMAIL.test(env.CONTACT_FROM_EMAIL || '')
    && env.CONTACT_TO_EMAIL.length <= 254 && env.CONTACT_FROM_EMAIL.length <= 254;
}
async function contactCaptcha(token, request, env) {
  if (!token || token.length > 2048) fail(400, 'invalid_captcha', 'Complete the verification and try again.');
  const body = new URLSearchParams({ secret: env.CONTACT_TURNSTILE_SECRET_KEY, response: token });
  const ip = request.headers.get('CF-Connecting-IP');
  if (ip) body.set('remoteip', ip);
  let result;
  try {
    const response = await fetch('https://challenges.cloudflare.com/turnstile/v0/siteverify', {
      method: 'POST', body, signal: AbortSignal.timeout(10_000), redirect: 'manual',
    });
    if (!response.ok) throw new Error('Verification unavailable');
    result = await response.json();
  } catch { fail(503, 'captcha_unavailable', 'Verification is temporarily unavailable. Your message has not been sent.'); }
  if (result?.success !== true || result.hostname !== new URL(request.url).hostname || result.action !== 'contact')
    fail(400, 'invalid_captcha', 'Complete the verification and try again.');
}
async function contactSubmit(request, env) {
  if (!contactConfigured(env, request)) fail(503, 'service_unavailable', 'The contact form is temporarily unavailable.');
  await limit(env, request, 'contact-attempt', 10);
  const data = await jsonBody(request, 24_000);
  const allowed = new Set(['name', 'email', 'subject', 'message', 'language', 'website', 'consent', 'token', 'request_id']);
  if (Object.keys(data).some(k => !allowed.has(k))) fail(400, 'invalid_field', 'Check the form fields.');
  if (field(data, 'website', 200)) fail(400, 'invalid_field', 'The message could not be accepted.');
  const name = field(data, 'name', 120, true), email = field(data, 'email', 254, true);
  const subject = field(data, 'subject', 160, true), message = field(data, 'message', 5000, true);
  const language = field(data, 'language', 2, true), id = field(data, 'request_id', 36, true);
  if (!CONTACT_EMAIL.test(email) || /[\r\n]/.test(name + subject) || !['en', 'bn'].includes(language) || !UUID.test(id) || data.consent !== 'yes')
    fail(400, 'invalid_field', 'Check your name, email, subject, message and consent.');
  const token = field(data, 'token', 2048, true);
  // Every attempt, including an idempotent retry, needs a new valid token.
  await contactCaptcha(token, request, env);
  const payloadHash = await hmac(env.EDITOR_KEY, JSON.stringify({ name, email, subject, message, language, consent: 'yes' }));
  let row = await stmt(env, 'SELECT payload_hash,status,created_at FROM contact_requests WHERE request_id=?', id).first();
  if (row && row.payload_hash !== payloadHash) fail(409, 'submission_conflict', 'This reference was used for different content. Please reload before sending a new message.');
  if (row?.status === 'sent') return json({ received: true, reference: id }, 200);
  // Resend retains its idempotency key for 24 hours. Never automatically resend
  // an uncertain older attempt after that window. The owner can reconcile it.
  if (row && (!Number.isFinite(Date.parse(row.created_at)) || Date.parse(row.created_at) > Date.now() || Date.now() - Date.parse(row.created_at) >= 23 * 3600_000))
    fail(409, 'submission_conflict', 'This earlier attempt needs to be checked before another message is sent.');
  if (!row) {
    await limit(env, request, 'contact-accepted', 100, 86400, true);
    const created = new Date().toISOString();
    await stmt(env, "INSERT OR IGNORE INTO contact_requests(request_id,payload_hash,status,created_at) VALUES(?,?,'pending',?)", id, payloadHash, created).run();
    row = await stmt(env, 'SELECT payload_hash,status,created_at FROM contact_requests WHERE request_id=?', id).first();
    if (!row || row.payload_hash !== payloadHash) fail(409, 'submission_conflict', 'This reference was used for different content.');
    if (row.status === 'sent') return json({ received: true, reference: id }, 200);
  }
  // Fixed sender/recipient plus plain text avoid an open relay and HTML/header
  // injection. All credentials are server bindings, never public config.
  const mail = {
    from: `Aguri Heritage <${env.CONTACT_FROM_EMAIL}>`, to: [env.CONTACT_TO_EMAIL], reply_to: email,
    subject: `Aguri Heritage contact: ${subject}`,
    text: `Name: ${name}\nEmail: ${email}\nLanguage: ${language}\nReference: ${id}\n\n${message}`,
  };
  try {
    const response = await fetch('https://api.resend.com/emails', {
      method: 'POST', headers: { Authorization: `Bearer ${env.CONTACT_RESEND_API_KEY}`, 'Content-Type': 'application/json', 'Idempotency-Key': `aguri-contact/${id}` },
      body: JSON.stringify(mail), signal: AbortSignal.timeout(10_000), redirect: 'manual',
    });
    if (!response.ok) throw new Error('Delivery unavailable');
    const result = await response.json();
    if (typeof result?.id !== 'string' || !result.id || result.id.length > 100) throw new Error('Delivery unavailable');
    const saved = await stmt(env, "UPDATE contact_requests SET status='sent' WHERE request_id=? AND payload_hash=?", id, payloadHash).run();
    if (saved?.success !== true || saved.meta?.changes !== 1) throw new Error('Receipt unavailable');
  } catch { fail(503, 'delivery_unavailable', 'Delivery could not be confirmed. Your message is still on screen; retry the same message to avoid duplicates.'); }
  // Only hashes/status are stored in D1; message contents travel privately to
  // the selected mail provider and the owner's configured inbox.
  await stmt(env, 'DELETE FROM contribution_rate_limits WHERE expires_at<?', Math.floor(Date.now() / 1000)).run();
  return json({ received: true, reference: id }, 201);
}

// Page comments are independently opt-in. Never load Google until the reader
// chooses sign-in. ID tokens are verified locally against Google's fixed JWKS.
const COMMENTS_TERMS = 'comments-2026-11-09';
const COMMENT_SESSION_SECONDS = 3600;
let commentJwks = { keys: [], expires: 0, fetched: 0, pending: null };
function commentsConfigured(env) {
  return env.COMMENTS_ENABLED === 'true' && !!env.CONTRIBUTIONS_DB && !!env.ASSETS
    && typeof env.GOOGLE_CLIENT_ID === 'string' && /^[a-zA-Z0-9_-]+\.apps\.googleusercontent\.com$/.test(env.GOOGLE_CLIENT_ID)
    && typeof env.COMMENTS_SESSION_SECRET === 'string' && env.COMMENTS_SESSION_SECRET.length >= 32
    && typeof env.EDITOR_KEY === 'string' && env.EDITOR_KEY.length >= 32
    && env.COMMENTS_SESSION_SECRET !== env.EDITOR_KEY;
}
function commentCookie(request, name) {
  const matches = (request.headers.get('Cookie') || '').split(';').map(s => s.trim()).filter(s => s.startsWith(name + '='));
  return matches.length === 1 ? matches[0].slice(name.length + 1) : '';
}
function commentSetCookie(name, value, seconds) {
  return `${name}=${value}; Path=/; Max-Age=${seconds}; HttpOnly; Secure; SameSite=Strict`;
}
function commentDecode(value) {
  if (!/^[A-Za-z0-9_-]+$/.test(value)) throw new Error('Invalid encoding');
  return Uint8Array.from(atob(value.replace(/-/g, '+').replace(/_/g, '/')), c => c.charCodeAt(0));
}
async function commentGoogleKeys(kid) {
  const now = Date.now();
  if (commentJwks.expires > now && commentJwks.keys.some(k => k.kid === kid)) return commentJwks.keys;
  // Unknown kids cannot force an unbounded number of outbound fetches.
  if (!commentJwks.pending && now - commentJwks.fetched >= 60_000) {
    commentJwks.fetched = now;
    commentJwks.pending = (async () => {
      const response = await fetch('https://www.googleapis.com/oauth2/v3/certs', { redirect: 'manual', signal: AbortSignal.timeout(5000) });
      if (!response.ok) throw new Error('Google keys unavailable');
      const parsed = JSON.parse(new TextDecoder().decode(await boundedBody(response, 40_000)));
      if (!Array.isArray(parsed.keys) || parsed.keys.length > 20) throw new Error('Invalid Google keys');
      const keys = parsed.keys.filter(k => k.kty === 'RSA' && k.alg === 'RS256' && k.use === 'sig' && typeof k.kid === 'string');
      if (!keys.length) throw new Error('No Google keys');
      const maxAge = Number((response.headers.get('Cache-Control') || '').match(/max-age=(\d+)/)?.[1] || 300);
      commentJwks.keys = keys;
      commentJwks.expires = Date.now() + Math.min(3600, Math.max(60, maxAge)) * 1000;
    })().finally(() => { commentJwks.pending = null; });
  }
  if (commentJwks.pending) await commentJwks.pending;
  if (commentJwks.expires <= Date.now()) throw new Error('Google keys expired');
  return commentJwks.keys;
}
async function commentVerifyGoogle(token, nonce, env) {
  try {
    if (typeof token !== 'string' || token.length > 12_000) throw new Error();
    const parts = token.split('.');
    if (parts.length !== 3) throw new Error();
    const header = JSON.parse(new TextDecoder('utf-8', { fatal: true }).decode(commentDecode(parts[0])));
    const claims = JSON.parse(new TextDecoder('utf-8', { fatal: true }).decode(commentDecode(parts[1])));
    if (header.alg !== 'RS256' || typeof header.kid !== 'string' || header.kid.length > 200 || header.crit) throw new Error();
    const now = Math.floor(Date.now() / 1000);
    if (!['https://accounts.google.com', 'accounts.google.com'].includes(claims.iss)
        || claims.aud !== env.GOOGLE_CLIENT_ID || (claims.azp && claims.azp !== env.GOOGLE_CLIENT_ID)
        || !Number.isInteger(claims.exp) || claims.exp <= now || claims.exp > now + 7200
        || !Number.isInteger(claims.iat) || claims.iat > now + 60 || claims.iat < now - 7200
        || (claims.nbf !== undefined && (!Number.isInteger(claims.nbf) || claims.nbf > now))
        || typeof claims.sub !== 'string' || !/^[A-Za-z0-9_-]{1,255}$/.test(claims.sub)
        || claims.nonce !== nonce) throw new Error();
    const jwk = (await commentGoogleKeys(header.kid)).find(k => k.kid === header.kid);
    if (!jwk) throw new Error();
    const key = await crypto.subtle.importKey('jwk', jwk, { name: 'RSASSA-PKCS1-v1_5', hash: 'SHA-256' }, false, ['verify']);
    if (!await crypto.subtle.verify('RSASSA-PKCS1-v1_5', key, commentDecode(parts[2]), encoder.encode(parts[0] + '.' + parts[1]))) throw new Error();
    return claims;
  } catch { fail(401, 'google_auth_failed', 'Google sign-in could not be verified. Please sign in again.'); }
}
async function commentRate(env, request, kind, maximum, seconds = 3600, user = '') {
  const now = Math.floor(Date.now() / 1000), window = Math.floor(now / seconds);
  const identity = await hmac(env.COMMENTS_SESSION_SECRET, user ? `user:${user}` : `ip:${request.headers.get('CF-Connecting-IP') || 'local'}`);
  const result = await stmt(env, `INSERT INTO comment_rate_limits(bucket,count,expires_at) VALUES(?,1,?)
    ON CONFLICT(bucket) DO UPDATE SET count=count+1 WHERE count<? RETURNING count`, `${kind}:${identity}:${window}`, (window + 1) * seconds, maximum).first();
  if (!result) fail(429, 'rate_limited', 'Too many requests. Please try again later.');
}
async function commentSession(request, env, required = true, csrf = false) {
  const token = commentCookie(request, '__Host-aguri-comments');
  let session = null;
  if (/^[a-f0-9]{64}$/.test(token)) session = await stmt(env, `SELECT s.token_hash,s.user_id,u.name FROM comment_sessions s
    JOIN comment_users u ON u.id=s.user_id WHERE s.token_hash=? AND s.expires_at>?`, await hmac(env.COMMENTS_SESSION_SECRET, token), Math.floor(Date.now() / 1000)).first();
  if (!session) { if (required) fail(401, 'login_required', 'Sign in with Google to continue.'); return null; }
  session.csrf_token = await hmac(env.COMMENTS_SESSION_SECRET, 'csrf:' + token);
  if (csrf && !await equal(request.headers.get('X-CSRF-Token') || '', session.csrf_token)) fail(403, 'csrf_rejected', 'Reload the page and try again.');
  return session;
}
async function commentPage(value, request, env) {
  if (typeof value !== 'string' || !/^[a-z0-9]+(?:-[a-z0-9]+)*$/.test(value) || value.length > 100
      || /^(review|contact|404|contribute|editor|admin)$/.test(value)) fail(400, 'invalid_page', 'Choose a public article page.');
  const origin = new URL(request.url).origin;
  let target = new URL('/' + (value === 'home' ? 'index' : value) + '.html', origin);
  let response;
  for (let hop = 0; hop < 3; hop++) {
    response = await env.ASSETS.fetch(new Request(target, { redirect: 'manual' }));
    if (![301,302,307,308].includes(response.status)) break;
    const location = response.headers.get('Location');
    if (!location || hop === 2) fail(404, 'page_not_found', 'This page could not be found.');
    const next = new URL(location, target);
    if (next.origin !== origin || next.search || next.hash || next.username || next.password
        || ![target.pathname.replace(/\.html$/, ''), target.pathname.replace(/\.html$/, '') + '/', '/'].includes(next.pathname)) fail(404, 'page_not_found', 'This page could not be found.');
    target = next;
  }
  if (response.status !== 200 || !(response.headers.get('Content-Type') || '').includes('text/html')) fail(404, 'page_not_found', 'This page could not be found.');
  const html = new TextDecoder().decode(await boundedBody(response, MAX_BODY));
  const marker = html.match(/<body\b[^>]*\sdata-page\s*=\s*(["'])(.*?)\1/i);
  if (!marker || marker[2] !== value) fail(404, 'page_not_found', 'This page could not be found.');
  return value;
}
function commentCursor(value) {
  if (!value) return null;
  try {
    const result = JSON.parse(new TextDecoder().decode(commentDecode(value)));
    if (!Array.isArray(result) || result.length !== 2 || !/^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d\.\d{3}Z$/.test(result[0]) || !UUID.test(result[1])) throw new Error();
    return result;
  } catch { fail(400, 'invalid_cursor', 'Reload the comments.'); }
}
function commentListResult(found) {
  const comments = found.slice(0, 20), last = comments.at(-1);
  return { comments, next_cursor: found.length > 20 ? btoa(JSON.stringify([last.created_at, last.id])).replace(/=/g, '').replace(/\+/g, '-').replace(/\//g, '_') : null };
}
async function commentsApi(request, env) {
  const url = new URL(request.url), path = url.pathname, method = request.method;
  if (path === '/api/comments/config' && method === 'GET') return json({ available: commentsConfigured(env), max_length: 2000, terms_version: COMMENTS_TERMS,
    ...(commentsConfigured(env) ? { google_client_id: env.GOOGLE_CLIENT_ID } : {}) });
  if (!commentsConfigured(env)) fail(503, 'service_unavailable', 'Comments are not available yet.');
  if (url.protocol !== 'https:') fail(403, 'https_required', 'Comments require HTTPS.');
  if (path === '/api/comments/auth/nonce' && method === 'GET') {
    await commentRate(env, request, 'nonce', 30);
    const nonce = hex(crypto.getRandomValues(new Uint8Array(32))), expires = Math.floor(Date.now() / 1000) + 300;
    const challenge = `${nonce}.${expires}`;
    return json({ nonce }, 200, { 'Set-Cookie': commentSetCookie('__Host-aguri-comments-login', challenge + '.' + await hmac(env.COMMENTS_SESSION_SECRET, challenge), 300) });
  }
  if (path === '/api/comments/auth/google' && method === 'POST') {
    await commentRate(env, request, 'login', 20);
    const data = await jsonBody(request, 16_000), nonce = field(data, 'nonce', 64, true);
    const cookie = commentCookie(request, '__Host-aguri-comments-login'), parts = cookie.split('.'), now = Math.floor(Date.now() / 1000);
    if (parts.length !== 3 || parts[0] !== nonce || !/^[a-f0-9]{64}$/.test(nonce) || !/^\d{10}$/.test(parts[1])
        || Number(parts[1]) < now || Number(parts[1]) > now + 300 || !await equal(parts[2], await hmac(env.COMMENTS_SESSION_SECRET, parts.slice(0,2).join('.')))) fail(401, 'login_expired', 'Start Google sign-in again.');
    const claims = await commentVerifyGoogle(data.credential, nonce, env);
    const userId = await digest('aguri-comments:google:' + claims.sub);
    const name = typeof claims.name === 'string' ? claims.name.normalize('NFC').replace(/[\u0000-\u001f\u007f]/g, '').trim().slice(0, 100) || 'Reader' : 'Reader';
    const token = hex(crypto.getRandomValues(new Uint8Array(32))), tokenHash = await hmac(env.COMMENTS_SESSION_SECRET, token);
    // nonce claim is single-use; the UNIQUE insert and session creation are atomic.
    try {
      await env.CONTRIBUTIONS_DB.batch([
        stmt(env, 'INSERT INTO comment_login_nonces(nonce_hash,expires_at) VALUES(?,?)', await digest(nonce), now + 7200),
        stmt(env, 'INSERT INTO comment_users(id,name,created_at) VALUES(?,?,?) ON CONFLICT(id) DO UPDATE SET name=excluded.name', userId, name, new Date().toISOString()),
        stmt(env, 'INSERT INTO comment_sessions(token_hash,user_id,expires_at) VALUES(?,?,?)', tokenHash, userId, now + COMMENT_SESSION_SECONDS),
        stmt(env, 'DELETE FROM comment_sessions WHERE expires_at<=?', now),
        stmt(env, 'DELETE FROM comment_login_nonces WHERE expires_at<=?', now),
        stmt(env, 'DELETE FROM comment_rate_limits WHERE expires_at<=?', now),
      ]);
    } catch (error) { if (/UNIQUE.*comment_login_nonces/i.test(String(error))) fail(401, 'login_replayed', 'Start Google sign-in again.'); throw error; }
    return json({ user: { id: userId, name }, csrf_token: await hmac(env.COMMENTS_SESSION_SECRET, 'csrf:' + token) }, 200,
      { 'Set-Cookie': commentSetCookie('__Host-aguri-comments', token, COMMENT_SESSION_SECONDS) });
  }
  if (path === '/api/comments/me' && method === 'GET') {
    const session = await commentSession(request, env, false);
    return json(session ? { user: { id: session.user_id, name: session.name }, csrf_token: session.csrf_token } : { user: null });
  }
  if (path === '/api/comments/auth/logout' && method === 'POST') {
    const session = await commentSession(request, env, true, true);
    await stmt(env, 'DELETE FROM comment_sessions WHERE token_hash=?', session.token_hash).run();
    return json({ signed_out: true }, 200, { 'Set-Cookie': commentSetCookie('__Host-aguri-comments', '', 0) });
  }
  if (path === '/api/comments/review' || path.startsWith('/api/comments/review/')) {
    await editor(request, env);
    if (path === '/api/comments/review' && method === 'GET') {
      const status = url.searchParams.get('status') || 'pending';
      if (!['pending','approved','rejected','hidden','deleted'].includes(status)) fail(400, 'invalid_status', 'Choose a comment status.');
      const cursor = commentCursor(url.searchParams.get('cursor'));
      const found = rows(await stmt(env, `SELECT id,page,name,body,status,version,created_at,updated_at,
        (SELECT count(*) FROM comment_reports r WHERE r.comment_id=comments.id) AS report_count
        FROM comments WHERE status=? ${cursor ? 'AND (created_at<? OR (created_at=? AND id<?))' : ''} ORDER BY created_at DESC,id DESC LIMIT 21`, status, ...(cursor ? [cursor[0],cursor[0],cursor[1]] : [])).all());
      for (const item of found.slice(0, 20)) item.reports = rows(await stmt(env,
        'SELECT reason,created_at FROM comment_reports WHERE comment_id=? ORDER BY created_at DESC LIMIT 20', item.id).all());
      return json(commentListResult(found));
    }
    const match = path.match(/^\/api\/comments\/review\/([a-f0-9-]{36})$/i);
    if (match && UUID.test(match[1]) && method === 'PATCH') {
      const data = await jsonBody(request, 6000), note = field(data, 'note', 1000);
      if (!['approved','rejected','hidden'].includes(data.status)) fail(400, 'invalid_status', 'Choose approved, rejected or hidden.');
      if (!Number.isSafeInteger(data.version) || data.version < 1) fail(400, 'invalid_version', 'Reload the moderation queue.');
      const results = await env.CONTRIBUTIONS_DB.batch([
        stmt(env, "UPDATE comments SET status=?,moderation_note=?,updated_at=?,version=version+1 WHERE id=? AND version=? AND status<>'deleted' RETURNING id,status,version", data.status,note,new Date().toISOString(),match[1],data.version),
      ]);
      const row = rows(results[0])[0];
      if (!row) fail(409, 'moderation_conflict', 'This comment changed. Reload the moderation queue.');
      return json(row);
    }
    fail(404, 'not_found', 'This service route could not be found.');
  }
  if (path === '/api/comments' && method === 'GET' || path === '/api/comments/mine' && method === 'GET') {
    await commentRate(env, request, 'read', 240);
    const page = await commentPage(url.searchParams.get('page'), request, env), cursor = commentCursor(url.searchParams.get('cursor'));
    const mine = path.endsWith('/mine'), session = mine ? await commentSession(request, env) : null;
    const found = rows(await stmt(env, `SELECT id,page,name,body,created_at${mine ? ',status' : ''} FROM comments
      WHERE page=? AND ${mine ? "user_id=? AND status<>'deleted'" : "status='approved'"}
      ${cursor ? 'AND (created_at<? OR (created_at=? AND id<?))' : ''} ORDER BY created_at DESC,id DESC LIMIT 21`, page,
      ...(mine ? [session.user_id] : []), ...(cursor ? [cursor[0],cursor[0],cursor[1]] : [])).all());
    return json(commentListResult(found));
  }
  if (path === '/api/comments' && method === 'POST') {
    const session = await commentSession(request, env, true, true), data = await jsonBody(request, 12_000);
    const page = await commentPage(data.page, request, env), body = field(data, 'body', 2000, true), clientId = field(data, 'client_id', 36, true);
    if (!UUID.test(clientId) || data.consent !== true || data.terms_version !== COMMENTS_TERMS) fail(400, 'consent_required', 'Accept the current comment publication terms.');
    const payloadHash = await digest(JSON.stringify([page,body,COMMENTS_TERMS]));
    const existing = await stmt(env, 'SELECT id,status,payload_hash FROM comments WHERE user_id=? AND client_id=?', session.user_id,clientId).first();
    if (existing) {
      if (existing.payload_hash !== payloadHash) fail(409, 'submission_conflict', 'Use a new reference for different text.');
      return json({ id:existing.id,status:existing.status });
    }
    await commentRate(env, request, 'post-ip', 20);
    await commentRate(env, request, 'post-user', 5, 3600, session.user_id);
    const id = crypto.randomUUID(), now = new Date().toISOString();
    await stmt(env, `INSERT OR IGNORE INTO comments(id,user_id,client_id,payload_hash,page,name,body,terms_version,consented_at,created_at,updated_at)
      VALUES(?,?,?,?,?,?,?,?,?,?,?)`, id,session.user_id,clientId,payloadHash,page,session.name,body,COMMENTS_TERMS,now,now,now).run();
    const saved = await stmt(env, 'SELECT id,status,payload_hash FROM comments WHERE user_id=? AND client_id=?', session.user_id,clientId).first();
    if (!saved || saved.payload_hash !== payloadHash) fail(409, 'submission_conflict', 'Use a new reference for different text.');
    return json({ id:saved.id,status:saved.status }, saved.id === id ? 201 : 200);
  }
  const match = path.match(/^\/api\/comments\/([a-f0-9-]{36})(\/report)?$/i);
  if (match && UUID.test(match[1])) {
    const session = await commentSession(request, env, true, true);
    if (!match[2] && method === 'DELETE') {
      const row = await stmt(env, "UPDATE comments SET body='',name='',status='deleted',moderation_note='',version=version+1,updated_at=? WHERE id=? AND user_id=? RETURNING id,status", new Date().toISOString(),match[1],session.user_id).first();
      if (!row) fail(404, 'comment_not_found', 'This comment could not be found.');
      return json(row);
    }
    if (match[2] && method === 'POST') {
      await commentRate(env, request, 'report', 10,3600,session.user_id);
      const data = await jsonBody(request, 3000), reason = field(data,'reason',500,true);
      const row = await stmt(env, "SELECT id FROM comments WHERE id=? AND status='approved'", match[1]).first();
      if (!row) fail(404, 'comment_not_found', 'This comment could not be found.');
      await stmt(env, 'INSERT OR IGNORE INTO comment_reports(comment_id,user_id,reason,created_at) VALUES(?,?,?,?)',match[1],session.user_id,reason,new Date().toISOString()).run();
      return json({ reported: true });
    }
  }
  fail(404, 'not_found', 'This service route could not be found.');
}

export default {
  async fetch(request, env) {
    const url = new URL(request.url), path = url.pathname;
    if ((request.method === 'GET' || request.method === 'HEAD') && (path === '/' || path === '/index.html'))
      return homepageLanguage(request, env);
    if (path !== '/api' && !path.startsWith('/api/')) {
      let decoded = path;
      try { decoded = decodeURIComponent(path); } catch { return new Response('Not found', { status: 404, headers: SECURITY }); }
      if (/(?:^|\/)(?:contributions(?:\/|$)|_worker(?:\.js|\.mjs)?$|schema\.sql$|\.dev\.vars$)/i.test(decoded))
        return new Response('Not found', { status: 404, headers: SECURITY });
      return env.ASSETS ? env.ASSETS.fetch(request) : new Response('Not found', { status: 404 });
    }
    try {
      if (path.startsWith('/api/documents/')) return await journalDocument(request, path);
      validateOrigin(request);
      if (path === '/api/comments' || path.startsWith('/api/comments/')) return await commentsApi(request, env);
      if (path === '/api/page-views') return await pageViews(request, env);
      if (path === '/api/contact/config' && request.method === 'GET') {
        const available = contactConfigured(env, request);
        return json({ available, ...(available ? { turnstile_site_key: env.CONTACT_TURNSTILE_SITE_KEY } : {}) });
      }
      if (path === '/api/contact' && request.method === 'POST') return await contactSubmit(request, env);
      if (path === '/api/config' && request.method === 'GET') return json({ available: configured(env), uploads: { max_files: MAX_FILES, max_file_bytes: MAX_FILE },
        ...(env.TURNSTILE_SECRET_KEY && env.TURNSTILE_SITE_KEY ? { turnstile_site_key: env.TURNSTILE_SITE_KEY } : {}) });
      if (path.startsWith('/api/push/')) {
        if (path === '/api/push/config' && request.method === 'GET')
          return json({ available: pushConfigured(env), ...(pushConfigured(env) ? { public_key: env.VAPID_PUBLIC_KEY } : {}) });
        if (!pushConfigured(env)) fail(503, 'service_unavailable', 'Notifications are not available yet.');
        if (path === '/api/push/subscribe' && request.method === 'POST') return await pushSubscribe(request, env);
        if (path === '/api/push/unsubscribe' && request.method === 'POST') return await pushUnsubscribe(request, env);
        if (path === '/api/push/send' && request.method === 'POST') { await editor(request, env); return await pushSend(request, env); }
        if (path === '/api/push/stats' && request.method === 'GET') { await editor(request, env); return await pushStats(env); }
        fail(404, 'not_found', 'This service route could not be found.');
      }
      if (!configured(env)) fail(503, 'service_unavailable', 'Contributions are not available yet. Please try again later.');
      if (path === '/api/contributions' && request.method === 'POST') return await submit(request, env);
      let match = path.match(/^\/api\/contributions\/([a-f0-9-]{36})(\/reply)?$/i);
      if (match && UUID.test(match[1])) {
        if (!match[2] && request.method === 'GET') return json(publicRecord(await receipt(request, env, match[1])));
        if (match[2] && request.method === 'POST') return await reply(request, env, match[1]);
      }
      if (path === '/api/review' || path.startsWith('/api/review/')) {
        await editor(request, env);
        if (path === '/api/review' && request.method === 'GET') return await reviewList(request, env);
        match = path.match(/^\/api\/review\/([a-f0-9-]{36})(?:\/files\/([a-f0-9-]{36}))?$/i);
        if (match && UUID.test(match[1]) && (!match[2] || UUID.test(match[2]))) {
          if (match[2] && request.method === 'GET') return await download(env, match[1], match[2]);
          if (!match[2] && request.method === 'GET') return await reviewDetail(env, match[1]);
          if (!match[2] && request.method === 'PATCH') return await reviewUpdate(request, env, match[1]);
        }
      }
      fail(404, 'not_found', 'This service route could not be found.');
    } catch (error) {
      if (error instanceof ApiError) return json({ error: error.code, message: error.message }, error.status, error.status === 429 ? { 'Retry-After': '3600' } : {});
      // Do not expose SQL, submitted text, tokens, database errors, or secrets.
      return json({ error: 'service_error', message: 'The service could not complete this request. Please try again.' }, 503);
    }
  },
};
