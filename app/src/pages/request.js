// /repair-request and /repair-request/complete (docs/API.md "Create request and preserve
// drafts"). One card with word-titled sections; draft fields, draft bearer, photo
// metadata and the submission key persist in sessionStorage for 24h (never files).
import '../styles/tokens.css';
import '../styles/base.css';
import '../styles/forms.css';
import { initChrome } from '../lib/chrome.js';
import { bootstrap, post, get, del, ApiError, describeRetry } from '../lib/api.js';
import { h, icon, replace, clear, button, setBusy, announce } from '../lib/dom.js';
import { read, write, remove, uuid, HOUR } from '../lib/store.js';
import { textField, choiceGroup, setError, focusTarget, alertBox, callFallback } from '../lib/fields.js';
import { ITEM_TYPES, WORK_TYPES, LOCATIONS } from '../lib/constants.js';
import { addDays, todayInShop, formatLongDateTime } from '../lib/format.js';
import { watchLocations, findLocation, locationCard, locationsList } from '../lib/locations.js';
import { saveStatusToken, tokenFromUrl } from '../lib/lookup.js';
import { PhotoManager } from './photos.js';

initChrome();

const app = document.getElementById('request-app');
const INTAKE = 'intake';
const RECEIPT = 'receipt';
const TTL = 24 * HOUR;
const DEFAULT_LIMITS = { maxFiles: 5, maxBytesEach: 10485760, mimeTypes: ['image/jpeg', 'image/png', 'image/webp', 'image/heic', 'image/heif'] };
const PRESETS = {
  soles: { itemType: 'shoes', workTypes: ['soles_heels'] },
  fit: { itemType: 'shoes', workTypes: ['stretch_fit'] },
  leather: { itemType: 'handbag_purse', workTypes: [] },
  dye: { itemType: 'shoes', workTypes: ['dye_color', 'clean_condition'] },
};
const EMPTY = { itemType: '', workTypes: [], description: '', brandAge: '', location: '', neededBy: '', name: '', email: '', phone: '', preferred: 'email' };

let boot = null;
let intake = read(INTAKE, 1) || { fields: { ...EMPTY }, draft: null, draftKey: null, photos: [], submit: null };
let locPayload = null;
const ui = {};
let photos = null;
let submitting = false;
let draftPromise = null;
let formGeneration = 0;

function persist() {
  intake.photos = photos ? photos.serialize() : intake.photos;
  write(INTAKE, 1, intake, TTL, { keepExpiry: true });
}
let persistTimer = 0;
const persistSoon = () => { window.clearTimeout(persistTimer); persistTimer = window.setTimeout(persist, 250); };

// ---------- routing ----------
function route() {
  const receipt = read(RECEIPT, 1);
  const complete = /^\/repair-request\/complete\/?$/.test(location.pathname);
  if (receipt) { renderReceipt(receipt); return; }
  if (complete) history.replaceState(null, '', '/repair-request');
  renderForm();
}
window.addEventListener('popstate', route);

// ---------- draft ----------
function draftValid() {
  return intake.draft && Date.parse(intake.draft.expiresAt) > Date.now();
}

async function ensureDraft({ existingOnly = false } = {}) {
  if (draftValid()) return intake.draft;
  if (existingOnly) return intake.draft || null;
  if (draftPromise) return draftPromise;
  if (intake.draft) await draftLost();
  const owner = intake;
  const current = () => owner === intake;
  draftPromise = (async () => {
    await bootstrap();
    if (!current()) throw new DOMException('Form cleared', 'AbortError');
    intake.draftKey ||= uuid();
    persist();
    const data = await post('/drafts', {}, { idempotencyKey: intake.draftKey });
    if (!current()) {
      del(`/drafts/${encodeURIComponent(data.draftId)}`, undefined, { draftToken: data.draftToken }).catch(() => {});
      throw new DOMException('Form cleared', 'AbortError');
    }
    intake.draft = { id: data.draftId, token: data.draftToken, expiresAt: data.expiresAt };
    intake.draftKey = null;
    persist();
    return intake.draft;
  })().finally(() => { if (current()) draftPromise = null; });
  return draftPromise;
}

