(() => {
  const carousel = document.querySelector('[data-home-article-carousel]');
  if (!carousel) return;

  const slides = [...carousel.querySelectorAll('[data-home-article-slide]')];
  const previous = carousel.querySelector('[data-home-prev]');
  const next = carousel.querySelector('[data-home-next]');
  const pause = carousel.querySelector('[data-home-pause]');
  if (slides.length < 2 || !previous || !next || !pause) return;

  const icon = pause.querySelector('[data-home-pause-icon]');
  const pauseText = pause.querySelector('[data-home-pause-text]');
  const status = carousel.querySelector('[data-home-status]');
  const numbers = new Intl.NumberFormat(document.documentElement?.lang || 'en');
  const reducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)');
  const desktop = window.matchMedia('(min-width: 900px)');
  const tablet = window.matchMedia('(min-width: 600px)');
  const track = slides[0].parentElement;
  let index = 0;
  let paused = reducedMotion.matches;
  let explicitPlay = false;
  let hovered = false;
  let focused = carousel.contains(document.activeElement);
  let timer;

  const visibleCount = () => Math.min(slides.length, desktop.matches ? 3 : tablet.matches ? 2 : 1);

  function show(target, preserveFocus = false) {
    index = (target + slides.length) % slides.length;
    const count = visibleCount();
    const focusedSlide = slides.find(slide => slide.contains(document.activeElement));
    const focusedIndex = slides.indexOf(focusedSlide);
    if (preserveFocus && focusedIndex >= 0 && (focusedIndex - index + slides.length) % slides.length >= count) {
      index = focusedIndex;
    }
    // Keep DOM order aligned with visual and keyboard order even across wrap.
    // Never move the currently focused card: moving a DOM node can blur it.
    const ordered = [...slides.slice(index), ...slides.slice(0, index)];
    const anchor = ordered.indexOf(focusedSlide);
    if (anchor >= 0) {
      ordered.slice(0, anchor).forEach(slide => track.insertBefore(slide, focusedSlide));
      ordered.slice(anchor + 1).forEach(slide => track.append(slide));
    } else {
      ordered.forEach(slide => track.append(slide));
    }
    if (status) {
      const first = numbers.format(index + 1);
      const last = numbers.format((index + count - 1) % slides.length + 1);
      const total = numbers.format(slides.length);
      status.textContent = count === 1 ? `${first} / ${total}` : `${first}–${last} / ${total}`;
    }
    ordered.forEach((slide, i) => {
      slide.hidden = i >= count;
      slide.inert = i >= count;
      if (i < count) {
        const image = slide.querySelector('img');
        if (image && image.loading === 'lazy') image.loading = 'eager';
      }
    });
  }

  function schedule() {
    window.clearTimeout(timer);
    const stopped = paused;
    const label = stopped ? carousel.dataset.playLabel : carousel.dataset.pauseLabel;
    pause.setAttribute('aria-label', label);
    if (pauseText) pauseText.textContent = label;
    pause.dataset.homePaused = String(stopped);
    if (icon) {
      icon.setAttribute('aria-hidden', 'true');
      icon.textContent = stopped ? '▶' : 'Ⅱ';
    }
    if (!stopped && (explicitPlay || (!hovered && !focused)) && !document.hidden) {
      timer = window.setTimeout(() => {
        show(index + 1, true);
        schedule();
      }, 8000);
    }
  }

  function navigate(delta) {
    show(index + delta, true);
    schedule();
  }
  previous.addEventListener('click', () => navigate(-1));
  next.addEventListener('click', () => navigate(1));
  carousel.addEventListener('keydown', (event) => {
    if (![previous, next, pause].includes(event.target) || event.altKey || event.ctrlKey || event.metaKey || event.shiftKey) return;
    const delta = event.key === 'ArrowLeft' ? -1 : event.key === 'ArrowRight' ? 1 : 0;
    if (!delta) return;
    event.preventDefault();
    navigate(delta);
  });
  function resize() {
    show(index, true);
    schedule();
  }
  desktop.addEventListener('change', resize);
  tablet.addEventListener('change', resize);
  pause.addEventListener('click', () => {
    paused = !paused;
    explicitPlay = !paused;
    schedule();
  });
  carousel.addEventListener('pointerenter', (event) => {
    if (event.pointerType === 'touch') return;
    hovered = true;
    explicitPlay = false;
    schedule();
  });
  carousel.addEventListener('pointerleave', () => {
    hovered = false;
    if (!focused) explicitPlay = false;
    schedule();
  });
  carousel.addEventListener('focusin', () => {
    focused = true;
    explicitPlay = false;
    schedule();
  });
  carousel.addEventListener('focusout', (event) => {
    focused = carousel.contains(event.relatedTarget);
    if (!focused && !hovered) explicitPlay = false;
    schedule();
  });
  reducedMotion.addEventListener('change', () => {
    if (reducedMotion.matches) {
      paused = true;
      explicitPlay = false;
    }
    schedule();
  });
  document.addEventListener('visibilitychange', schedule);

  show(0);
  for (const control of [previous, next, pause, carousel.querySelector('[data-home-controls]')]) {
    if (control) control.hidden = false;
  }
  schedule();
})();
