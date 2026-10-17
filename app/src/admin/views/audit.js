// /admin/audit (Admin): safe action records, newest first, filterable by request.
import { h, icon, replace, uid } from '../../lib/dom.js';
import { get, ApiError } from '../../lib/api.js';
import { pageHead, panel, emptyState, loadingState, pager, showError, when, memberId } from '../core.js';

export default async function audit({ main, sessionExpired }) {
  const members = new Map();
  try { (await get('/admin/team/members', { query: { limit: 100 } })).items.forEach(m => members.set(m.id, m.email)); } catch { /* actor IDs stay generic */ }
  const who = id => (!id ? 'System' : id === memberId() ? 'You' : members.get(id) || 'Staff');
  const reqId = uid('audit-req');
  const actionId = uid('audit-action');
  const reqInput = h('input', { id: reqId, type: 'text', autocomplete: 'off', placeholder: 'Request ID', maxlength: 36, value: new URLSearchParams(location.search).get('requestId') || '' });
  const actionInput = h('input', { id: actionId, type: 'text', autocomplete: 'off', placeholder: 'e.g. request.status_changed', maxlength: 80 });
  const error = h('p', { class: 'field-error', hidden: true });
  const form = h('form', { class: 'inbox-tools', novalidate: true },
    h('div', { class: 'field' }, h('label', { for: reqId }, 'Request ID'), reqInput),
    h('div', { class: 'field' }, h('label', { for: actionId }, 'Action'), actionInput),
    h('div', { class: 'field' }, h('span', { class: 'field-label', 'aria-hidden': 'true' }, ' '), h('button', { type: 'submit', class: 'btn btn-secondary btn-small' }, icon('search', { size: 18 }), h('span', { class: 'btn-label' }, 'Filter'))),
    error);
  const list = h('div');
  let rows = []; let cursor = null;

  async function load(more = false) {
    const requestId = reqInput.value.trim();
    error.hidden = true;
    if (requestId && !/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(requestId)) {
      error.textContent = 'Paste a full request ID (from the request page address).'; error.hidden = false; return;
    }
    if (!more) replace(list, loadingState());
    try {
      const page = await get('/admin/audit', { query: { requestId: requestId || undefined, action: actionInput.value.trim() || undefined, limit: 50, cursor: more ? cursor : undefined } });
      rows = more ? [...rows, ...page.items] : page.items;
      cursor = page.nextCursor;
      if (!rows.length) { replace(list, emptyState('No audit records', 'Try a different filter.')); return; }
      replace(list, h('ol', { class: 'event-list' }, rows.map(r => h('li', null,
        h('div', { class: 'event-head' }, h('strong', null, r.summary || r.action), h('span', { class: 'small muted' }, r.action)),
        h('p', { class: 'small muted' }, `${when(r.at)} · ${who(r.actorId)}`,
          r.fromVersion != null || r.toVersion != null ? ` · version ${r.fromVersion ?? '—'} to ${r.toVersion ?? '—'}` : '',
          r.entityType === 'request' ? [' · ', h('a', { href: `/admin/requests/${encodeURIComponent(r.entityId)}`, 'data-nav': '' }, 'Open request')] : '')))),
      pager(cursor, () => load(true)));
    } catch (e) {
      if (e instanceof ApiError && e.code === 'INVALID_CURSOR') { cursor = null; return load(); }
      showError(list, e, { sessionExpired });
    }
    return undefined;
  }
  form.addEventListener('submit', event => { event.preventDefault(); load(); });
  replace(main, pageHead('Audit', { sub: 'Who changed what and when. Contact details, notes and message bodies are not copied here.' }), panel(null, form), panel(null, list));
  await load();
}
