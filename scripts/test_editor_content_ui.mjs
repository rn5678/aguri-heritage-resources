import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import vm from 'node:vm';

const source = readFileSync(new URL('../local-editor/editor.js', import.meta.url), 'utf8');
const escape = value => String(value).replaceAll('&', '&amp;').replaceAll('<', '&lt;').replaceAll('>', '&gt;').replaceAll('"', '&quot;');

// A small DOM fixture for the exact shipped tree transforms and editing actions.
// Native browser Range/execCommand behavior is checked separately in browser QA.
class Node {
  constructor(doc, tag = 'div', text = '') {
    this.ownerDocument = doc;
    this.nodeType = tag === '#text' ? 3 : tag === '#fragment' ? 11 : 1;
    this.tagName = this.nodeType === 1 ? tag.toUpperCase() : undefined;
    this.data = text; this.childNodes = []; this.attrs = new Map(); this.parentElement = null;
    this.dataset = {}; this.style = {}; this.hidden = false; this.disabled = false; this.open = false;
    this.listeners = {}; this.options = []; this.value = ''; this.content = 'a'.repeat(43);
    this.classList = {
      contains: value => this.className.split(/\s+/).includes(value),
      add: (...values) => { this.className = [...new Set([...this.className.split(/\s+/).filter(Boolean), ...values])].join(' '); },
      remove: (...values) => { this.className = this.className.split(/\s+/).filter(value => !values.includes(value)).join(' '); },
      toggle: (value, force) => { const enabled = force ?? !this.classList.contains(value); this.classList[enabled ? 'add' : 'remove'](value); return enabled; },
    };
  }
  get attributes() { return [...this.attrs].map(([name, value]) => ({ name, value })); }
  get className() { return this.attrs.get('class') || ''; }
  set className(value) { this.attrs.set('class', value); }
  get children() { return this.childNodes.filter(child => child.nodeType === 1); }
  get isConnected() { return true; }
  get textContent() { return this.nodeType === 3 ? this.data : this.childNodes.map(child => child.textContent).join(''); }
  set textContent(value) { this.replaceChildren(this.ownerDocument.createTextNode(value)); }
  get innerHTML() { return this.childNodes.map(child => child.outerHTML).join(''); }
  set innerHTML(value) { this.replaceChildren(this.ownerDocument.createTextNode(value)); }
  get outerHTML() {
    if (this.nodeType === 3) return escape(this.data);
    if (this.nodeType === 11) return this.innerHTML;
    const tag = this.tagName.toLowerCase();
    return `<${tag}${this.attributes.map(attr => ` ${attr.name}="${escape(attr.value)}"`).join('')}>${this.innerHTML}</${tag}>`;
  }
  setAttribute(name, value) { this.attrs.set(name, String(value)); }
  getAttribute(name) { return this.attrs.get(name) ?? null; }
  hasAttribute(name) { return this.attrs.has(name); }
  removeAttribute(name) { this.attrs.delete(name); }
  append(...nodes) {
    for (const node of nodes) {
      if (node.nodeType === 11) { this.append(...[...node.childNodes]); continue; }
      node.remove(); this.childNodes.push(node); node.parentElement = this;
    }
  }
  replaceChildren(...nodes) { for (const child of this.childNodes) child.parentElement = null; this.childNodes = []; this.append(...nodes); }
  remove() { if (this.parentElement) this.parentElement.childNodes = this.parentElement.childNodes.filter(child => child !== this); this.parentElement = null; }
  contains(node) { return this === node || this.childNodes.some(child => child.contains(node)); }
  cloneNode(deep = false) {
    const copy = new Node(this.ownerDocument, this.nodeType === 3 ? '#text' : this.nodeType === 11 ? '#fragment' : this.tagName, this.data);
    for (const [key, value] of this.attrs) copy.setAttribute(key, value);
    if (deep) copy.append(...this.childNodes.map(child => child.cloneNode(true)));
    return copy;
  }
  matches(selector) {
    if (selector === '[id]') return this.hasAttribute('id');
    if (selector === 'a[name]') return this.tagName === 'A' && this.hasAttribute('name');
    if (selector.startsWith('.')) return selector.slice(1).split('.').every(name => this.classList.contains(name));
    return this.tagName === selector.toUpperCase();
  }
  querySelectorAll(selector) {
    const result = [];
    for (const child of this.childNodes) {
      if (child.nodeType === 1 && selector.split(',').some(item => child.matches(item.trim()))) result.push(child);
      result.push(...child.querySelectorAll(selector));
    }
    return result;
  }
  querySelector(selector) { return this.querySelectorAll(selector)[0] || null; }
  addEventListener(name, handler) { this.listeners[name] = handler; }
  add(option) { this.options.push(option); }
  focus() { this.ownerDocument.activeElement = this; }
  blur() {}
  scrollIntoView() {}
  showModal() { this.open = true; }
  close() { this.open = false; }
}

