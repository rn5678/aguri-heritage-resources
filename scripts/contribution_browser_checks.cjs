/* End-to-end checks against the real Worker and an isolated temporary SQLite
 * database. Build the site first. No test data is written to the preview or
 * production service, and editor/receipt keys are never printed. */
const { chromium } = require('playwright');
const assert = require('node:assert/strict');
const fs = require('node:fs/promises');
const path = require('node:path');
const os = require('node:os');
const net = require('node:net');
const { spawn } = require('node:child_process');
const { once } = require('node:events');
const root = path.resolve(__dirname, '..');
const pause = ms => new Promise(resolve => setTimeout(resolve, ms));

async function openedFile(page, selector, expectedType) {
  const [preview] = await Promise.all([page.waitForEvent('popup'), page.locator(selector).click()]);
  try {
    await preview.waitForURL(url => url.protocol === 'blob:');
    await preview.waitForLoadState('domcontentloaded');
    assert.equal(await preview.evaluate(() => window.opener), null, 'The opened file cannot access its parent page');
    const file = await preview.evaluate(async () => {
      const response = await fetch(location.href);
      return { url: location.href, type: response.headers.get('content-type'), text: await response.text() };
    });
    assert.ok(file.url.startsWith('blob:'), 'The file opens locally without an external viewer');
    assert.equal(file.type.split(';')[0], expectedType, 'The file keeps its browser-readable MIME type');
    return file.text;
  } finally { await preview.close(); }
}

async function freePort() {
  const socket = net.createServer();
  socket.listen(0, '127.0.0.1');
  await once(socket, 'listening');
  const port = socket.address().port;
  await new Promise(resolve => socket.close(resolve));
  return port;
}