async function draftLost({ submitted = false } = {}) {
  if (submitted) { await recoverReceipt(); return; }
  const hadPhotos = photos?.items.some(i => i.state !== 'local-rejected');
  intake.draft = null;
  intake.draftKey = null;
  intake.submit = null;
  photos?.draftLost();
  persist();
  if (hadPhotos && photos.blocking().length) showFormAlert(alertBox('Photos are kept for 24 hours. Some of yours expired; remove them and attach them again. Your other details are kept.', { tone: 'info' }));
}

async function recoverReceipt() {
  if (!intake.draft) return false;
  const generation = formGeneration;
  try {
    const d = await get(`/drafts/${encodeURIComponent(intake.draft.id)}`, { draftToken: intake.draft.token });
    if (generation !== formGeneration) return false;
    if (d.state === 'submitted' && d.receipt) { finish(d.receipt, { push: true }); return true; }
  } catch { /* handled by caller */ }
  return false;
}

// ---------- form ----------
function applyPreset() {
  const params = new URLSearchParams(location.search);
  const preset = PRESETS[params.get('repair')];
  if (params.has('repair')) history.replaceState(null, '', '/repair-request');
  const untouched = !intake.fields.itemType && !intake.fields.description;
  if (preset && untouched) Object.assign(intake.fields, preset);
}

function section(title, help, ...children) {
  return h('section', { class: 'form-section' },
    h('h2', { class: 'form-section-title' }, title),
    help ? h('p', { class: 'form-section-help' }, help) : null,
    ...children);
}

