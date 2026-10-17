// /admin/requests/new: walk-in ticket in under a minute. Email optional; phone-only works.
import { h, replace, setBusy } from '../../lib/dom.js';
import { post, ApiError } from '../../lib/api.js';
import { uuid, write } from '../../lib/store.js';
import { textField, choiceGroup, setError, focusTarget } from '../../lib/fields.js';
import { ITEM_TYPES, WORK_TYPES } from '../../lib/constants.js';
import { todayInShop } from '../../lib/format.js';
import { pageHead, panel, showError, inlineAlert, getDraft, saveDraft, clearDraft } from '../core.js';

const KEY = 'ticket:new';

function normalizePhone(raw) {
  const text = String(raw || '').trim();
  if (!text) return null;
  const digits = text.replace(/\D/g, '');
  if (/[a-z]/i.test(text)) return undefined;
  if (text.startsWith('+')) return digits.length >= 8 && digits.length <= 15 ? `+${digits}` : undefined;
  if (digits.length === 10) return `+1${digits}`;
  if (digits.length === 11 && digits.startsWith('1')) return `+${digits}`;
  return undefined;
}

export default async function ticket({ main, navigate, sessionExpired }) {
  const saved = getDraft(KEY)?.fields || {};
  const name = textField({ name: 'name', label: 'Customer name', value: saved.name, attrs: { autocomplete: 'off', maxlength: 100 } });
  const phone = textField({ name: 'phone', label: 'Phone', optional: true, type: 'tel', value: saved.phone, attrs: { autocomplete: 'off', inputmode: 'tel', maxlength: 24 } });
  const email = textField({ name: 'email', label: 'Email', optional: true, type: 'email', value: saved.email, help: 'Give at least a phone number or an email. Without email, print a slip or text the status link.', attrs: { autocomplete: 'off', maxlength: 254 } });
  const preferred = choiceGroup({ name: 'preferred', legend: 'Customer prefers', segmented: true, value: saved.preferred || 'text', options: [['text', 'Text'], ['call', 'Call'], ['email', 'Email']] });
  const itemType = choiceGroup({ name: 'itemType', legend: 'Item', options: ITEM_TYPES, value: saved.itemType });
  const workTypes = choiceGroup({ name: 'workTypes', legend: 'Work', type: 'checkbox', optional: true, options: WORK_TYPES, value: saved.workTypes || [] });
  const description = textField({ name: 'description', label: 'Description', multiline: true, value: saved.description, attrs: { rows: 3, maxlength: 2000 }, help: '10 to 2,000 characters.' });
  const brandAge = textField({ name: 'brandAge', label: 'Brand or age', optional: true, value: saved.brandAge, attrs: { maxlength: 120 } });
  const neededBy = textField({ name: 'neededBy', label: 'Needed by', optional: true, type: 'date', value: saved.neededBy, attrs: { min: todayInShop() } });
  const location = choiceGroup({ name: 'location', legend: 'Dropped off at', segmented: true, value: saved.location || 'bel_air', options: [['bel_air', 'Bel Air'], ['dundalk', 'Dundalk']] });
  const note = textField({ name: 'internalNote', label: 'Internal note', optional: true, multiline: true, value: saved.internalNote, attrs: { rows: 2, maxlength: 4000 }, help: 'Staff only.' });
  const slot = h('div', { class: 'form-alert-slot' });
  const submit = h('button', { type: 'submit', class: 'btn btn-primary' }, h('span', { class: 'btn-label' }, 'Create ticket'));

  const fields = () => ({
    name: name.input.value, phone: phone.input.value, email: email.input.value,
    preferred: preferred.inputs.find(i => i.checked)?.value || 'text',
    itemType: itemType.inputs.find(i => i.checked)?.value || '',
    workTypes: workTypes.inputs.filter(i => i.checked).map(i => i.value),
    description: description.input.value, brandAge: brandAge.input.value, neededBy: neededBy.input.value,
    location: location.inputs.find(i => i.checked)?.value || 'bel_air', internalNote: note.input.value,
  });
  const persist = () => { const d = getDraft(KEY); saveDraft(KEY, { fields: fields(), key: d?.key, payload: d?.payload }); };

  const form = h('form', { class: 'stack', novalidate: true },
    panel('Customer', h('div', { class: 'grid-2' }, name.wrap, phone.wrap), email.wrap, preferred.wrap),
    panel('Item', itemType.wrap, workTypes.wrap, description.wrap, h('div', { class: 'grid-2' }, brandAge.wrap, neededBy.wrap)),
    panel('Drop-off', location.wrap, note.wrap,
      h('p', { class: 'small muted' }, 'A ticket records that the item is in the shop. It isn’t an estimate approval or a promise of timing.')),
    slot,
    h('div', { class: 'form-actions' }, submit, h('a', { href: '/admin/requests', 'data-nav': '', class: 'btn btn-quiet' }, h('span', { class: 'btn-label' }, 'Cancel'))));

  form.addEventListener('input', event => { persist(); if (event.target.getAttribute?.('aria-invalid')) setError(event.target, null); });
  form.addEventListener('change', persist);
  for (const c of workTypes.inputs) c.addEventListener('change', () => {
    if (c.value === 'not_sure' && c.checked) workTypes.inputs.forEach(o => { if (o !== c) o.checked = false; });
    if (c.value !== 'not_sure' && c.checked) workTypes.inputs.find(o => o.value === 'not_sure').checked = false;
  });

  form.addEventListener('submit', async event => {
    event.preventDefault();
    replace(slot);
    const f = fields();
    const errors = [];
    const fail = (t, m) => { setError(t, m); errors.push(t); };
    [name.input, phone.input, email.input, itemType.wrap, description.input, preferred.wrap].forEach(t => setError(t, null));
    const phoneValue = normalizePhone(f.phone);
    if (!f.name.trim()) fail(name.input, 'Enter the customer’s name.');
    if (phoneValue === undefined) fail(phone.input, 'Enter a phone number with area code.');
    if (f.email.trim() && !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(f.email.trim())) fail(email.input, 'Enter a valid email or leave it blank.');
    if (!phoneValue && !f.email.trim()) fail(phone.input, 'Add a phone number or an email.');
    if (f.preferred === 'email' && !f.email.trim()) fail(preferred.wrap, 'Add an email, or choose call or text.');
    if (['call', 'text'].includes(f.preferred) && !phoneValue) fail(preferred.wrap, 'Add a phone number, or choose email.');
    if (!f.itemType) fail(itemType.wrap, 'Choose the item type.');
    if (f.description.trim().length < 10) fail(description.input, 'Describe the item and work in at least 10 characters.');
    if (errors.length) { focusTarget(errors[0]); return; }
    const body = {
      itemType: f.itemType, workTypes: f.workTypes, description: f.description.trim(), brandAge: f.brandAge.trim() || null,
      neededBy: f.neededBy || null, location: f.location,
      contact: { name: f.name.trim(), email: f.email.trim() || null, phone: phoneValue || null, preferred: f.preferred },
      internalNote: f.internalNote.trim() || null,
    };
    const d = getDraft(KEY) || {};
    const text = JSON.stringify(body);
    if (!d.key || d.payload !== text) saveDraft(KEY, { fields: f, key: uuid(), payload: text });
    setBusy(submit, true, 'Creating');
    try {
      const created = await post('/admin/requests', body, { idempotencyKey: getDraft(KEY).key });
      clearDraft(KEY);
      write('flash', 1, 'ticket', 60000);
      navigate(`/admin/requests/${encodeURIComponent(created.id)}`);
    } catch (error) {
      setBusy(submit, false);
      if (error instanceof ApiError && error.status === 422) {
        const map = { 'contact.name': name.input, 'contact.phone': phone.input, 'contact.email': email.input, 'contact.preferred': preferred.wrap, itemType: itemType.wrap, workTypes: workTypes.wrap, description: description.input, brandAge: brandAge.input, neededBy: neededBy.input, location: location.wrap, internalNote: note.input, contact: phone.input };
        const targets = Object.entries(error.fields).map(([k, v]) => { const t = map[k]; if (t) setError(t, v); return t; }).filter(Boolean);
        replace(slot, inlineAlert(error.message || 'Check the highlighted fields.'));
        if (targets[0]) focusTarget(targets[0]);
        return;
      }
      showError(slot, error, { sessionExpired });
    }
  });

  replace(main, pageHead('New walk-in ticket', { back: { href: '/admin/requests', label: 'All requests' }, sub: 'For items handed over at the counter. The customer gets the same reference and status link.' }), form);
}