function fixture() {
  const elements = new Map(), ranges = [], events = [];
  const doc = {
    createElement: tag => new Node(doc, tag), createTextNode: text => new Node(doc, '#text', text),
    createDocumentFragment: () => new Node(doc, '#fragment'),
    createRange: () => ranges.shift(),
    querySelector(selector) { if (!elements.has(selector)) elements.set(selector, new Node(doc)); return elements.get(selector); },
    querySelectorAll: () => [], addEventListener() {},
  };
  doc.body = doc.createElement('body');
  doc.querySelector('#publish-steps').append(...Array.from({ length: 4 }, () => doc.createElement('li')));
  doc.querySelector('#block-select').replaceChildren = function(...children) { this.options = children; };
  const window = { addEventListener() {}, location: { origin: 'http://127.0.0.1:45873' },
    getSelection: () => ({ removeAllRanges() {}, rangeCount: 0 }), confirm: () => true };
  const instrumented = source.replace('  init();\n})();',
    '  globalThis.app = { state, ui, deleteImage, restoreImage, undoBlockChange, setBlockAlignment, dirtyCount, findInsertionTarget, serializedInsertions };\n})();');
  assert.notEqual(instrumented, source);
  const context = vm.createContext({ document: doc, window, navigator: { platform: 'MacIntel' }, URL, Headers, Response,
    Option: function(text, value) { const option = doc.createElement('option'); option.textContent = text; option.value = value; return option; },
    fetch: () => { throw new Error('No network allowed'); }, setTimeout: () => 0, clearTimeout() {} });
  vm.runInContext(instrumented + '\nglobalThis.content = EditorContent;', context);
  return { ...context.app, content: context.content, doc, ranges, events };
}

function node(f, tag, attrs = {}, ...children) {
  const result = f.doc.createElement(tag);
  for (const [name, value] of Object.entries(attrs)) result.setAttribute(name, value);
  result.append(...children.map(child => typeof child === 'string' ? f.doc.createTextNode(child) : child));
  return result;
}

function draft(f) {
  f.state.doc = { id: 'example', lang: 'en', insertionTarget: { id: 'document-end', position: 'after' } };
  f.state.translation.enabled = false;
  const caption = node(f, 'figcaption', {}, 'An edited caption.'); caption.dataset.blockId = 'caption';
  const wrapper = node(f, 'section', { class: 'content-block' }, node(f, 'div', { class: 'block-label' }), caption);
  wrapper.dataset.blockWrapper = 'caption'; f.ui.content.append(wrapper);
  f.state.blocks.set('caption', caption); f.state.blockWrappers.set('caption', wrapper);
  f.state.blockMeta.set('caption', { id: 'caption', tag: 'figcaption', canDelete: true });
  f.state.changedBlocks.set('caption', 'An edited caption.');
  f.state.formatOriginals.set('caption', '');
  const photo = node(f, 'figure', {}, node(f, 'div', { class: 'image-stage' }), node(f, 'div', { class: 'image-tombstone' }));
  f.state.imageWrappers.set('photo', photo);
  f.state.imageMeta.set('photo', { canDelete: true, deleteBlockIds: ['caption'] });
  f.state.imageChanges.set('photo', { alt: 'Updated description', dataUrl: 'data:image/png;base64,fixture' });
  return { caption, wrapper, photo };
}

