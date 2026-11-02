import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import vm from 'node:vm';

const source = readFileSync(new URL('../local-editor/editor.js', import.meta.url), 'utf8');
const repository = 'https://github.com/rn5678/aguri-heritage-resources';

function element() {
  const attributes = new Map();
  const classes = new Set();
  return {
    hidden: false, disabled: false, open: false, textContent: '', innerHTML: '', content: 'a'.repeat(43),
    dataset: {}, children: [], listeners: {},
    classList: { toggle(name, value) { if (value) classes.add(name); else classes.delete(name); }, add(...names) { names.forEach(name => classes.add(name)); }, remove(...names) { names.forEach(name => classes.delete(name)); } },
    setAttribute(name, value) { attributes.set(name, value); },
    removeAttribute(name) { attributes.delete(name); if (name === 'href') delete this.href; },
    getAttribute(name) { return attributes.get(name); },
    addEventListener(name, callback) { this.listeners[name] = callback; },
    replaceChildren(...children) { this.children = children; }, append(child) { this.children.push(child); },
    showModal() { this.open = true; }, close() { this.open = false; }, focus() {}, blur() {},
  };
}

function editor(fetcher = async () => { throw new Error('Unexpected request'); }) {
  const elements = new Map();
  const get = selector => {
    if (!elements.has(selector)) elements.set(selector, element());
    return elements.get(selector);
  };
  get('#publish-steps').children = Array.from({ length: 4 }, element);
  const timers = [];
  const document = { querySelector: get, querySelectorAll: () => [], createElement: element, body: element(), addEventListener() {} };
  const context = vm.createContext({ document, navigator: { platform: 'MacIntel' }, URL, Headers, Response,
    window: { addEventListener() {}, location: { origin: 'http://127.0.0.1:45873' }, confirm: () => true },
    fetch: fetcher, setTimeout(callback, delay) { timers.push({ callback, delay }); return timers.length; }, clearTimeout() {} });
  const instrumented = source.replace('  init();\n})();',
    '  globalThis.testEditor = { state, ui, acceptPublication, renderPublication, preparePublication, confirmPublication, refreshPublication, noteLocalSourceSave };\n})();');
  assert.notEqual(instrumented, source, 'test harness must disable only startup, never change the publishing logic');
  vm.runInContext(instrumented + '\nglobalThis.testPublishing = EditorPublishing;', context);
  return { ...context.testEditor, tools: context.testPublishing, timers };
}

function ready() {
  return { phase: 'ready', preparation: { id: 'checked-snapshot', files: 1070, pages: 102,
    changedFiles: ['content/history.html', 'content/bn/history.html'], branch: 'editor/update-1',
    preparedAt: '2026-11-02T12:00:00Z', siteUrl: 'https://aguri-heritage.in/' } };
}
function review(checks = 'pending', withPR = true) {
  return { phase: 'review', github: { branch: 'editor/update-1', headSha: 'a'.repeat(40),
    compareUrl: `${repository}/compare/main...editor/update-1?expand=1`,
    pullRequestUrl: withPR ? `${repository}/pull/2` : undefined,
    actionsUrl: `${repository}/actions`, checks: { state: checks, url: `${repository}/actions/runs/12` } } };
}

test('GitHub handoffs are limited to the exact repository and approved review/check paths', () => {
  const { tools } = editor();
  for (const url of [`${repository}/pull/2`, `${repository}/compare/main...editor/update-1?expand=1`, `${repository}/actions/runs/12/job/34`]) {
    assert.equal(tools.githubLink(url), url);
  }
  for (const url of ['javascript:alert(1)', 'https://github.com.evil.example/rn5678/aguri-heritage-resources/pull/2',
    'https://user@github.com/rn5678/aguri-heritage-resources/pull/2', 'https://github.com/other/repo/pull/2',
    `${repository}/settings/secrets/actions`, `${repository}/issues/2`, `${repository}/pull/2#untrusted`]) {
    assert.equal(tools.githubLink(url), '');
  }
  assert.equal(tools.siteLink('https://aguri-heritage.in'), 'https://aguri-heritage.in/');
  for (const url of ['https://www.aguri-heritage.in/', 'https://aguri-heritage.in/other', 'https://aguri-heritage.in/?next=x', 'http://aguri-heritage.in/']) {
    assert.equal(tools.siteLink(url), '');
  }
});

