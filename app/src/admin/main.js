// Staff app shell: client-side router over the contract's /admin/* routes, signed-in
// layout, role gating (Viewer gets a 403 page on management routes) and session expiry.
import '../styles/tokens.css';
import '../styles/base.css';
import '../styles/forms.css';
import '../styles/admin.css';
import { h, icon, replace, button, hydrateIcons, announce } from '../lib/dom.js';
import { ApiError } from '../lib/api.js';
import { session, loadSession, isAdmin, logout, startGoogle, pageHead, inlineAlert } from './core.js';

const root = document.getElementById('admin-root');
const UUID = '[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}';
const ROUTES = [
  { pattern: /^\/admin\/login\/?$/, view: () => import('./views/login.js'), public: true },
  { pattern: /^\/admin\/invite\/?$/, view: () => import('./views/invite.js'), public: true },
  { pattern: /^\/admin\/requests\/?$/, view: () => import('./views/inbox.js'), nav: 'requests' },
  { pattern: /^\/admin\/requests\/new\/?$/, view: () => import('./views/ticket.js'), nav: 'new' },
  { pattern: new RegExp(`^/admin/requests/(${UUID})/?$`, 'i'), view: () => import('./views/detail.js'), nav: 'requests' },
  { pattern: /^\/admin\/locations\/?$/, view: () => import('./views/hours.js'), admin: true, nav: 'locations' },
  { pattern: /^\/admin\/notices\/?$/, view: () => import('./views/notices.js'), admin: true, nav: 'notices' },
  { pattern: /^\/admin\/settings\/?$/, view: () => import('./views/settings.js'), admin: true, nav: 'settings' },
  { pattern: /^\/admin\/team\/?$/, view: () => import('./views/team.js'), admin: true, nav: 'team' },
  { pattern: /^\/admin\/emails\/?$/, view: () => import('./views/emails.js'), admin: true, nav: 'emails' },
  { pattern: new RegExp(`^/admin/emails/outbox/(${UUID})/?$`, 'i'), view: () => import('./views/outbox.js'), admin: true, nav: 'emails' },
  { pattern: /^\/admin\/audit\/?$/, view: () => import('./views/audit.js'), admin: true, nav: 'audit' },
];

const NAV = [
  ['requests', 'Requests', '/admin/requests'],
  ['new', 'New ticket', '/admin/requests/new'],
  ['locations', 'Hours', '/admin/locations', true],
  ['notices', 'Notices', '/admin/notices', true],
  ['settings', 'Settings', '/admin/settings', true],
  ['team', 'Team', '/admin/team', true],
  ['emails', 'Emails', '/admin/emails', true],
  ['audit', 'Audit', '/admin/audit', true],
];

let cleanup = null;
let layout = null;
let renderSeq = 0;

export function navigate(path, { replaceState = false } = {}) {
  if (replaceState) history.replaceState(null, '', path); else history.pushState(null, '', path);
  render();
}

function buildLayout() {
  const menuButton = h('button', { type: 'button', class: 'icon-button admin-menu-toggle', 'aria-expanded': 'false', 'aria-controls': 'admin-nav' }, icon('menu'), h('span', { class: 'visually-hidden' }, 'Menu'));
  const nav = h('nav', { class: 'admin-nav', id: 'admin-nav', 'aria-label': 'Staff' },
    h('ul', null, NAV.filter(([, , , adminOnly]) => !adminOnly || isAdmin()).map(([id, label, href]) => h('li', null, h('a', { href, 'data-nav': '', dataset: { navId: id } }, label)))));
  const member = session.data.member;
  const signOut = button('Sign out', { variant: 'quiet', class: 'btn-small' });
  signOut.addEventListener('click', async () => {
    await logout();
    navigate('/admin/login?signedOut=1', { replaceState: true });
  });
  const bar = h('header', { class: 'admin-bar' },
    h('div', { class: 'admin-bar-inner' },
      menuButton,
      h('a', { class: 'wordmark admin-wordmark', href: '/admin/requests', 'data-nav': '' },
        h('img', { class: 'wordmark-mark', src: '/media/clarke-mark.png', alt: '', width: 27, height: 32 }),
        h('span', { class: 'wordmark-text' }, h('span', { class: 'wordmark-name' }, 'Clarke’s Express'), h('span', { class: 'wordmark-sub' }, 'Staff'))),
      nav,
      h('div', { class: 'admin-who' },
        session.data.demoMode ? h('span', { class: 'badge badge-demo', title: 'Messages only go to the private test list' }, 'Demo mode') : null,
        h('span', { class: 'admin-member' }, icon('user', { size: 18 }), h('span', { class: 'admin-member-text' }, member.email, h('small', null, member.role === 'admin' ? 'Admin' : 'Viewer'))),
        signOut)));
  menuButton.addEventListener('click', () => {
    const open = bar.classList.toggle('is-open');
    menuButton.setAttribute('aria-expanded', String(open));
  });
  document.addEventListener('keydown', event => {
    if (event.key === 'Escape' && bar.classList.contains('is-open')) { bar.classList.remove('is-open'); menuButton.setAttribute('aria-expanded', 'false'); menuButton.focus(); }
  });
  const main = h('main', { id: 'admin-main', class: 'admin-main', tabindex: '-1' });
  const expired = h('div', { class: 'session-banner', hidden: true, role: 'alert' });
  replace(root, bar, expired, main);
  return { bar, nav, main, expired };
}

