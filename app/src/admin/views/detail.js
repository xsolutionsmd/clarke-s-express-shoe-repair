// /admin/requests/{id}: everything staff need for one request. Forms keep typed text in
// member-scoped sessionStorage with the version they were based on; a 409 never
// auto-retries with a newer version, it loads the latest and waits for a deliberate save.
import { h, icon, replace, button, setBusy, announce } from '../../lib/dom.js';
import { get, post, patch, ApiError } from '../../lib/api.js';
import { uuid, read, remove } from '../../lib/store.js';
import { textField, selectField, choiceGroup, setError } from '../../lib/fields.js';
import { STATUS, STATUS_ORDER, CLOSED, RESPONSE_LABELS, itemLabel, workLabel, locationName } from '../../lib/constants.js';
import { formatDateTime, formatLocalDate, formatPhone, moneyRange, parseCents, bytes, hoursRows } from '../../lib/format.js';
import { watchLocations, findLocation } from '../../lib/locations.js';
import {
  pageHead, statusBadge, deliveryBadges, badge, panel, inlineAlert, showError, confirmDialog, copyText,
  getDraft, saveDraft, clearDraft, bumpDrafts, isAdmin, memberId, when, pager,
} from '../core.js';

const STATUS_CHOICES = Object.entries(STATUS).filter(([s]) => s !== 'estimate_sent' && s !== 'needs_visit');
const OFFER_FROM = new Set(['new', 'reviewing', 'estimate_sent', 'needs_visit']);

