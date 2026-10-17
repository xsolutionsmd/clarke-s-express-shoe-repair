// Staff session, member-scoped draft storage and shared admin UI pieces.
import { get, post, bootstrap, setStaffCsrf, useAnonymousCsrf, ApiError } from '../lib/api.js';
import { h, icon, replace, button, setBusy } from '../lib/dom.js';
import { read, write, remove, keys, HOUR } from '../lib/store.js';
import { STATUS } from '../lib/constants.js';
import { formatDateTime } from '../lib/format.js';

// ---------- session ----------
export const session = { data: null };

export async function loadSession() {
  const data = await get('/admin/session');
  session.data = data;
  setStaffCsrf(data.csrfToken, async () => {
    const fresh = await get('/admin/session');
    session.data = fresh;
    return fresh.csrfToken;
  });
  initDrafts(data.member.id);
  return data;
}

export const isAdmin = () => session.data?.member?.role === 'admin';
export const memberId = () => session.data?.member?.id || null;

export function safeReturnTo(path) {
  if (typeof path !== 'string' || path.length > 256) return '/admin/requests';
  if (!/^\/admin\/[A-Za-z0-9/_-]*$/.test(path) || path.startsWith('//') || path.startsWith('/admin/login') || path.startsWith('/admin/invite')) return '/admin/requests';
  return path;
}

export async function startGoogle({ returnTo, inviteToken = null }) {
  useAnonymousCsrf();
  await bootstrap({ force: true });
  const data = await post('/auth/google/start', { returnTo: safeReturnTo(returnTo), inviteToken });
  redirectToGoogle(data.authorizationUrl);
}

export function redirectToGoogle(url) {
  const target = new URL(url);
  if (target.protocol !== 'https:' || target.hostname !== 'accounts.google.com') throw new ApiError({ status: 0, code: 'BAD_REDIRECT', message: 'Google sign-in could not start. Try again.' });
  window.location.assign(target.href);
}

export async function logout() {
  try { await post('/admin/logout', {}); } catch { /* signed out locally regardless */ }
  clearAllStaff();
  session.data = null;
  useAnonymousCsrf();
}

// ---------- staff drafts (sessionStorage, keyed by member, 12h) ----------
const STAFF_TTL = 12 * HOUR;

export function initDrafts(id) {
  const last = read('staff-last', 1);
  if (last && last !== id) clearAllStaff();
  write('staff-last', 1, id, STAFF_TTL);
}

export function clearAllStaff() {
  for (const k of keys('staff')) remove(k);
}

const draftsKey = () => `staff.${memberId()}`;
function allDrafts() { return memberId() ? read(draftsKey(), 1) || {} : {}; }

export function getDraft(key) { return allDrafts()[key] || null; }
export function saveDraft(key, value) {
  if (!memberId()) return;
  const all = allDrafts();
  all[key] = { ...all[key], ...value, savedAt: Date.now() };
  write(draftsKey(), 1, all, STAFF_TTL);
}
export function clearDraft(key) {
  const all = allDrafts();
  delete all[key];
  write(draftsKey(), 1, all, STAFF_TTL);
}
// After our own successful change, drafts based on the version we just replaced are
// still based on everything except our own edit, so they move forward with it.
export function bumpDrafts(prefix, fromVersion, toVersion) {
  const all = allDrafts();
  for (const [k, v] of Object.entries(all)) if (k.startsWith(prefix) && v.baseVersion === fromVersion) v.baseVersion = toVersion;
  write(draftsKey(), 1, all, STAFF_TTL);
}
export function viewState(name, value) {
  const key = `staff.${memberId()}.view.${name}`;
  if (value === undefined) return read(key, 1);
  write(key, 1, value, STAFF_TTL);
  return value;
}

// ---------- UI helpers ----------
export function pageHead(title, { sub, actions, back } = {}) {
  return h('header', { class: 'page-head' },
    back ? h('a', { class: 'back-link', href: back.href, 'data-nav': '' }, icon('arrow-left', { size: 18 }), back.label) : null,
    h('div', { class: 'page-head-row' },
      h('div', { class: 'page-head-text' }, h('h1', { class: 'page-title', tabindex: '-1' }, title), sub ? h('p', { class: 'page-sub' }, sub) : null),
      actions ? h('div', { class: 'page-actions' }, actions) : null));
}

export function badge(text, tone = 'neutral') {
  return h('span', { class: ['badge', `badge-${tone}`] }, text);
}

const STATUS_TONE = {
  new: 'new', reviewing: 'new', estimate_sent: 'wait', needs_visit: 'wait', awaiting_dropoff: 'wait',
  in_shop: 'shop', in_progress: 'shop', ready: 'ready', picked_up: 'closed', cancelled: 'closed', not_repairable: 'closed',
};
export function statusBadge(status) { return badge(STATUS[status] || status, STATUS_TONE[status] || 'neutral'); }