(async () => {
  const state = await fs.mkdtemp(path.join(os.tmpdir(), 'aguri-contributions-test-'));
  const port = await freePort(), origin = `http://127.0.0.1:${port}`;
  let browser;
  const server = spawn(process.execPath, [path.join(root, 'scripts/serve_contributions.mjs')], {
    cwd: root, env: { ...process.env, AGURI_LOCAL_STATE: state, AGURI_PORT: String(port) }, stdio: ['ignore', 'pipe', 'pipe']
  });
  let serverErrors = '';
  server.stderr.on('data', chunk => { serverErrors += String(chunk); });
  const logs = [];
  try {
    let ready = false;
    for (let attempt = 0; attempt < 100; attempt++) {
      if (server.exitCode !== null) throw new Error(`Isolated test server exited: ${serverErrors}`);
      try { ready = (await (await fetch(origin + '/api/config')).json()).available === true; } catch (_) {}
      if (ready) break;
      await pause(100);
    }
    assert.ok(ready, 'The isolated real service starts');
    const editorKey = (await fs.readFile(path.join(state, 'editor-key.txt'), 'utf8')).trim();
    const api = (pathname, { token, ...options } = {}) => fetch(origin + pathname, {
      ...options, headers: { Origin: origin, ...(token ? { Authorization: `Bearer ${token}` } : {}), ...options.headers }
    });
    assert.equal((await api('/api/review')).status, 401, 'Inbox requires authentication');
    browser = await chromium.launch({ channel: 'chrome', headless: true });
    await fs.mkdir(path.join(root, 'research'), { recursive: true });
    for (const lang of ['en', 'bn']) {
      const base = origin + (lang === 'bn' ? '/bn/' : '/');
      const publicPage = await browser.newPage({ viewport: { width: 1440, height: 1000 } });
      const editorPage = await browser.newPage({ viewport: { width: 1440, height: 1000 } });
      const errors = [];
      const downloads = [];
      publicPage.on('pageerror', error => errors.push(error.message));
      editorPage.on('pageerror', error => errors.push(error.message));
      publicPage.on('download', download => downloads.push(download));
      editorPage.on('download', download => downloads.push(download));
      editorPage.on('dialog', dialog => dialog.accept());
      publicPage.on('dialog', dialog => dialog.accept());
      const title = `${lang.toUpperCase()} browser fixture <img src=x onerror=alert(1)>`;
      const publicNote = lang === 'bn' ? 'অনুগ্রহ করে তারিখটি নিশ্চিত করুন।' : 'Please confirm the approximate date.';
      const reply = lang === 'bn' ? 'স্মৃতিটি আনুমানিক ১৯৫০ সালের।' : 'The memory dates to approximately 1950.';
      const privateNote = 'Private fixture note: verify the source before publication.';
      const sourcePath = `${lang === 'bn' ? '/bn' : ''}/history.html#historical-test-context`;

      await publicPage.goto(origin + sourcePath);
      await publicPage.locator('[data-correction]').click();
      await publicPage.waitForURL('**/contribute.html?**');
      await publicPage.waitForFunction(() => !document.querySelector('#contribution-send').disabled);
      assert.equal(await publicPage.locator('[name=source_page]').inputValue(), sourcePath, 'Correction context keeps its page and anchor');
      assert.equal(await publicPage.locator('[name=type]:checked').inputValue(), 'correction');
      assert.equal(await publicPage.locator('[name=terms_version]').inputValue(), '2026-10-04');
      assert.equal(await publicPage.locator('#contribution-consent').isChecked(), false, 'Publication consent is never preselected');
      assert.equal(await publicPage.locator('#consent-publication').isVisible(), true);
      assert.equal(await publicPage.locator('#consent-rights').isVisible(), false);
      assert.equal(await publicPage.locator('#consent-publication a').getAttribute('href'), 'contributor-terms.html');
      await publicPage.locator('#contribution-title').fill(title);
      await publicPage.locator('#contribution-description').fill('A synthetic correction for automated verification.\nOriginal source retained; exact date uncertain.');
      if (lang === 'en') {
        await publicPage.locator('#contribution-name').evaluate(input => { input.closest('details').open = true; });
        await publicPage.locator('#contribution-name').fill('Test contributor');
        await publicPage.locator('#contribution-email').fill('private@example.test');
        await publicPage.locator('[name=credit]').check();
      }
      await publicPage.locator('#contribution-files').setInputFiles({ name: 'source-note.txt', mimeType: 'text/plain', buffer: Buffer.from('Synthetic source document for automated review checks.\n') });
      await publicPage.locator('#contribution-rights').check();
      await publicPage.locator('#contribution-consent').check();
      for (const width of [1440, 390, 320]) {
        await publicPage.setViewportSize({ width, height: 1000 });
        assert.equal(await publicPage.evaluate(() => document.documentElement.scrollWidth > innerWidth + 1), false, `${lang}: contribution form fits ${width}px`);
        if (width !== 320) await publicPage.screenshot({ path: path.join(root, `research/contribution-${lang}-${width}.png`), fullPage: true });
      }
      const submitted = publicPage.waitForResponse(response => response.url() === origin + '/api/contributions' && response.request().method() === 'POST');
      await publicPage.locator('#contribution-send').click();
      const response = await submitted;
      assert.equal(response.status(), 201, `Actual ${lang} form submission accepted`);
      const receipt = await response.json();
      await publicPage.locator('#contribution-receipt').waitFor({ state: 'visible' });
      assert.equal(await publicPage.locator('#receipt-title').innerText(), title);
      assert.equal(await publicPage.locator('#receipt-title img').count(), 0, 'Submitted title is text, not markup');
      const tracking = await publicPage.locator('#receipt-link').inputValue();
      assert.ok(new URL(tracking).hash.startsWith('#receipt='));
      assert.equal(new URL(tracking).search, '', 'Private tracking key is not a query parameter');
      assert.equal((await api(`/api/contributions/${receipt.id}`)).status, 404, 'Receipt requires its private token and hides whether the ID exists');
      const publicRecord = await (await api(`/api/contributions/${receipt.id}`, { token: receipt.token })).json();
      for (const field of ['email', 'internal_note', 'description', 'token_hash']) assert.equal(Object.hasOwn(publicRecord, field), false, `Receipt excludes ${field}`);
      const initialRefresh = publicPage.waitForResponse(r => r.url() === origin + `/api/contributions/${receipt.id}` && r.request().method() === 'GET');
      await publicPage.locator('#refresh-receipt').click();
      await initialRefresh;
      await publicPage.waitForFunction(() => !document.querySelector('#refresh-receipt').disabled);
      assert.equal(await publicPage.locator('#receipt-publication').isVisible(), false, 'An unpublished contribution has no publication link');
      const openedReceipt = JSON.parse(await openedFile(publicPage, '#download-receipt', 'application/json'));
      assert.equal(openedReceipt.id, receipt.id);
      assert.equal(openedReceipt.tracking_link, tracking);
      for (const field of ['email', 'internal_note', 'description', 'token_hash'])
        assert.equal(Object.hasOwn(openedReceipt, field), false, `Opened receipt excludes ${field}`);

      await editorPage.goto(base + 'review.html');
      await editorPage.locator('#editor-key').fill('invalid-editor-key');
      await editorPage.locator('#review-login button').click();
      await editorPage.waitForFunction(() => document.querySelector('#review-message').dataset.error === 'true');
      assert.equal(await editorPage.locator('#review-workspace').isVisible(), false);
      await editorPage.locator('#editor-key').fill(editorKey);
      await editorPage.locator('#review-login button').click();
      await editorPage.locator('#review-workspace').waitFor({ state: 'visible' });
      assert.equal(await editorPage.locator('#editor-key').inputValue(), '', 'Editor key immediately cleared from input');
      await editorPage.locator('#review-query').fill(title);
      await editorPage.locator('#review-filters button').click();
      await editorPage.waitForFunction(() => document.querySelectorAll('.review-item').length === 1);
      await editorPage.locator('.review-item').click();
      await editorPage.locator('#review-record').waitFor({ state: 'visible' });
      assert.equal(await editorPage.locator('#review-record-title').innerText(), title);
      assert.equal(await editorPage.locator('#review-record-title img').count(), 0);
      for (const width of [1440, 390, 320]) {
        await editorPage.setViewportSize({ width, height: 1000 });
        assert.equal(await editorPage.evaluate(() => document.documentElement.scrollWidth > innerWidth + 1), false, `${lang}: editor dashboard fits ${width}px`);
        if (width !== 320) await editorPage.screenshot({ path: path.join(root, `research/review-${lang}-${width}.png`), fullPage: true });
      }
      const save = async (status, publicMessage = publicNote) => {
        await editorPage.locator('#review-decision-status').selectOption(status);
        await editorPage.locator('#review-public-note').fill(publicMessage);
        await editorPage.locator('#review-internal-note').fill(privateNote);
        const update = editorPage.waitForResponse(r => r.url() === origin + `/api/review/${receipt.id}` && r.request().method() === 'PATCH');
        await editorPage.locator('#review-save').click();
        assert.equal((await update).status(), 200, `Save ${status}`);
        await editorPage.waitForFunction(() => document.querySelector('#review-save-status').textContent.includes(document.documentElement.lang === 'bn' ? 'সংরক্ষিত' : 'saved'));
      };
      await save('under_review');
      await save('needs_information');
      await publicPage.locator('#refresh-receipt').click();
      await publicPage.waitForFunction(expected => document.querySelector('#receipt-note').textContent === expected, publicNote);
      assert.equal(await publicPage.locator('#contribution-receipt').innerText().then(value => value.includes(privateNote)), false, 'Internal editorial note never reaches public receipt');
      await publicPage.locator('#contribution-reply').fill(reply);
      const replied = publicPage.waitForResponse(r => r.url().endsWith(`/api/contributions/${receipt.id}/reply`) && r.request().method() === 'POST');
      await publicPage.locator('#reply-send').click();
      assert.equal((await replied).status(), 201);
      await publicPage.waitForFunction(() => document.querySelector('#contribution-reply').value === '');

      // A real contributor reply invalidates the editor's existing version.
      await editorPage.locator('#review-internal-note').fill('Unsaved note retained during conflict');
      const conflict = editorPage.waitForResponse(r => r.url() === origin + `/api/review/${receipt.id}` && r.request().method() === 'PATCH');
      await editorPage.locator('#review-save').click();
      assert.equal((await conflict).status(), 409);
      await editorPage.waitForFunction(() => document.querySelector('#review-message').dataset.error === 'true');
      assert.equal(await editorPage.locator('#review-internal-note').inputValue(), 'Unsaved note retained during conflict');
      await editorPage.locator('#review-reload').click();
      await editorPage.locator('#review-replies').getByText(reply, { exact: true }).waitFor({ state: 'visible' });
      await save('approved');
      await editorPage.locator('#review-published-url').fill(`${lang === 'bn' ? '/bn' : ''}/history.html`);
      await save('published', lang === 'bn' ? 'প্রকাশিত নিবন্ধের লিঙ্ক সংযুক্ত করা হয়েছে।' : 'The published article is linked here.');
      await publicPage.locator('#refresh-receipt').click();
      await publicPage.waitForFunction(() => document.querySelector('#receipt-status').dataset.status === 'published');
      await publicPage.locator('#receipt-publication').waitFor({ state: 'visible' });
      assert.equal(await publicPage.locator('#receipt-published-link').getAttribute('href'), base + 'history.html');

      assert.match(await editorPage.locator('.review-file-button').innerText(), lang === 'bn' ? /খুলুন/ : /^Open /);
      assert.match(await openedFile(editorPage, '.review-file-button', 'text/plain'), /Synthetic source document/);
      const exported = JSON.parse(await openedFile(editorPage, '#review-export', 'application/json'));
      assert.equal(exported.submission.id, receipt.id);
      assert.equal(exported.submission.status, 'published');
      assert.equal(exported.submission.internal_note, privateNote);
      assert.equal(exported.consent_info.status, 'recorded');
      assert.equal(exported.consent_info.terms_version, '2026-10-04');
      assert.equal(exported.consent_info.purpose, 'contribution');
      assert.equal(exported.consent_info.language, lang);
      assert.ok(exported.consent_info.accepted_at);
      assert.equal(await editorPage.locator('#review-consent-warning').isVisible(), false);
      assert.match(await editorPage.locator('#review-metadata').innerText(), /2026-10-04/);
      assert.equal(exported.attachments.length, 1);
      assert.equal(exported.replies[0].message, reply);
      assert.ok(exported.history.length >= 5);
      assert.equal(JSON.stringify(exported).includes(editorKey), false);
      const attachmentId = exported.attachments[0].id;
      assert.equal((await api(`/api/review/${receipt.id}/files/${attachmentId}`)).status, 401, 'Files require editor authentication');

      // Exercise the private rights path in each language against the same isolated Worker.
      const rightsTitle = `${lang.toUpperCase()} private rights enquiry fixture`;
      await publicPage.goto(base + 'contribute.html?type=rights&page=history.html');
      await publicPage.waitForFunction(() => !document.querySelector('#contribution-send').disabled);
      assert.equal(await publicPage.locator('[name=type]:checked').inputValue(), 'rights');
      assert.equal(await publicPage.locator('#contribution-consent').isChecked(), false);
      assert.equal(await publicPage.locator('#consent-rights').isVisible(), true);
      assert.equal(await publicPage.locator('#consent-publication').isVisible(), false);
      assert.equal(await publicPage.locator('#consent-rights a').getAttribute('href'), 'rights.html#permission');
      assert.equal(await publicPage.locator('#credit-label').isVisible(), false);
      assert.equal(await publicPage.locator('[name=credit]').isDisabled(), true);
      await publicPage.locator('#contribution-consent').check();
      await publicPage.locator('[name=type][value=correction]').check();
      assert.equal(await publicPage.locator('#contribution-consent').isChecked(), false, 'Changing purpose clears prior private consent');
      assert.equal(await publicPage.locator('#consent-publication').isVisible(), true);
      await publicPage.locator('#contribution-consent').check();
      await publicPage.locator('[name=type][value=rights]').check();
      assert.equal(await publicPage.locator('#contribution-consent').isChecked(), false, 'Changing purpose clears prior publication consent');
      await publicPage.locator('#contribution-title').fill(rightsTitle);
      await publicPage.locator('#contribution-description').fill('Synthetic removal enquiry. The attached evidence is for private assessment only; its copyright belongs to another person.');
      await publicPage.locator('#contribution-files').setInputFiles({ name: 'private-evidence.txt', mimeType: 'text/plain', buffer: Buffer.from('Synthetic private evidence; not licensed for publication.\n') });
      const attachmentConsent = await publicPage.locator('#attachment-consent').innerText();
      assert.ok(attachmentConsent.includes(lang === 'bn' ? 'প্রকাশের অনুমতি দেওয়া হচ্ছে না' : 'not permission to publish'));
      await publicPage.locator('#contribution-rights').check();
      const draft = JSON.parse(await openedFile(publicPage, '#download-draft', 'application/json'));
      assert.equal(draft.draft, true);
      assert.equal(draft.consent, 'no', 'Draft explicitly records lack of acceptance');
      assert.equal(draft.terms_version, '2026-10-04');
      assert.equal(draft.consent_purpose, 'rights-enquiry');
      assert.equal(draft.terms_url, base + 'rights.html#permission');
      assert.equal(draft.attachments.length, 1);
      await publicPage.locator('#contribution-consent').check();
      const rightsSubmitted = publicPage.waitForResponse(r => r.url() === origin + '/api/contributions' && r.request().method() === 'POST');
      await publicPage.locator('#contribution-send').click();
      const rightsResponse = await rightsSubmitted;
      assert.equal(rightsResponse.status(), 201, `Actual ${lang} private enquiry accepted`);
      const rightsReceipt = await rightsResponse.json();
      assert.equal(rightsReceipt.type, 'rights');
      await publicPage.locator('#contribution-receipt').waitFor({ state: 'visible' });
      assert.ok((await publicPage.locator('#receipt-intro').innerText()).includes(lang === 'bn' ? 'অনুমতি দেওয়া' : 'permission has been granted'));
      await publicPage.reload();
      await publicPage.waitForFunction(() => !document.querySelector('#reply-send').disabled);
      assert.ok((await publicPage.locator('#receipt-heading').innerText()).includes(lang === 'bn' ? 'অনুরোধ' : 'enquiry'));
      assert.equal(await publicPage.locator('#receipt-publication').isVisible(), false);

      await editorPage.locator('#review-status').selectOption('');
      await editorPage.locator('#review-query').fill(rightsTitle);
      await editorPage.locator('#review-filters button').click();
      await editorPage.waitForFunction(title => document.querySelectorAll('.review-item').length === 1 && document.querySelector('.review-item-title')?.textContent === title, rightsTitle);
      await editorPage.locator('.review-item').click();
      await editorPage.waitForFunction(title => document.querySelector('#review-record-title').textContent === title, rightsTitle);
      assert.ok((await editorPage.locator('#review-record-type').textContent()).includes(lang === 'bn' ? 'ব্যক্তিগত' : 'Private'));
      assert.equal(await editorPage.locator('#review-consent-warning').isVisible(), true);
      assert.equal(await editorPage.locator('#review-publication-controls').isVisible(), false);
      assert.equal(await editorPage.locator('#review-published-url').isDisabled(), true);
      assert.deepEqual(await editorPage.locator('#review-decision-status option').evaluateAll(options => options.filter(option => !option.disabled && !option.hidden).map(option => option.value)), ['received', 'under_review', 'needs_information', 'declined']);
      const rightsDetail = await (await api(`/api/review/${rightsReceipt.id}`, { token: editorKey })).json();
      assert.equal(rightsDetail.submission.type, 'rights');
      assert.equal(rightsDetail.submission.credit, 'no');
      assert.equal(rightsDetail.consent_info.status, 'recorded');
      assert.equal(rightsDetail.consent_info.terms_version, '2026-10-04');
      assert.equal(rightsDetail.consent_info.purpose, 'rights-enquiry');
      assert.equal(rightsDetail.consent_info.language, lang);
      assert.ok(rightsDetail.consent_info.accepted_at);
      assert.equal(rightsDetail.attachments.length, 1);
      const privateReply = lang === 'bn' ? 'এই প্রমাণ শুধু গোপনীয় পর্যালোচনার জন্য।' : 'This evidence is for private review only.';
      await publicPage.locator('#contribution-reply').fill(privateReply);
      const rightsReplied = publicPage.waitForResponse(r => r.url().endsWith(`/api/contributions/${rightsReceipt.id}/reply`) && r.request().method() === 'POST');
      await publicPage.locator('#reply-send').click();
      assert.equal((await rightsReplied).status(), 201);
      await publicPage.waitForFunction(() => document.querySelector('#contribution-reply').value === '');
      await editorPage.locator('#review-reload').click();
      await editorPage.locator('#review-replies').getByText(privateReply, { exact: true }).waitFor({ state: 'visible' });
      await editorPage.locator('#review-decision-status').selectOption('declined');
      await editorPage.locator('#review-public-note').fill('Synthetic enquiry handled privately; this message is not a reuse licence.');
      const rightsClosed = editorPage.waitForResponse(r => r.url() === origin + `/api/review/${rightsReceipt.id}` && r.request().method() === 'PATCH');
      await editorPage.locator('#review-save').click();
      assert.equal((await rightsClosed).status(), 200);
      await editorPage.waitForFunction(() => !document.querySelector('#review-save').disabled);
      await publicPage.locator('#refresh-receipt').click();
      await publicPage.waitForFunction(() => document.querySelector('#receipt-status').dataset.status === 'declined');
      assert.equal(await publicPage.locator('#receipt-status').innerText(), lang === 'bn' ? 'বন্ধ' : 'Closed');

      await editorPage.locator('#review-status').selectOption('published');
      await editorPage.locator('#review-query').fill('no-such-fixture-title');
      await editorPage.locator('#review-filters button').click();
      await editorPage.locator('.review-no-items').waitFor({ state: 'visible' });
      await editorPage.locator('#review-lock').click();
      assert.equal(await editorPage.locator('#review-workspace').isVisible(), false);
      assert.equal(await editorPage.locator('#review-metadata').textContent(), '');
      assert.equal(await editorPage.locator('#review-internal-note').inputValue(), '');
      assert.equal(await editorPage.evaluate(key => JSON.stringify({ local: { ...localStorage }, session: { ...sessionStorage } }).includes(key), editorKey), false);
      await editorPage.reload();
      assert.equal(await editorPage.locator('#review-workspace').isVisible(), false, 'Refresh requires a new login');
      assert.equal(downloads.length, 0, 'Files open in tabs without forcing downloads');
      assert.deepEqual(errors, [], 'No browser script errors');
      await publicPage.close();
      await editorPage.close();
      logs.push(`${lang}: real contribution and private rights forms, versioned consent/reset/evidence, draft permissions, private receipt/reply, restricted rights review, review statuses, concurrent-change protection, publishing link, authenticated file/record tabs, local JSON tabs with isolated openers, filters, responsive layout and locking passed.`);
    }
    const noJs = await browser.newPage({ javaScriptEnabled: false });
    await noJs.goto(origin + '/review.html');
    assert.equal(await noJs.locator('#review-login').isVisible(), false, 'No-script page cannot submit an editor key');
    await noJs.close();
    console.log(logs.join('\n'));
    console.log('All data lived in an isolated temporary database; no shared preview or production records were changed.');
  } finally {
    if (browser) await browser.close();
    if (server.exitCode === null) {
      const stopped = once(server, 'exit');
      server.kill('SIGTERM');
      await Promise.race([stopped, pause(3000)]);
      if (server.exitCode === null) server.kill('SIGKILL');
    }
    await fs.rm(state, { recursive: true, force: true });
  }
})().catch(error => { console.error(error.message); process.exitCode = 1; });
