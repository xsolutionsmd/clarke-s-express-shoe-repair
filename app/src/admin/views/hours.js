// /admin/locations (Admin): Bel Air weekly hours. Dundalk never has hours; it is always
// by appointment. One interval per day; closing must be after opening.
import { h, replace, setBusy, uid } from '../../lib/dom.js';
import { get, put, ApiError } from '../../lib/api.js';
import { DAY_NAMES, hoursRows } from '../../lib/format.js';
import { watchLocations, findLocation, stateBadge, noticeView } from '../../lib/locations.js';
import { pageHead, panel, showError, inlineAlert, getDraft, saveDraft, clearDraft, when } from '../core.js';
import { uuid } from '../../lib/store.js';

const ORDER = [1, 2, 3, 4, 5, 6, 0];

export default async function hours({ main, sessionExpired }) {
  let data = await get('/admin/hours');
  const saved = getDraft('hours');
  const days = saved?.fields?.days || data.days;
  const slot = h('div', { class: 'form-alert-slot' });
  const rows = new Map();
  const restored = saved?.fields ? inlineAlert(saved.baseVersion !== data.version ? 'Restored your unsaved hours. They were changed by someone else since; review and save again.' : 'Restored your unsaved hours.', 'info') : null;
  if (saved && saved.baseVersion !== data.version) saveDraft('hours', { ...saved, baseVersion: data.version, key: null });

  const table = h('div', { class: 'hours-editor', role: 'group', 'aria-label': 'Bel Air weekly hours' }, ORDER.map(index => {
    const day = days[index];
    const id = uid('day');
    const open = h('input', { type: 'checkbox', id: `${id}-open`, checked: Boolean(day) });
    const from = h('input', { type: 'time', id: `${id}-from`, value: day?.open || '09:00', step: 60, 'aria-label': `${DAY_NAMES[index]} opens` });
    const to = h('input', { type: 'time', id: `${id}-to`, value: day?.close || '17:00', step: 60, 'aria-label': `${DAY_NAMES[index]} closes` });
    const error = h('p', { class: 'field-error', id: `${id}-error`, hidden: true });
    const sync = () => { from.disabled = !open.checked; to.disabled = !open.checked; };
    open.addEventListener('change', sync);
    sync();
    rows.set(index, { open, from, to, error });
    return h('div', { class: 'hours-edit-row' },
      h('label', { class: 'check-inline', for: `${id}-open` }, open, ` ${DAY_NAMES[index]}`),
      h('div', { class: 'hours-times' }, from, h('span', { 'aria-hidden': 'true' }, 'to'), to),
      error);
  }));

  const collect = () => {
    const out = Array(7).fill(null);
    for (const [index, r] of rows) out[index] = r.open.checked ? { open: r.from.value, close: r.to.value } : null;
    return out;
  };
  table.addEventListener('input', () => { const d = getDraft('hours'); saveDraft('hours', { fields: { days: collect() }, baseVersion: d?.baseVersion ?? data.version, key: d?.key }); });
  table.addEventListener('change', () => { const d = getDraft('hours'); saveDraft('hours', { fields: { days: collect() }, baseVersion: d?.baseVersion ?? data.version, key: d?.key }); });

  const submit = h('button', { type: 'submit', class: 'btn btn-primary btn-small' }, h('span', { class: 'btn-label' }, 'Save hours'));
  const form = h('form', { novalidate: true, class: 'stack' }, restored, table, slot, h('div', { class: 'form-actions' }, submit));
  form.addEventListener('submit', async event => {
    event.preventDefault();
    replace(slot);
    let bad = null;
    for (const [index, r] of rows) {
      r.error.hidden = true;
      r.from.removeAttribute('aria-invalid'); r.to.removeAttribute('aria-invalid');
      if (!r.open.checked) continue;
      const msg = !/^\d{2}:\d{2}$/.test(r.from.value) || !/^\d{2}:\d{2}$/.test(r.to.value) ? 'Enter both times.'
        : r.to.value <= r.from.value ? 'Closing time must be after opening time (no overnight hours).' : null;
      if (msg) {
        r.error.textContent = `${DAY_NAMES[index]}: ${msg}`; r.error.hidden = false;
        r.to.setAttribute('aria-invalid', 'true'); r.to.setAttribute('aria-describedby', r.error.id);
        bad ??= r.to;
      }
    }
    if (bad) { bad.focus(); return; }
    const draft = getDraft('hours') || {};
    const body = { expectedVersion: draft.baseVersion ?? data.version, days: collect() };
    const key = draft.key && draft.payload === JSON.stringify(body) ? draft.key : uuid();
    saveDraft('hours', { fields: { days: body.days }, baseVersion: body.expectedVersion, key, payload: JSON.stringify(body) });
    setBusy(submit, true, 'Saving');
    try {
      await put('/admin/hours', body, { idempotencyKey: key });
      clearDraft('hours');
      data = await get('/admin/hours');
      replace(slot, inlineAlert('Hours saved. The website shows them right away.', 'ok'));
      renderSummary();
    } catch (error) {
      if (error instanceof ApiError && error.status === 422 && error.fields) {
        const first = Object.entries(error.fields)[0];
        replace(slot, inlineAlert(first ? first[1] : error.message));
      } else {
        showError(slot, error, { sessionExpired }, { onReload: async () => {
          data = await get('/admin/hours');
          const d = getDraft('hours');
          if (d) saveDraft('hours', { ...d, baseVersion: data.version, key: null });
          renderSummary();
          replace(slot, inlineAlert('Latest hours loaded below. Your edits are still in the form; save again to apply them.', 'info'));
        } });
      }
    } finally { setBusy(submit, false); }
  });

  const summary = h('div');
  const publicState = h('div');
  function renderSummary() {
    const list = hoursRows(data.days);
    replace(summary, h('p', { class: 'small muted' }, `Saved hours (version ${data.version}, ${when(data.updatedAt)}): `,
      list.length ? list.map(r => `${r.days} ${r.text}`).join('; ') : 'closed every day'));
  }
  renderSummary();
  const stop = watchLocations(payload => {
    const bel = findLocation(payload, 'bel_air');
    replace(publicState, h('div', { class: 'stack' },
      h('p', { class: 'label-caps' }, 'Bel Air on the website now'), stateBadge(bel, payload.stale), noticeView(bel.activeNotice),
      h('p', { class: 'label-caps' }, 'Dundalk on the website'), h('p', null, 'Always “By appointment, call or text 443-386-3800”. There are no Dundalk hours to set.')));
  });

  replace(main,
    pageHead('Hours', { sub: 'Bel Air regular weekly hours, Eastern Time. Use Notices for closures and holidays.' }),
    h('div', { class: 'detail-grid' },
      h('div', { class: 'detail-main' }, panel('Bel Air weekly hours', summary, form)),
      h('div', { class: 'detail-side' }, panel('Public view', publicState))));
  return () => stop();
}