test('local jobs poll quickly while GitHub progress respects the slower read budget', () => {
  const { tools } = editor();
  for (const phase of ['preparing', 'publishing']) assert.equal(tools.pollDelay(phase), 1500);
  for (const phase of ['review', 'deploying']) assert.equal(tools.pollDelay(phase), 15000);
  assert.equal(tools.pollDelay('publishing', true), 15000);
  for (const phase of ['idle', 'ready', 'clean', 'success', 'error']) assert.equal(tools.pollDelay(phase), null);
});

test('explicit progress checks request refresh while automatic polling uses cached status', async () => {
  const calls = [];
  const app = editor(async url => {
    calls.push(url);
    return new Response(JSON.stringify(review()), { status: 200 });
  });
  await app.refreshPublication();
  await app.refreshPublication(true);
  await app.timers.at(-1).callback();
  assert.deepEqual(calls, ['/api/publish/status', '/api/publish/status?refresh=1', '/api/publish/status']);
});

test('source preparation is gated by drafts and Bengali work but progress stays available without a page', () => {
  const app = editor();
  app.state.translationLoaded = true;
  app.state.translation = { enabled: true, phase: 'running', pending: 1, reviewCount: 0 };
  app.state.changedBlocks.set('draft', '<p>Keep this unsaved draft.</p>');
  app.acceptPublication(review());
  assert.equal(app.state.doc, null);
  assert.equal(app.ui.publish.disabled, false);
  assert.equal(app.ui.publish.textContent, 'View progress');
  assert.equal(app.ui.publishPrepare.disabled, true);
  assert.equal(app.ui.publishGithub.hidden, false);
  assert.equal(app.ui.publishRetry.disabled, false);
  app.acceptPublication(ready());
  assert.equal(app.ui.publishConfirm.disabled, true);
  assert.match(app.ui.publishMessage.textContent, /unsaved edits/);
});

test('ready, sent, checking, deploying, and live remain distinct outcomes', () => {
  const app = editor();
  app.state.translation.enabled = false;
  app.acceptPublication(ready());
  assert.equal(app.ui.publishConfirm.hidden, false);
  assert.equal(app.ui.publishConfirm.disabled, false);
  assert.equal(app.ui.publishFiles.children.length, 2);
  assert.equal(app.ui.publishLive.hidden, true);
  app.acceptPublication(review('pending', false));
  assert.equal(app.ui.publishGithub.textContent, 'Create review on GitHub');
  assert.match(app.ui.publishNextStep.textContent, /Create pull request/);
  assert.equal(app.ui.publishConfirm.hidden, true);
  app.acceptPublication(review('success'));
  assert.equal(app.ui.publishGithub.textContent, 'Review and merge on GitHub');
  assert.equal(app.ui.publishLive.hidden, true);
  app.acceptPublication({ ...review('success'), phase: 'deploying' });
  assert.equal(app.ui.publishLive.hidden, true);
  app.acceptPublication({ phase: 'success', publication: { url: 'https://aguri-heritage.in/', completedAt: '2026-11-02T13:00:00Z' } });
  assert.equal(app.ui.publishLive.hidden, false);
  assert.equal(app.ui.publishLive.href, 'https://aguri-heritage.in/');
  assert.equal(app.ui.publishPrepare.hidden, false);
  app.acceptPublication({ phase: 'clean' });
  assert.equal(app.ui.publishLive.hidden, true);
  assert.match(app.ui.publishDetail.textContent, /does not report a new deployment/);
});