test('deleting a photo masks its caption edits and replacement without erasing the draft; Undo restores both', () => {
  const f = fixture(), { wrapper, photo } = draft(f);
  f.deleteImage('photo');
  assert.equal(f.dirtyCount(), 1, 'photo removal is one pending operation');
  assert.equal(wrapper.hidden, true); assert.equal(photo.classList.contains('removed'), true);
  let payload = f.content.saveFields(f.state, []);
  assert.deepEqual(JSON.parse(JSON.stringify(payload)), { blocks: {}, blockFormats: {}, images: {}, deleteBlocks: [], deleteImages: ['photo'], insertBlocks: [] });
  assert.equal(f.state.changedBlocks.get('caption'), 'An edited caption.');
  assert.equal(f.state.imageChanges.get('photo').alt, 'Updated description');
  f.undoBlockChange();
  assert.equal(wrapper.hidden, false); assert.equal(photo.classList.contains('removed'), false);
  assert.equal(f.dirtyCount(), 2);
  payload = f.content.saveFields(f.state, []);
  assert.equal(payload.blocks.caption, 'An edited caption.'); assert.equal(payload.images.photo.alt, 'Updated description');
});

test('restoring a photo respects an independently deleted caption instead of resurrecting it', () => {
  const f = fixture(); draft(f); f.state.deletedBlocks.add('caption');
  f.deleteImage('photo'); f.restoreImage('photo');
  assert.equal(f.state.deletedBlocks.has('caption'), true);
  const payload = f.content.saveFields(f.state, []);
  assert.deepEqual([...payload.deleteBlocks], ['caption']); assert.equal('caption' in payload.blocks, false);
});

test('alignment-only edits are dirty, serialize separately, and disappear when restored to the original', () => {
  const f = fixture(), { caption } = draft(f);
  f.state.changedBlocks.clear(); f.state.imageChanges.clear();
  f.setBlockAlignment('caption', 'center');
  assert.equal(caption.style.textAlign, 'center'); assert.equal(f.dirtyCount(), 1);
  assert.equal(f.content.saveFields(f.state, []).blockFormats.caption.align, 'center');
  f.setBlockAlignment('caption', '');
  assert.equal(f.dirtyCount(), 0); assert.equal(f.state.blockFormats.size, 0);
});

test('a deleted block omits its formatting; inserted paragraph alignment stays on the insertion', () => {
  const f = fixture(); draft(f); f.state.imageChanges.clear();
  f.state.blockFormats.set('caption', { align: 'right' }); f.state.deletedBlocks.add('caption');
  const addition = { id: 'new-one', anchor: 'document-end', position: 'after', tag: 'p', html: 'বাংলা', format: { align: 'justify' } };
  f.state.insertedBlocks.set(addition.id, addition);
  const payload = f.content.saveFields(f.state, [addition]);
  assert.equal('caption' in payload.blockFormats, false);
  assert.equal(payload.insertBlocks[0].format.align, 'justify');
  assert.equal(f.dirtyCount(), 2);
});

test('empty content and content with every previous block removed retain an insertion target', () => {
  const f = fixture(); draft(f); f.state.deletedBlocks.add('caption');
  assert.deepEqual(JSON.parse(JSON.stringify(f.findInsertionTarget())), { anchor: 'document-end', position: 'after' });
  f.state.blockMeta.clear(); f.state.deletedBlocks.clear();
  assert.equal(f.findInsertionTarget().anchor, 'document-end');
});

test('cross-block and disconnected formatting selections are rejected', () => {
  const f = fixture(), first = node(f, 'p', {}, 'one'), second = node(f, 'p', {}, 'two');
  assert.equal(f.content.validRange({ startContainer: first.childNodes[0], endContainer: first.childNodes[0] }, first), true);
  assert.equal(f.content.validRange({ startContainer: first.childNodes[0], endContainer: second.childNodes[0] }, first), false);
  assert.equal(f.content.validRange({ startContainer: first, endContainer: first }, { isConnected: false }), false);
});

