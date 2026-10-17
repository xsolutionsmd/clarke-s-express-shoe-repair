// /admin/notices (Admin): closure notices per location with start/end in New York time.
// Preview renders the public banner without saving. Expired notices hide automatically.
import { h, icon, replace, button, setBusy, uid } from '../../lib/dom.js';
import { get, post, patch, del, ApiError } from '../../lib/api.js';
import { uuid } from '../../lib/store.js';
import { textField, choiceGroup, setError, focusTarget } from '../../lib/fields.js';
import { formatLongDateTime } from '../../lib/format.js';
import { offsetsFor, instantToLocal, offsetOf, toRfc } from '../../lib/nytime.js';
import { pageHead, panel, badge, showError, inlineAlert, confirmDialog, emptyState, loadingState, pager, getDraft, saveDraft, clearDraft } from '../core.js';

const STATE_LABEL = { active: ['Showing now', 'ready'], scheduled: ['Scheduled', 'wait'], expired: ['Ended', 'muted'] };
const LOC_LABEL = { bel_air: 'Bel Air', dundalk: 'Dundalk' };

function timeField(name, label, value, offset) {
  const f = textField({ name, label, type: 'datetime-local', value, help: 'Eastern Time (New York).', attrs: { step: 60 } });
  const which = h('fieldset', { class: 'field fold-choice', hidden: true },
    h('legend', null, 'This time happens twice on the clock change day. Which one?'),
    h('div', { class: 'segmented' },
      h('label', null, h('input', { type: 'radio', name: `${name}-fold`, value: '-04:00', checked: offset === '-04:00' }), h('span', null, 'First (daylight time)')),
      h('label', null, h('input', { type: 'radio', name: `${name}-fold`, value: '-05:00', checked: offset === '-05:00' }), h('span', null, 'Second (standard time)'))));
  f.wrap.append(which);
  const sync = () => { which.hidden = offsetsFor(f.input.value).length !== 2; };
  f.input.addEventListener('input', sync);
  sync();
  return {
    ...f, which, sync,
    rfc() {
      const options = offsetsFor(f.input.value);
      if (!f.input.value) return { error: 'Choose a date and time.' };
      if (!options.length) return { error: 'That time doesn’t exist on the clock change day. Choose another time.' };
      if (options.length === 1) return { value: toRfc(f.input.value, options[0]) };
      const chosen = which.querySelector('input:checked')?.value;
      return chosen ? { value: toRfc(f.input.value, chosen) } : { error: 'Choose which occurrence of this time you mean.' };
    },
  };
}

