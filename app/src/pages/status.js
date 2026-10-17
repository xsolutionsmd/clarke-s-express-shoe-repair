// /repair-status: capability link (#token=...) or reference lookup. The fragment is moved
// into sessionStorage and removed from the address bar before any request is made.
import '../styles/tokens.css';
import '../styles/base.css';
import '../styles/forms.css';
import { initChrome } from '../lib/chrome.js';
import { get, post, bootstrap, ApiError, describeRetry } from '../lib/api.js';
import { h, replace, button, setBusy, announce } from '../lib/dom.js';
import { read, write, remove, uuid, HOUR } from '../lib/store.js';
import { textField, setError, alertBox, callFallback } from '../lib/fields.js';
import { STATUS, CLOSED, RESPONSE_LABELS, itemLabel, statusLabel } from '../lib/constants.js';
import { formatDateTime, formatLongDateTime, moneyRange } from '../lib/format.js';
import { watchLocations, findLocation, locationCard } from '../lib/locations.js';
import { initLookup, saveStatusToken, readStatusToken, clearStatusToken } from '../lib/lookup.js';

// Capture and strip the capability fragment immediately.
(() => {
  const params = new URLSearchParams(location.hash.slice(1));
  const token = params.get('token');
  if (location.hash) history.replaceState(null, '', '/repair-status');
  if (token) saveStatusToken(token);
})();

initChrome();

const app = document.getElementById('status-app');
const lookupSection = document.getElementById('lookup-section');
let status = null;
let olderEvents = [];
let olderCursor = null;
let locPayload = null;
let lastLoad = 0;
let loading = false;

initLookup(lookupSection.querySelector('[data-lookup]'), { onSuccess: () => { lookupSection.hidden = true; load(); } });

watchLocations(payload => { locPayload = payload; renderLocation(); });

function showLookup(intro) {
  app.removeAttribute('aria-busy');
  replace(app, intro || []);
  lookupSection.hidden = false;
  if (intro) intro.querySelector('h1')?.focus({ preventScroll: true });
  else lookupSection.querySelector('h2').textContent = 'Find your repair';
}

async function load({ quiet = false } = {}) {
  const token = readStatusToken();
  if (!token) {
    showLookup(h('div', { class: 'form-card' },
      h('h1', { class: 'form-title', tabindex: '-1' }, 'Repair status'),
      h('p', { class: 'form-lede' }, 'Open the private link from your confirmation email, or find your repair with its reference below.')));
    return;
  }
  if (loading) return;
  loading = true;
  if (!quiet) app.setAttribute('aria-busy', 'true');
  try {
    status = await get('/status', { bearer: token });
    lastLoad = Date.now();
    lookupSection.hidden = true;
    render();
    if (quiet) announce(`Status: ${status.statusLabel || statusLabel(status.status)}.`);
  } catch (error) {
    if (error instanceof ApiError && (error.code === 'STATUS_UNAVAILABLE' || error.status === 404 || error.status === 401)) {
      clearStatusToken();
      status = null;
      showLookup(h('div', { class: 'form-card' },
        h('h1', { class: 'form-title', tabindex: '-1' }, 'This request is unavailable'),
        h('p', { class: 'form-lede' }, 'The link may be incomplete, or the request may have been closed for a while. Check your details below or call the shop.'),
        h('div', { class: 'receipt-list' }, callFallback())));
    } else if (!quiet || !status) {
      const message = error instanceof ApiError && error.code === 'RATE_LIMITED'
        ? `Too many checks in a short time. ${describeRetry(error) || 'Please wait a minute.'}`
        : error.message;
      replace(app, h('div', { class: 'form-card' },
        h('h1', { class: 'form-title', tabindex: '-1' }, 'Repair status'),
        alertBox(message, { extra: [callFallback(), h('div', { class: 'form-actions' }, button('Try again', { variant: 'secondary', class: 'btn-small', onclick: () => load() }, 'refresh'))] })));
    }
  } finally {
    loading = false;
    app.removeAttribute('aria-busy');
  }
}

