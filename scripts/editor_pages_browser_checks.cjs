/* Run only against a disposable content-editor copy, never the working site.
 * Example: AGURI_EDITOR_QA=1 node scripts/editor_pages_browser_checks.cjs
 *          http://127.0.0.1:45874
 * This creates a synthetic page/type and saves synthetic English text. It never
 * publishes. The caller owns creation and deletion of the disposable QA copy.
 */
'use strict';

const { chromium } = require('playwright');
const assert = require('node:assert/strict');
const fs = require('node:fs/promises');
const path = require('node:path');

const origin = new URL(process.argv[2] || 'http://127.0.0.1:45874').origin;
const destination = new URL(origin);
const output = path.resolve(process.env.AGURI_EDITOR_QA_OUTPUT || 'output/editor-page-creation-checks');
const timeout = 60000;
const checks = [];
const screenshots = [];
const scriptErrors = [];
const stamp = `${Date.now().toString(36)}-${process.pid}`;
const initialTitle = `QA Community Memories ${stamp}`;
const title = `QA Community Memories Revised ${stamp}`;
const slug = `qa-community-memories-${stamp}`;
const typeName = `QA Village Story ${stamp}`;
const description = 'Synthetic community memories created only in the disposable browser-check site.';
const titleBn = `পরীক্ষামূলক সম্প্রদায়ের স্মৃতি ${stamp}`;
const descriptionBn = 'এই পাতাটি কেবল অস্থায়ী ব্রাউজার পরীক্ষার জন্য তৈরি করা হয়েছে।';
const savedText = `QA saved text ${stamp}. This text belongs only to the disposable browser-check site.`;
const unsavedText = `QA unsaved draft ${stamp}. This draft must survive a failed page creation.`;

function passed(message) { checks.push(message); }
function isPost(response, pathname) {
  return new URL(response.url()).pathname === pathname && response.request().method() === 'POST';
}

async function ready(page) {
  await page.locator('#document-heading').waitFor({ state: 'visible' });
  await page.waitForFunction(() => !document.querySelector('#add-page').disabled);
}

async function screenshot(page, filename) {
  await page.screenshot({ path: path.join(output, filename) });
  screenshots.push(filename);
}

async function dialogFits(page, selector, label) {
  const measurements = await page.locator(selector).evaluate(dialog => {
    const bounds = dialog.getBoundingClientRect();
    return {
      left: bounds.left, right: bounds.right, width: innerWidth,
      scrollWidth: dialog.scrollWidth, clientWidth: dialog.clientWidth,
      pageWidth: document.documentElement.scrollWidth
    };
  });
  assert.ok(measurements.left >= -1 && measurements.right <= measurements.width + 1, `${label}: dialog fits the viewport`);
  assert.ok(measurements.scrollWidth <= measurements.clientWidth + 1, `${label}: no horizontal scrolling inside dialog`);
  assert.ok(measurements.pageWidth <= measurements.width + 1, `${label}: editor has no horizontal overflow`);
}

async function fillPage(page, values = {}) {
  const value = { title, slug, description, titleBn, descriptionBn, ...values };
  await page.locator('#new-page-title').fill(value.title);
  await page.locator('#new-page-slug').fill(value.slug);
  await page.locator('#new-page-description').fill(value.description);
  await page.locator('#new-page-title-bn').fill(value.titleBn);
  await page.locator('#new-page-description-bn').fill(value.descriptionBn);
  if (value.type) await page.locator('#new-page-type').selectOption(value.type);
  if (value.section) await page.locator('#new-page-section').selectOption(value.section);
}

async function delayedSubmit(page, pathname, button, fields, cancel, assertExtra) {
  let release;
  const gate = new Promise(resolve => { release = resolve; });
  const handler = async route => { await gate; await route.continue(); };
  const matcher = url => url.pathname === pathname;
  await page.route(matcher, handler);
  const responsePromise = page.waitForResponse(response => isPost(response, pathname), { timeout });
  try {
    await page.locator(button).click();
    await page.waitForFunction(selector => document.querySelector(selector).disabled, fields);
    assert.equal(await page.locator(button).isDisabled(), true, `${pathname}: submit is locked during the request`);
    assert.equal(await page.locator(cancel).isDisabled(), true, `${pathname}: close is locked during the request`);
    assert.equal(await page.locator('#add-page').isDisabled(), true, `${pathname}: another page cannot be started`);
    assert.equal(await page.locator('#manage-page-types').isDisabled(), true, `${pathname}: another type cannot be started`);
    assert.equal(await page.locator('#save-button').isDisabled(), true, `${pathname}: document save is locked`);
    assert.equal(await page.locator('.language[data-lang=en]').isDisabled(), true, `${pathname}: language navigation is locked`);
    await page.keyboard.press('Escape');
    const dialog = pathname === '/api/pages/create' ? '#create-page-dialog' : '#page-types-dialog';
    assert.equal(await page.locator(dialog).evaluate(element => element.open), true, `${pathname}: Escape cannot hide an in-flight creation`);
    if (assertExtra) await assertExtra();
  } finally { release(); }
  try { return await responsePromise; }
  finally { await page.unroute(matcher, handler); }
}

