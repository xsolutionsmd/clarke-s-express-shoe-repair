// One IntersectionObserver for section entrances. Entrances replay on re-entry (saved
// design preference) and the observer stops working while the tab is hidden.
const reduce = window.matchMedia('(prefers-reduced-motion: reduce)');

export function initMotion(scope = document) {
  const targets = [...scope.querySelectorAll('[data-reveal]')];
  if (!targets.length || !('IntersectionObserver' in window)) return;
  document.documentElement.classList.add('motion-ready');
  // Items already on screen at load appear immediately, without a late fade.
  const viewport = window.innerHeight;
  for (const el of targets) {
    const rect = el.getBoundingClientRect();
    if (rect.top < viewport && rect.bottom > 0) el.classList.add('is-visible');
  }
  let observer = null;
  const start = () => {
    observer = new IntersectionObserver(entries => {
      for (const entry of entries) {
        // Replay only after the element has fully left the viewport.
        if (entry.isIntersecting) entry.target.classList.add('is-visible');
        else if (!reduce.matches && entry.intersectionRatio === 0) entry.target.classList.remove('is-visible');
      }
    }, { rootMargin: '0px 0px -8% 0px', threshold: [0, 0.12] });
    targets.forEach(el => observer.observe(el));
  };
  start();
  document.addEventListener('visibilitychange', () => {
    if (document.hidden) { observer?.disconnect(); observer = null; } else if (!observer) start();
  });
}