function renderForm() {
  formGeneration += 1;
  submitting = false;
  photos?.clearAll();
  applyPreset();
  const f = intake.fields;
  clear(app);
  ui.alert = h('div', { class: 'form-alert-slot' });

  // Where
  ui.location = choiceGroup({ name: 'location', legend: 'Location', segmented: true, value: f.location,
    options: [['bel_air', 'Bel Air', 'Main repair shop, walk in'], ['dundalk', 'Dundalk', 'By appointment']] });
  ui.dundalk = h('div', { class: ['reveal-panel', f.location === 'dundalk' ? 'is-open' : null] }, h('div', null,
    h('div', { class: 'appointment-panel', id: 'dundalk-panel' },
      h('p', null, h('strong', null, 'Dundalk is by appointment only.'), ' Call or text 443-386-3800 to set a time now, or send this request and we’ll contact you to arrange a visit. You don’t have an appointment until we confirm one with you. All repairs are performed in Bel Air.'),
      h('div', { class: 'loc-actions' },
        h('a', { class: 'btn btn-secondary btn-small', href: LOCATIONS.dundalk.tel }, icon('phone', { size: 18 }), h('span', { class: 'btn-label' }, 'Call 443-386-3800')),
        h('a', { class: 'btn btn-secondary btn-small', href: LOCATIONS.dundalk.sms }, icon('message', { size: 18 }), h('span', { class: 'btn-label' }, 'Text 443-386-3800'))))));
  ui.belAirNote = h('div', { class: ['reveal-panel', f.location === 'bel_air' ? 'is-open' : null] }, h('div', null,
    h('div', { class: 'appointment-panel', id: 'belair-panel' },
      h('p', null, 'Bel Air is at 23 South Main St. (REAR), on Burns Alley behind Boyd Fulford Pharmacy. Walk in during opening hours once we’ve replied.'),
      ui.belAirState = h('div'))));
  ui.dundalk.inert = f.location !== 'dundalk';
  ui.belAirNote.inert = f.location !== 'bel_air';
  ui.neededBy = textField({ name: 'neededBy', label: 'Needed by', type: 'date', optional: true, value: f.neededBy,
    help: 'If there’s an event or a date you need it for. We’ll confirm timing after we review it.', attrs: { min: boot?.today || todayInShop() } });
  ui.neededWarning = h('p', { class: 'field-warning', hidden: true, role: 'status' });
  ui.neededBy.wrap.append(ui.neededWarning);

  // Item
  ui.itemType = choiceGroup({ name: 'itemType', legend: 'What is it?', options: ITEM_TYPES, value: f.itemType });
  ui.workTypes = choiceGroup({ name: 'workTypes', legend: 'What does it need?', type: 'checkbox', optional: true, options: WORK_TYPES, value: f.workTypes,
    help: 'Choose any that apply, or “Not sure”.' });
  ui.description = textField({ name: 'description', label: 'Describe the item and the problem', multiline: true, value: f.description,
    help: 'For example: heel separated from the sole on the left boot; leather lining torn inside. 10 to 2,000 characters.', attrs: { rows: 5, maxlength: 2000 } });
  ui.brandAge = textField({ name: 'brandAge', label: 'Brand or approximate age', optional: true, value: f.brandAge, attrs: { maxlength: 120, autocomplete: 'off' } });

  // Photos
  const fileInput = h('input', { type: 'file', id: 'photo-input', accept: 'image/jpeg,image/png,image/webp,image/heic,image/heif,.heic,.heif', multiple: true, 'aria-describedby': 'photo-help' });
  ui.dropzone = h('div', { class: 'dropzone' },
    icon('upload', { size: 28 }),
    h('p', null, 'Drag photos here, or'),
    h('span', { class: 'file-button' }, fileInput, h('span', { class: 'btn btn-secondary btn-small', 'aria-hidden': 'true' }, h('span', { class: 'btn-label' }, 'Choose photos'))),
    h('label', { for: 'photo-input', class: 'visually-hidden' }, 'Choose photos'));
  ui.photoNotice = h('p', { class: 'field-error', hidden: true, role: 'status' });
  ui.photoList = h('ul', { class: 'photo-list', 'aria-label': 'Photos', hidden: true });
  ui.photosError = h('p', { class: 'field-error', id: 'photos-error', hidden: true });

  // Contact
  ui.name = textField({ name: 'name', label: 'Your name', value: f.name, attrs: { autocomplete: 'name', maxlength: 100 } });
  ui.email = textField({ name: 'email', label: 'Email', type: 'email', value: f.email, help: 'We send your reference and private status link here.', attrs: { autocomplete: 'email', maxlength: 254, inputmode: 'email', spellcheck: 'false' } });
  ui.phone = textField({ name: 'phone', label: 'Phone', type: 'tel', optional: true, value: f.phone, help: 'Needed if you’d like a call or text.', attrs: { autocomplete: 'tel', maxlength: 24, inputmode: 'tel' } });
  ui.preferred = choiceGroup({ name: 'preferred', legend: 'Best way to reach you', segmented: true, value: f.preferred || 'email',
    options: [['email', 'Email me'], ['call', 'Call me'], ['text', 'Text me']] });
  const honeypot = h('div', { class: 'honeypot', 'aria-hidden': 'true' },
    h('label', { for: 'website-field' }, 'Website'), h('input', { id: 'website-field', name: 'website', type: 'text', tabindex: '-1', autocomplete: 'off' }));

  ui.submit = h('button', { type: 'submit', class: 'btn btn-primary btn-large' }, h('span', { class: 'btn-label' }), icon('arrow', { size: 18 }));
  ui.submitAlert = h('div', { class: 'form-alert-slot' });
  ui.consent = h('p', { class: 'consent' }, boot?.consentText || 'Your photos and details are used only to answer this repair request.');
  ui.clearBtn = button('Clear form', { variant: 'quiet', onclick: clearDraft });

  ui.form = h('form', { novalidate: true, class: 'request-form', 'aria-labelledby': 'request-title' },
    ui.alert,
    section('Where you’ll bring it', null, ui.location.wrap, ui.dundalk, ui.belAirNote, ui.neededBy.wrap),
    section('Your item', null, ui.itemType.wrap, ui.workTypes.wrap, ui.description.wrap, ui.brandAge.wrap),
    section('Photos', null,
      h('p', { class: 'field-help', id: 'photo-help' }, 'Optional, but they help us reply with an estimate. Up to 5 photos, 10 MB each: JPEG, PNG, WebP or HEIC. Show the whole item and a close-up of the area that needs work.'),
      ui.dropzone, ui.photoNotice, ui.photoList, ui.photosError),
    section('How to reach you', null, ui.name.wrap, ui.email.wrap, ui.phone.wrap, ui.preferred.wrap, honeypot),
    h('div', { class: 'form-foot' }, ui.consent, ui.submitAlert, h('div', { class: 'form-actions' }, ui.submit, ui.clearBtn)));

  replace(app,
    h('h1', { class: 'form-title', id: 'request-title', tabindex: '-1' }, 'Send photos for an estimate'),
    h('p', { class: 'form-lede' }, 'Tell us about the item. We’ll look at your photos and reply with an estimate, or ask to see it in person. This isn’t an appointment or a final price.'),
    h('p', { class: 'form-lede small' }, 'Prefer to talk? Call Bel Air at ', h('a', { href: LOCATIONS.bel_air.tel }, '410-836-8316'), ', or call or text Dundalk at ', h('a', { href: LOCATIONS.dundalk.tel }, '443-386-3800'), '.'),
    ui.form);

  photos = new PhotoManager({
    list: ui.photoList, notice: ui.photoNotice, input: fileInput, dropzone: ui.dropzone,
    limits: boot?.uploadLimits || DEFAULT_LIMITS, ensureDraft, onDraftLost: draftLost,
    onChange: () => { persistSoon(); if (!photos.blocking().length) setPhotosError(null); },
  });
  photos.restore(intake.photos);

  bindForm();
  syncLocation(false);
  syncPreferred();
  checkNeededBy();
  reconcileDraft();
}