(async () => {
  assert.equal(process.env.AGURI_EDITOR_QA, '1', 'Set AGURI_EDITOR_QA=1 only after starting a disposable content-editor copy.');
  assert.equal(destination.protocol, 'http:', 'QA must use the local disposable HTTP editor.');
  assert.ok(['127.0.0.1', 'localhost', '[::1]'].includes(destination.hostname), 'QA must target this computer.');
  assert.notEqual(destination.port || '80', '45873', 'Refusing to write to the normal content-editor port. Use a disposable QA server.');
  await fs.mkdir(output, { recursive: true });
  let browser;
  let page;
  let createdType;
  let section;
  try {
    browser = await chromium.launch({ channel: 'chrome', headless: true });
    page = await browser.newPage({ viewport: { width: 1440, height: 1040 } });
    page.setDefaultTimeout(timeout);
    page.setDefaultNavigationTimeout(timeout);
    page.on('pageerror', error => scriptErrors.push(error.message));
    let pageRequests = 0;
    page.on('request', request => {
      if (new URL(request.url()).pathname === '/api/pages/create' && request.method() === 'POST') pageRequests++;
    });
    await page.goto(origin + '/', { waitUntil: 'domcontentloaded' });
    await ready(page);
    const token = await page.locator('meta[name=editor-token]').getAttribute('content');
    assert.ok(token, 'The local editor supplies its request token.');
    const post = (pathname, data, headers = {}) => page.request.post(origin + pathname, {
      timeout, data, headers: { Origin: origin, 'X-Editor-Token': token, ...headers }
    });
    const catalog = await (await page.request.get(origin + '/api/pages')).json();
    assert.ok(catalog.types?.length && catalog.sections?.length, 'The editor supplies reusable page types and website sections.');
    section = catalog.sections[0].id;
    passed('Catalog includes pages, page types and sections.');

    // Keep this test entirely local: saving its English fixture must not start
    // an external translation session against the user's subscription.
    if (await page.locator('#translation-enabled').isChecked()) {
      const setting = page.waitForResponse(response => isPost(response, '/api/translation/settings'));
      await page.locator('#translation-enabled').uncheck();
      assert.equal((await setting).status(), 200, 'Automatic translation can be disabled in the disposable copy.');
      await page.waitForFunction(() => !document.querySelector('#translation-enabled').disabled);
    }

    await page.locator('#add-page').click();
    await page.locator('#create-page-dialog').waitFor({ state: 'visible' });
    assert.equal(await page.locator('#create-page-form').evaluate(form => form.checkValidity()), false);
    const beforeInvalid = pageRequests;
    await page.locator('#create-page-submit').click();
    assert.equal(pageRequests, beforeInvalid, 'Required fields prevent an API request.');
    assert.equal(await page.locator('#create-page-dialog').evaluate(dialog => dialog.open), true);
    await page.locator('#new-page-title').fill(initialTitle);
    assert.equal(await page.locator('#new-page-slug').inputValue(), slug, 'English title generates the address.');
    const manualSlug = `qa-custom-address-${stamp}`;
    await page.locator('#new-page-slug').fill(manualSlug);
    await page.locator('#new-page-title').fill(title);
    assert.equal(await page.locator('#new-page-slug').inputValue(), manualSlug, 'An edited address survives later title edits.');
    await fillPage(page, { section });
    passed('Required bilingual fields, automatic addresses and address overrides work.');

    await page.locator('#create-page-add-type').click();
    assert.equal(await page.locator('#create-page-dialog').evaluate(dialog => dialog.open), true, 'The parent Add page form stays open.');
    await page.locator('#new-type-name').fill(typeName);
    await page.locator('#new-type-template').selectOption('general');
    await page.locator('#new-type-description').fill('Synthetic reusable layout for the disposable QA site.');
    await dialogFits(page, '#page-types-dialog', 'Desktop page types');
    await screenshot(page, 'desktop-page-types.png');
    await page.setViewportSize({ width: 320, height: 850 });
    await dialogFits(page, '#page-types-dialog', '320px page types');
    await screenshot(page, 'mobile-page-types-320.png');
    await page.setViewportSize({ width: 1440, height: 1040 });
    const typeResponse = await delayedSubmit(page, '/api/page-types/create', '#page-types-submit', '#page-types-fields', '#page-types-cancel');
    assert.equal(typeResponse.status(), 200, 'Custom page type is saved by the real server.');
    const typeData = await typeResponse.json();
    createdType = typeData.types.find(type => type.name === typeName)?.id;
    assert.ok(createdType, 'The saved custom type is returned.');
    await page.locator('#page-types-dialog').waitFor({ state: 'hidden' });
    await page.waitForFunction(() => !document.querySelector('#create-page-submit').disabled);
    assert.equal(await page.locator('#new-page-type').inputValue(), createdType, 'The new custom type is selected.');
    for (const [selector, expected] of [['#new-page-title', title], ['#new-page-slug', slug], ['#new-page-description', description], ['#new-page-title-bn', titleBn], ['#new-page-description-bn', descriptionBn]]) {
      assert.equal(await page.locator(selector).inputValue(), expected, `Nested type creation preserves ${selector}.`);
    }
    passed('Nested page-type creation preserves all Add page inputs and selects the new reusable type.');

    await dialogFits(page, '#create-page-dialog', 'Desktop Add page');
    await page.locator('#create-page-dialog').evaluate(dialog => { dialog.scrollTop = 0; });
    await screenshot(page, 'desktop-add-page.png');
    await page.setViewportSize({ width: 320, height: 850 });
    await dialogFits(page, '#create-page-dialog', '320px Add page');
    await page.locator('#create-page-dialog').evaluate(dialog => { dialog.scrollTop = 0; });
    await screenshot(page, 'mobile-add-page-320.png');
    await page.setViewportSize({ width: 1440, height: 1040 });
    const createResponse = await delayedSubmit(page, '/api/pages/create', '#create-page-submit', '#create-page-fields', '#create-page-cancel');
    assert.equal(createResponse.status(), 200, 'The real server builds and accepts a bilingual page.');
    const created = await createResponse.json();
    assert.equal(created.document.id, slug);
    assert.equal(created.document.lang, 'en');
    await page.locator('#create-page-dialog').waitFor({ state: 'hidden' });
    await page.waitForFunction(expected => document.querySelector('#document-title').textContent === expected && !document.querySelector('#add-page').disabled, title);
    assert.match(await page.locator('#document-eyebrow').innerText(), new RegExp(typeName.toUpperCase()));
    assert.ok((await page.locator('#document-content').innerText()).includes(description));
    passed('Creation opens the new saved document and records the chosen custom page type.');
    passed('Creation requests lock fields, cancellation, navigation and document saves until complete.');
    passed('Both dialogs fit desktop and 320px viewports without horizontal overflow.');

    const paragraph = page.locator('#document-content p.editable-block').first();
    await paragraph.fill(savedText);
    assert.equal(await page.locator('#save-button').isDisabled(), false);
    const saveResponse = page.waitForResponse(response => isPost(response, '/api/save'), { timeout });
    await page.locator('#save-button').click();
    assert.equal((await saveResponse).status(), 200, 'New page uses the existing real document save/build flow.');
    await page.waitForFunction(() => !document.querySelector('#add-page').disabled && document.querySelector('#save-button').disabled);
    assert.equal(await page.locator('#document-content p.editable-block').first().innerText(), savedText);
    await screenshot(page, 'desktop-created-page.png');
    await page.locator('.language[data-lang=bn]').click();
    await page.waitForFunction(expected => document.querySelector('#document-title').textContent === expected && document.querySelector('#document-content').lang === 'bn' && !document.querySelector('#add-page').disabled, titleBn);
    const bengaliContent = await page.locator('#document-content').innerText();
    assert.ok(bengaliContent.includes(descriptionBn), 'Bengali description is preserved independently.');
    assert.ok(bengaliContent.includes('পরিচিতি'), 'Bengali uses localized scaffold headings.');
    assert.equal(bengaliContent.includes('Add the information this page should share.'), false, 'Bengali scaffold has no English starter prose.');
    passed('The new page supports body editing/saving and a separate localized Bengali document.');

    await page.reload({ waitUntil: 'domcontentloaded' });
    await ready(page);
    await page.locator('#page-search').fill(slug);
    await page.locator('.page-item').filter({ hasText: title }).click();
    await page.waitForFunction(expected => document.querySelector('#document-title').textContent === expected && !document.querySelector('#add-page').disabled, title);
    assert.equal(await page.locator('#document-content p.editable-block').first().innerText(), savedText, 'Saved new-page text persists after reload.');
    await page.locator('#manage-page-types').click();
    assert.ok((await page.locator('#page-types-list').innerText()).includes(typeName), 'The custom page type persists after reload.');
    await page.locator('#page-types-cancel').click();
    passed('The new page, saved text and custom page type persist across an editor reload.');

    await page.locator('#document-content p.editable-block').first().fill(unsavedText);
    await page.locator('#add-page').click();
    await fillPage(page, { title: `Duplicate QA page ${stamp}`, slug, type: createdType, section });
    const beforeDiscard = pageRequests;
    page.once('dialog', dialog => dialog.dismiss());
    await page.locator('#create-page-submit').click();
    assert.equal(pageRequests, beforeDiscard, 'Declining the unsaved-edit confirmation sends no creation request.');
    assert.equal(await page.locator('#create-page-dialog').evaluate(dialog => dialog.open), true);
    page.once('dialog', dialog => dialog.accept());
    const duplicateResponse = page.waitForResponse(response => isPost(response, '/api/pages/create'), { timeout });
    await page.locator('#create-page-submit').click();
    assert.equal((await duplicateResponse).status(), 400, 'A duplicate page address is rejected.');
    await page.locator('#create-page-status.error').waitFor({ state: 'visible' });
    assert.equal(await page.locator('#new-page-slug').inputValue(), slug, 'Failed creation keeps the form details.');
    await page.locator('#create-page-cancel').click();
    assert.equal(await page.locator('#document-title').innerText(), title);
    assert.equal(await page.locator('#document-content p.editable-block').first().innerText(), unsavedText, 'Failed creation keeps existing unsaved document text.');
    assert.equal(await page.locator('#save-button').isDisabled(), false);
    passed('Discard confirmation can be declined; duplicate-address errors preserve both the creation form and the current unsaved document.');

    const payload = { type: createdType, slug: `qa-security-${stamp}`, title: 'Rejected synthetic page', description, titleBn, descriptionBn, section, lang: 'en' };
    const beforeSecurity = await (await page.request.get(origin + '/api/pages')).json();
    assert.equal((await page.request.post(origin + '/api/pages/create', { data: payload, headers: { Origin: origin } })).status(), 403, 'Page creation requires the editor token.');
    assert.equal((await post('/api/pages/create', payload, { 'X-Editor-Token': 'invalid-qa-token' })).status(), 403, 'A false token is rejected.');
    assert.equal((await post('/api/pages/create', payload, { Origin: 'https://example.invalid' })).status(), 403, 'Cross-origin creation is rejected.');
    assert.equal((await post('/api/pages/create', { ...payload, slug: '../qa-outside-content' })).status(), 400, 'Traversal addresses are rejected.');
    assert.equal((await post('/api/pages/create', { ...payload, slug: `person-qa-${stamp}` })).status(), 400, 'Reserved addresses are rejected.');
    assert.equal((await post('/api/pages/create', { ...payload, title: '{{unsafe_template_field}}' })).status(), 400, 'Template markers are rejected.');
    assert.equal((await post('/api/pages/create', { ...payload, descriptionBn: '' })).status(), 400, 'API requires Bengali content.');
    assert.equal((await post('/api/page-types/create', { name: `QA invalid ${stamp}`, template: '../unknown', description })).status(), 400, 'Unknown type templates are rejected.');
    const afterSecurity = await (await page.request.get(origin + '/api/pages')).json();
    assert.deepEqual(afterSecurity.pages.map(item => item.id).sort(), beforeSecurity.pages.map(item => item.id).sort(), 'Rejected requests add no pages.');
    assert.deepEqual(afterSecurity.types.map(item => item.id).sort(), beforeSecurity.types.map(item => item.id).sort(), 'Rejected requests add no types.');
    passed('Authentication, origin, traversal, reserved-address, template-marker, bilingual-content and unknown-template checks reject invalid requests without adding records.');
    assert.deepEqual(scriptErrors, [], 'The browser reports no JavaScript errors.');
    passed('No browser JavaScript errors.');
    await fs.writeFile(path.join(output, 'report.json'), JSON.stringify({ ok: true, origin, disposableOnly: true, createdPage: slug, createdType, checks, screenshots, scriptErrors }, null, 2) + '\n');
    console.log(checks.map(message => `PASS ${message}`).join('\n'));
    console.log(`Screenshots and report: ${output}`);
  } catch (error) {
    if (page && !page.isClosed()) await page.screenshot({ path: path.join(output, 'failure.png') }).catch(() => {});
    await fs.writeFile(path.join(output, 'report.json'), JSON.stringify({ ok: false, origin, disposableOnly: true, createdPage: slug, createdType, checks, screenshots, scriptErrors, error: error.message }, null, 2) + '\n');
    throw error;
  } finally { if (browser) await browser.close(); }
})().catch(error => { console.error(error.stack || error.message); process.exitCode = 1; });