function progressSteps(s) {
  if (s.status === 'not_repairable' || s.status === 'cancelled') return null;
  const offerStep = s.status === 'needs_visit' || s.offer?.kind === 'visit' ? 'needs_visit' : 'estimate_sent';
  const order = ['new', 'reviewing', offerStep, 'awaiting_dropoff', 'in_shop', 'in_progress', 'ready', 'picked_up'];
  const seen = new Set((s.history || []).map(e => e.status));
  const current = order.indexOf(s.status);
  if (current === -1) return null;
  return order.map((step, index) => {
    if (index === current) return { step, state: 'current' };
    if (index < current) return seen.has(step) ? { step, state: 'past' } : null;
    return { step, state: 'future' };
  }).filter(Boolean);
}

function progressLine(s) {
  const steps = progressSteps(s);
  if (!steps) return null;
  return h('ol', { class: 'status-line is-horizontal', 'aria-label': 'Progress' },
    steps.map(({ step, state }) => h('li', { class: state === 'past' ? 'is-past' : null, 'aria-current': state === 'current' ? 'step' : null },
      STATUS[step], state === 'past' ? h('span', { class: 'visually-hidden' }, ', done') : null)));
}

function responseStore(offerId) { return read(`resp.${offerId}`, 1) || {}; }
function saveResponseStore(offerId, data) { write(`resp.${offerId}`, 1, data, 24 * HOUR); }

function offerPanel(s) {
  const offer = s.offer;
  if (!offer) return null;
  const isEstimate = offer.kind === 'estimate';
  const answered = offer.response;
  const allowed = !answered && Array.isArray(s.allowedResponses) ? s.allowedResponses : [];
  const panel = h('section', { class: 'offer', 'aria-labelledby': 'offer-title' },
    h('h2', { class: 'form-section-title', id: 'offer-title' }, isEstimate ? 'Your estimate' : 'Please bring it in'),
    isEstimate ? h('p', { class: 'offer-amount' }, moneyRange(offer.amountMinCents, offer.amountMaxCents)) : null,
    offer.scope ? h('p', { class: 'offer-scope' }, offer.scope) : null,
    offer.timingNote ? h('p', null, h('strong', null, 'Timing: '), offer.timingNote) : null,
    offer.disclaimer ? h('p', { class: 'offer-disclaimer' }, offer.disclaimer) : null,
    offer.sentAt ? h('p', { class: 'small muted' }, `Sent ${formatDateTime(offer.sentAt)}`) : null);
  if (answered) {
    panel.append(alertBox(`You replied “${RESPONSE_LABELS[answered.choice] || answered.choice}” on ${formatDateTime(answered.recordedAt)}.`, { tone: 'ok' }));
  } else if (allowed.length) {
    panel.append(responseControls(s, offer, allowed));
  }
  return panel;
}

