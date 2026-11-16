"use strict";
(() => {
  const releases = new WeakMap();
  let pressed = null;
  function release() {
    if (!pressed) return;
    const element = pressed;
    releases.set(element, setTimeout(() => element.classList.remove('is-pressed'), 120));
    pressed = null;
  }
  document.addEventListener('pointerdown', event => {
    if (event.button !== 0 || !event.isPrimary) return;
    release();
    const element = event.target.closest('button, a[href], summary, label:has(input[type="radio"])');
    if (!element || element.matches(':disabled, [aria-disabled="true"]')) return;
    clearTimeout(releases.get(element));
    pressed = element;
    element.classList.add('is-pressed');
  }, { passive: true });
  document.addEventListener('pointerup', release, { passive: true });
  document.addEventListener('pointercancel', release, { passive: true });
  window.addEventListener('blur', release);

  document.addEventListener('click', event => {
    const link = event.target.closest('a[href]');
    if (!link || event.button !== 0 || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey || link.hasAttribute('download') || (link.target && link.target !== '_self')) return;
    const url = new URL(link.href, location.href);
    if (url.origin !== location.origin || (url.pathname === location.pathname && url.search === location.search)) return;
    queueMicrotask(() => {
      if (event.defaultPrevented) return;
      link.classList.add('is-opening');
      link.setAttribute('aria-busy', 'true');
      document.body.classList.add('ui-navigating');
    });
  });
  window.addEventListener('pageshow', () => {
    document.body.classList.remove('ui-navigating');
    document.querySelectorAll('.is-opening, .is-pressed').forEach(element => {
      element.classList.remove('is-opening', 'is-pressed');
      element.removeAttribute('aria-busy');
    });
  });
})();