function setPhotosError(message) {
  replace(ui.photosError, message ? [icon('alert', { size: 16 }), message] : []);
  ui.photosError.hidden = !message;
}

function showFormAlert(node, { focus = false } = {}) {
  replace(ui.submitAlert, node || []);
  if (node && focus) node.focus?.();
}

function bindForm() {
  const f = intake.fields;
  const on = (input, key, transform = v => v) => input.addEventListener('input', () => { f[key] = transform(input.value); persistSoon(); });
  on(ui.description.input, 'description');
  on(ui.brandAge.input, 'brandAge');
  on(ui.name.input, 'name');
  on(ui.email.input, 'email');
  on(ui.phone.input, 'phone');
  ui.neededBy.input.addEventListener('change', () => { f.neededBy = ui.neededBy.input.value; persistSoon(); checkNeededBy(); });
  ui.neededBy.input.addEventListener('input', () => { f.neededBy = ui.neededBy.input.value; persistSoon(); });
  for (const r of ui.itemType.inputs) r.addEventListener('change', () => { f.itemType = r.value; setError(ui.itemType.wrap, null); persistSoon(); });
  for (const r of ui.location.inputs) r.addEventListener('change', () => { f.location = r.value; setError(ui.location.wrap, null); persistSoon(); syncLocation(true); });
  for (const r of ui.preferred.inputs) r.addEventListener('change', () => { f.preferred = r.value; persistSoon(); syncPreferred(); });
  for (const c of ui.workTypes.inputs) c.addEventListener('change', () => {
    if (c.value === 'not_sure' && c.checked) ui.workTypes.inputs.forEach(o => { if (o !== c) o.checked = false; });
    if (c.value !== 'not_sure' && c.checked) ui.workTypes.inputs.find(o => o.value === 'not_sure').checked = false;
    f.workTypes = ui.workTypes.inputs.filter(o => o.checked).map(o => o.value);
    persistSoon();
  });
  // Clear an inline error as soon as the field is corrected.
  for (const field of [ui.description, ui.brandAge, ui.name, ui.email, ui.phone, ui.neededBy]) {
    field.input.addEventListener('input', () => { if (field.input.getAttribute('aria-invalid')) setError(field.input, null); });
  }
  ui.form.addEventListener('submit', event => { event.preventDefault(); submit(); });
  window.addEventListener('online', () => {
    if (ui.submitAlert.querySelector('[data-offline]')) showFormAlert(alertBox('You’re back online. Your details are still here; press Send when you’re ready.', { tone: 'info' }));
  });
}

function syncLocation(animate) {
  const value = intake.fields.location;
  ui.dundalk.classList.toggle('is-open', value === 'dundalk');
  ui.belAirNote.classList.toggle('is-open', value === 'bel_air');
  ui.dundalk.inert = value !== 'dundalk';
  ui.belAirNote.inert = value !== 'bel_air';
  ui.submit.querySelector('.btn-label').textContent = value === 'dundalk' ? 'Send request and ask for a Dundalk appointment' : 'Send request';
  if (animate && value === 'dundalk') announce('Dundalk is by appointment. Call or text 443-386-3800, or send this request and we’ll contact you.');
}

function syncPreferred() {
  const needsPhone = ['call', 'text'].includes(intake.fields.preferred);
  const label = ui.phone.wrap.querySelector('label');
  replace(label, 'Phone', needsPhone ? null : h('span', { class: 'optional' }, ' (optional)'));
  if (needsPhone) ui.phone.input.setAttribute('aria-required', 'true'); else ui.phone.input.removeAttribute('aria-required');
  ui.phone.wrap.querySelector('.field-help').textContent = needsPhone ? `Required so we can ${intake.fields.preferred === 'call' ? 'call' : 'text'} you.` : 'Needed if you’d like a call or text.';
}