export default async function notices({ main, sessionExpired }) {
  const ctx = { sessionExpired };
  const filter = h('select', { id: uid('notice-filter') },
    ['active', 'scheduled', 'expired', 'all'].map(v => h('option', { value: v }, { active: 'Showing now', scheduled: 'Scheduled', expired: 'Ended', all: 'All' }[v])));
  filter.value = 'all';
  const listBox = h('div');
  const formBox = h('div');
  let items = [];
  let cursor = null;

  async function loadList(more = false) {
    if (!more) replace(listBox, loadingState());
    try {
      const page = await get('/admin/notices', { query: { state: filter.value, limit: 25, cursor: more ? cursor : undefined } });
      items = more ? [...items, ...page.items] : page.items;
      cursor = page.nextCursor;
      drawList();
    } catch (error) {
      if (error instanceof ApiError && error.code === 'INVALID_CURSOR') { cursor = null; return loadList(); }
      showError(listBox, error, ctx);
    }
    return undefined;
  }

  function drawList() {
    if (!items.length) { replace(listBox, emptyState('No notices', filter.value === 'active' ? 'Nothing is showing on the website right now.' : '')); return; }
    replace(listBox, h('ul', { class: 'notice-list' }, items.map(n => {
      const [label, tone] = STATE_LABEL[n.state] || [n.state, 'neutral'];
      const edit = button('Edit', { variant: 'secondary', class: 'btn-small' });
      edit.addEventListener('click', () => openForm(n));
      const remove = button('Delete', { variant: 'quiet', class: 'btn-small' });
      remove.addEventListener('click', async () => {
        const ok = await confirmDialog({ title: 'Delete this notice?', body: 'It disappears from the website immediately.', confirmLabel: 'Delete notice', danger: true });
        if (!ok) return;
        setBusy(remove, true);
        try { await del(`/admin/notices/${encodeURIComponent(n.id)}`, { expectedVersion: n.version }); await loadList(); } catch (error) { setBusy(remove, false); showError(listBox, error, ctx, { onReload: () => loadList() }); }
      });
      return h('li', { class: 'notice-item' },
        h('div', { class: 'notice-item-head' }, badge(label, tone), h('span', { class: 'small muted' }, n.locations.map(l => LOC_LABEL[l]).join(' and '))),
        h('p', null, h('strong', null, n.message), n.reopenText ? ` ${n.reopenText}` : ''),
        h('p', { class: 'small muted' }, `${formatLongDateTime(n.startsAt)} until ${formatLongDateTime(n.endsAt)}`),
        h('div', { class: 'loc-actions' }, edit, remove));
    })), pager(cursor, () => loadList(true)));
  }

  function openForm(existing) {
    const draftKey = existing ? `notice:${existing.id}` : 'notice:new';
    const saved = getDraft(draftKey)?.fields;
    const v = saved || (existing ? {
      locations: existing.locations, message: existing.message, reopenText: existing.reopenText || '',
      start: instantToLocal(existing.startsAt), startOffset: offsetOf(existing.startsAt),
      end: instantToLocal(existing.endsAt), endOffset: offsetOf(existing.endsAt),
    } : { locations: ['bel_air'], message: '', reopenText: '', start: '', end: '' });
    const locs = choiceGroup({ name: 'noticeLocations', legend: 'Show at', type: 'checkbox', value: v.locations, options: [['bel_air', 'Bel Air'], ['dundalk', 'Dundalk']] });
    const message = textField({ name: 'message', label: 'Notice', multiline: true, value: v.message, help: 'Up to 280 characters, e.g. “Closed today for snow.”', attrs: { rows: 2, maxlength: 280 } });
    const reopen = textField({ name: 'reopenText', label: 'Reopening note', optional: true, value: v.reopenText, help: 'Up to 160 characters, e.g. “Reopening Wednesday at 10 am.” This doesn’t change the hours.', attrs: { maxlength: 160 } });
    const start = timeField('startsAt', 'Starts', v.start, v.startOffset);
    const end = timeField('endsAt', 'Ends', v.end, v.endOffset);
    const preview = h('div', { class: 'notice-preview', 'aria-live': 'polite' });
    const slot = h('div', { class: 'form-alert-slot' });
    const save = h('button', { type: 'submit', class: 'btn btn-primary btn-small' }, h('span', { class: 'btn-label' }, existing ? 'Save changes' : 'Publish notice'));
    const previewBtn = button('Preview banner', { variant: 'secondary', class: 'btn-small' });
    const cancel = button('Cancel', { variant: 'quiet', class: 'btn-small' });
    const form = h('form', { class: 'stack', novalidate: true },
      saved ? inlineAlert('Restored your unsaved notice.', 'info') : null,
      locs.wrap, message.wrap, reopen.wrap, h('div', { class: 'grid-2' }, start.wrap, end.wrap), preview, slot,
      h('div', { class: 'form-actions' }, save, previewBtn, cancel));
    const fields = () => ({
      locations: locs.inputs.filter(i => i.checked).map(i => i.value), message: message.input.value, reopenText: reopen.input.value,
      start: start.input.value, startOffset: start.which.querySelector('input:checked')?.value, end: end.input.value, endOffset: end.which.querySelector('input:checked')?.value,
    });
    form.addEventListener('input', () => { const d = getDraft(draftKey); saveDraft(draftKey, { fields: fields(), baseVersion: d?.baseVersion ?? existing?.version, key: d?.key, payload: d?.payload }); });
    form.addEventListener('change', () => { const d = getDraft(draftKey); saveDraft(draftKey, { fields: fields(), baseVersion: d?.baseVersion ?? existing?.version, key: d?.key, payload: d?.payload }); });

    const build = () => {
      [locs.wrap, message.input, reopen.input, start.input, end.input].forEach(t => setError(t, null));
      const errors = [];
      const fail = (t, m) => { setError(t, m); errors.push(t); };
      const f = fields();
      if (!f.locations.length) fail(locs.wrap, 'Choose at least one location.');
      if (!f.message.trim()) fail(message.input, 'Write the notice.');
      const s = start.rfc(); const e = end.rfc();
      if (s.error) fail(start.input, s.error);
      if (e.error) fail(end.input, e.error);
      if (s.value && e.value && Date.parse(e.value) <= Date.parse(s.value)) fail(end.input, 'The end must be after the start.');
      if (errors.length) { focusTarget(errors[0]); return null; }
      return { locations: f.locations, message: f.message.trim(), reopenText: f.reopenText.trim() || null, startsAt: s.value, endsAt: e.value };
    };
    const fieldErrors = error => {
      const map = { locations: locs.wrap, message: message.input, reopenText: reopen.input, startsAt: start.input, endsAt: end.input };
      let first = null;
      for (const [k, m] of Object.entries(error.fields || {})) if (map[k]) { setError(map[k], m); first ??= map[k]; }
      if (first) focusTarget(first);
      return Boolean(first);
    };

    previewBtn.addEventListener('click', async () => {
      const body = build();
      if (!body) return;
      setBusy(previewBtn, true);
      try {
        const p = await post('/admin/notices/preview', body);
        replace(preview, h('p', { class: 'label-caps' }, 'Preview'),
          h('div', { class: 'notice-band notice-band-preview' }, h('div', { class: 'notice-inner' }, h('p', null, icon('alert', { size: 18 }),
            h('span', null, h('strong', null, `${p.locationIds.map(l => LOC_LABEL[l]).join(' and ')}: `), p.banner.message, p.banner.reopenText ? ` ${p.banner.reopenText}` : '')))),
          h('p', { class: 'small muted' }, `${formatLongDateTime(p.startsAt)} until ${formatLongDateTime(p.endsAt)}`,
            p.replacesActiveNoticeIds?.length ? '. This will show instead of the current notice for that location.' : ''));
      } catch (error) {
        if (!(error instanceof ApiError && error.status === 422 && fieldErrors(error))) showError(slot, error, ctx);
      } finally { setBusy(previewBtn, false); }
    });
    cancel.addEventListener('click', () => { clearDraft(draftKey); replace(formBox, newButton()); });
    form.addEventListener('submit', async event => {
      event.preventDefault();
      replace(slot);
      const body = build();
      if (!body) return;
      const d = getDraft(draftKey) || {};
      const payload = existing ? { expectedVersion: d.baseVersion ?? existing.version, ...body } : body;
      const text = JSON.stringify(payload);
      const key = d.key && d.payload === text ? d.key : uuid();
      saveDraft(draftKey, { fields: fields(), baseVersion: d.baseVersion ?? existing?.version, key, payload: text });
      setBusy(save, true, 'Saving');
      try {
        if (existing) await patch(`/admin/notices/${encodeURIComponent(existing.id)}`, payload, { idempotencyKey: key });
        else await post('/admin/notices', payload, { idempotencyKey: key });
        clearDraft(draftKey);
        replace(formBox, newButton(), inlineAlert(existing ? 'Notice updated.' : 'Notice saved. It shows on the website from its start time.', 'ok'));
        await loadList();
      } catch (error) {
        setBusy(save, false);
        if (error instanceof ApiError && (error.status === 422) && fieldErrors(error)) return;
        if (error instanceof ApiError && error.code === 'INVALID_LOCAL_TIME') { replace(slot, inlineAlert(error.message)); return; }
        showError(slot, error, ctx, { onReload: async () => {
          const fresh = await get(`/admin/notices/${encodeURIComponent(existing.id)}`);
          const cur = getDraft(draftKey);
          saveDraft(draftKey, { ...cur, baseVersion: fresh.version, key: null, payload: null });
          replace(slot, inlineAlert(`Latest version: “${fresh.message}”, ${formatLongDateTime(fresh.startsAt)} until ${formatLongDateTime(fresh.endsAt)}. Your edits are kept; save again to apply them.`, 'info'));
          await loadList();
        } });
      }
    });
    replace(formBox, panel(existing ? 'Edit notice' : 'New notice', form));
    form.querySelector('input')?.focus();
  }

  function newButton() {
    const b = button('New notice', { variant: 'primary', class: 'btn-small' }, 'plus');
    b.addEventListener('click', () => openForm(null));
    return b;
  }

  filter.addEventListener('change', () => loadList());
  replace(formBox, newButton());
  if (getDraft('notice:new')) openForm(null);
  replace(main,
    pageHead('Notices', { sub: 'Closures and holiday notices. The newest active notice for a location shows on the website, and it disappears when it ends.' }),
    formBox,
    panel('All notices', h('div', { class: 'field inline-field' }, h('label', { for: filter.id }, 'Show'), h('div', { class: 'select-wrap' }, filter, icon('chevron-down', { size: 18 }))), listBox));
  await loadList();
}
