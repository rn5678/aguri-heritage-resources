/* A local, accessible editorial carousel; the next weekly lead is bundled too. */
(() => {
  'use strict';
  let dispose = () => {};

  function startCarousel(root) {
    const slides = Array.from(root.querySelectorAll('[data-feature-slide]'));
    const controls = root.querySelector('[data-feature-controls]');
    if (slides.length < 2 || !controls) return () => {};
    const dots = Array.from(root.querySelectorAll('[data-feature-dot]'));
    const counter = root.querySelector('[data-feature-counter]');
    const status = root.querySelector('[data-feature-status]');
    const reducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)');
    const locale = document.documentElement.lang === 'bn' ? 'bn' : 'en';
    const number = new Intl.NumberFormat(locale);
    const interval = Math.max(5000, Number(root.dataset.carouselInterval) || 7000);
    let index = 0;
    let onscreen = !('IntersectionObserver' in window);
    let timer;
    let disposed = false;
    const events = new AbortController();
    const listen = (element, name, handler) => element.addEventListener(name, handler, {signal: events.signal});

    function schedule() {
      if (disposed) return;
      window.clearTimeout(timer);
      // A focused article link must stay available until its reader moves away.
      const readingWithKeyboard = slides[index].contains(document.activeElement);
      if (!reducedMotion.matches && !readingWithKeyboard && onscreen && !document.hidden) {
        timer = window.setTimeout(() => show(index + 1, false), interval);
      }
      root.dataset.carouselPaused = String(reducedMotion.matches || readingWithKeyboard);
    }

    function show(next, manual) {
      index = (next + slides.length) % slides.length;
      slides.forEach((slide, position) => {
        const active = position === index;
        slide.classList.toggle('is-active', active);
        slide.setAttribute('aria-hidden', String(!active));
        slide.inert = !active;
        dots[position]?.setAttribute('aria-pressed', String(active));
      });
      root.dataset.weeklyFeatureKey = slides[index].dataset.featureKey;
      root.dataset.carouselIndex = String(index);
      counter.textContent = `${number.format(index + 1)} / ${number.format(slides.length)}`;
      if (manual) {
        status.textContent = slides[index].getAttribute('aria-label');
      }
      schedule();
    }

    // The grid reserves the tallest slide's space; inactive slides cannot receive focus.
    root.classList.add('weekly-feature-ready');
    slides.forEach(slide => { slide.hidden = false; });
    controls.hidden = false;
    root.setAttribute('aria-roledescription', locale === 'bn' ? 'ক্যারোসেল' : 'carousel');
    listen(root.querySelector('[data-feature-prev]'), 'click', () => show(index - 1, true));
    listen(root.querySelector('[data-feature-next]'), 'click', () => show(index + 1, true));
    dots.forEach((dot, position) => listen(dot, 'click', () => show(position, true)));
    // Arrows and dots restart the seven-second interval; hover never stops rotation.
    listen(root, 'focusin', schedule);
    listen(root, 'focusout', () => window.setTimeout(() => {
      updateWeeklyFeature();
      schedule();
    }, 0));
    listen(document, 'visibilitychange', schedule);
    listen(reducedMotion, 'change', schedule);
    let observer;
    if ('IntersectionObserver' in window) {
      observer = new IntersectionObserver(entries => {
        onscreen = entries[0].isIntersecting && entries[0].intersectionRatio >= 0.25;
        schedule();
      }, {threshold: 0.25});
      observer.observe(root);
    }
    show(0, false);
    return () => {
      disposed = true;
      window.clearTimeout(timer);
      observer?.disconnect();
      events.abort();
    };
  }

  function updateWeeklyFeature() {
    const upcoming = document.querySelector('template[data-weekly-feature-next]');
    const current = document.querySelector('section.weekly-feature');
    if (!upcoming || !current) return;
    // Use the publication's India calendar, regardless of the reader's timezone.
    const parts = new Intl.DateTimeFormat('en-CA', {
      timeZone: 'Asia/Kolkata', year: 'numeric', month: '2-digit', day: '2-digit'
    }).formatToParts(new Date());
    const part = type => parts.find(item => item.type === type).value;
    const today = `${part('year')}-${part('month')}-${part('day')}`;
    if (today < upcoming.dataset.weeklyFeatureNext) return;
    const replacement = upcoming.content.querySelector('section.weekly-feature');
    if (!replacement) return;
    // Do not replace an article or controls while the reader is interacting with them.
    if (current.contains(document.activeElement)) return;
    dispose();
    const next = replacement.cloneNode(true);
    next.querySelector('.weekly-feature-label').id = 'weekly-feature-heading';
    next.setAttribute('aria-labelledby', 'weekly-feature-heading');
    current.replaceWith(next);
    upcoming.remove();
    dispose = startCarousel(next);
  }
  const feature = document.querySelector('section.weekly-feature');
  if (feature) dispose = startCarousel(feature);
  updateWeeklyFeature();
  document.addEventListener('visibilitychange', () => {
    if (document.visibilityState === 'visible') updateWeeklyFeature();
  });
})();