export default async function detail({ main, params, sessionExpired }) {
  const id = params[0];
  const base = `/admin/requests/${encodeURIComponent(id)}`;
  const state = { detail: null, contact: null, offers: [], offersCursor: null, notes: [], notesCursor: null, events: [], eventsCursor: null, members: new Map(), locations: null };
  const ctx = { sessionExpired };
  let stopLocations = null;

  // ---------- loading ----------
  async function loadAll() {
    const [detailData, contact, offers, notes, events] = await Promise.all([
      get(base),
      get(`${base}/contact-actions`).catch(() => null),
      get(`${base}/offers`, { query: { limit: 10 } }).catch(() => ({ items: [], nextCursor: null })),
      get(`${base}/notes`, { query: { limit: 25 } }).catch(() => ({ items: [], nextCursor: null })),
      get(`${base}/events`, { query: { limit: 25 } }).catch(() => ({ items: [], nextCursor: null })),
    ]);
    state.detail = detailData;
    state.contact = contact;
    state.offers = offers.items; state.offersCursor = offers.nextCursor;
    state.notes = notes.items; state.notesCursor = notes.nextCursor;
    state.events = events.items; state.eventsCursor = events.nextCursor;
  }
  async function loadMembers() {
    if (!isAdmin()) return;
    try {
      const page = await get('/admin/team/members', { query: { limit: 100 } });
      for (const m of page.items) state.members.set(m.id, m.email);
    } catch { /* names fall back to "Staff" */ }
  }
  const who = actorId => (!actorId ? 'System' : actorId === memberId() ? 'You' : state.members.get(actorId) || 'Staff');

  await Promise.all([loadAll(), loadMembers()]);

  // ---------- draft helpers ----------
  function draft(name) {
    const key = `req:${id}:${name}`;
    return {
      read: () => getDraft(key),
      save(fields) {
        const d = getDraft(key);
        saveDraft(key, { fields, baseVersion: d?.baseVersion ?? state.detail.version, key: d?.key, payload: d?.payload });
      },
      base: () => getDraft(key)?.baseVersion ?? state.detail.version,
      idempotency(payload) {
        const d = getDraft(key) || { fields: {}, baseVersion: state.detail.version };
        const text = JSON.stringify(payload);
        if (!d.key || d.payload !== text) saveDraft(key, { ...d, key: uuid(), payload: text });
        return getDraft(key).key;
      },
      rebase(version) { const d = getDraft(key); if (d) saveDraft(key, { ...d, baseVersion: version, key: null, payload: null }); },
      clear: () => clearDraft(key),
    };
  }
  function afterSuccess(oldVersion, newVersion) {
    if (Number.isInteger(newVersion)) bumpDrafts(`req:${id}:`, oldVersion, newVersion);
  }
  async function reloadLatest(forms) {
    await loadAll();
    for (const f of forms) f.rebase(state.detail.version);
    renderData();
    announce('Latest details loaded. Your text is kept; save again to apply it.');
  }

  // ---------- containers ----------
  const head = h('div');
  const summary = h('div');
  const photosBox = h('div');
  const offerBox = h('div');
  const historyBox = h('div', { class: 'detail-stack' });
  const notesList = h('div');
  const contactBox = h('div', { class: 'stack contact-box' });

  // ---------- status form ----------
  const statusDraft = draft('status');
  const sSaved = statusDraft.read()?.fields || {};
  const statusSelect = selectField({ name: 'status', label: 'Status', options: STATUS_CHOICES, value: sSaved.status || '' , placeholder: 'Choose a status',
    help: 'Estimates and “Please bring it in” are sent from the offer panel.' });
  const pickup = selectField({ name: 'pickupLocation', label: 'Pickup location', options: [['bel_air', 'Bel Air'], ['dundalk', 'Dundalk (by appointment)']], value: sSaved.pickupLocation || state.detail.pickupLocation || state.detail.dropoffLocation });
  const custMsg = textField({ name: 'customerMessage', label: 'Message to the customer', optional: true, multiline: true, value: sSaved.customerMessage || '',
    help: 'Shown on their status page and in the email for this change. Required for “We can’t repair this”.', attrs: { rows: 3, maxlength: 2000 } });
  const reason = textField({ name: 'reason', label: 'Reason (staff only)', multiline: true, value: sSaved.reason || '',
    help: 'Required when moving a request back or reopening it. 10 to 500 characters.', attrs: { rows: 2, maxlength: 500 } });
  const statusSlot = h('div', { class: 'form-alert-slot' });
  const statusRestored = h('div');
  const statusBtn = h('button', { type: 'submit', class: 'btn btn-primary btn-small' }, h('span', { class: 'btn-label' }, 'Update status'));
  const statusForm = h('form', { class: 'stack', novalidate: true }, statusRestored, statusSelect.wrap, pickup.wrap, custMsg.wrap, reason.wrap, statusSlot, h('div', { class: 'form-actions' }, statusBtn));

  const needsReason = target => {
    const current = state.detail.status;
    if (!target || target === current) return false;
    if (CLOSED.has(current) && !CLOSED.has(target)) return true;
    if (current === 'not_repairable' && target !== 'cancelled') return true;
    const a = STATUS_ORDER.indexOf(current);
    const b = STATUS_ORDER.indexOf(target);
    return a !== -1 && b !== -1 && b < a;
  };
  const syncStatusForm = () => {
    const target = statusSelect.input.value;
    pickup.wrap.hidden = target !== 'ready';
    reason.wrap.hidden = !needsReason(target);
  };
  const saveStatusDraft = () => statusDraft.save({ status: statusSelect.input.value, pickupLocation: pickup.input.value, customerMessage: custMsg.input.value, reason: reason.input.value });
  for (const el of [statusSelect.input, pickup.input, custMsg.input, reason.input]) {
    el.addEventListener('input', () => { saveStatusDraft(); syncStatusForm(); setError(el, null); });
    el.addEventListener('change', () => { saveStatusDraft(); syncStatusForm(); });
  }
  statusForm.addEventListener('submit', async event => {
    event.preventDefault();
    replace(statusSlot);
    const target = statusSelect.input.value;
    const message = custMsg.input.value.trim();
    const why = reason.input.value.trim();
    let bad = null;
    if (!target) { setError(statusSelect.input, 'Choose a status.'); bad ??= statusSelect.input; }
    if (target === 'not_repairable' && !message) { setError(custMsg.input, 'Explain to the customer why it can’t be repaired.'); bad ??= custMsg.input; }
    if (needsReason(target) && (why.length < 10 || why.length > 500)) { setError(reason.input, 'Give a reason of 10 to 500 characters.'); bad ??= reason.input; }
    if (bad) { bad.focus(); return; }
    if (target === state.detail.status && !message && (target !== 'ready' || pickup.input.value === state.detail.pickupLocation)) {
      replace(statusSlot, inlineAlert('Nothing to change: the request already has this status.', 'info'));
      return;
    }
    const body = { expectedVersion: statusDraft.base(), status: target };
    if (target === 'ready') body.pickupLocation = pickup.input.value;
    if (message) body.customerMessage = message;
    body.reason = needsReason(target) ? why : null;
    setBusy(statusBtn, true, 'Saving');
    const before = state.detail.version;
    try {
      const result = await patch(base, body, { idempotencyKey: statusDraft.idempotency(body) });
      statusDraft.clear();
      afterSuccess(before, result.version);
      statusSelect.input.value = ''; custMsg.input.value = ''; reason.input.value = '';
      replace(statusRestored);
      await loadAll();
      renderData();
      replace(statusSlot, inlineAlert(`Status changed to “${STATUS[result.status] || result.status}”.`, 'ok'));
    } catch (error) {
      if (error instanceof ApiError && error.status === 422) {
        const map = { status: statusSelect.input, pickupLocation: pickup.input, customerMessage: custMsg.input, reason: reason.input };
        for (const [k, v] of Object.entries(error.fields)) map[k] && setError(map[k], v);
      }
      showError(statusSlot, error, ctx, { onReload: () => reloadLatest([statusDraft]) });
      if (error instanceof ApiError && error.code === 'INVALID_TRANSITION') replace(statusSlot, inlineAlert(error.message || 'That status change isn’t allowed from here.'));
    } finally { setBusy(statusBtn, false); }
  });

  // ---------- offer form ----------
  const offerDraft = draft('offer');
  const oSaved = offerDraft.read()?.fields || {};
  const kind = choiceGroup({ name: 'offerKind', legend: 'Reply with', segmented: true, value: oSaved.kind || 'estimate',
    options: [['estimate', 'Estimate'], ['visit', 'Ask to see it']] });
  const amountMode = choiceGroup({ name: 'amountMode', legend: 'Amount', segmented: true, value: oSaved.amountMode || 'single',
    options: [['single', 'Single amount'], ['range', 'Range']] });
  const minField = textField({ name: 'amountMin', label: 'Amount in dollars', value: oSaved.min || '', attrs: { inputmode: 'decimal', autocomplete: 'off', maxlength: 12 } });
  const maxField = textField({ name: 'amountMax', label: 'Up to, in dollars', value: oSaved.max || '', attrs: { inputmode: 'decimal', autocomplete: 'off', maxlength: 12 } });
  const scope = textField({ name: 'scope', label: 'What the estimate covers', multiline: true, value: oSaved.scope || '', attrs: { rows: 4, maxlength: 2000 },
    help: '10 to 2,000 characters. The customer sees this exactly as written.' });
  const timing = textField({ name: 'timingNote', label: 'Timing note', optional: true, value: oSaved.timingNote || '', attrs: { maxlength: 300 },
    help: 'Only include timing you can commit to.' });
  const offerMsg = textField({ name: 'offerMessage', label: 'Message to the customer', optional: true, multiline: true, value: oSaved.customerMessage || '', attrs: { rows: 3, maxlength: 2000 } });
  const disclaimer = h('p', { class: 'small muted' }, 'Added automatically: “Estimate; final price confirmed when we see the item in person.”');
  const amountBox = h('div', { class: 'stack' }, amountMode.wrap, h('div', { class: 'grid-2' }, minField.wrap, maxField.wrap), disclaimer);
  const offerSlot = h('div', { class: 'form-alert-slot' });
  const offerRestored = h('div');
  const closedNote = h('p', { class: 'small muted', hidden: true });
  const offerBtn = h('button', { type: 'submit', class: 'btn btn-primary btn-small' }, h('span', { class: 'btn-label' }, 'Send estimate'));
  const offerForm = h('form', { class: 'stack', novalidate: true }, offerRestored, closedNote, kind.wrap, amountBox, scope.wrap, timing.wrap, offerMsg.wrap, offerSlot, h('div', { class: 'form-actions' }, offerBtn));
  const offerFields = () => ({
    kind: kind.inputs.find(i => i.checked)?.value || 'estimate', amountMode: amountMode.inputs.find(i => i.checked)?.value || 'single',
    min: minField.input.value, max: maxField.input.value, scope: scope.input.value, timingNote: timing.input.value, customerMessage: offerMsg.input.value,
  });
  const syncOffer = () => {
    const f = offerFields();
    amountBox.hidden = f.kind !== 'estimate';
    maxField.wrap.hidden = f.amountMode !== 'range';
    minField.wrap.querySelector('label').firstChild.textContent = f.amountMode === 'range' ? 'From, in dollars' : 'Amount in dollars';
    scope.wrap.querySelector('label').firstChild.textContent = f.kind === 'estimate' ? 'What the estimate covers' : 'Why you need to see it';
    offerBtn.querySelector('.btn-label').textContent = f.kind === 'estimate' ? 'Send estimate' : 'Ask customer to bring it in';
    // Offers only move forward (docs/API.md): from later, closed or not-repairable states the
    // request must first go back to "Being reviewed" with a staff-only reason.
    const blocked = !OFFER_FROM.has(state.detail.status);
    closedNote.textContent = CLOSED.has(state.detail.status)
      ? 'This request is closed. To send a new estimate, first set the status to “Being reviewed” with a reason.'
      : `To send a new estimate from “${STATUS[state.detail.status]}”, first set the status to “Being reviewed” with a reason.`;
    closedNote.hidden = !blocked;
    offerBtn.disabled = blocked;
  };
  for (const el of [...kind.inputs, ...amountMode.inputs]) el.addEventListener('change', () => { offerDraft.save(offerFields()); syncOffer(); });
  for (const el of [minField.input, maxField.input, scope.input, timing.input, offerMsg.input]) el.addEventListener('input', () => { offerDraft.save(offerFields()); setError(el, null); });
  offerForm.addEventListener('submit', async event => {
    event.preventDefault();
    replace(offerSlot);
    const f = offerFields();
    let bad = null;
    const fail = (input, message) => { setError(input, message); bad ??= input; };
    let min = null; let max = null;
    if (f.kind === 'estimate') {
      min = parseCents(f.min);
      if (min === null || min < 1) fail(minField.input, 'Enter an amount such as 45 or 45.50.');
      if (f.amountMode === 'range') {
        max = parseCents(f.max);
        if (max === null) fail(maxField.input, 'Enter the top of the range.');
        else if (min !== null && max < min) fail(maxField.input, 'The top of the range must be at least the starting amount.');
      }
    }
    const scopeText = f.scope.trim();
    if (scopeText.length < 10) fail(scope.input, 'Write at least 10 characters.');
    if (f.timingNote.trim().length > 300) fail(timing.input, 'Keep the timing note under 300 characters.');
    if (bad) { bad.focus(); return; }
    const amountText = f.kind === 'estimate' ? moneyRange(min, max) : null;
    const ok = await confirmDialog({
      title: f.kind === 'estimate' ? `Send an estimate of ${amountText}?` : 'Ask the customer to bring it in?',
      body: f.kind === 'estimate' ? 'The customer sees it on their status page and can accept, decline or ask for a call. A sent estimate can’t be edited; send a new one to replace it.' : 'The customer sees your explanation and can reply once.',
      confirmLabel: f.kind === 'estimate' ? 'Send estimate' : 'Send request to visit',
    });
    if (!ok) return;
    const body = {
      expectedVersion: offerDraft.base(), kind: f.kind,
      amountMinCents: f.kind === 'estimate' ? min : null,
      amountMaxCents: f.kind === 'estimate' && f.amountMode === 'range' ? max : null,
      scope: scopeText, timingNote: f.timingNote.trim() || null, customerMessage: f.customerMessage.trim() || null,
    };
    setBusy(offerBtn, true, 'Sending');
    const before = state.detail.version;
    try {
      const result = await post(`${base}/offers`, body, { idempotencyKey: offerDraft.idempotency(body) });
      offerDraft.clear();
      afterSuccess(before, result.version);
      for (const input of [minField.input, maxField.input, scope.input, timing.input, offerMsg.input]) input.value = '';
      replace(offerRestored);
      await loadAll();
      renderData();
      replace(offerSlot, inlineAlert(result.kind === 'estimate' ? 'Estimate sent to the customer’s status page.' : 'Visit request sent to the customer’s status page.', 'ok'));
    } catch (error) {
      if (error instanceof ApiError && error.status === 422) {
        const map = { amountMinCents: minField.input, amountMaxCents: maxField.input, scope: scope.input, timingNote: timing.input, customerMessage: offerMsg.input };
        for (const [k, v] of Object.entries(error.fields)) map[k] && setError(map[k], v);
      }
      showError(offerSlot, error, ctx, { onReload: () => reloadLatest([offerDraft]) });
      if (error instanceof ApiError && error.code === 'INVALID_TRANSITION') replace(offerSlot, inlineAlert('An estimate can’t be sent from this status. First set the status to “Being reviewed” with a reason, then send it. Your text is kept.'));
    } finally { setBusy(offerBtn, false); syncOffer(); }
  });

  // ---------- note form ----------
  const noteDraft = draft('note');
  const noteField = textField({ name: 'note', label: 'Add an internal note', multiline: true, value: noteDraft.read()?.fields?.text || '', attrs: { rows: 3, maxlength: 4000 },
    help: 'Staff only. Never shown to the customer. Notes can’t be edited later.' });
  const noteSlot = h('div', { class: 'form-alert-slot' });
  const noteBtn = h('button', { type: 'submit', class: 'btn btn-secondary btn-small' }, h('span', { class: 'btn-label' }, 'Add note'));
  const noteForm = h('form', { class: 'stack', novalidate: true }, noteField.wrap, noteSlot, h('div', { class: 'form-actions' }, noteBtn));
  noteField.input.addEventListener('input', () => { noteDraft.save({ text: noteField.input.value }); setError(noteField.input, null); });
  noteForm.addEventListener('submit', async event => {
    event.preventDefault();
    replace(noteSlot);
    const text = noteField.input.value.trim();
    if (!text) { setError(noteField.input, 'Write a note first.'); noteField.input.focus(); return; }
    const body = { expectedVersion: noteDraft.base(), text };
    setBusy(noteBtn, true, 'Saving');
    const before = state.detail.version;
    try {
      const result = await post(`${base}/notes`, body, { idempotencyKey: noteDraft.idempotency(body) });
      noteDraft.clear();
      afterSuccess(before, result.requestVersion);
      noteField.input.value = '';
      await loadAll();
      renderData();
      replace(noteSlot, inlineAlert('Note added.', 'ok'));
    } catch (error) {
      if (error instanceof ApiError && error.fields?.text) setError(noteField.input, error.fields.text);
      showError(noteSlot, error, ctx, { onReload: () => reloadLatest([noteDraft]) });
    } finally { setBusy(noteBtn, false); }
  });

  // ---------- share / print / text ----------
  const shareSlot = h('div', { class: 'form-alert-slot' });
  const printBtn = button('Print status slip', { variant: 'secondary', class: 'btn-small' }, 'print');
  const textBtn = button('Text status link', { variant: 'secondary', class: 'btn-small' }, 'message');
  const copyBtn = button('Copy status link', { variant: 'quiet', class: 'btn-small' }, 'copy');
  async function share(channel, btn) {
    setBusy(btn, true);
    replace(shareSlot);
    try {
      return await post(`${base}/share-link`, { channel });
    } catch (error) {
      if (error instanceof ApiError && error.code === 'STATUS_UNAVAILABLE') replace(shareSlot, inlineAlert('The customer’s status link has expired for this closed request. Reopen it to issue a new link.', 'info'));
      else if (error instanceof ApiError && error.fields && Object.keys(error.fields).length) replace(shareSlot, inlineAlert(Object.values(error.fields)[0]));
      else showError(shareSlot, error, ctx);
      return null;
    } finally { setBusy(btn, false); }
  }
  printBtn.addEventListener('click', async () => {
    const link = await share('print', printBtn);
    if (link) printSlip(link);
  });
  copyBtn.addEventListener('click', async () => {
    const link = await share('print', copyBtn);
    if (link) { await copyText(link.statusUrl, copyBtn); replace(shareSlot, inlineAlert('Status link copied. Share it only with this customer.', 'ok')); }
  });
  textBtn.addEventListener('click', async () => {
    const link = await share('text', textBtn);
    if (!link) return;
    const preview = h('pre', { class: 'message-preview' }, link.message || '');
    if (link.smsHref && link.deliveryState === 'manual') {
      replace(shareSlot, h('div', { class: 'stack' },
        h('p', null, 'Opens your phone’s messaging app with the message ready. Nothing is sent until you press send there.'),
        preview,
        h('div', { class: 'form-actions' }, h('a', { class: 'btn btn-primary btn-small', href: smsHref(link.smsHref) }, icon('message', { size: 18 }), h('span', { class: 'btn-label' }, 'Open messages')))));
    } else {
      replace(shareSlot, h('div', { class: 'stack' },
        inlineAlert('Demo mode: this customer’s number isn’t on the private test list, so no text link was created. Preview only.', 'info'),
        preview));
    }
  });
  // iOS uses "&body=", others "?body=". Only the separator changes, never recipient or content.
  function smsHref(href) {
    if (!/iPhone|iPad|iPod/.test(navigator.userAgent)) return href;
    return href.replace('?body=', '&body=');
  }

  function printSlip(link) {
    const d = state.detail;
    const loc = findLocation(state.locations, d.status === 'ready' ? d.pickupLocation : d.dropoffLocation) || {};
    const rows = loc.id === 'bel_air' ? hoursRows(loc.weeklyHours) : [];
    const slip = h('section', { class: 'print-slip', 'aria-hidden': 'true' },
      h('p', { class: 'print-brand' }, 'Clarke’s Express Shoe Repair'),
      h('h1', null, 'Repair status slip'),
      h('p', null, h('strong', null, 'Reference: '), link.reference),
      h('p', null, h('strong', null, 'Item: '), itemLabel(d.itemType)),
      h('p', null, h('strong', null, 'Status: '), STATUS[d.status] || d.status),
      h('p', null, h('strong', null, 'Check your repair: '), link.statusUrl),
      h('p', null, 'Or visit the website’s Repair status page and enter the reference with your email or phone’s last four digits.'),
      h('hr'),
      loc.id === 'dundalk'
        ? h('p', null, h('strong', null, 'Dundalk: '), '6920 Holabird Ave., Dundalk, MD 21222. By appointment: call or text 443-386-3800. All repairs are performed in Bel Air.')
        : h('p', null, h('strong', null, 'Bel Air: '), '23 South Main St. (REAR), Burns Alley, Bel Air, MD 21014, behind Boyd Fulford Pharmacy. 410-836-8316.'),
      rows.length ? h('p', null, rows.map(r => `${r.days}: ${r.text}`).join('; ')) : null);
    document.body.append(slip);
    document.body.classList.add('is-printing');
    const done = () => { slip.remove(); document.body.classList.remove('is-printing'); window.removeEventListener('afterprint', done); };
    window.addEventListener('afterprint', done);
    window.print();
    window.setTimeout(done, 1500);
  }

  // ---------- photo zoom ----------
  function openPhoto(index) {
    const list = state.detail.photos || [];
    let i = index;
    let zoomed = false;
    const img = h('img', { alt: '' });
    const frame = h('div', { class: 'zoom-frame' }, img);
    const caption = h('p', { class: 'zoom-caption', 'aria-live': 'polite' });
    const prev = h('button', { type: 'button', class: 'icon-button', 'aria-label': 'Previous photo' }, icon('arrow-left'));
    const next = h('button', { type: 'button', class: 'icon-button', 'aria-label': 'Next photo' }, icon('arrow'));
    const zoom = h('button', { type: 'button', class: 'btn btn-secondary btn-small', 'aria-pressed': 'false' }, icon('zoom', { size: 18 }), h('span', { class: 'btn-label' }, 'Actual size'));
    const close = h('button', { type: 'button', class: 'icon-button', 'aria-label': 'Close photo' }, icon('close'));
    const dialog = h('dialog', { class: 'zoom-dialog', 'aria-label': 'Photo viewer' },
      h('div', { class: 'zoom-bar' }, caption, h('div', { class: 'zoom-tools' }, prev, next, zoom, close)), frame);
    const show = () => {
      const p = list[i];
      img.alt = `Customer photo ${i + 1} of ${list.length}`;
      img.src = p.url;
      img.onerror = () => { frame.classList.add('is-missing'); caption.textContent = 'This photo is unavailable.'; };
      frame.classList.remove('is-missing');
      caption.textContent = `Photo ${i + 1} of ${list.length}${p.width ? `, ${p.width} × ${p.height}` : ''}`;
      prev.disabled = list.length < 2; next.disabled = list.length < 2;
    };
    const setZoom = value => { zoomed = value; frame.classList.toggle('is-zoomed', zoomed); zoom.setAttribute('aria-pressed', String(zoomed)); zoom.querySelector('.btn-label').textContent = zoomed ? 'Fit to screen' : 'Actual size'; };
    prev.addEventListener('click', () => { i = (i - 1 + list.length) % list.length; setZoom(false); show(); });
    next.addEventListener('click', () => { i = (i + 1) % list.length; setZoom(false); show(); });
    zoom.addEventListener('click', () => setZoom(!zoomed));
    img.addEventListener('click', () => setZoom(!zoomed));
    close.addEventListener('click', () => dialog.close());
    dialog.addEventListener('keydown', event => {
      if (event.key === 'ArrowLeft') prev.click();
      if (event.key === 'ArrowRight') next.click();
    });
    const opener = document.activeElement;
    dialog.addEventListener('close', () => { dialog.remove(); opener?.focus?.(); });
    document.body.append(dialog);
    show();
    dialog.showModal();
    close.focus();
  }

  // ---------- rendering ----------
  function renderData() {
    const d = state.detail;
    replace(head, pageHead(d.contact?.name || 'Request', {
      back: { href: '/admin/requests', label: 'All requests' },
      sub: [d.reference, ' · ', d.source === 'walk_in' ? 'Walk-in ticket' : 'Online request', ' · Received ', formatDateTime(d.createdAt)],
      actions: h('div', { class: 'badge-row' }, statusBadge(d.status), d.demoMode ? badge('Demo', 'demo') : null),
    }));
    const callback = d.contact?.callbackPhone;
    replace(summary, panel('Customer',
      callback ? inlineAlert(`Customer asked for a call back at ${formatPhone(callback)}.`, 'info') : null,
      h('dl', { class: 'kv' },
        h('dt', null, 'Name'), h('dd', null, d.contact?.name || ''),
        h('dt', null, 'Email'), h('dd', null, d.contact?.email || 'None given'),
        h('dt', null, 'Phone'), h('dd', null, d.contact?.phone ? formatPhone(d.contact.phone) : 'None given'),
        h('dt', null, 'Prefers'), h('dd', null, { email: 'Email', call: 'Call', text: 'Text' }[d.contact?.preferred] || '—')),
      contactBox));
    renderContactActions();
    replace(historyBox, panel('Item',
      h('dl', { class: 'kv' },
        h('dt', null, 'Item'), h('dd', null, itemLabel(d.itemType)),
        h('dt', null, 'Needs'), h('dd', null, (d.workTypes || []).map(workLabel).join(', ') || 'Not specified'),
        h('dt', null, 'Brand or age'), h('dd', null, d.brandAge || '—'),
        h('dt', null, 'Needed by'), h('dd', null, d.neededBy ? formatLocalDate(d.neededBy) : '—'),
        h('dt', null, 'Drop-off'), h('dd', null, locationName(d.dropoffLocation)),
        h('dt', null, 'Pickup'), h('dd', null, locationName(d.pickupLocation)),
        h('dt', null, 'Repaired at'), h('dd', null, locationName(d.repairLocation || 'bel_air'))),
      h('div', { class: 'description' }, h('p', { class: 'label-caps' }, 'Description'), h('p', { class: 'pre' }, d.description || '')),
      d.customerMessage ? h('div', { class: 'description' }, h('p', { class: 'label-caps' }, 'Current message to customer'), h('p', { class: 'pre' }, d.customerMessage)) : null,
      deliveryBadges(d.delivery, { link: `/admin/emails?requestId=${encodeURIComponent(d.id)}` })),
    panel('History', eventsList()));
    renderPhotos();
    renderOffer();
    replace(notesList, notesView());
    syncOffer();
    syncStatusForm();
    statusSelect.input.querySelectorAll('option').forEach(o => { o.textContent = o.value ? `${STATUS[o.value]}${o.value === d.status ? ' (current)' : ''}` : 'Choose a status'; });
  }

  function renderContactActions() {
    const c = state.contact;
    if (!c) { replace(contactBox, h('p', { class: 'small muted' }, 'Contact actions couldn’t be loaded.')); return; }
    const links = [
      c.callHref ? h('a', { class: 'btn btn-secondary btn-small', href: c.callHref }, icon('phone', { size: 18 }), h('span', { class: 'btn-label' }, 'Call')) : null,
      c.smsHref ? h('a', { class: 'btn btn-secondary btn-small', href: c.smsHref }, icon('message', { size: 18 }), h('span', { class: 'btn-label' }, 'Text')) : null,
      c.emailHref ? h('a', { class: 'btn btn-secondary btn-small', href: c.emailHref }, icon('mail', { size: 18 }), h('span', { class: 'btn-label' }, 'Email')) : null,
    ].filter(Boolean);
    replace(contactBox,
      links.length ? h('div', { class: 'loc-actions' }, links) : null,
      c.blockedByDemo ? h('p', { class: 'small muted' }, 'Demo mode: contact buttons appear only for destinations on the private test list.') : null,
      !links.length && !c.blockedByDemo ? h('p', { class: 'small muted' }, 'No phone or email to contact.') : null);
  }

  function renderPhotos() {
    const list = state.detail.photos || [];
    replace(photosBox, panel('Photos', !list.length ? h('p', { class: 'muted' }, 'No photos with this request.') :
      h('ul', { class: 'photo-grid' }, list.map((p, index) => {
        const ready = p.state === 'ready' && p.url;
        const thumb = h('img', { src: ready ? p.url : undefined, alt: `Customer photo ${index + 1}`, loading: 'lazy', decoding: 'async' });
        const cell = h('li', null, ready
          ? h('button', { type: 'button', class: 'photo-cell', onclick: () => openPhoto(index), 'aria-label': `Open photo ${index + 1} of ${list.length}` }, thumb, h('span', { class: 'photo-cell-meta' }, icon('zoom', { size: 16 }), p.bytes ? bytes(p.bytes) : ''))
          : h('div', { class: 'photo-cell is-missing' }, icon('image'), h('span', { class: 'small' }, p.state === 'processing' ? 'Still processing' : 'Unavailable')));
        thumb.addEventListener('error', () => { const box = cell.querySelector('.photo-cell'); box?.classList.add('is-missing'); thumb.replaceWith(h('span', { class: 'small' }, 'Photo unavailable')); });
        return cell;
      }))));
  }

  function offerSummary(o) {
    return h('div', { class: 'offer-row' },
      h('div', { class: 'offer-row-head' },
        h('strong', null, o.kind === 'estimate' ? moneyRange(o.amountMinCents, o.amountMaxCents) : 'Asked to see it'),
        badge(o.state === 'active' ? 'Waiting for reply' : o.state === 'answered' ? 'Answered' : 'Replaced', o.state === 'active' ? 'wait' : 'neutral')),
      o.scope ? h('p', { class: 'pre' }, o.scope) : null,
      o.timingNote ? h('p', { class: 'small' }, `Timing: ${o.timingNote}`) : null,
      o.response ? h('p', { class: 'small' }, `Customer replied “${RESPONSE_LABELS[o.response.choice] || o.response.choice}” ${when(o.response.recordedAt)}`) : null,
      h('p', { class: 'small muted' }, `Sent ${when(o.sentAt || o.createdAt)} by ${who(o.createdBy)}`));
  }

  function renderOffer() {
    const current = state.detail.offer;
    const older = state.offers.filter(o => !current || o.id !== current.id);
    replace(offerBox,
      current ? h('div', { class: 'stack' }, h('p', { class: 'label-caps' }, 'Current'), offerSummary(current)) : h('p', { class: 'muted' }, 'No estimate or visit request sent yet.'),
      older.length ? h('details', { class: 'older' }, h('summary', null, `Earlier offers (${older.length})`), h('div', { class: 'stack' }, older.map(offerSummary)),
        pager(state.offersCursor, async cursor => { const page = await get(`${base}/offers`, { query: { limit: 10, cursor } }); state.offers.push(...page.items); state.offersCursor = page.nextCursor; renderOffer(); })) : null);
  }

  function eventsList() {
    if (!state.events.length) return h('p', { class: 'muted' }, 'No history yet.');
    return h('div', null, h('ol', { class: 'event-list' }, state.events.map(e => h('li', null,
      h('div', { class: 'event-head' },
        h('strong', null, e.status ? STATUS[e.status] || e.status : e.type.replace(/_/g, ' ')),
        badge(e.visibility === 'customer' ? 'Customer sees' : 'Staff only', e.visibility === 'customer' ? 'neutral' : 'muted')),
      e.message ? h('p', { class: 'pre' }, e.message) : null,
      e.reason ? h('p', { class: 'small' }, `Reason: ${e.reason}`) : null,
      h('p', { class: 'small muted' }, `${when(e.at)} · ${who(e.actorId)}`)))),
    pager(state.eventsCursor, async cursor => { const page = await get(`${base}/events`, { query: { limit: 25, cursor } }); state.events.push(...page.items); state.eventsCursor = page.nextCursor; renderData(); }));
  }

  function notesView() {
    if (!state.notes.length) return h('p', { class: 'muted small' }, 'No notes yet.');
    return h('div', null, h('ul', { class: 'note-list' }, state.notes.map(n => h('li', null,
      h('p', { class: 'pre' }, n.text), h('p', { class: 'small muted' }, `${when(n.createdAt)} · ${who(n.authorId)}`)))),
    pager(state.notesCursor, async cursor => { const page = await get(`${base}/notes`, { query: { limit: 25, cursor } }); state.notes.push(...page.items); state.notesCursor = page.nextCursor; replace(notesList, notesView()); }));
  }

  function restoredNotes() {
    for (const [d, slot] of [[statusDraft, statusRestored], [offerDraft, offerRestored]]) {
      const saved = d.read();
      const typed = Object.entries(saved?.fields || {}).filter(([k]) => !['pickupLocation', 'kind', 'amountMode'].includes(k)).some(([, v]) => v);
      if (!typed) continue;
      const changed = saved.baseVersion !== state.detail.version;
      replace(slot, inlineAlert(changed
        ? 'Restored your unsaved text. This request has changed since you started; review the latest details and history, then save again to apply it.'
        : 'Restored your unsaved text from earlier.', 'info'));
      if (changed) d.rebase(state.detail.version);
    }
    if (noteDraft.read()?.fields?.text && noteDraft.read().baseVersion !== state.detail.version) noteDraft.rebase(state.detail.version);
  }

  // Location data feeds the printable slip.
  stopLocations = watchLocations(payload => { state.locations = payload; });

  renderData();
  restoredNotes();
  syncStatusForm();
  syncOffer();

  const flash = read('flash', 1);
  remove('flash');

  replace(main,
    head,
    flash === 'ticket' ? inlineAlert('Ticket created. Print a slip or text the status link to the customer below.', 'ok') : null,
    h('div', { class: 'detail-grid' },
      h('div', { class: 'detail-main' }, summary, photosBox, historyBox),
      h('div', { class: 'detail-side' },
        panel('Status', statusForm),
        panel('Estimate or visit request', offerBox, h('hr', { class: 'rule' }), offerForm),
        panel('Share with the customer', h('p', { class: 'small muted' }, 'The status link is private. Share it only with this customer.'),
          h('div', { class: 'loc-actions' }, printBtn, textBtn, copyBtn), shareSlot),
        panel('Internal notes', noteForm, notesList))));
  return () => stopLocations?.();
}
