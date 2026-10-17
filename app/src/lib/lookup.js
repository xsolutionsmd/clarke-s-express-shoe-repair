// Status lookup form (reference + email or phone last four). Failures are always the
// same generic message from the server; the browser never hints which part was wrong.
import { post, bootstrap, ApiError, describeRetry } from './api.js';
import { h, icon, replace, setBusy, announce } from './dom.js';
import { read, write, remove, HOUR } from './store.js';
import { normalizeReference } from './format.js';

const TOKEN_KEY = 'status';

export function saveStatusToken(token) {
  if (typeof token === 'string' && /^[A-Za-z0-9_-]{20,200}$/.test(token)) write(TOKEN_KEY, 1, { token }, 24 * HOUR);
}
export function readStatusToken() { return read(TOKEN_KEY, 1)?.token || null; }
export function clearStatusToken() { remove(TOKEN_KEY); }

export function tokenFromUrl(url) {
  try {
    const hash = new URL(url, location.origin).hash.slice(1);
    return new URLSearchParams(hash).get('token');
  } catch {
    return null;
  }
}

function fieldError(input, message) {
  const id = `${input.id}-error`;
  let el = document.getElementById(id);
  const help = input.getAttribute('aria-describedby')?.split(' ').filter(x => x !== id) || [];
  if (!message) {
    el?.remove();
    input.removeAttribute('aria-invalid');
    input.setAttribute('aria-describedby', help.join(' '));
    return;
  }
  if (!el) {
    el = h('p', { class: 'field-error', id });
    input.insertAdjacentElement('afterend', el);
  }
  replace(el, icon('alert', { size: 16 }), message);
  input.setAttribute('aria-invalid', 'true');
  input.setAttribute('aria-describedby', [...help, id].join(' '));
}

export function initLookup(form, { onSuccess } = {}) {
  if (!form || form.dataset.ready) return;
  form.dataset.ready = '1';
  const ref = form.elements.reference;
  const value = form.elements.value;
  const label = form.querySelector('[data-lookup-value-label]');
  const help = form.querySelector('[data-lookup-value-help]');
  const alertBox = form.querySelector('[data-lookup-error]');
  const submit = form.querySelector('button[type="submit"]');

  const syncType = () => {
    const type = form.elements.verifyType.value;
    fieldError(value, null);
    if (type === 'email') {
      value.type = 'email'; value.autocomplete = 'email'; value.inputMode = 'email'; value.maxLength = 254;
      value.removeAttribute('pattern');
      label.textContent = 'Email address';
      help.textContent = 'The email you used for the request.';
    } else {
      value.type = 'text'; value.autocomplete = 'off'; value.inputMode = 'numeric'; value.maxLength = 4;
      value.setAttribute('pattern', '[0-9]{4}');
      label.textContent = 'Last four digits of your phone';
      help.textContent = 'The phone number you gave us, last four digits only.';
    }
    value.value = '';
  };
  for (const radio of form.querySelectorAll('input[name="verifyType"]')) radio.addEventListener('change', syncType);

  const showAlert = message => {
    if (!message) { alertBox.hidden = true; replace(alertBox); return; }
    replace(alertBox, icon('alert', { size: 20 }), h('div', { class: 'form-alert-body' }, h('p', null, message),
      h('p', null, 'You can also call Bel Air at ', h('a', { href: 'tel:+14108368316' }, '410-836-8316'), ', or call or text Dundalk at ', h('a', { href: 'tel:+14433863800' }, '443-386-3800'), '.')));
    alertBox.hidden = false;
  };

  let busy = false;
  form.addEventListener('submit', async event => {
    event.preventDefault();
    if (busy) return;
    showAlert(null);
    const type = form.elements.verifyType.value;
    const reference = normalizeReference(ref.value);
    const raw = value.value.trim();
    let invalid = null;
    fieldError(ref, null);
    fieldError(value, null);
    if (reference.replace(/-/g, '').length < 10) { fieldError(ref, 'Enter the full reference, starting with CLK.'); invalid ??= ref; }
    if (type === 'email' && !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(raw)) { fieldError(value, 'Enter the email address you used.'); invalid ??= value; }
    if (type === 'phone_last4' && !/^\d{4}$/.test(raw)) { fieldError(value, 'Enter exactly four digits.'); invalid ??= value; }
    if (invalid) { invalid.focus(); return; }
    busy = true;
    setBusy(submit, true, 'Checking');
    try {
      await bootstrap();
      const data = await post('/status/lookup', { reference, verification: { type, value: raw } });
      const token = data.statusToken || tokenFromUrl(data.statusUrl);
      saveStatusToken(token);
      value.value = '';
      if (onSuccess) onSuccess(token); else location.assign('/repair-status');
    } catch (error) {
      if (!(error instanceof ApiError)) throw error;
      if (error.code === 'RATE_LIMITED') showAlert(`Too many attempts. ${describeRetry(error) || 'Please wait a few minutes and try again.'}`);
      else if (error.code === 'STATUS_UNAVAILABLE') showAlert('This request is unavailable. Check your details or call the shop.');
      else showAlert(error.message);
      announce('Lookup failed.');
      alertBox.focus?.();
    } finally {
      busy = false;
      setBusy(submit, false);
    }
  });
  alertBox.tabIndex = -1;
}