function checkNeededBy() {
  const value = ui.neededBy.input.value;
  const today = boot?.today || todayInShop();
  ui.neededBy.input.min = today;
  ui.neededWarning.hidden = true;
  if (!value) { setError(ui.neededBy.input, null); return; }
  if (value < today) { setError(ui.neededBy.input, 'Choose today or a later date.'); return; }
  setError(ui.neededBy.input, null);
  if (value <= addDays(today, 3)) {
    replace(ui.neededWarning, icon('clock', { size: 16 }), 'Timing is confirmed only after we review your request.');
    ui.neededWarning.hidden = false;
  }
}

async function reconcileDraft() {
  const generation = formGeneration;
  try {
    boot = await bootstrap();
    if (generation !== formGeneration) return;
  } catch (error) {
    if (generation !== formGeneration) return;
    showFormAlert(alertBox('We couldn’t connect to the shop’s website. You can keep filling in the form; we’ll try again when you send it.', { tone: 'info', extra: callFallback() }));
  }
  if (boot) {
    photos.setLimits(boot.uploadLimits || DEFAULT_LIMITS);
    ui.consent.textContent = boot.consentText || ui.consent.textContent;
    checkNeededBy();
    if (boot.intake && boot.intake.accepting === false) { renderPaused(boot.intake.message); return; }
  }
  if (!intake.draft) return;
  try {
    const d = await get(`/drafts/${encodeURIComponent(intake.draft.id)}`, { draftToken: intake.draft.token });
    if (generation !== formGeneration) return;
    if (d.state === 'submitted' && d.receipt) { finish(d.receipt, { push: true }); return; }
    if (d.state !== 'active') { draftLost(); return; }
    intake.draft.expiresAt = d.expiresAt || intake.draft.expiresAt;
    photos.reconcile(d.photos);
  } catch (error) {
    if (generation !== formGeneration) return;
    if (error instanceof ApiError && (error.code === 'DRAFT_EXPIRED' || error.status === 404)) draftLost();
  }
}

watchLocations(payload => {
  locPayload = payload;
  if (ui.belAirState?.isConnected) replace(ui.belAirState, locationCard(findLocation(payload, 'bel_air'), { stale: payload.stale, heading: 'h3' }));
  if (app.querySelector('[data-paused]')) renderPausedLocations();
  if (app.querySelector('[data-receipt-loc]')) renderReceiptLocation();
});

// ---------- validation and submit ----------
function normalizePhone(raw) {
  const text = String(raw || '').trim();
  if (!text) return null;
  if (/[a-z]/i.test(text) || /(ext|x)\s*\d/i.test(text)) return undefined;
  const digits = text.replace(/\D/g, '');
  if (text.startsWith('+')) return digits.length >= 8 && digits.length <= 15 ? `+${digits}` : undefined;
  if (digits.length === 10) return `+1${digits}`;
  if (digits.length === 11 && digits.startsWith('1')) return `+${digits}`;
  return undefined;
}