test('a failed GitHub check shows review guidance and never offers a live-success link', () => {
  const app = editor();
  app.acceptPublication(review('failure'));
  assert.match(app.ui.publishNextStep.textContent, /check failed/);
  assert.equal(app.ui.publishLive.hidden, true);
  assert.equal(app.ui.publishConfirm.hidden, true);
});

test('read-only GitHub status notices stay visible without changing the publication result', () => {
  const app = editor();
  app.acceptPublication({ ...review('pending'), statusNotice: 'GitHub requests are temporarily limited. Showing the last known status.' });
  assert.equal(app.state.publication.phase, 'review');
  assert.equal(app.ui.publishStatusNotice.hidden, false);
  assert.match(app.ui.publishStatusNotice.textContent, /last known status/);
  assert.equal(app.ui.publishGithub.hidden, false);
  app.acceptPublication(review('success'));
  assert.equal(app.ui.publishStatusNotice.hidden, true);
});

test('closed unmerged review allows preparation while preserving its historical link', () => {
  const app = editor();
  app.state.translation.enabled = false;
  app.acceptPublication({ ...review('failure'), phase: 'error', closedWithoutMerge: true, canPrepare: true });
  assert.equal(app.ui.publishPrepare.hidden, false);
  assert.equal(app.ui.publishPrepare.disabled, false);
  assert.equal(app.ui.publishGithub.textContent, 'View closed GitHub review');
  assert.match(app.ui.publishNextStep.textContent, /closed without merging/);
});

test('successful deployment links to its checks without asking for another merge', () => {
  const app = editor();
  app.acceptPublication({ ...review('success'), phase: 'success', publication: { url: 'https://aguri-heritage.in/' } });
  assert.equal(app.ui.publishGithub.hidden, true);
  assert.equal(app.ui.publishChecks.hidden, false);
  assert.match(app.ui.publishNextStep.textContent, /already been deployed/);
  assert.doesNotMatch(app.ui.publishNextStep.textContent, /Merge pull request/);
});

test('saving newer content retains remote review progress and polling', () => {
  const app = editor();
  app.acceptPublication(review('pending'));
  app.noteLocalSourceSave();
  assert.equal(app.state.publication.phase, 'review');
  assert.equal(app.ui.publish.textContent, 'View progress');
  assert.equal(app.ui.publishGithub.hidden, false);
  assert.equal(app.timers.at(-1).delay, 15000);
  app.acceptPublication({ ...review('success'), phase: 'success', publication: { url: 'https://aguri-heritage.in/' } });
  assert.equal(app.ui.publishTitle.textContent, 'Earlier update is live');
  assert.equal(app.ui.publicationStatus.textContent, 'New changes saved locally');
});

test('saving after preparation requires a fresh snapshot before Send', async () => {
  let requests = 0;
  const app = editor(async () => { requests++; throw new Error('Unexpected source send'); });
  app.state.translation.enabled = false;
  app.acceptPublication(ready());
  app.noteLocalSourceSave();
  // A status refresh returning the same preparation must not clear this guard.
  app.acceptPublication(ready());
  assert.equal(app.ui.publishConfirm.disabled, true);
  assert.equal(app.ui.publishPrepare.hidden, false);
  assert.equal(app.ui.publishPrepare.disabled, false);
  assert.equal(app.ui.publishPrepare.textContent, 'Prepare latest changes');
  await app.confirmPublication();
  assert.equal(requests, 0);
});

test('response URLs outside the repository are rejected before changing displayed state', () => {
  const app = editor();
  const invalid = review();
  invalid.github.pullRequestUrl = 'https://other.example/pull/2';
  assert.throws(() => app.acceptPublication(invalid), /does not match/);
  assert.equal(app.state.publication.phase, 'idle');
});

