import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import vm from 'node:vm';

// Execute the exact shipped language-control code. The remaining application
// code concerns search, citations and other services outside this test's scope.
const source = readFileSync(new URL('../assets/app.js', import.meta.url), 'utf8');
const marker = '// Resolve at click time';
assert.equal(source.includes(marker), true, 'language-control section boundary exists');
const controls = source.slice(0, source.indexOf(marker));
const ORIGIN = 'https://aguri-heritage.in';

function eventTarget(extra = {}) {
  const listeners = new Map();
  const target = {
    addEventListener(type, listener) {
      if (!listeners.has(type)) listeners.set(type, []);
      listeners.get(type).push(listener);
    },
    dispatch(type, event = {}) {
      for (const listener of listeners.get(type) || []) listener(event);
    },
  };
  Object.defineProperties(target, Object.getOwnPropertyDescriptors(extra));
  return target;
}

function link(language, href) {
  const attrs = { href, lang: language, 'data-language-switch': '',
    class: 'language-choice', 'aria-label': language === 'bn' ? 'বাংলা' : 'English' };
  let resolved = href;
  return eventTarget({
    lang: language, hidden: false, attrs,
    getAttribute(name) { return attrs[name] ?? null; },
    get href() { return resolved; },
    set href(value) { resolved = value; attrs.href = value; },
  });
}

function fixture({ href = ORIGIN + '/', edition = 'en', picker = false,
  options, links = [], blockedCookies = false, cookie = '' } = {}) {
  let current = new URL(href);
  const assignments = [], writes = [], cookieJar = new Map();
  for (const pair of cookie.split(';').map(item => item.trim()).filter(Boolean)) {
    const at = pair.indexOf('=');
    cookieJar.set(pair.slice(0, at), pair.slice(at + 1));
  }
  const location = { assign(value) { assignments.push(value); } };
  for (const name of ['href', 'protocol', 'pathname', 'search', 'hash'])
    Object.defineProperty(location, name, { get: () => current[name] });
  const classes = new Set();
  const select = picker ? eventTarget({
    selectedIndex: edition === 'bn' ? 1 : 0,
    options: options || (edition === 'bn' ? ['../index.html', 'index.html'] : ['index.html', 'bn/index.html']),
    hidden: false,
    get value() { return this.options[this.selectedIndex]; },
  }) : null;
  const document = {
    documentElement: { lang: edition, classList: { add(name) { classes.add(name); } } },
    querySelector(selector) { assert.equal(selector, '#language-picker'); return select; },
    querySelectorAll(selector) { assert.equal(selector, '[data-language-switch]'); return links; },
  };
  Object.defineProperty(document, 'cookie', {
    get() { return [...cookieJar].map(([name, value]) => `${name}=${value}`).join('; '); },
    set(value) {
      if (blockedCookies) throw new Error('Browser blocks cookie storage');
      writes.push(value);
      const pair = value.split(';')[0], at = pair.indexOf('=');
      cookieJar.set(pair.slice(0, at), pair.slice(at + 1));
    },
  });
  const window = eventTarget();
  vm.runInNewContext(controls, { document, window, location, URL, URLSearchParams, Intl },
    { filename: 'assets/app.js:language-controls' });
  return { document, window, select, links, assignments, writes, classes,
    setLocation(value) { current = new URL(value, current.href); },
  };
}

function manualCookie(f, language, { secure = true } = {}) {
  assert.equal(f.writes.at(-1),
    `aguri_language=${language}; Max-Age=31536000; Path=/; SameSite=Lax${secure ? '; Secure' : ''}`);
  assert.equal(f.document.cookie.includes(`aguri_language=${language}`), true);
  assert.doesNotMatch(f.writes.at(-1), /Domain=/i);
}

for (const [edition, selectedIndex, language] of [
  ['en', 1, 'bn'], ['bn', 0, 'en'], ['en', 0, 'en'], ['bn', 1, 'bn'],
]) {
  test(`picker records manual ${language} from ${edition} edition and carries homepage query/fragment`, () => {
    const f = fixture({ edition, href: ORIGIN + (edition === 'bn' ? '/bn/' : '/') + '?scan=4&utm_source=reader#intro', picker: true });
    assert.equal(f.writes.length, 0, 'loading a direct edition is not a manual choice');
    f.select.selectedIndex = selectedIndex;
    f.select.dispatch('change');
    manualCookie(f, language);
    const target = new URL(f.assignments.at(-1));
    assert.equal(target.pathname, language === 'bn' ? '/bn/index.html' : '/index.html');
    assert.equal(target.searchParams.get('lang'), language);
    assert.equal(target.searchParams.get('scan'), '4');
    assert.equal(target.searchParams.get('utm_source'), 'reader');
    assert.equal(target.hash, '#intro');
    assert.equal(f.select.hidden, false);
  });
}

