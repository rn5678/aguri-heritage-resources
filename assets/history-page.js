'use strict';
// History page header behaviour, matching the homepage (homepage-carousel.js) without the carousel.
(() => {
  const menu = document.querySelector('.header .menu');
  const nav = document.querySelector('.header .nav');
  menu?.addEventListener('click', () => {
    const open = menu.getAttribute('aria-expanded') !== 'true';
    menu.setAttribute('aria-expanded', String(open));
    nav?.classList.toggle('is-open', open);
  });
  document.addEventListener('keydown', event => {
    if (event.key === 'Escape' && menu?.getAttribute('aria-expanded') === 'true') {
      menu.setAttribute('aria-expanded', 'false');
      nav?.classList.remove('is-open');
      menu.focus();
    }
  });
})();
