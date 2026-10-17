// Public page chrome: icons, phone menu (Escape, outside click, focus return) and
// current-page marking. Shared by the home, request and status pages.
import { $, hydrateIcons } from './dom.js';
import { hydrateStaticLocations } from './locations.js';

export function initChrome() {
  hydrateIcons();
  const header = $('[data-header]');
  const toggle = $('[data-menu-toggle]');
  const nav = $('#site-menu');
  if (header && toggle && nav) {
    const mobile = window.matchMedia('(max-width: 1040px)');
    const setOpen = open => {
      header.classList.toggle('is-open', open);
      toggle.setAttribute('aria-expanded', String(open));
      toggle.querySelector('.visually-hidden').textContent = open ? 'Close menu' : 'Menu';
      if (mobile.matches) nav.inert = !open;
    };
    const sync = () => { nav.inert = mobile.matches && !header.classList.contains('is-open'); };
    sync();
    mobile.addEventListener('change', () => { setOpen(false); sync(); });
    toggle.addEventListener('click', () => {
      const open = !header.classList.contains('is-open');
      setOpen(open);
      if (open) nav.querySelector('a')?.focus();
    });
    document.addEventListener('keydown', event => {
      if (event.key === 'Escape' && header.classList.contains('is-open')) { setOpen(false); toggle.focus(); }
    });
    document.addEventListener('click', event => {
      if (header.classList.contains('is-open') && !header.contains(event.target)) setOpen(false);
    });
    nav.addEventListener('click', event => { if (event.target.closest('a')) setOpen(false); });
  }
  const path = location.pathname.replace(/\/$/, '') || '/';
  for (const link of document.querySelectorAll('.nav-links a, .footer-nav a')) {
    const href = link.getAttribute('href');
    if (href === path) link.setAttribute('aria-current', 'page');
  }
  hydrateStaticLocations();
}