for (const [edition, language, route] of [
  ['en', 'bn', 'bn/index.html'], ['bn', 'en', '../index.html?lang=en'],
]) {
  test(`visible custom ${language} homepage link records the manual choice`, () => {
    const choice = link(language, route);
    const f = fixture({ edition, href: ORIGIN + (edition === 'bn' ? '/bn/' : '/') + '?source=header#main', links: [choice] });
    assert.equal(f.writes.length, 0);
    assert.equal(choice.hidden, false);
    assert.equal(choice.lang, language);
    assert.equal(choice.attrs.class, 'language-choice');
    assert.equal(choice.attrs['aria-label'], language === 'bn' ? 'বাংলা' : 'English');
    choice.dispatch('click');
    manualCookie(f, language);
    const target = new URL(choice.href);
    assert.equal(target.pathname, language === 'bn' ? '/bn/index.html' : '/index.html');
    assert.equal(target.searchParams.get('lang'), language);
    assert.equal(target.searchParams.get('source'), 'header');
    assert.equal(target.hash, '#main');
  });
}

test('blocked cookie storage does not throw or prevent English homepage switching', () => {
  const f = fixture({ edition: 'bn', href: ORIGIN + '/bn/?source=toggle#top', picker: true,
    blockedCookies: true });
  f.select.selectedIndex = 0;
  assert.doesNotThrow(() => f.select.dispatch('change'));
  assert.equal(f.document.cookie, '');
  assert.equal(f.writes.length, 0);
  assert.equal(new URL(f.assignments.at(-1)).searchParams.get('lang'), 'en');
  assert.equal(new URL(f.assignments.at(-1)).hash, '#top');
});

test('blocked cookies preserve visible custom English link and its explicit override', () => {
  const choice = link('en', '../index.html?lang=en');
  const f = fixture({ edition: 'bn', href: ORIGIN + '/bn/?source=header#top',
    links: [choice], blockedCookies: true });
  assert.doesNotThrow(() => choice.dispatch('click'));
  assert.equal(new URL(choice.href).searchParams.get('lang'), 'en');
  assert.equal(new URL(choice.href).searchParams.get('source'), 'header');
  assert.equal(choice.hidden, false);
  assert.equal(f.document.cookie, '');
});

for (const [edition, selectedIndex, expected] of [
  ['en', 1, '/bn/history.html'], ['bn', 0, '/history.html'],
]) {
  test(`article picker ${edition} keeps query/hash and direct article route`, () => {
    const f = fixture({ edition, href: ORIGIN + (edition === 'bn' ? '/bn/history.html' : '/history.html') + '?scan=21&volume=2&word=%E0%A6%AC#source-4',
      picker: true, options: edition === 'bn' ? ['../history.html', 'history.html'] : ['history.html', 'bn/history.html'] });
    f.select.selectedIndex = selectedIndex;
    f.select.dispatch('change');
    const target = new URL(f.assignments.at(-1));
    assert.equal(target.pathname, expected);
    assert.equal(target.search, '?scan=21&volume=2&word=%E0%A6%AC');
    assert.equal(target.hash, '#source-4');
    assert.equal(target.searchParams.has('lang'), false, 'no homepage override is added to article links');
    manualCookie(f, selectedIndex === 1 ? 'bn' : 'en');
  });
}

test('article link with a trailing slash does not receive a homepage override', () => {
  const choice = link('bn', 'bn/history/');
  fixture({ href: ORIGIN + '/?scan=2#source', links: [choice] });
  assert.equal(new URL(choice.href).pathname, '/bn/history/');
  assert.equal(new URL(choice.href).search, '?scan=2');
  assert.equal(new URL(choice.href).hash, '#source');
});

test('History custom links keep article queries and fragments while remembering a manual edition', () => {
  const choice = link('bn', 'bn/history.html');
  const f = fixture({ href: ORIGIN + '/history?scan=8&lang=en#reference-7', links: [choice] });
  choice.dispatch('click');
  const target = new URL(choice.href);
  assert.equal(target.pathname, '/bn/history.html');
  assert.equal(target.search, '?scan=8&lang=en');
  assert.equal(target.hash, '#reference-7');
  manualCookie(f, 'bn');
});

