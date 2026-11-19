(() => {
  const carousel = document.querySelector('[data-home-article-carousel]');
  if (!carousel) return;

  const slides = [...carousel.querySelectorAll('[data-home-article-slide]')];
  const previous = carousel.querySelector('[data-home-prev]');
  const next = carousel.querySelector('[data-home-next]');
  const pause = carousel.querySelector('[data-home-pause]');
  if (slides.length < 2 || !previous || !next || !pause) return;

  const icon = pause.querySelector('[data-home-pause-icon]');
  const reducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)');
  let index = 0;
  let paused = reducedMotion.matches;
  let explicitPlay = false;
  let hovered = false;
  let focused = carousel.contains(document.activeElement);
  let timer;

  function show(target) {
    index = (target + slides.length) % slides.length;
    slides.forEach((slide, i) => {
      slide.hidden = i !== index;
      slide.inert = i !== index;
    });
    const image = slides[index].querySelector('img');
    if (image && image.loading === 'lazy') image.loading = 'eager';
  }

  function schedule() {
    window.clearTimeout(timer);
    const stopped = paused;
    pause.setAttribute('aria-label', stopped ? carousel.dataset.playLabel : carousel.dataset.pauseLabel);
    pause.dataset.homePaused = String(stopped);
    if (icon) {
      icon.setAttribute('aria-hidden', 'true');
      icon.textContent = stopped ? '▶' : 'Ⅱ';
    }
    if (!stopped && (explicitPlay || (!hovered && !focused)) && !document.hidden) {
      timer = window.setTimeout(() => {
        show(index + 1);
        schedule();
      }, 8000);
    }
  }

  previous.addEventListener('click', () => {
    show(index - 1);
    schedule();
  });
  next.addEventListener('click', () => {
    show(index + 1);
    schedule();
  });
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
