'use strict';
(() => {
const menu = document.querySelector('.menu');
const nav = document.querySelector('.nav');
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

document.querySelectorAll('[data-story-carousel]').forEach((carousel, carouselIndex) => {
  const track = carousel.querySelector('.story-grid');
  const viewport = carousel.querySelector('.carousel-viewport');
  const controls = carousel.querySelector('.carousel-controls');
  const previous = carousel.querySelector('[data-carousel-prev]');
  const next = carousel.querySelector('[data-carousel-next]');
  const toggle = carousel.querySelector('[data-carousel-toggle]');
  const status = carousel.querySelector('[data-carousel-status]');
  const dotContainer = carousel.querySelector('[data-carousel-dots]');
  if (!track || !viewport || !controls || !previous || !next || !toggle || !status || !dotContainer) return;

  const cards = [...track.querySelectorAll('.story')];
  if (cards.length < 2) return;
  const reducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)');
  const number = new Intl.NumberFormat(document.documentElement.lang || 'en');
  const interval = Math.max(5000, Number(carousel.dataset.interval) || 8000);
  let pausedByUser = false;
  let motionRequested = false;
  let hovered = false;
  let keyboardMode = false;
  let keyboardFocus = false;
  let inView = !('IntersectionObserver' in window);
  let animating = false;
  let timer;
  let finishAnimation;
  let pointerStart;
  let suppressClick = false;
  let suppressClickTimer;

  const visibleCount = () => Math.min(cards.length, Math.max(1,
    parseInt(getComputedStyle(carousel).getPropertyValue('--cards-visible'), 10) || 1));
  const wantsAutoplay = () => !pausedByUser && (!reducedMotion.matches || motionRequested);
  const canAutoplay = () => wantsAutoplay() && !animating && !hovered && !keyboardFocus &&
    !document.hidden && inView && !track.contains(document.activeElement);

  cards.forEach((card, index) => {
    card.id ||= `story-carousel-${carouselIndex + 1}-slide-${index + 1}`;
    card.setAttribute('role', 'group');
    card.setAttribute('aria-roledescription', carousel.dataset.slideRoleLabel || 'slide');
    card.setAttribute('aria-label', `${carousel.dataset.carouselLabel || 'Story'} ${number.format(index + 1)} / ${number.format(cards.length)}`);
  });

  const dots = cards.map((card, index) => {
    const dot = document.createElement('button');
    dot.type = 'button';
    dot.className = 'carousel-dot';
    dot.setAttribute('aria-label', `${carousel.dataset.slideLabel || 'Show story'} ${number.format(index + 1)}: ${card.dataset.storyTitle || ''}`);
    dot.setAttribute('aria-controls', card.id);
    dot.addEventListener('click', () => jumpTo(index));
    dotContainer.append(dot);
    return dot;
  });

  function updateToggle() {
    const label = wantsAutoplay() ? carousel.dataset.pauseLabel || 'Pause stories' : carousel.dataset.playLabel || 'Play stories';
    toggle.textContent = label;
    toggle.setAttribute('aria-label', label);
    toggle.removeAttribute('aria-pressed');
  }

  function updateCards(manual = false) {
    const visible = visibleCount();
    [...track.children].forEach((card, position) => {
      const hidden = position >= visible;
      if (hidden && card.contains(document.activeElement)) next.focus({ preventScroll: true });
      card.inert = hidden;
      card.setAttribute('aria-hidden', String(hidden));
    });
    const index = cards.indexOf(track.firstElementChild);
    dots.forEach((dot, position) => {
      if (position === index) dot.setAttribute('aria-current', 'true');
      else dot.removeAttribute('aria-current');
    });
    status.setAttribute('aria-live', manual ? 'polite' : 'off');
    status.setAttribute('aria-atomic', 'true');
    status.textContent = `${number.format(index + 1)} / ${number.format(cards.length)}`;
  }

  function schedule() {
    clearTimeout(timer);
    updateToggle();
    if (canAutoplay()) timer = setTimeout(() => move(1, false), interval);
  }

  function pauseForNavigation() {
    pausedByUser = true;
    motionRequested = false;
    schedule();
  }

  function move(direction, manual = true) {
    if (manual) pauseForNavigation();
    if (animating || (!manual && !canAutoplay())) return;
    if (track.contains(document.activeElement)) {
      (direction > 0 ? next : previous).focus({ preventScroll: true });
    }
    clearTimeout(timer);
    const first = track.children[0];
    const second = track.children[1];
    const step = second.getBoundingClientRect().left - first.getBoundingClientRect().left;
    if (!step) return;
    animating = true;
    // Cards are unavailable during motion, so focus cannot enter a departing slide.
    cards.forEach(card => {
      card.inert = true;
      card.setAttribute('aria-hidden', 'true');
    });
    track.style.transition = 'none';
    if (direction < 0) {
      track.prepend(track.lastElementChild);
      track.style.transform = `translateX(${-step}px)`;
    } else {
      track.style.transform = 'translateX(0)';
    }
    let fallback;
    const onTransitionEnd = event => {
      if (event.target === track && event.propertyName === 'transform') finish();
    };
    const finish = () => {
      if (!animating) return;
      clearTimeout(fallback);
      track.removeEventListener('transitionend', onTransitionEnd);
      track.style.transition = 'none';
      if (direction > 0) track.append(track.firstElementChild);
      track.style.transform = 'translateX(0)';
      void track.offsetWidth;
      track.style.transition = '';
      animating = false;
      finishAnimation = undefined;
      updateCards(manual);
      schedule();
    };
    finishAnimation = finish;
    if (reducedMotion.matches) {
      finish();
      return;
    }
    void track.offsetWidth;
    track.addEventListener('transitionend', onTransitionEnd);
    track.style.transition = '';
    track.style.transform = direction > 0 ? `translateX(${-step}px)` : 'translateX(0)';
    fallback = setTimeout(finish, 750);
  }

  function jumpTo(index) {
    pauseForNavigation();
    if (animating) return;
    track.style.transition = 'none';
    track.append(...cards.slice(index), ...cards.slice(0, index));
    track.style.transform = 'translateX(0)';
    void track.offsetWidth;
    track.style.transition = '';
    updateCards(true);
  }

  function updateFocus() {
    keyboardFocus = keyboardMode && carousel.contains(document.activeElement);
    schedule();
  }

  previous.addEventListener('click', () => move(-1));
  next.addEventListener('click', () => move(1));
  toggle.addEventListener('click', () => {
    const play = !wantsAutoplay();
    pausedByUser = !play;
    motionRequested = play;
    // Explicit Play works while its own button retains keyboard focus.
    if (play && document.activeElement === toggle) keyboardFocus = false;
    schedule();
  });
  carousel.addEventListener('pointerenter', event => {
    if (event.pointerType !== 'mouse') return;
    hovered = true;
    schedule();
  });
  carousel.addEventListener('pointerleave', () => {
    hovered = false;
    schedule();
  });
  carousel.addEventListener('focusin', updateFocus);
  carousel.addEventListener('focusout', () => requestAnimationFrame(updateFocus));
  document.addEventListener('pointerdown', () => {
    keyboardMode = false;
    updateFocus();
  });
  document.addEventListener('keydown', () => {
    keyboardMode = true;
    updateFocus();
  });
  carousel.addEventListener('keydown', event => {
    if (event.altKey || event.ctrlKey || event.metaKey || event.shiftKey ||
      event.target.closest('input, textarea, select, [contenteditable="true"]')) return;
    if (event.key === 'ArrowLeft' || event.key === 'ArrowRight') {
      event.preventDefault();
      move(event.key === 'ArrowLeft' ? -1 : 1);
    }
  });

  viewport.addEventListener('pointerdown', event => {
    if (event.isPrimary && event.pointerType !== 'mouse') {
      pointerStart = { x: event.clientX, y: event.clientY, time: performance.now(), id: event.pointerId };
    }
  });
  document.addEventListener('pointerup', event => {
    if (!pointerStart || pointerStart.id !== event.pointerId) return;
    const dx = event.clientX - pointerStart.x;
    const dy = event.clientY - pointerStart.y;
    const quick = performance.now() - pointerStart.time < 1200;
    pointerStart = undefined;
    if (quick && Math.abs(dx) > 45 && Math.abs(dx) > Math.abs(dy) * 1.3) {
      suppressClick = true;
      clearTimeout(suppressClickTimer);
      suppressClickTimer = setTimeout(() => { suppressClick = false; }, 400);
      move(dx < 0 ? 1 : -1);
    }
  });
  viewport.addEventListener('pointercancel', () => { pointerStart = undefined; });
  viewport.addEventListener('click', event => {
    if (suppressClick) {
      event.preventDefault();
      event.stopPropagation();
      suppressClick = false;
    }
  }, true);

  document.addEventListener('visibilitychange', schedule);
  reducedMotion.addEventListener('change', () => {
    motionRequested = false;
    finishAnimation?.();
    schedule();
  });
  if ('IntersectionObserver' in window) {
    new IntersectionObserver(entries => {
      inView = entries[0].isIntersecting;
      schedule();
    }, { threshold: 0.15 }).observe(viewport);
  }
  function resize() {
    finishAnimation?.();
    updateCards();
    schedule();
  }
  if ('ResizeObserver' in window) new ResizeObserver(resize).observe(viewport);
  else window.addEventListener('resize', resize);

  carousel.classList.add('is-carousel');
  controls.hidden = false;
  updateCards();
  schedule();
});

})();