test('explicit Send to GitHub sends one checked snapshot and leaves production waiting for review', async () => {
  const calls = [];
  const app = editor(async (url, options) => {
    calls.push({ url, options });
    return new Response(JSON.stringify(review('pending', false)), { status: 200 });
  });
  app.state.translation.enabled = false;
  app.acceptPublication(ready());
  await app.confirmPublication();
  assert.equal(calls.length, 1);
  assert.equal(calls[0].url, '/api/publish/confirm');
  assert.deepEqual(JSON.parse(calls[0].options.body), { preparationId: 'checked-snapshot' });
  assert.equal(app.state.publication.phase, 'review');
  assert.equal(app.ui.publishLive.hidden, true);
});

test('expired local session renews in memory and preserves unsaved text while reconnecting progress', async () => {
  const calls = [];
  const fresh = 'b'.repeat(43);
  const app = editor(async (url, options) => {
    calls.push({ url, token: options.headers?.get?.('X-Editor-Token') });
    if (calls.length === 1) return new Response(JSON.stringify({ error: 'Refresh the editor.' }), { status: 403 });
    if (url === '/') return new Response(`<html><meta name="editor-token" content="${fresh}"></html>`, { status: 200 });
    return new Response(JSON.stringify(review()), { status: 200 });
  });
  app.ui.content.innerHTML = '<p>My unsaved words.</p>';
  app.state.changedBlocks.set('draft', app.ui.content.innerHTML);
  await app.refreshPublication();
  assert.equal(calls.length, 3);
  assert.equal(calls[1].url, '/');
  assert.equal(calls[2].token, fresh);
  assert.equal(app.ui.content.innerHTML, '<p>My unsaved words.</p>');
  assert.equal(app.state.changedBlocks.get('draft'), '<p>My unsaved words.</p>');
  assert.equal(app.state.publication.phase, 'review');
});

test('a lost mutation response is never automatically retried', async () => {
  const { tools } = editor();
  let calls = 0;
  const request = tools.createRequest(async () => { calls++; throw new TypeError('connection lost'); }, 'a'.repeat(43));
  await assert.rejects(request('/api/publish/confirm', { method: 'POST', headers: { 'X-Editor-Token': 'a'.repeat(43) }, body: '{}' }));
  assert.equal(calls, 1);
});

test('a second rejected session stops after one renewal and one retry', async () => {
  const { tools } = editor();
  const calls = [];
  const request = tools.createRequest(async url => {
    calls.push(url);
    return url === '/'
      ? new Response(`<meta name="editor-token" content="${'b'.repeat(43)}">`, { status: 200 })
      : new Response(JSON.stringify({ error: 'expired' }), { status: 403 });
  }, 'a'.repeat(43));
  await assert.rejects(request('/api/publish/confirm', { method: 'POST', headers: { 'X-Editor-Token': 'a'.repeat(43) }, body: '{}' }), /Keep this tab open/);
  assert.deepEqual(calls, ['/api/publish/confirm', '/', '/api/publish/confirm']);
});

test('other server errors never renew the session or retry a mutation', async () => {
  const { tools } = editor();
  for (const status of [400, 409, 500, 503]) {
    let calls = 0;
    const request = tools.createRequest(async () => {
      calls++;
      return new Response(JSON.stringify({ error: 'Check this update before trying again.' }), { status });
    }, 'a'.repeat(43));
    await assert.rejects(request('/api/publish/confirm', { method: 'POST', headers: { 'X-Editor-Token': 'a'.repeat(43) }, body: '{}' }), /Check this update/);
    assert.equal(calls, 1);
  }
});

test('failed session renewal keeps the draft and asks for reconnection without a page reload', async () => {
  const app = editor(async url => url === '/' ? new Response('unavailable', { status: 503 })
    : new Response(JSON.stringify({ error: 'expired' }), { status: 403 }));
  app.ui.content.innerHTML = '<p>Keep this draft.</p>';
  app.state.changedBlocks.set('draft', app.ui.content.innerHTML);
  await app.refreshPublication();
  assert.match(app.ui.publishMessage.textContent, /Keep this tab open/);
  assert.equal(app.ui.content.innerHTML, '<p>Keep this draft.</p>');
  assert.equal(app.ui.publishRetry.hidden, false);
});