test('English and Bengali generated fields may be selected whole but never split by formatting', () => {
  const f = fixture();
  for (const text of ['There are {{source_count}} sources.', 'মোট {{source_count}} উৎস।']) {
    const start = text.indexOf('{{'), end = text.indexOf('}}') + 2;
    assert.equal(f.content.splitsGeneratedField(text, start, end), false);
    assert.equal(f.content.splitsGeneratedField(text, start + 1, end), true);
    assert.equal(f.content.splitsGeneratedField(text, start, end - 1), true);
    assert.equal(f.content.splitsGeneratedField(text, 0, text.length), false);
  }
});

test('clear formatting retains Bengali text, citations, generated fields, links, IDs and direction', () => {
  const f = fixture();
  const cite = node(f, 'span', { class: 'editor-citation', 'data-cite': 'one', contenteditable: 'false' }, '[1]');
  const input = node(f, 'div', {}, node(f, 'strong', { id: 'target', lang: 'bn', dir: 'ltr' },
    'বাংলা ', node(f, 'em', {}, '{{source_count}}'), cite), node(f, 'a', { href: '/history', title: 'Read' }, node(f, 'u', {}, 'উৎস')));
  const output = f.content.cleanFragment(input, f.doc, 'clear');
  assert.equal(output.innerHTML, '<span id="target" lang="bn" dir="ltr">বাংলা {{source_count}}<span class="editor-citation" data-cite="one" contenteditable="false">[1]</span></span><a href="/history" title="Read">উৎস</a>');
});

test('remove-link preserves emphasis and named targets while removing only link destinations', () => {
  const f = fixture();
  const input = node(f, 'div', {}, node(f, 'a', { id: 'target', name: 'legacy', href: '/old', lang: 'bn' }, node(f, 'strong', {}, 'বাংলা')));
  const output = f.content.cleanFragment(input, f.doc, 'unlink');
  assert.equal(output.innerHTML, '<a id="target" name="legacy" lang="bn"><strong>বাংলা</strong></a>');
});

test('unlinking a legacy name-only anchor keeps a[name] so backend target validation can round-trip it', () => {
  const f = fixture();
  const input = node(f, 'a', { href: '/old', name: 'legacy', dir: 'ltr', title: 'Historical reference' }, 'Reference');
  const output = f.content.cleanFragment(input, f.doc, 'unlink');
  assert.equal(output.tagName, 'A');
  assert.equal(output.getAttribute('name'), 'legacy');
  assert.equal(output.hasAttribute('href'), false);
  assert.equal(output.outerHTML, '<a name="legacy" dir="ltr" title="Historical reference">Reference</a>');
});

test('clearing a partial selection restores surrounding link/language wrappers without duplicating IDs', () => {
  const f = fixture();
  const anchor = node(f, 'a', { id: 'target', href: '/history', lang: 'bn' }, node(f, 'strong', {}, 'এক দুই তিন'));
  const block = node(f, 'p', {}, anchor), text = anchor.childNodes[0].childNodes[0];
  const fragment = child => { const result = f.doc.createDocumentFragment(); result.append(child); return result; };
  for (const value of ['এক ', ' তিন']) {
    const contents = fragment(node(f, 'a', { id: 'target', href: '/history', lang: 'bn' }, node(f, 'strong', {}, value)));
    f.ranges.push({ selectNodeContents() {}, setEnd() {}, setStart() {}, cloneContents: () => contents });
  }
  const range = { startContainer: text, endContainer: text, commonAncestorContainer: text, startOffset: 3, endOffset: 6,
    collapsed: false, cloneContents: () => fragment(f.doc.createTextNode('দুই')) };
  assert.equal(f.content.clearedSelectionHTML(block, range), '<a id="target" href="/history" lang="bn"><strong>এক </strong></a><a href="/history" lang="bn">দুই</a><a href="/history" lang="bn"><strong> তিন</strong></a>');
});

test('the alignment allowlist cannot serialize arbitrary CSS', () => {
  const f = fixture();
  for (const value of ['', 'left', 'center', 'right', 'justify']) assert.equal(f.content.alignment(value), value);
  for (const value of ['center;color:red', 'url(javascript:x)', null, {}, 'inherit']) assert.equal(f.content.alignment(value), '');
});
