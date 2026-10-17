// One IntersectionObserver for section entrances. Entrances replay on re-entry (saved
// design preference) and the observer stops working while the tab is hidden.
const reduce = window.matchMedia('(prefers-reduced-motion: reduce)');

export function initMotion(scope = document) {
  const targets = [...scope.querySelectorAll('[data-reveal]')];
  if (!targets.length || !('IntersectionObserver' in window)) return;
  // Items already on screen at load appear immediately, without a late fade: measure
  // first, mark them visible, then enable the hidden starting state for the rest.
  const viewport = window.innerHeight;
  const onScreen = targets.filter(el => { const r = el.getBoundingClientRect(); return r.top < viewport && r.bottom > 0; });
  onScreen.forEach(el => el.classList.add('is-visible'));
  document.documentElement.classList.add('motion-ready');
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
