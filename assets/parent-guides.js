/* Progressive enhancement: every guide entry is readable without JavaScript. */
(() => {
 'use strict';
 const bn = document.documentElement.lang === 'bn';
 const number = n => new Intl.NumberFormat(bn ? 'bn' : 'en').format(n);
 const normalize = text => text.normalize('NFD').replace(/[\u0300-\u036f]/g, '').normalize('NFC').toLocaleLowerCase().trim();
 const searches = [];
 document.querySelectorAll('.surname-browser').forEach(browser => {
  const input = browser.querySelector('[data-surname-search]');
  if (!input) return;
  const entries = [...browser.querySelectorAll('[data-surname-entry]')];
  const status = browser.querySelector('[data-surname-count]');
  const empty = browser.querySelector('[data-surname-empty]');
  const update = () => {
   const words = normalize(input.value).split(/\s+/).filter(Boolean);
   let count = 0;
   entries.forEach(entry => {
    const text = normalize((entry.dataset.search || '') + ' ' + entry.textContent);
    entry.hidden = !words.every(word => text.includes(word));
    if (!entry.hidden) count++;
   });
   if (status) status.textContent = bn ? `${number(count)}টি নাম দেখা যাচ্ছে` : `${number(count)} ${count === 1 ? 'name' : 'names'} shown`;
   if (empty) empty.hidden = count !== 0;
  };
  input.addEventListener('input', update);
  searches.push({browser, input, update});
  update();
 });
 const groups = [];
 document.querySelectorAll('[data-guide-filter]').forEach(group => {
  const buttons = [...group.querySelectorAll('button[data-topic]')];
  const entries = [...group.querySelectorAll('[data-guide-entry]')];
  const status = group.querySelector('[data-guide-count]');
  const empty = group.querySelector('[data-guide-empty]');
  const update = topic => {
   buttons.forEach(button => button.setAttribute('aria-pressed', String(button.dataset.topic === topic)));
   let count = 0;
   entries.forEach(entry => {
    entry.hidden = topic !== 'all' && !(entry.dataset.topics || '').split(/\s+/).includes(topic);
    if (!entry.hidden) count++;
   });
   if (status) status.textContent = bn ? `${number(count)}টি পাঠের পথ দেখা যাচ্ছে` : `${number(count)} reading ${count === 1 ? 'path' : 'paths'} shown`;
   if (empty) empty.hidden = count !== 0;
  };
  buttons.forEach(button => button.addEventListener('click', () => update(button.dataset.topic)));
  groups.push({group, update});
  update('all');
 });
 const reveal = () => {
  let id;
  try { id = decodeURIComponent(location.hash.slice(1)); } catch (_) { return; }
  const target = document.getElementById(id);
  if (!target) return;
  searches.forEach(({browser,input,update}) => { if (browser.contains(target)) { input.value = ''; update(); } });
  groups.forEach(({group,update}) => { if (group.contains(target)) update('all'); });
  for (let parent = target.parentElement; parent; parent = parent.parentElement) {
   if (parent.tagName === 'DETAILS') parent.open = true;
  }
 };
 // Existing app.js handles details.notes; these additional guide disclosures
 // also belong in the printed copy, including entries hidden by a search.
 let printState = [];
 window.addEventListener('beforeprint', () => {
  printState = [...document.querySelectorAll('details.guide-depth:not(.notes), details.surname-entry')].map(element => ({element, open: element.open}));
  printState.forEach(({element}) => { element.open = true; });
 });
 window.addEventListener('afterprint', () => { printState.forEach(({element,open}) => { element.open = open; }); printState = []; });
 document.addEventListener('click', event => {
  const link = event.target.closest('a[href]');
  if (link && link.getAttribute('href') === location.hash) reveal();
 });
 window.addEventListener('hashchange', reveal);
 reveal();
})();