function responseControls(s, offer, allowed) {
  const saved = responseStore(offer.id);
  const wrap = h('div', { class: 'response' });
  const status = h('div', { class: 'form-alert-slot', 'aria-live': 'polite' });
  const actions = h('div', { class: 'response-actions' });
  const confirmPanel = h('div', { class: 'reveal-panel' }, h('div', null, h('div', { class: 'appointment-panel' })));
  const callPanel = h('div', { class: 'reveal-panel' }, h('div', null, h('div', { class: 'appointment-panel' })));
  confirmPanel.inert = true;
  callPanel.inert = true;
  const phone = textField({ name: 'callbackPhone', label: 'Phone number to call', type: 'tel', value: saved.phone || '', attrs: { autocomplete: 'tel', inputmode: 'tel', maxlength: 24 },
    help: 'We’ll call this number. It isn’t shown on this page afterwards.' });
  phone.input.addEventListener('input', () => { saveResponseStore(offer.id, { ...responseStore(offer.id), phone: phone.input.value }); setError(phone.input, null); });

  const open = (panel, other) => {
    other.classList.remove('is-open'); other.inert = true;
    panel.classList.add('is-open'); panel.inert = false;
    panel.querySelector('button, input')?.focus({ preventScroll: true });
  };
  const close = panel => { panel.classList.remove('is-open'); panel.inert = true; };

  const send = async (choice, btn) => {
    const store = responseStore(offer.id);
    if (!store.key || store.choice !== choice) { store.key = uuid(); store.choice = choice; }
    saveResponseStore(offer.id, store);
    let phoneValue = null;
    if (choice === 'request_call') {
      const digits = phone.input.value.replace(/\D/g, '');
      if (digits.length < 10) { setError(phone.input, 'Enter a phone number with area code.'); phone.input.focus(); return; }
      phoneValue = phone.input.value.trim().startsWith('+') ? `+${digits}` : digits.length === 10 ? `+1${digits}` : `+${digits}`;
    }
    setBusy(btn, true, 'Sending');
    replace(status);
    try {
      await bootstrap();
      const result = await post('/status/responses', { offerId: offer.id, expectedVersion: s.version, choice, phone: phoneValue },
        { bearer: readStatusToken(), idempotencyKey: store.key });
      remove(`resp.${offer.id}`);
      await load({ quiet: true });
      const note = app.querySelector('[data-response-note]');
      const text = `You replied “${RESPONSE_LABELS[choice]}”. ${result.message || 'Your response is recorded.'}`;
      if (note) replace(note, alertBox(text, { tone: 'ok' }));
      announce(text);
    } catch (error) {
      setBusy(btn, false);
      if (!(error instanceof ApiError)) throw error;
      if (['RESPONSE_ALREADY_RECORDED', 'OFFER_SUPERSEDED', 'VERSION_CONFLICT', 'INVALID_TRANSITION'].includes(error.code)) {
        const message = error.code === 'OFFER_SUPERSEDED' ? 'The shop has sent a newer estimate. Please review it before replying.'
          : error.code === 'RESPONSE_ALREADY_RECORDED' ? 'A reply to this estimate was already recorded.'
            : 'This request was updated. Please review the latest details before replying.';
        await load({ quiet: true });
        const note = app.querySelector('[data-response-note]');
        if (note) replace(note, alertBox(message, { tone: 'info' }));
        return;
      }
      if (error.fields?.phone) { setError(phone.input, error.fields.phone); phone.input.focus(); return; }
      replace(status, alertBox(error.code === 'RATE_LIMITED' ? `Too many attempts. ${describeRetry(error)}` : error.message, { extra: callFallback() }));
    }
  };

  const labels = {
    accept: offer.kind === 'estimate' ? 'Accept, I’ll bring it in' : 'I’ll bring it in',
    decline: 'No thanks',
    request_call: 'Please call me',
  };
  if (allowed.includes('accept')) {
    const b = button(labels.accept, { variant: 'primary' });
    b.addEventListener('click', () => send('accept', b));
    actions.append(b);
  }
  if (allowed.includes('request_call')) {
    const b = button(labels.request_call, { variant: 'secondary', 'aria-expanded': 'false' });
    b.addEventListener('click', () => { open(callPanel, confirmPanel); b.setAttribute('aria-expanded', 'true'); });
    actions.append(b);
    const sendCall = button('Request a call', { variant: 'primary', class: 'btn-small' });
    sendCall.addEventListener('click', () => send('request_call', sendCall));
    replace(callPanel.querySelector('.appointment-panel'), phone.wrap,
      h('div', { class: 'form-actions' }, sendCall, button('Cancel', { variant: 'quiet', class: 'btn-small', onclick: () => { close(callPanel); b.setAttribute('aria-expanded', 'false'); b.focus(); } })));
    if (saved.choice === 'request_call' && saved.phone) { callPanel.classList.add('is-open'); callPanel.inert = false; }
  }
  if (allowed.includes('decline')) {
    const b = button(labels.decline, { variant: 'quiet' });
    b.addEventListener('click', () => open(confirmPanel, callPanel));
    actions.append(b);
    const yes = button('Yes, close my request', { variant: 'danger', class: 'btn-small' });
    yes.addEventListener('click', () => send('decline', yes));
    replace(confirmPanel.querySelector('.appointment-panel'),
      h('p', null, 'This closes your request. You can still call the shop about it later.'),
      h('div', { class: 'form-actions' }, yes, button('Keep it open', { variant: 'quiet', class: 'btn-small', onclick: () => { close(confirmPanel); b.focus(); } })));
  }
  wrap.append(h('p', { class: 'small muted' }, 'Replying doesn’t take a payment or book a time.'), actions, callPanel, confirmPanel, status);
  return wrap;
}

