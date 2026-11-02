/* Scoped History story carousel. The original four story cards remain below. */
(() => {
  'use strict';
  document.querySelectorAll('[data-history-carousel]').forEach((root) => {
    const slides = Array.from(root.querySelectorAll('.history-hero-slide'));
    const indicators = Array.from(root.querySelectorAll('[data-hero-indicator]'));
    const controls = root.querySelector('.history-hero-controls');
    const toggle = root.querySelector('[data-hero-toggle]');
    const previous = root.querySelector('[data-hero-prev]');
    const next = root.querySelector('[data-hero-next]');
    const status = root.querySelector('[data-hero-status]');
    if (slides.length < 2 || indicators.length !== slides.length ||
        !controls || !toggle || !previous || !next || !status) return;

    const motion = window.matchMedia('(prefers-reduced-motion: reduce)');
    const interval = Math.max(12000, Number(root.dataset.interval) || 12000);
    const originalTabIndexes = new Map();
    slides.forEach((slide) => slide.querySelectorAll('a, button, input, select, textarea, [tabindex]').forEach((el) => {
      originalTabIndexes.set(el, el.getAttribute('tabindex'));
    }));
    let current = 0;
    let enabled = !motion.matches;
    let inView = !('IntersectionObserver' in window);
    let hovered = false;
    let timer = null;
    let pointerToggleIntent = null;
    let allowFocusedToggle = false;
    let printing = false;

    const clearTimer = () => {
      if (timer !== null) window.clearTimeout(timer);
      timer = null;
    };
    const focusedHere = () => root.contains(document.activeElement) &&
      !(allowFocusedToggle && document.activeElement === toggle);
    const updateToggle = () => {
      toggle.disabled = motion.matches;
      toggle.textContent = motion.matches ? root.dataset.reducedLabel :
        enabled ? root.dataset.pauseLabel : root.dataset.resumeLabel;
    };
    const schedule = () => {
      clearTimer();
      if (!enabled || motion.matches || !inView || hovered ||
          document.hidden || printing || focusedHere()) return;
      timer = window.setTimeout(() => {
        timer = null;
        if (!enabled || motion.matches || !inView || hovered ||
            document.hidden || printing || focusedHere()) return;
        show(current + 1, false);
        schedule();
      }, interval);
    };
    const stop = () => {
      enabled = false;
      allowFocusedToggle = false;
      clearTimer();
      updateToggle();
    };
    const show = (index, manual) => {
      current = (index + slides.length) % slides.length;
      slides.forEach((slide, i) => {
        const active = i === current;
        slide.classList.toggle('is-active', active);
        slide.setAttribute('aria-hidden', String(!active));
        slide.inert = !active;
        slide.querySelectorAll('a, button, input, select, textarea, [tabindex]').forEach((el) => {
          if (!active) el.setAttribute('tabindex', '-1');
          else if (originalTabIndexes.get(el) === null) el.removeAttribute('tabindex');
          else el.setAttribute('tabindex', originalTabIndexes.get(el));
        });
        if (active) indicators[i].setAttribute('aria-current', 'true');
        else indicators[i].removeAttribute('aria-current');
      });
      const lang = document.documentElement.lang === 'bn' ? 'bn' : 'en';
      const number = (n) => String(n).replace(/\d/g, (digit) => lang === 'bn' ? '০১২৩৪৫৬৭৮৯'[Number(digit)] : digit);
      status.setAttribute('aria-live', manual ? 'polite' : 'off');
      status.textContent = `${number(current + 1)} / ${number(slides.length)} · ${slides[current].dataset.heroTitle}`;
    };
    const navigate = (index) => {
      stop();
      show(index, true);
    };

    root.addEventListener('pointerdown', (event) => {
      // Pointer focus arrives before click. Remember the action the user saw.
      pointerToggleIntent = toggle.contains(event.target) ? !enabled : null;
      stop();
    });
    root.addEventListener('pointercancel', () => { pointerToggleIntent = null; });
    root.addEventListener('keydown', () => { pointerToggleIntent = null; });
    root.addEventListener('focusin', () => { stop(); });
    root.addEventListener('pointerenter', (event) => {
      if (event.pointerType === 'touch') return;
      hovered = true;
      clearTimer();
    });
    root.addEventListener('pointerleave', (event) => {
      if (event.pointerType === 'touch') return;
      hovered = false;
      schedule();
    });
    toggle.addEventListener('click', () => {
      const resume = pointerToggleIntent === null ? !enabled : pointerToggleIntent;
      pointerToggleIntent = null;
      enabled = resume && !motion.matches;
      allowFocusedToggle = enabled;
      status.setAttribute('aria-live', 'off');
      updateToggle();
      schedule();
    });
    previous.addEventListener('click', () => navigate(current - 1));
    next.addEventListener('click', () => navigate(current + 1));
    indicators.forEach((button, index) => button.addEventListener('click', () => navigate(index)));
    document.addEventListener('visibilitychange', schedule);
    window.addEventListener('beforeprint', () => { printing = true; clearTimer(); });
    window.addEventListener('afterprint', () => { printing = false; schedule(); });
    const motionChanged = () => { stop(); };
    if (motion.addEventListener) motion.addEventListener('change', motionChanged);
    else motion.addListener(motionChanged);
    if ('IntersectionObserver' in window) {
      const observer = new window.IntersectionObserver((entries) => {
        entries.forEach((entry) => {
          if (entry.target !== root) return;
          inView = entry.isIntersecting && entry.intersectionRatio >= 0.5;
        });
        schedule();
      }, { threshold: [0, 0.5] });
      observer.observe(root);
    }
    // A delayed script must not hide a story someone already reached without JS.
    const focusedSlide = slides.findIndex((slide) => slide.contains(document.activeElement));
    if (root.contains(document.activeElement)) stop();
    show(focusedSlide < 0 ? 0 : focusedSlide, false);
    updateToggle();
    root.classList.add('is-enhanced');
    controls.hidden = false;
    schedule();
  });
})();
