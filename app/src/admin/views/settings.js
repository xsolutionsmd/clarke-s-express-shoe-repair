// /admin/settings (Admin): intake pause, alert addresses, delivery switch, staff-only
// response expectation and retention (reductions previewed, confirmed and delayed 24h).
import { h, icon, replace, button, setBusy } from '../../lib/dom.js';
import { get, post, patch, ApiError } from '../../lib/api.js';
import { uuid } from '../../lib/store.js';
import { textField, selectField, setError, focusTarget } from '../../lib/fields.js';
import { formatLongDateTime } from '../../lib/format.js';
import { pageHead, panel, showError, inlineAlert, getDraft, saveDraft, clearDraft, when, badge, draftComparison } from '../core.js';

const KEY = 'settings';

export default async function settings({ main, sessionExpired }) {
  const ctx = { sessionExpired };
  let data = await get('/admin/settings');
  const saved = getDraft(KEY);
  const v = saved?.fields || {
    intakeAccepting: data.intakeAccepting, intakePauseMessage: data.intakePauseMessage || '', notificationEmails: data.notificationEmails || [],
    emailDeliveryEnabled: data.emailDeliveryEnabled, responseExpectation: data.responseExpectation || '',
    photoRetentionDays: String(data.photoRetentionDays), closedLinkDays: String(data.closedLinkDays),
  };

  const accepting = h('input', { type: 'checkbox', id: 'set-accepting', checked: v.intakeAccepting });
  const pauseMsg = textField({ name: 'intakePauseMessage', label: 'Message while paused', multiline: true, value: v.intakePauseMessage, attrs: { rows: 2, maxlength: 280 },
    help: 'Shown instead of the form, with both shops’ call and text buttons. 1 to 280 characters.' });
  const emailsBox = h('div', { class: 'stack' });
  const emailInputs = [];
  const addEmail = (value = '') => {
    if (emailInputs.length >= 5) return;
    const f = textField({ name: `notify-${emailInputs.length}`, label: `Alert address`, type: 'email', value, attrs: { autocomplete: 'off', maxlength: 254 } });
    const rm = h('button', { type: 'button', class: 'icon-button', 'aria-label': 'Remove this address' }, icon('close', { size: 18 }));
    const row = h('div', { class: 'email-row' }, f.wrap, rm);
    rm.addEventListener('click', () => { emailInputs.splice(emailInputs.indexOf(f.input), 1); row.remove(); persist(); syncEmails(); });
    emailInputs.push(f.input);
    emailsBox.append(row);
    syncEmails();
    return f.input;
  };
  const addBtn = button('Add address', { variant: 'secondary', class: 'btn-small' }, 'plus');
  addBtn.addEventListener('click', () => { addEmail('')?.focus(); persist(); });
  const emptyWarn = h('div');
  const syncEmails = () => {
    addBtn.hidden = emailInputs.length >= 5;
    replace(emptyWarn, emailInputs.every(i => !i.value.trim()) ? inlineAlert('No alert addresses: staff won’t get emails about new requests. Requests are still saved.', 'info') : null);
  };
  (v.notificationEmails.length ? v.notificationEmails : []).forEach(e => addEmail(e));

  const delivery = h('input', { type: 'checkbox', id: 'set-delivery', checked: v.emailDeliveryEnabled });
  const expectation = textField({ name: 'responseExpectation', label: 'Response target (staff only)', optional: true, value: v.responseExpectation, attrs: { maxlength: 300 },
    help: 'For planning only. It is never shown to customers.' });
  const retentionAction = selectField({ name: 'retentionAction', label: 'Retention change',
    options: [['preserve', 'Keep the current and scheduled policy'], ['change', 'Set or replace the retention policy'], ['cancel', 'Cancel the scheduled change']], value: v.retentionAction || 'preserve' });
  const pendingSlot = h('div');
  function renderPending() {
    replace(pendingSlot, h('p', { class: 'small muted' }, `Active policy: photos ${data.photoRetentionDays} days; status links ${data.closedLinkDays} days.`),
      data.pendingRetention ? inlineAlert(`Scheduled change: photos ${data.pendingRetention.photoRetentionDays} days, links ${data.pendingRetention.closedLinkDays} days, from ${formatLongDateTime(data.pendingRetention.effectiveAt)}.`, 'info') : h('p', { class: 'small muted' }, 'No scheduled retention change.'));
  }
  const photoDays = textField({ name: 'photoRetentionDays', label: 'Delete photos after closing, days', type: 'number', value: v.photoRetentionDays, attrs: { min: 1, max: 730, step: 1, inputmode: 'numeric' } });
  const linkDays = textField({ name: 'closedLinkDays', label: 'Status links stop working after closing, days', type: 'number', value: v.closedLinkDays, attrs: { min: 1, max: 365, step: 1, inputmode: 'numeric' } });
  const retentionPreview = h('div');
  const confirmReduce = h('input', { type: 'checkbox', id: 'set-confirm-reduce' });
  const confirmWrap = h('label', { class: 'check-inline', for: 'set-confirm-reduce', hidden: true }, confirmReduce, ' I understand the shorter periods take effect in 24 hours and can’t be undone for items deleted after that.');
  const previewBtn = button('Preview impact', { variant: 'secondary', class: 'btn-small' });
  const slot = h('div', { class: 'form-alert-slot' });
  const submit = h('button', { type: 'submit', class: 'btn btn-primary btn-small' }, h('span', { class: 'btn-label' }, 'Save settings'));

  const reducing = () => retentionAction.input.value === 'change' && (Number(photoDays.input.value) < data.photoRetentionDays || Number(linkDays.input.value) < data.closedLinkDays);
  const syncRetention = () => {
    const change = retentionAction.input.value === 'change';
    photoDays.input.disabled = !change; linkDays.input.disabled = !change; previewBtn.disabled = !change;
    confirmWrap.hidden = !reducing(); if (!reducing()) confirmReduce.checked = false;
  };
  const syncPause = () => { pauseMsg.wrap.hidden = accepting.checked; };
  const fields = () => ({
    retentionAction: retentionAction.input.value, intakeAccepting: accepting.checked, intakePauseMessage: pauseMsg.input.value, notificationEmails: emailInputs.map(i => i.value),
    emailDeliveryEnabled: delivery.checked, responseExpectation: expectation.input.value, photoRetentionDays: photoDays.input.value, closedLinkDays: linkDays.input.value,
  });
  const persist = () => { const d = getDraft(KEY); saveDraft(KEY, { fields: fields(), baseVersion: d?.baseVersion ?? data.version, key: d?.key, payload: d?.payload }); };

  previewBtn.addEventListener('click', async () => {
    setBusy(previewBtn, true);
    try {
      const p = await post('/admin/settings/retention-preview', { photoRetentionDays: Number(photoDays.input.value), closedLinkDays: Number(linkDays.input.value) });
      replace(retentionPreview, inlineAlert(`${p.photosEligibleForDeletion} photo${p.photosEligibleForDeletion === 1 ? '' : 's'} would be deleted and ${p.linksBecomingUnavailable} status link${p.linksBecomingUnavailable === 1 ? '' : 's'} would stop working, from ${formatLongDateTime(p.effectiveAt)}. Counts can change before then.`, 'info'));
    } catch (error) {
      if (error instanceof ApiError && error.status === 422) {
        if (error.fields.photoRetentionDays) setError(photoDays.input, error.fields.photoRetentionDays);
        if (error.fields.closedLinkDays) setError(linkDays.input, error.fields.closedLinkDays);
      } else showError(retentionPreview, error, ctx);
    } finally { setBusy(previewBtn, false); }
  });

  const form = h('form', { class: 'stack', novalidate: true },
    saved ? inlineAlert(saved.baseVersion !== data.version ? 'Restored your unsaved settings. Someone saved settings since; review and save again.' : 'Restored your unsaved settings.', 'info') : null,
    panel('Online requests',
      h('label', { class: 'check-inline', for: 'set-accepting' }, accepting, ' Accept new online repair requests'),
      pauseMsg.wrap,
      h('p', { class: 'small muted' }, 'Pausing affects only new online requests. Existing status links, staff tickets and replies keep working.')),
    panel('Staff alerts and email',
      h('p', { class: 'small muted' }, 'Each address gets a separate alert for every new request and customer reply. Up to five.'),
      emailsBox, addBtn, emptyWarn,
      h('label', { class: 'check-inline', for: 'set-delivery' }, delivery, ' Send emails through the connected Gmail sender'),
      data.demoMode ? h('p', { class: 'small muted' }, badge('Demo mode', 'demo'), ' Only addresses on the private test list receive email. Everything else is kept as a preview in the email log.') : null),
    panel('Planning', expectation.wrap),
    panel('Retention',
      pendingSlot, retentionAction.wrap,
      h('div', { class: 'grid-2' }, photoDays.wrap, linkDays.wrap), h('div', { class: 'form-actions' }, previewBtn), retentionPreview, confirmWrap),
    slot,
    h('div', { class: 'form-actions' }, submit, h('span', { class: 'small muted' }, `Last saved ${when(data.updatedAt)}`)));

  form.addEventListener('input', event => { persist(); syncRetention(); syncPause(); syncEmails(); if (event.target.getAttribute?.('aria-invalid')) setError(event.target, null); });
  form.addEventListener('change', () => { persist(); syncRetention(); syncPause(); });
  syncRetention(); syncPause();

  form.addEventListener('submit', async event => {
    event.preventDefault();
    replace(slot);
    if (getDraft(KEY) && getDraft(KEY).baseVersion !== data.version) { compare(); return; }
    const f = fields();
    const errors = [];
    const fail = (t, m) => { setError(t, m); errors.push(t); };
    [pauseMsg.input, photoDays.input, linkDays.input, ...emailInputs].forEach(i => setError(i, null));
    const emails = [];
    emailInputs.forEach(i => {
      const value = i.value.trim();
      if (!value) return;
      if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(value)) fail(i, 'Enter a valid email address.');
      else if (emails.some(e => e.toLowerCase() === value.toLowerCase())) fail(i, 'This address is already listed.');
      else emails.push(value);
    });
    if (!f.intakeAccepting && !f.intakePauseMessage.trim()) fail(pauseMsg.input, 'Write the message customers see while requests are paused.');
    const pd = Number(f.photoRetentionDays); const ld = Number(f.closedLinkDays);
    if (!Number.isInteger(pd) || pd < 1 || pd > 730) fail(photoDays.input, 'Use a whole number from 1 to 730.');
    if (!Number.isInteger(ld) || ld < 1 || ld > 365) fail(linkDays.input, 'Use a whole number from 1 to 365.');
    if (reducing() && !confirmReduce.checked) fail(confirmReduce, 'Confirm the shorter retention periods first.');
    if (errors.length) { if (errors[0] === confirmReduce) { replace(slot, inlineAlert('Confirm the shorter retention periods before saving.')); confirmReduce.focus(); } else focusTarget(errors[0]); return; }
    const d = getDraft(KEY) || {};
    const body = {
      expectedVersion: d.baseVersion ?? data.version, intakeAccepting: f.intakeAccepting,
      intakePauseMessage: f.intakeAccepting ? (f.intakePauseMessage.trim() || null) : f.intakePauseMessage.trim(),
      notificationEmails: emails, emailDeliveryEnabled: f.emailDeliveryEnabled, responseExpectation: f.responseExpectation.trim() || null,
    };
    if (f.retentionAction === 'change') Object.assign(body, { photoRetentionDays: pd, closedLinkDays: ld });
    if (f.retentionAction === 'cancel') Object.assign(body, { photoRetentionDays: data.photoRetentionDays, closedLinkDays: data.closedLinkDays });
    if (reducing()) body.confirmRetentionReduction = true;
    const text = JSON.stringify(body);
    const key = d.key && d.payload === text ? d.key : uuid();
    saveDraft(KEY, { fields: f, baseVersion: body.expectedVersion, key, payload: text });
    setBusy(submit, true, 'Saving');
    try {
      const result = await patch('/admin/settings', body, { idempotencyKey: key });
      clearDraft(KEY);
      data = await get('/admin/settings');
      replace(slot, inlineAlert(result.retentionEffectiveAt ? `Settings saved. Shorter retention takes effect ${formatLongDateTime(result.retentionEffectiveAt)}.` : 'Settings saved.', 'ok'));
      confirmReduce.checked = false;
      retentionAction.input.value = 'preserve';
      photoDays.input.value = String(data.photoRetentionDays);
      linkDays.input.value = String(data.closedLinkDays);
      renderPending();
      replace(retentionPreview);
      syncRetention();
    } catch (error) {
      if (error instanceof ApiError && error.code === 'SENDER_DISCONNECTED') {
        replace(slot, inlineAlert('Connect a Gmail sender before turning on email delivery.', 'error', h('a', { href: '/admin/emails', 'data-nav': '' }, 'Go to Emails')));
      } else if (error instanceof ApiError && error.status === 422 && Object.keys(error.fields).length) {
        const map = { intakePauseMessage: pauseMsg.input, photoRetentionDays: photoDays.input, closedLinkDays: linkDays.input, responseExpectation: expectation.input };
        let first = null;
        for (const [k, m] of Object.entries(error.fields)) {
          const idx = /^notificationEmails\.(\d+)$/.exec(k);
          const t = map[k] || (idx ? emailInputs[Number(idx[1])] : null);
          if (t) { setError(t, m); first ??= t; }
        }
        replace(slot, inlineAlert(error.message || 'Check the highlighted fields.'));
        if (first) focusTarget(first);
      } else {
        showError(slot, error, ctx, { onReload: async () => {
          data = await get('/admin/settings');
          renderPending();
          compare();
        } });
      }
    } finally { setBusy(submit, false); }
  });

  function compare() {
    const f = fields();
    replace(slot, draftComparison({ rows: [
      ['Accepting requests', data.intakeAccepting, f.intakeAccepting],
      ['Pause message', data.intakePauseMessage, f.intakePauseMessage],
      ['Alert addresses', data.notificationEmails, f.notificationEmails],
      ['Email delivery', data.emailDeliveryEnabled, f.emailDeliveryEnabled],
      ['Response target', data.responseExpectation, f.responseExpectation],
      ['Photo retention (days)', data.photoRetentionDays, f.retentionAction === 'change' ? f.photoRetentionDays : 'Keep active policy'],
      ['Link retention (days)', data.closedLinkDays, f.retentionAction === 'change' ? f.closedLinkDays : 'Keep active policy'],
      ['Scheduled policy', data.pendingRetention ? `Photos ${data.pendingRetention.photoRetentionDays}, links ${data.pendingRetention.closedLinkDays}, from ${formatLongDateTime(data.pendingRetention.effectiveAt)}` : 'None', retentionAction.input.selectedOptions[0].textContent],
    ], onReapply: () => {
      saveDraft(KEY, { fields: fields(), baseVersion: data.version, key: null, payload: null });
      confirmReduce.checked = false;
      syncRetention();
      replace(slot, inlineAlert('Draft reapplied. Review your settings and save when ready.', 'info'));
    } }));
  }
  renderPending();
  if (saved && saved.baseVersion !== data.version) compare();
  replace(main, pageHead('Settings', { sub: 'Changes apply to this environment only. Sign-in, the sender connection and test lists are managed elsewhere.' }), form);
}