for (const pathname of ['/bn/', '/bn/index.html']) {
  test(`new-tab explicit Bengali homepage records preference: ${pathname}`, () => {
    const f = fixture({ edition: 'bn', href: ORIGIN + pathname + '?lang=bn&source=language-link', cookie: 'aguri_language=en' });
    manualCookie(f, 'bn');
    assert.equal(f.assignments.length, 0, 'the explicit edition is not geographically redirected in the browser');
  });
}

test('new-tab explicit English homepage records preference', () => {
  const f = fixture({ href: ORIGIN + '/?lang=en', cookie: 'aguri_language=bn' });
  manualCookie(f, 'en');
  assert.equal(f.assignments.length, 0);
});

for (const [edition, path] of [
  ['bn', '/bn/?lang=en'], ['en', '/?lang=bn'], ['bn', '/bn/?lang=fr'],
  ['bn', '/bn/history?lang=bn'], ['en', '/history.html?lang=en'],
]) {
  test(`query does not create an unrelated or contradictory preference: ${path}`, () => {
    const f = fixture({ edition, href: ORIGIN + path, cookie: 'aguri_language=en' });
    assert.equal(f.writes.length, 0);
    assert.equal(f.document.cookie, 'aguri_language=en');
    assert.equal(f.assignments.length, 0);
  });
}

test('direct Bengali homepage never overwrites an existing manual English preference', () => {
  const f = fixture({ edition: 'bn', href: ORIGIN + '/bn/', cookie: 'aguri_language=en' });
  assert.equal(f.writes.length, 0);
  assert.equal(f.document.cookie, 'aguri_language=en');
  assert.equal(f.assignments.length, 0);
});

test('hashchange and history popstate refresh the visible toggle target without changing preference', () => {
  const choice = link('bn', 'bn/index.html');
  const f = fixture({ href: ORIGIN + '/?source=first#old', links: [choice] });
  f.setLocation('/?source=second#new');
  f.window.dispatch('hashchange');
  let target = new URL(choice.href);
  assert.equal(target.searchParams.get('source'), 'second');
  assert.equal(target.hash, '#new');
  f.setLocation('/?source=back&scan=3#previous');
  f.window.dispatch('popstate');
  target = new URL(choice.href);
  assert.equal(target.searchParams.get('source'), 'back');
  assert.equal(target.searchParams.get('scan'), '3');
  assert.equal(target.searchParams.get('lang'), 'bn');
  assert.equal(target.hash, '#previous');
  assert.equal(f.writes.length, 0);
});

test('context menu prepares new-tab link without recording a choice before navigation', () => {
  const choice = link('en', '../index.html?lang=en');
  const f = fixture({ edition: 'bn', href: ORIGIN + '/bn/#old', links: [choice] });
  f.setLocation('/bn/?source=context#current');
  choice.dispatch('contextmenu');
  const target = new URL(choice.href);
  assert.equal(target.searchParams.get('lang'), 'en');
  assert.equal(target.searchParams.get('source'), 'context');
  assert.equal(target.hash, '#current');
  assert.equal(f.writes.length, 0);
});

for (const edition of ['en', 'bn']) {
  test(`back/forward restores ${edition} picker to the current document edition`, () => {
    const f = fixture({ edition, href: ORIGIN + (edition === 'bn' ? '/bn/history' : '/history'), picker: true });
    f.select.selectedIndex = edition === 'bn' ? 0 : 1;
    f.window.dispatch('pageshow');
    assert.equal(f.select.selectedIndex, edition === 'bn' ? 1 : 0);
    assert.equal(f.select.hidden, false);
    assert.equal(f.classes.has('js'), true);
    assert.equal(f.writes.length, 0);
  });
}

test('local file preview remains usable without writing an HTTP cookie', () => {
  const f = fixture({ href: 'file:///preview/bn/index.html', edition: 'bn', picker: true });
  f.select.selectedIndex = 0;
  assert.doesNotThrow(() => f.select.dispatch('change'));
  assert.equal(f.writes.length, 0);
  assert.equal(f.assignments.at(-1), 'file:///preview/index.html');
});

test('HTTP local preview persists host-only choice without a Secure attribute', () => {
  const f = fixture({ href: 'http://127.0.0.1:8080/', picker: true });
  f.select.selectedIndex = 1;
  f.select.dispatch('change');
  manualCookie(f, 'bn', { secure: false });
});