function validate() {
  const f = intake.fields;
  const errors = [];
  const add = (target, message) => { setError(target, message); errors.push(target); };
  [ui.location.wrap, ui.itemType.wrap, ui.workTypes.wrap, ui.description.input, ui.brandAge.input, ui.name.input, ui.email.input, ui.phone.input, ui.preferred.wrap].forEach(t => setError(t, null));
  setPhotosError(null);
  if (!f.location) add(ui.location.wrap, 'Choose where you’ll bring the item.');
  checkNeededBy();
  if (ui.neededBy.input.getAttribute('aria-invalid')) errors.push(ui.neededBy.input);
  if (!f.itemType) add(ui.itemType.wrap, 'Choose the type of item.');
  const desc = f.description.trim();
  if (desc.length < 10) add(ui.description.input, 'Describe the item and what it needs, in at least 10 characters.');
  else if (desc.length > 2000) add(ui.description.input, 'Keep the description under 2,000 characters.');
  if (f.brandAge.trim().length > 120) add(ui.brandAge.input, 'Keep this under 120 characters.');
  if (photos.blocking().length) { setPhotosError('Remove the photos marked above before sending, or attach them again.'); errors.push(ui.photoList.querySelector('.is-error button') || ui.dropzone); }
  if (!f.name.trim()) add(ui.name.input, 'Enter your name.');
  else if (f.name.trim().length > 100) add(ui.name.input, 'Keep your name under 100 characters.');
  if (!/^[^\s@<>()",;]+@[^\s@<>()",;]+\.[^\s@<>()",;]+$/.test(f.email.trim())) add(ui.email.input, 'Enter an email address like name@example.com.');
  const phone = normalizePhone(f.phone);
  if (phone === undefined) add(ui.phone.input, 'Enter a phone number with area code, like 410-555-0123.');
  else if (!phone && ['call', 'text'].includes(f.preferred)) add(ui.phone.input, `Add a phone number so we can ${f.preferred === 'call' ? 'call' : 'text'} you, or choose email.`);
  return errors;
}

function payloadFor(draft) {
  const f = intake.fields;
  return {
    draftId: draft.id,
    itemType: f.itemType,
    workTypes: f.workTypes,
    description: f.description.trim(),
    brandAge: f.brandAge.trim() || null,
    location: f.location,
    neededBy: f.neededBy || null,
    contact: { name: f.name.trim(), email: f.email.trim(), phone: normalizePhone(f.phone) || null, preferred: f.preferred },
    photoIds: photos.readyIds(),
    consentVersion: boot?.consentVersion || 'repair-intake-v1',
    website: ui.form.elements.website.value,
  };
}

const FIELD_MAP = () => ({
  itemType: ui.itemType.wrap, workTypes: ui.workTypes.wrap, description: ui.description.input, brandAge: ui.brandAge.input,
  location: ui.location.wrap, neededBy: ui.neededBy.input, 'contact.name': ui.name.input, 'contact.email': ui.email.input,
  'contact.phone': ui.phone.input, 'contact.preferred': ui.preferred.wrap,
});

function applyServerErrors(fields) {
  const map = FIELD_MAP();
  const targets = [];
  const loose = [];
  for (const [key, message] of Object.entries(fields || {})) {
    const target = map[key] || map[key.split('.').slice(0, 2).join('.')];
    if (target) { setError(target, message); targets.push(target); }
    else if (key.startsWith('photoIds')) { setPhotosError(message); targets.push(ui.dropzone); }
    else loose.push(message);
  }
  return { targets, loose };
}

async function submit() {
  if (submitting) return;
  showFormAlert(null);
  const errors = validate();
  if (errors.length) {
    showFormAlert(alertBox(`Check the ${errors.length === 1 ? 'highlighted field' : `${errors.length} highlighted fields`}. Your details and photos are kept.`));
    focusTarget(errors[0]);
    return;
  }
  const generation = formGeneration;
  const current = () => generation === formGeneration;
  submitting = true;
  setBusy(ui.submit, true, 'Sending');
  try {
    if (!boot) boot = await bootstrap();
    if (!current()) return;
    if (boot.intake?.accepting === false) { renderPaused(boot.intake.message); return; }
    if (photos.pending()) {
      setBusy(ui.submit, true, 'Finishing photo uploads');
      await photos.settle();
      if (!current()) return;
      setBusy(ui.submit, true, 'Sending');
      if (photos.blocking().length) {
        setPhotosError('One or more photos couldn’t be used. Remove them before sending, or attach them again.');
        focusTarget(ui.photoList.querySelector('.is-error button'));
        return;
      }
    }
    await send(true, current);
  } catch (error) {
    if (current() && error?.name !== 'AbortError') handleSubmitError(error);
  } finally {
    if (current()) {
      submitting = false;
      if (ui.submit.isConnected) setBusy(ui.submit, false);
      ui.clearBtn.disabled = false;
    }
  }
}

async function send(allowRetry, current) {
  const draft = await ensureDraft();
  if (!current()) return;
  await photos.settle();
  if (!current()) return;
  if (photos.blocking().length) throw new ApiError({ code: 'DRAFT_EXPIRED', message: 'Some photos expired. Remove the marked photos and attach them again before sending. Your details are kept.' });
  const payload = payloadFor(draft);
  const canonical = JSON.stringify(payload);
  if (!intake.submit || intake.submit.payload !== canonical) intake.submit = { key: uuid(), payload: canonical };
  persist();
  try {
    ui.clearBtn.disabled = true;
    const receipt = await post('/requests', payload, { idempotencyKey: intake.submit.key, draftToken: draft.token });
    if (current()) finish(receipt, { push: true });
  } catch (error) {
    if (!current()) return;
    if (!(error instanceof ApiError) || !allowRetry) throw error;
    if (error.code === 'IDEMPOTENCY_CONFLICT') { intake.submit = null; return send(false, current); }
    if (error.code === 'DRAFT_SUBMITTED') { if (await recoverReceipt()) return undefined; throw error; }
    if (error.code === 'DRAFT_EXPIRED' || (error.status === 404 && error.code === 'NOT_FOUND')) {
      const hadPhotos = photos.items.some(i => i.photoId);
      await draftLost();
      if (!hadPhotos) return send(false, current);
      throw new ApiError({ status: 409, code: 'DRAFT_EXPIRED', message: 'Your photos expired after 24 hours. Remove the marked photos and attach them again, then send.' });
    }
    if (error.code === 'PHOTOS_NOT_READY') {
      await photos.settle();
      return send(false, current);
    }
    throw error;
  }
  return undefined;
}

function handleSubmitError(error) {
  if (!(error instanceof ApiError)) {
    showFormAlert(alertBox('Something went wrong in the page. Your details are kept; try again.', { extra: callFallback() }), { focus: true });
    return;
  }
  if (error.code === 'VALIDATION_FAILED' || error.status === 422) {
    const { targets, loose } = applyServerErrors(error.fields);
    showFormAlert(alertBox(loose.length ? loose.join(' ') : error.message || 'Check the highlighted fields.'), { focus: !targets.length });
    if (targets.length) focusTarget(targets[0]);
    return;
  }
  if (error.code === 'INTAKE_PAUSED') { renderPaused(error.details?.message || error.message); return; }
  if (error.code === 'RATE_LIMITED') {
    showFormAlert(alertBox(`We’ve had several requests from this connection in a short time. ${describeRetry(error) || 'Please try again later.'}`, { extra: callFallback() }), { focus: true });
    return;
  }
  if (error.code === 'OFFLINE' || error.code === 'NETWORK') {
    const node = alertBox(error.message, { extra: [callFallback(), h('div', { class: 'form-actions' }, button('Try again', { variant: 'secondary', class: 'btn-small', onclick: () => submit() }))] });
    node.dataset.offline = '1';
    showFormAlert(node, { focus: true });
    return;
  }
  showFormAlert(alertBox(error.message, { extra: [callFallback(), h('div', { class: 'form-actions' }, button('Try again', { variant: 'secondary', class: 'btn-small', onclick: () => submit() }))] }), { focus: true });
}

async function clearDraft() {
  if (!window.confirm('Clear this form and remove any attached photos?')) return;
  const draft = intake.draft;
  formGeneration += 1;
  draftPromise = null;
  window.clearTimeout(persistTimer);
  photos?.clearAll();
  intake = { fields: { ...EMPTY }, draft: null, draftKey: null, photos: [], submit: null };
  remove(INTAKE);
  if (draft) del(`/drafts/${encodeURIComponent(draft.id)}`, undefined, { draftToken: draft.token }).catch(() => {});
  renderForm();
  document.getElementById('request-title')?.focus();
  announce('Form cleared.');
}

// ---------- success ----------
function finish(receipt, { push }) {
  const token = tokenFromUrl(receipt.statusUrl);
  if (token) saveStatusToken(token);
  // The create-request receipt holds no contact details; keep it exactly as returned.
  const stored = { ...receipt, warnings: Array.isArray(receipt.warnings) ? receipt.warnings : [] };
  write(RECEIPT, 1, stored, TTL);
  photos?.clearAll();
  intake = { fields: { ...EMPTY }, draft: null, draftKey: null, photos: [], submit: null };
  remove(INTAKE);
  if (push && location.pathname !== '/repair-request/complete') history.pushState(null, '', '/repair-request/complete');
  renderReceipt(stored);
  window.scrollTo({ top: 0 });
}

function renderReceiptLocation() {
  const slot = app.querySelector('[data-receipt-loc]');
  const receipt = read(RECEIPT, 1);
  if (!slot || !receipt) return;
  replace(slot, locationCard(findLocation(locPayload, receipt.location), { stale: locPayload?.stale, heading: 'h3', role: receipt.location === 'dundalk' ? 'Your location' : 'Bring it to' }));
}

function renderReceipt(r) {
  const copyBtn = button('Copy private status link', { variant: 'secondary', class: 'btn-small' }, 'copy');
  copyBtn.addEventListener('click', async () => {
    try { await navigator.clipboard.writeText(r.statusUrl); announce('Status link copied.'); copyBtn.querySelector('.btn-label').textContent = 'Link copied'; } catch { window.prompt('Copy your private status link:', r.statusUrl); }
  });
  const items = [
    r.locationMessage ? h('p', null, icon(r.location === 'dundalk' ? 'phone' : 'pin', { size: 20 }), h('span', null, r.locationMessage)) : null,
    r.location === 'dundalk' && !r.appointmentConfirmed && !r.locationMessage ? h('p', null, icon('phone', { size: 20 }), 'This is a request for contact, not an appointment. Call or text 443-386-3800 to arrange a Dundalk visit.') : null,
    r.closureMessage ? h('p', null, icon('clock', { size: 20 }), h('span', null, r.closureMessage, r.nextOpensAt ? ` (${formatLongDateTime(r.nextOpensAt)})` : '')) : null,
    ...r.warnings.map(w => h('p', null, icon('alert', { size: 20 }), w.message || '')),
  ].filter(Boolean);
  replace(app,
    h('div', { class: 'receipt' },
      h('p', { class: 'receipt-ok' }, icon('check'), 'Request received'),
      h('h1', { class: 'form-title', id: 'receipt-title', tabindex: '-1' }, 'Thank you. We have your request.'),
      h('p', { class: 'form-lede' }, r.message || 'We’ll look at your photos and reply with an estimate or ask to see it in person.'),
      h('div', { class: 'reference-box' },
        h('p', { class: 'label-caps' }, 'Your reference'),
        h('p', { class: 'reference-value' }, r.reference),
        h('p', { class: 'field-help' }, 'Keep this reference. With your email or phone number, it lets you look up this request.')),
      items.length ? h('div', { class: 'receipt-list' }, items) : null,
      h('div', { class: 'form-actions' },
        h('a', { class: 'btn btn-primary', href: '/repair-status' }, h('span', { class: 'btn-label' }, 'View repair status'), icon('arrow', { size: 18 })),
        copyBtn),
      h('div', { 'data-receipt-loc': '' }),
      h('div', { class: 'form-foot' },
        h('p', { class: 'small muted' }, `Sent ${r.createdAt ? formatLongDateTime(r.createdAt) : ''}${r.location ? ` for ${LOCATIONS[r.location]?.long || ''}` : ''}.`),
        h('div', { class: 'form-actions' }, button('Start another request', { variant: 'secondary', onclick: startAnother })))));
  renderReceiptLocation();
  document.title = 'Request received | Clarke’s Express Shoe Repair';
  document.getElementById('receipt-title')?.focus({ preventScroll: true });
}

function startAnother() {
  remove(RECEIPT);
  history.pushState(null, '', '/repair-request');
  document.title = 'Send photos for an estimate | Clarke’s Express Shoe Repair';
  renderForm();
  document.getElementById('request-title')?.focus();
}

// ---------- paused ----------
function renderPausedLocations() {
  const slot = app.querySelector('[data-paused-locs]');
  if (!slot) return;
  replace(slot, locationsList(locPayload).map(loc => locationCard(loc, { stale: locPayload?.stale, heading: 'h2' })));
}

function renderPaused(message) {
  photos?.clearAll();
  replace(app,
    h('div', { class: 'paused', 'data-paused': '' },
      h('h1', { class: 'form-title', tabindex: '-1', id: 'paused-title' }, 'Online requests are paused'),
      h('p', { class: 'form-lede' }, message || 'Please call or text the shop.'),
      h('p', { class: 'small muted' }, 'Anything you already typed is kept in this tab for 24 hours.'),
      h('div', { class: 'loc-pair', 'data-paused-locs': '' })));
  renderPausedLocations();
  document.getElementById('paused-title')?.focus({ preventScroll: true });
}

route();
// Persist the latest field values when the tab is hidden or closed.
document.addEventListener('visibilitychange', () => { if (document.hidden && app.querySelector('form')) persist(); });
window.addEventListener('pagehide', () => { if (app.querySelector('form')) persist(); });