export function deliveryBadges(delivery, { link } = {}) {
  if (!delivery) return null;
  const parts = [];
  if (delivery.failed) parts.push(badge(`${delivery.failed} email${delivery.failed === 1 ? '' : 's'} failed`, 'danger'));
  if (delivery.uncertain) parts.push(badge(`${delivery.uncertain} uncertain`, 'warn'));
  if (delivery.pending) parts.push(badge(`${delivery.pending} sending`, 'neutral'));
  if (delivery.previewOnly) parts.push(badge(`${delivery.previewOnly} preview only`, 'neutral'));
  if (!parts.length) return null;
  return h('span', { class: 'badge-row' }, parts, link && isAdmin() ? h('a', { href: link, 'data-nav': '', class: 'small' }, 'Email log') : null);
}

export function panel(title, ...children) {
  return h('section', { class: 'panel' }, title ? h('h2', { class: 'panel-title' }, title) : null, ...children);
}

export function emptyState(title, text, action) {
  return h('div', { class: 'empty' }, h('p', { class: 'empty-title' }, title), text ? h('p', { class: 'muted' }, text) : null, action || null);
}

export function loadingState(text = 'Loading') {
  return h('div', { class: 'admin-loading', role: 'status' }, h('span', { class: 'spinner', 'aria-hidden': 'true' }), h('span', null, text));
}

export function inlineAlert(message, tone = 'error', extra) {
  return h('div', { class: ['form-alert', tone === 'ok' ? 'is-ok' : tone === 'info' ? 'is-info' : null], role: tone === 'error' ? 'alert' : 'status', tabindex: '-1' },
    icon(tone === 'ok' ? 'check' : 'alert', { size: 20 }),
    h('div', { class: 'form-alert-body' }, h('p', null, message), extra || null));
}

export function when(value) { return value ? formatDateTime(value) : ''; }

// Native <dialog> confirmation; resolves true only on the explicit confirm button.
export function confirmDialog({ title, body, confirmLabel = 'Confirm', danger = false, extra }) {
  return new Promise(resolve => {
    const ok = button(confirmLabel, { variant: danger ? 'danger' : 'primary' });
    const cancel = button('Cancel', { variant: 'secondary' });
    const dialog = h('dialog', { class: 'confirm-dialog', 'aria-labelledby': 'confirm-title' },
      h('h2', { id: 'confirm-title', class: 'panel-title' }, title),
      body ? h('p', null, body) : null,
      extra || null,
      h('div', { class: 'form-actions' }, ok, cancel));
    const opener = document.activeElement;
    const done = value => { dialog.close(); dialog.remove(); opener?.focus?.(); resolve(value); };
    ok.addEventListener('click', () => done(true));
    cancel.addEventListener('click', () => done(false));
    dialog.addEventListener('cancel', event => { event.preventDefault(); done(false); });
    document.body.append(dialog);
    dialog.showModal();
    cancel.focus();
  });
}

// Standard error rendering for a form slot; returns true when handled.
export function showError(slot, error, ctx, { onReload } = {}) {
  if (!(error instanceof ApiError)) { replace(slot, inlineAlert('Something went wrong in the page. Your text is kept; try again.')); return true; }
  if (error.status === 401) { ctx.sessionExpired(); replace(slot, inlineAlert('Your session ended. Sign in again; your unsaved text is kept.', 'info')); return true; }
  if (error.code === 'VERSION_CONFLICT') {
    const reload = button('Load latest details', { variant: 'secondary', class: 'btn-small' }, 'refresh');
    reload.addEventListener('click', async () => { setBusy(reload, true, 'Loading'); await onReload?.(error); });
    replace(slot, inlineAlert(error.message || 'Updated by someone else. Reload the latest details; your draft is kept.', 'error',
      h('div', { class: 'form-actions' }, reload)));
    slot.firstChild?.focus();
    return true;
  }
  if (error.status === 403 && error.code === 'FORBIDDEN') { replace(slot, inlineAlert('Your role doesn’t allow this action. Ask an Admin.')); return true; }
  replace(slot, inlineAlert(error.code === 'RATE_LIMITED' ? 'Too many changes in a short time. Wait a moment and try again.' : error.message));
  slot.firstChild?.focus();
  return true;
}

export function pager(nextCursor, onMore) {
  if (!nextCursor) return null;
  const more = button('Load more', { variant: 'secondary', class: 'btn-small' });
  more.addEventListener('click', async () => { setBusy(more, true, 'Loading'); try { await onMore(nextCursor); } finally { if (more.isConnected) setBusy(more, false); } });
  return h('div', { class: 'pager' }, more);
}

export async function copyText(text, btn) {
  try {
    await navigator.clipboard.writeText(text);
    if (btn) { const l = btn.querySelector('.btn-label'); const old = l.textContent; l.textContent = 'Copied'; window.setTimeout(() => { l.textContent = old; }, 1600); }
  } catch {
    window.prompt('Copy this text:', text);
  }
}