function markNav(id) {
  for (const a of layout.nav.querySelectorAll('a')) {
    if (a.dataset.navId === id) a.setAttribute('aria-current', 'page'); else a.removeAttribute('aria-current');
  }
  layout.bar.classList.remove('is-open');
}

function sessionExpired() {
  if (!layout) return;
  const path = location.pathname;
  const signIn = button('Sign in with Google', { variant: 'primary', class: 'btn-small' });
  signIn.addEventListener('click', async () => {
    try { await startGoogle({ returnTo: path }); } catch (error) { replace(layout.expired, inlineAlert(error.message)); }
  });
  replace(layout.expired, h('div', { class: 'session-banner-inner' },
    icon('alert', { size: 20 }), h('p', null, 'Your session ended. Sign in again to save; your unsaved text is kept on this device.'), signIn));
  layout.expired.hidden = false;
}

function forbidden(main) {
  replace(main,
    pageHead('You don’t have access to this page'),
    h('div', { class: 'panel' }, h('p', null, 'Admins manage hours, notices, settings, the team and email. Viewers can work on repair requests.'),
      h('p', null, h('a', { href: '/admin/requests', 'data-nav': '' }, 'Go to requests'))));
}

function notFound(main) {
  replace(main, pageHead('Page not found'), h('div', { class: 'panel' }, h('p', null, h('a', { href: '/admin/requests', 'data-nav': '' }, 'Go to requests'))));
}

async function render() {
  const seq = ++renderSeq;
  cleanup?.();
  cleanup = null;
  let path = location.pathname;
  if (/^\/admin\/?$/.test(path)) { history.replaceState(null, '', '/admin/requests'); path = '/admin/requests'; }
  const route = ROUTES.find(r => r.pattern.test(path));
  if (route?.public) {
    layout = null;
    root.removeAttribute('aria-busy');
    const mod = await route.view();
    if (seq !== renderSeq) return;
    const host = h('main', { id: 'admin-main', class: 'admin-public', tabindex: '-1' });
    replace(root, host);
    cleanup = await mod.default({ main: host, navigate, params: [], sessionExpired });
    hydrateIcons(root);
    return;
  }
  if (!session.data) {
    try {
      await loadSession();
    } catch (error) {
      if (seq !== renderSeq) return;
      if (error instanceof ApiError && error.status === 401) {
        navigate(`/admin/login?returnTo=${encodeURIComponent(path)}`, { replaceState: true });
        return;
      }
      root.removeAttribute('aria-busy');
      const retry = button('Try again', { variant: 'secondary' });
      retry.addEventListener('click', () => render());
      replace(root, h('main', { id: 'admin-main', class: 'admin-public' }, h('div', { class: 'login-card' },
        h('h1', { class: 'form-title-sm' }, 'Staff area unavailable'), inlineAlert(error.message), h('div', { class: 'form-actions' }, retry))));
      return;
    }
  }
  if (seq !== renderSeq) return;
  if (!layout) layout = buildLayout();
  layout.expired.hidden = true;
  root.removeAttribute('aria-busy');
  const main = layout.main;
  markNav(route?.nav);
  if (!route) { notFound(main); return; }
  if (route.admin && !isAdmin()) { forbidden(main); document.title = 'No access | Staff | Clarke’s Express'; return; }
  replace(main, h('div', { class: 'admin-loading', role: 'status' }, h('span', { class: 'spinner', 'aria-hidden': 'true' }), h('span', null, 'Loading')));
  const mod = await route.view();
  if (seq !== renderSeq) return;
  const params = path.match(route.pattern).slice(1);
  try {
    cleanup = await mod.default({ main, navigate, params, sessionExpired, forbidden: () => forbidden(main) });
  } catch (error) {
    if (seq !== renderSeq) return;
    if (error instanceof ApiError && error.status === 401) { sessionExpired(); return; }
    if (error instanceof ApiError && error.status === 403) { forbidden(main); return; }
    if (error instanceof ApiError && error.status === 404) { notFound(main); return; }
    const retry = button('Try again', { variant: 'secondary', class: 'btn-small' }, 'refresh');
    retry.addEventListener('click', () => render());
    replace(main, pageHead('Couldn’t load this page'), inlineAlert(error.message || 'Something went wrong.', 'error', h('div', { class: 'form-actions' }, retry)));
  }
  hydrateIcons(main);
  const heading = main.querySelector('h1');
  if (heading) {
    document.title = `${heading.textContent} | Staff | Clarke’s Express`;
    heading.focus({ preventScroll: true });
    announce(heading.textContent);
  }
}

// Same-tab navigation for links marked data-nav.
document.addEventListener('click', event => {
  const a = event.target.closest('a[data-nav]');
  if (!a || event.defaultPrevented || event.button !== 0 || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return;
  const url = new URL(a.href, location.href);
  if (url.origin !== location.origin || !url.pathname.startsWith('/admin')) return;
  event.preventDefault();
  if (url.pathname + url.search !== location.pathname + location.search) navigate(url.pathname + url.search);
  window.scrollTo({ top: 0 });
});
window.addEventListener('popstate', render);

render();
