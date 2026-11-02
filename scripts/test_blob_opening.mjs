// VM checks execute the shipped helpers and authenticated click handler with
// browser primitives stubbed. They do not launch or control a browser.
import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';

const contribute = fs.readFileSync(new URL('../assets/contribute.js', import.meta.url), 'utf8');
const review = fs.readFileSync(new URL('../assets/review.js', import.meta.url), 'utf8');

class Element {
  constructor(tag = 'div') { this.tagName = tag; this.children = []; this.listeners = {}; this.elements = []; this.dataset = {}; this.value = ''; }
  append(...nodes) { this.children.push(...nodes); }
  replaceChildren(...nodes) { this.children = nodes; }
  addEventListener(type, callback) { this.listeners[type] = callback; }
  setAttribute() {}
  removeAttribute() {}
  setCustomValidity() {}
  reset() {}
  focus() {}
  querySelector() { return new Element('button'); }
}

function fixture(lang = 'en') {
  const nodes = new Map(), events = [], urls = new Map(), revoked = [], timers = new Map();
  let blocked = false, timer = 0;
  const tabs = [];
  class LocalURL extends URL {
    static createObjectURL(blob) { const url = `blob:fixture-${urls.size + 1}`; urls.set(url, blob); return url; }
    static revokeObjectURL(url) { revoked.push(url); }
  }
  const window = {
    addEventListener() {},
    open() {
      events.push('open');
      if (blocked) return null;
      const tab = { opener: {}, closed: false, document: { body: {}, title: '' },
        close() { this.closed = true; }, location: { replace(url) { tab.url = url; events.push('navigate'); } } };
      tabs.push(tab);
      return tab;
    }
  };
  const context = vm.createContext({
    Blob, Response, Request, Headers, URL: LocalURL, URLSearchParams, AbortController, DOMException,
    console, Intl, Date, crypto, setTimeout() {},
    setInterval(fn) { timers.set(++timer, fn); return timer; }, clearInterval(id) { timers.delete(id); },
    location: { origin: 'https://heritage.example' }, window,
    document: { documentElement: { lang }, createElement: tag => new Element(tag),
      getElementById(id) { if (!nodes.has(id)) nodes.set(id, new Element()); return nodes.get(id); } },
  });
  return { context, nodes, events, urls, revoked, timers, tabs,
    block(value) { blocked = value; }, tick() { for (const callback of timers.values()) callback(); } };
}

function reviewFixture(lang) {
  const state = fixture(lang);
  state.context.fetch = async () => new Response('Synthetic original file', { headers: { 'Content-Type': 'text/plain; charset=utf-8' } });
  const instrumented = review.replace(/\}\)\(\);\s*$/, `globalThis.qa = { openBlob, renderFiles, lock,
    setKey(value) { editorKey = value; }, getSession() { return session; } }; })();`);
  vm.runInContext(instrumented, state.context);
  state.context.qa.setKey('fixture-editor-key');
  return state;
}

for (const lang of ['en', 'bn']) {
  test(`${lang}: local JSON opens in an isolated tab, keeps its data and reports blocked pop-ups`, async () => {
    const state = fixture(lang);
    state.context.words = (en, bn) => lang === 'bn' ? bn : en;
    let error = '';
    state.context.setError = value => { error = value; };
    const helper = contribute.slice(contribute.indexOf('  function openJSON('), contribute.indexOf('  function formDraft('));
    vm.runInContext(helper + '\nglobalThis.qa = {openJSON};', state.context);
    state.context.qa.openJSON('draft.json', { draft: true, consent: 'no', text: 'বাংলা', attachments: [{ name: 'original.pdf' }] });
    assert.equal(state.tabs.length, 1);
    assert.equal(state.tabs[0].opener, null);
    assert.equal(state.tabs[0].url.startsWith('blob:'), true);
    const blob = state.urls.get(state.tabs[0].url);
    assert.equal(blob.type, 'application/json;charset=utf-8');
    assert.equal(JSON.parse(await blob.text()).text, 'বাংলা');
    assert.equal(JSON.parse(await blob.text()).consent, 'no');
    assert.deepEqual(state.revoked, [], 'Reading/reloading the open file does not race a one-second revocation');
    state.tabs[0].close(); state.tick();
    assert.equal(state.revoked.length, 1);
    state.block(true);
    state.context.qa.openJSON('receipt.json', { id: 'private-receipt' });
    assert.equal(state.tabs.length, 1);
    assert.match(error, lang === 'bn' ? /পপ-আপ/ : /blocked/);
  });

  test(`${lang}: private attachments reserve a tab before fetching and preserve authenticated MIME/data`, async () => {
    const state = reviewFixture(lang);
    let release, fetchOptions;
    state.context.fetch = async (url, options) => {
      state.events.push('fetch'); fetchOptions = options;
      return new Promise(resolve => { release = () => resolve(new Response('Synthetic original file', {
        headers: { 'Content-Type': 'text/plain; charset=utf-8' }
      })); });
    };
    state.context.qa.renderFiles([{ id: 'file-id', name: 'source-note.txt', type: 'text/plain', size: 23 }], 'contribution-id');
    const button = state.nodes.get('review-files').children[0].children[0];
    assert.match(button.textContent, lang === 'bn' ? /খুলুন/ : /^Open /);
    const completed = button.listeners.click();
    assert.deepEqual(state.events, ['open', 'fetch']);
    assert.equal(state.tabs[0].opener, null);
    assert.equal(fetchOptions.headers.Authorization, 'Bearer fixture-editor-key');
    assert.equal(fetchOptions.credentials, 'omit');
    release(); await completed;
    const blob = state.urls.get(state.tabs[0].url);
    assert.equal(blob.type, 'text/plain;charset=utf-8');
    assert.equal(await blob.text(), 'Synthetic original file');
    assert.equal(button.disabled, false);
    state.context.qa.lock(); state.tick();
    assert.equal(state.revoked.length, 1);
  });

  test(`${lang}: blocked private-file popups do not fetch; locked sessions close pending tabs`, async () => {
    const state = reviewFixture(lang);
    let fetched = 0, release;
    state.context.fetch = async () => { fetched++; return new Promise(resolve => { release = () => resolve(new Response('private', { headers: { 'Content-Type': 'text/plain' } })); }); };
    state.context.qa.renderFiles([{ id: 'file-id', name: 'source.txt', type: 'text/plain', size: 7 }], 'record');
    const button = state.nodes.get('review-files').children[0].children[0];
    state.block(true); await button.listeners.click();
    assert.equal(fetched, 0);
    assert.match(state.nodes.get('review-message').textContent, lang === 'bn' ? /পপ-আপ/ : /blocked/);
    state.block(false);
    const completed = button.listeners.click();
    state.context.qa.lock(); release(); await completed;
    assert.equal(state.tabs[0].closed, true);
    assert.equal(state.urls.size, 0, 'No Blob is opened after the authenticated session ends');
  });

  test(`${lang}: editorial JSON uses a local tab and unsupported private MIME never becomes executable content`, async () => {
    const state = reviewFixture(lang);
    state.context.qa.openBlob(new Blob(['{"private_note":"kept"}'], { type: 'application/json' }), 'record.json');
    assert.equal(state.tabs[0].opener, null);
    assert.equal(JSON.parse(await state.urls.get(state.tabs[0].url).text()).private_note, 'kept');
    state.context.qa.openBlob(new Blob(['<script>bad()</script>'], { type: 'text/html' }), 'unsafe.html');
    assert.equal(state.tabs[1].closed, true);
    assert.equal(state.urls.size, 1);
  });
}