function historyList(s) {
  const events = [...olderEvents, ...(s.history || [])];
  const seen = new Set();
  const unique = events.filter(e => (seen.has(e.id) ? false : seen.add(e.id))).sort((a, b) => Date.parse(a.at) - Date.parse(b.at));
  if (!unique.length) return null;
  const more = (s.history || []).length >= 50 && olderCursor !== false
    ? button('Show earlier updates', { variant: 'quiet', class: 'btn-small', onclick: loadOlder }) : null;
  return h('section', { class: 'history-section', 'aria-labelledby': 'history-title' },
    h('h2', { class: 'form-section-title', id: 'history-title' }, 'Updates'),
    more,
    h('ol', { class: 'history' }, unique.map(e => h('li', null,
      h('time', { datetime: e.at }, formatDateTime(e.at)),
      h('p', null, e.message || STATUS[e.status] || '')))));
}

async function loadOlder(event) {
  const btn = event.currentTarget;
  setBusy(btn, true, 'Loading');
  try {
    const page = await get('/status/events', { bearer: readStatusToken(), query: { limit: 25, cursor: olderCursor || undefined } });
    olderEvents = [...olderEvents, ...page.items];
    olderCursor = page.nextCursor || false;
    render();
  } catch (error) {
    setBusy(btn, false);
    if (error instanceof ApiError && error.code === 'INVALID_CURSOR') { olderCursor = null; olderEvents = []; }
    announce('Couldn’t load earlier updates.');
  }
}

function locationRole(s) {
  if (s.status === 'ready') return { id: s.pickupLocation || s.dropoffLocation, role: 'Pick up at' };
  if (['estimate_sent', 'needs_visit', 'awaiting_dropoff', 'new', 'reviewing'].includes(s.status)) return { id: s.dropoffLocation, role: s.dropoffLocation === 'dundalk' ? 'Arrange a visit' : 'Bring it to' };
  if (CLOSED.has(s.status) || s.status === 'not_repairable') return { id: s.dropoffLocation || 'bel_air', role: 'Questions? Contact' };
  return { id: s.dropoffLocation || 'bel_air', role: 'Your shop' };
}

function renderLocation() {
  const slot = app.querySelector('[data-status-loc]');
  if (!slot || !status) return;
  const { id, role } = locationRole(status);
  const loc = findLocation(locPayload, id || 'bel_air');
  replace(slot, locationCard(loc, { stale: locPayload?.stale, heading: 'h2', role }));
}

function render() {
  const s = status;
  const label = s.statusLabel || statusLabel(s.status);
  const refresh = button('Refresh', { variant: 'quiet', class: 'btn-small' }, 'refresh');
  refresh.addEventListener('click', async () => { setBusy(refresh, true, 'Refreshing'); await load({ quiet: true }); });
  const forget = h('button', { type: 'button', class: 'link-button', onclick: () => { clearStatusToken(); status = null; load(); } }, 'Forget this link in this tab');
  replace(app,
    h('article', { class: 'form-card status-card' },
      h('div', { class: 'status-head' },
        h('p', { class: 'status-ref' }, `Reference ${s.reference}`, s.itemType ? ` · ${itemLabel(s.itemType)}` : ''),
        h('h1', { class: 'status-title', tabindex: '-1', id: 'status-title' }, label),
        s.nextAction ? h('p', { class: 'form-lede' }, s.nextAction) : null),
      h('div', { class: 'form-section' },
        progressLine(s),
        s.customerMessage ? h('div', { class: 'shop-message' }, h('p', { class: 'label-caps' }, 'A note from the shop'), h('p', null, s.customerMessage)) : null,
        h('div', { 'data-response-note': '' }),
        offerPanel(s),
        s.dropoffLocation === 'dundalk' && !s.appointmentConfirmed && !CLOSED.has(s.status) ? h('p', { class: 'small muted' }, 'Dundalk visits are arranged by phone or text. No appointment is booked until the shop confirms one with you.') : null,
        h('div', { 'data-status-loc': '' }),
        historyList(s),
        h('div', { class: 'status-tools' },
          refresh,
          h('span', { class: 'small muted' }, `Updated ${formatLongDateTime(s.updatedAt)}`),
          forget))));
  renderLocation();
  document.title = `${label} | Repair status | Clarke’s Express Shoe Repair`;
  if (!app.dataset.focused) { app.dataset.focused = '1'; document.getElementById('status-title')?.focus({ preventScroll: true }); }
}

document.addEventListener('visibilitychange', () => {
  if (!document.hidden && status && Date.now() - lastLoad > 30000) load({ quiet: true });
});

load();
