// Native form controls with labels, help and linked inline errors (aria-describedby,
// aria-invalid). Errors replace help text visually but both stay programmatically linked.
import { h, icon, replace, uid } from './dom.js';

function describedBy(...ids) { return ids.filter(Boolean).join(' ') || undefined; }

function labelNode(text, optional) {
  return [text, optional ? h('span', { class: 'optional' }, ' (optional)') : null];
}

export function textField({ name, label, type = 'text', optional = false, help, value = '', attrs = {}, multiline = false }) {
  const id = uid(name.replace(/\W/g, '-'));
  const helpId = help ? `${id}-help` : null;
  const errorId = `${id}-error`;
  const control = multiline
    ? h('textarea', { id, name, ...attrs, 'aria-describedby': describedBy(helpId) })
    : h('input', { id, name, type, ...attrs, 'aria-describedby': describedBy(helpId) });
  control.value = value ?? '';
  if (!optional) control.setAttribute('aria-required', 'true');
  const wrap = h('div', { class: 'field', dataset: { field: name } },
    h('label', { for: id }, labelNode(label, optional)),
    control,
    help ? h('p', { class: 'field-help', id: helpId }, help) : null,
    h('p', { class: 'field-error', id: errorId, hidden: true }));
  control._errorId = errorId;
  control._helpId = helpId;
  return { wrap, input: control };
}

export function selectField({ name, label, options, optional = false, help, value = '', placeholder, attrs = {} }) {
  const id = uid(name.replace(/\W/g, '-'));
  const helpId = help ? `${id}-help` : null;
  const errorId = `${id}-error`;
  const select = h('select', { id, name, ...attrs, 'aria-describedby': describedBy(helpId) },
    placeholder !== undefined ? h('option', { value: '' }, placeholder) : null,
    options.map(([v, text]) => h('option', { value: v }, text)));
  select.value = value ?? '';
  if (!optional) select.setAttribute('aria-required', 'true');
  select._errorId = errorId;
  select._helpId = helpId;
  const wrap = h('div', { class: 'field', dataset: { field: name } },
    h('label', { for: id }, labelNode(label, optional)),
    h('div', { class: 'select-wrap' }, select, icon('chevron-down', { size: 18 })),
    help ? h('p', { class: 'field-help', id: helpId }, help) : null,
    h('p', { class: 'field-error', id: errorId, hidden: true }));
  return { wrap, input: select };
}

// Radio or checkbox chips inside a fieldset; returns the fieldset and its inputs.
export function choiceGroup({ name, legend, options, type = 'radio', optional = false, help, value, segmented = false }) {
  const base = uid(name.replace(/\W/g, '-'));
  const helpId = help ? `${base}-help` : null;
  const errorId = `${base}-error`;
  const selected = new Set(Array.isArray(value) ? value : value ? [value] : []);
  const inputs = [];
  const items = options.map(([v, text, sub]) => {
    const input = h('input', { type, name, value: v, checked: selected.has(v) });
    inputs.push(input);
    return h('label', { class: segmented ? null : 'chip' }, input, h('span', null, text, sub ? h('small', null, sub) : null));
  });
  const fieldset = h('fieldset', { class: 'field', dataset: { field: name }, 'aria-describedby': describedBy(helpId) },
    h('legend', null, labelNode(legend, optional)),
    help ? h('p', { class: 'field-help', id: helpId }, help) : null,
    h('div', { class: segmented ? 'segmented' : 'chips', role: type === 'radio' && !optional ? 'radiogroup' : null, 'aria-required': type === 'radio' && !optional ? 'true' : null }, items),
    h('p', { class: 'field-error', id: errorId, hidden: true }));
  fieldset._errorId = errorId;
  fieldset._helpId = helpId;
  return { wrap: fieldset, inputs };
}

export function setError(target, message) {
  if (!target) return;
  const errorEl = document.getElementById(target._errorId);
  if (!errorEl) return;
  const controls = target.tagName === 'FIELDSET' ? [...target.querySelectorAll('input')] : [target];
  if (message) {
    replace(errorEl, icon('alert', { size: 16 }), message);
    errorEl.hidden = false;
    for (const c of controls) {
      c.setAttribute('aria-invalid', 'true');
      if (target.tagName !== 'FIELDSET') c.setAttribute('aria-describedby', describedBy(target._helpId, target._errorId));
    }
    if (target.tagName === 'FIELDSET') target.setAttribute('aria-describedby', describedBy(target._helpId, target._errorId));
  } else {
    replace(errorEl);
    errorEl.hidden = true;
    for (const c of controls) {
      c.removeAttribute('aria-invalid');
      if (target.tagName !== 'FIELDSET') {
        const d = describedBy(target._helpId);
        if (d) c.setAttribute('aria-describedby', d); else c.removeAttribute('aria-describedby');
      }
    }
    if (target.tagName === 'FIELDSET') {
      const d = describedBy(target._helpId);
      if (d) target.setAttribute('aria-describedby', d); else target.removeAttribute('aria-describedby');
    }
  }
}

export function focusTarget(target) {
  if (!target) return;
  const el = target.tagName === 'FIELDSET' ? (target.querySelector('input:checked') || target.querySelector('input')) : target;
  el?.focus({ preventScroll: true });
  (target.tagName === 'FIELDSET' ? target : el)?.scrollIntoView({ block: 'center', behavior: window.matchMedia('(prefers-reduced-motion: reduce)').matches ? 'auto' : 'smooth' });
}

export function alertBox(message, { tone = 'error', extra, title } = {}) {
  return h('div', { class: ['form-alert', tone === 'ok' ? 'is-ok' : tone === 'info' ? 'is-info' : null], role: tone === 'error' ? 'alert' : 'status', tabindex: '-1' },
    icon(tone === 'ok' ? 'check' : 'alert', { size: 20 }),
    h('div', { class: 'form-alert-body' }, title ? h('p', null, h('strong', null, title)) : null, message ? h('p', null, message) : null, extra || null));
}

export function callFallback() {
  return h('p', null, 'You can also call Bel Air at ', h('a', { href: 'tel:+14108368316' }, '410-836-8316'),
    ', or call or text Dundalk at ', h('a', { href: 'tel:+14433863800' }, '443-386-3800'), '.');
}
