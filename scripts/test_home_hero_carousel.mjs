import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { runInNewContext } from 'node:vm';

const source = readFileSync(new URL('../assets/homepage-hero-carousel.js', import.meta.url), 'utf8');

function setup(motion = false) {
  function element(dataset = {}) {
    const listeners = new Map();
    return {
      dataset, hidden: true,
      addEventListener(name, handler) { listeners.set(name, handler); },
      send(name, event = {}) { listeners.get(name)(event); },
      setAttribute(name, value) { this[name] = value; },
    };
  }
  const images = ['eager', 'lazy', 'lazy'].map(loading => ({ loading }));
  const slides = images.map(image => ({ ...element(), querySelector: () => image }));
  const previous = element(), next = element(), pause = element(), icon = element();
  pause.querySelector = () => icon;
  const root = element({ pauseLabel: 'Pause', playLabel: 'Play' });
  root.querySelectorAll = () => slides;
  root.querySelector = name => ({
    '[data-home-prev]': previous, '[data-home-next]': next, '[data-home-pause]': pause,
  })[name];
  root.contains = child => [previous, next, pause].includes(child);
  const document = element();
  document.hidden = false;
  document.querySelector = () => root;
  const preference = element();
  preference.matches = motion;
  let timer;
  const window = {
    matchMedia: () => preference,
    clearTimeout() { timer = null; },
    setTimeout(handler, ms) { assert.equal(ms, 8000); timer = handler; },
  };
  runInNewContext(source, { window, document });
  return {
    previous, next, pause, icon, slides, images, root, document, preference,
    selected: () => slides.findIndex(slide => !slide.hidden),
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
  assert.equal(c.selected(), 2);
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
