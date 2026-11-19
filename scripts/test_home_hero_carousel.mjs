import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { runInNewContext } from 'node:vm';

const source = readFileSync(new URL('../assets/homepage-hero-carousel.js', import.meta.url), 'utf8');

function setup(motion = false, width = 375, lang = 'en') {
  function element(dataset = {}) {
    const listeners = new Map();
    return {
      dataset, hidden: true,
      addEventListener(name, handler) { listeners.set(name, handler); },
      send(name, event = {}) { listeners.get(name)(event); },
      setAttribute(name, value) { this[name] = value; },
    };
  }
  const images = ['eager', 'lazy', 'lazy', 'lazy'].map(loading => ({ loading }));
  const order = [];
  const track = {
    append(slide) { order.splice(order.indexOf(slide), 1); order.push(slide); },
    insertBefore(slide, reference) {
      order.splice(order.indexOf(slide), 1);
      order.splice(order.indexOf(reference), 0, slide);
    },
  };
  const slides = images.map(image => {
    const link = element();
    const slide = { ...element(), parentElement: track, contains: node => node === link, link, querySelector: () => image };
    order.push(slide);
    return slide;
  });
  const previous = element(), next = element(), pause = element(), icon = element();
  const pauseText = element(), status = element();
  pause.querySelector = name => ({ '[data-home-pause-icon]': icon, '[data-home-pause-text]': pauseText })[name];
  const root = element({ pauseLabel: 'Pause', playLabel: 'Play' });
  root.querySelectorAll = () => slides;
  root.querySelector = name => ({
    '[data-home-prev]': previous, '[data-home-next]': next, '[data-home-pause]': pause, '[data-home-status]': status,
  })[name];
  root.contains = child => [previous, next, pause].includes(child) || slides.some(slide => slide.contains(child));
  const document = element();
  document.documentElement = { lang };
  document.hidden = false;
  document.querySelector = () => root;
  const preference = element();
  preference.matches = motion;
  const desktop = element(), tablet = element();
  desktop.matches = width >= 900;
  tablet.matches = width >= 600;
  let timer;
  const window = {
    matchMedia: query => ({
      '(min-width: 900px)': desktop, '(min-width: 600px)': tablet,
      '(prefers-reduced-motion: reduce)': preference,
    })[query],
    clearTimeout() { timer = null; },
    setTimeout(handler, ms) { assert.equal(ms, 8000); timer = handler; },
  };
  runInNewContext(source, { window, document });
  return {
    previous, next, pause, icon, pauseText, status, slides, images, root, document, preference,
    selected: () => slides.indexOf(order.find(slide => !slide.hidden)),
    visible: () => order.filter(slide => !slide.hidden).map(slide => slides.indexOf(slide)),
    resize(width) {
      desktop.matches = width >= 900;
      tablet.matches = width >= 600;
      desktop.send('change');
      tablet.send('change');
    },
    running: () => !!timer,
    tick() { assert.ok(timer); timer(); },
  };
}

test('rotates and wraps, loads only selected lazy images and excludes hidden slides', () => {
  const c = setup();
  assert.equal(c.selected(), 0);
  assert.equal(c.previous.hidden, false);
  assert.equal(c.images[1].loading, 'lazy');
  c.tick();
  assert.equal(c.selected(), 1);
  assert.equal(c.images[1].loading, 'eager');
  assert.equal(c.slides[0].inert, true);
  c.previous.send('click');
  c.previous.send('click');
  assert.equal(c.selected(), 3);
  c.next.send('click');
  assert.equal(c.selected(), 0);
});

test('explicit play resumes while hovered and focused; later interactions pause again', () => {
  const c = setup();
  c.root.send('pointerenter', { pointerType: 'mouse' });
  c.root.send('focusin');
  assert.equal(c.running(), false);
  c.pause.send('click');
  assert.equal(c.pause['aria-label'], 'Play');
  c.pause.send('click');
  assert.equal(c.pause['aria-label'], 'Pause');
  assert.equal(c.icon['aria-hidden'], 'true');
  c.tick();
  assert.equal(c.selected(), 1);
  c.root.send('focusout');
  c.root.send('pointerleave');
  c.root.send('focusin');
  assert.equal(c.running(), false);
  c.root.send('focusout');
  assert.equal(c.running(), true);
  c.document.hidden = true;
  c.document.send('visibilitychange');
  assert.equal(c.running(), false);
  c.document.hidden = false;
  c.document.send('visibilitychange');
  assert.equal(c.running(), true);
});

test('reduced motion defaults to paused but explicit Play opts in immediately', () => {
  const c = setup(true);
  assert.equal(c.running(), false);
  assert.equal(c.pause['aria-label'], 'Play');
  c.root.send('focusin');
  c.pause.send('click');
  c.tick();
  assert.equal(c.selected(), 1);
  c.preference.matches = false;
  c.preference.send('change');
  c.preference.matches = true;
  c.preference.send('change');
  assert.equal(c.running(), false);
  assert.equal(c.pause['aria-label'], 'Play');
});

test('breakpoints show 3, 2 or 1; wrapping keeps DOM and keyboard order', () => {
  const c = setup(false, 900);
  assert.deepEqual(c.visible(), [0, 1, 2]);
  c.previous.send('click');
  assert.deepEqual(c.visible(), [3, 0, 1]);
  assert.equal(c.slides[2].inert, true);
  c.resize(600);
  assert.deepEqual(c.visible(), [3, 0]);
  let defaultPrevented = false;
  c.root.send('keydown', { target: c.next, key: 'ArrowRight', preventDefault() { defaultPrevented = true; } });
  assert.ok(defaultPrevented);
  assert.deepEqual(c.visible(), [0, 1]);
  c.resize(599);
  assert.deepEqual(c.visible(), [0]);
  assert.equal(c.slides[1].inert, true);
});

test('breakpoint change keeps the focused article visible', () => {
  const c = setup(false, 900);
  c.document.activeElement = c.slides[2].link;
  c.root.send('focusin');
  c.resize(599);
  assert.deepEqual(c.visible(), [2]);
  assert.equal(c.slides[2].inert, false);
  assert.equal(c.running(), false);
});

test('status uses edition digits and Pause/Play text follows explicit state', () => {
  const c = setup(false, 900, 'bn');
  assert.equal(c.status.textContent, '১–৩ / ৪');
  assert.equal(c.pauseText.textContent, 'Pause');
  c.previous.send('click');
  assert.equal(c.status.textContent, '৪–২ / ৪');
  c.pause.send('click');
  assert.equal(c.pauseText.textContent, 'Play');
  c.resize(599);
  assert.equal(c.status.textContent, '৪ / ৪');
});
