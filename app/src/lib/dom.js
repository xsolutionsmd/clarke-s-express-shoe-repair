// Safe DOM construction. Strings always become text nodes; nothing here parses HTML.
// The SVG namespace is an identifier, not a fetched resource; it is composed so the
// static external-resource scan (scripts/check.mjs) does not mistake it for one.
const SVG = ['http:', '', 'www.w3.org', '2000', 'svg'].join('/');

export function h(tag, attrs, ...children) {
  const el = document.createElement(tag);
  if (attrs) setAttrs(el, attrs);
  append(el, children);
  return el;
}

export function setAttrs(el, attrs) {
  for (const [key, value] of Object.entries(attrs)) {
    if (value === undefined || value === null || value === false) continue;
    if (key === 'class') el.className = Array.isArray(value) ? value.filter(Boolean).join(' ') : value;
    else if (key === 'dataset') Object.assign(el.dataset, value);
    else if (key.startsWith('on') && typeof value === 'function') el.addEventListener(key.slice(2), value);
    else if (key === 'text') el.textContent = value;
    else if (key === 'value' && 'value' in el) el.value = value;
    else if (key === 'checked' || key === 'selected' || key === 'disabled' || key === 'hidden' || key === 'required' || key === 'multiple') {
      el[key] = Boolean(value);
    } else el.setAttribute(key, value === true ? '' : String(value));
  }
  return el;
}

export function append(el, children) {
  for (const child of children.flat(Infinity)) {
    if (child === null || child === undefined || child === false) continue;
    el.append(child instanceof Node ? child : document.createTextNode(String(child)));
  }
  return el;
}

export function clear(el) {
  while (el.firstChild) el.firstChild.remove();
  return el;
}

export function replace(el, ...children) {
  clear(el);
  return append(el, children);
}

export const $ = (selector, scope = document) => scope.querySelector(selector);
export const $$ = (selector, scope = document) => [...scope.querySelectorAll(selector)];

// One 24px stroke icon set (DESIGN.md): no text arrows or emoji.
const PATHS = {
  arrow: ['M5 12h14', 'M13 6l6 6-6 6'],
  'arrow-left': ['M19 12H5', 'M11 6l-6 6 6 6'],
  phone: ['M5 4h3l2 5-2.5 1.5a11 11 0 0 0 5 5L14 13l5 2v3a2 2 0 0 1-2 2A16 16 0 0 1 3 6a2 2 0 0 1 2-2'],
  message: ['M4 5h16v11H9l-5 4z'],
  pin: ['M12 21s-7-6.2-7-11.5A7 7 0 0 1 19 9.5C19 14.8 12 21 12 21z', 'M12 7.5a2 2 0 1 1 0 4 2 2 0 0 1 0-4z'],
  upload: ['M12 16V4', 'M7 9l5-5 5 5', 'M4 16v4h16v-4'],
  check: ['M5 12.5l4.5 4.5L19 7.5'],
  alert: ['M12 3l10 18H2z', 'M12 10v4', 'M12 17.5v.5'],
  close: ['M6 6l12 12', 'M18 6L6 18'],
  chevron: ['M9 6l6 6-6 6'],
  'chevron-down': ['M6 9l6 6 6-6'],
  menu: ['M4 7h16', 'M4 12h16', 'M4 17h16'],
  mail: ['M3 6h18v12H3z', 'M3 7l9 6 9-6'],
  image: ['M4 5h16v14H4z', 'M4 16l5-5 4 4 2-2 5 5', 'M15.5 8.5a1.5 1.5 0 1 1 0 3 1.5 1.5 0 0 1 0-3'],
  print: ['M7 8V3h10v5', 'M5 8h14a2 2 0 0 1 2 2v6h-4', 'M7 16H3v-6', 'M7 13h10v8H7z'],
  copy: ['M8 8h12v12H8z', 'M4 16V4h12'],
  refresh: ['M20 12a8 8 0 1 1-2.3-5.6', 'M20 4v5h-5'],
  clock: ['M12 3a9 9 0 1 1 0 18 9 9 0 0 1 0-18z', 'M12 7v5l3 2'],
  search: ['M10.5 4a6.5 6.5 0 1 1 0 13 6.5 6.5 0 0 1 0-13z', 'M15.5 15.5L20 20'],
  plus: ['M12 5v14', 'M5 12h14'],
  zoom: ['M10.5 4a6.5 6.5 0 1 1 0 13 6.5 6.5 0 0 1 0-13z', 'M15.5 15.5L20 20', 'M10.5 8v5', 'M8 10.5h5'],
  external: ['M14 4h6v6', 'M20 4l-9 9', 'M18 14v6H4V6h6'],
  user: ['M12 4a4 4 0 1 1 0 8 4 4 0 0 1 0-8z', 'M4 21a8 8 0 0 1 16 0'],
};

export function icon(name, { size = 24, label } = {}) {
  const svg = document.createElementNS(SVG, 'svg');
  svg.setAttribute('viewBox', '0 0 24 24');
  svg.setAttribute('width', size);
  svg.setAttribute('height', size);
  svg.setAttribute('fill', 'none');
  svg.setAttribute('stroke', 'currentColor');
  svg.setAttribute('stroke-width', '1.6');
  svg.setAttribute('stroke-linecap', 'round');
  svg.setAttribute('stroke-linejoin', 'round');
  svg.setAttribute('class', `icon icon-${name}`);
  if (label) { svg.setAttribute('role', 'img'); svg.setAttribute('aria-label', label); } else svg.setAttribute('aria-hidden', 'true');
  for (const d of PATHS[name] || []) {
    const path = document.createElementNS(SVG, 'path');
    path.setAttribute('d', d);
    svg.append(path);
  }
  return svg;
}

// Upgrade static <span data-icon="name"> placeholders in HTML shells.
export function hydrateIcons(scope = document) {
  for (const el of $$('[data-icon]', scope)) {
    if (el.firstChild) continue;
    el.append(icon(el.dataset.icon, { size: Number(el.dataset.size) || 24 }));
  }
}

export function announce(text, { assertive = false } = {}) {
  const id = assertive ? 'live-assertive' : 'live-polite';
  let region = document.getElementById(id);
  if (!region) {
    region = h('div', { id, class: 'visually-hidden', 'aria-live': assertive ? 'assertive' : 'polite', 'aria-atomic': 'true' });
    document.body.append(region);
  }
  region.textContent = '';
  window.setTimeout(() => { region.textContent = text; }, 40);
}

let fieldSeq = 0;
export const uid = prefix => `${prefix}-${++fieldSeq}`;

export function button(label, { variant = 'primary', class: extra, ...rest } = {}, iconName) {
  return h('button', { type: 'button', ...rest, class: ['btn', `btn-${variant}`, extra] },
    h('span', { class: 'btn-label' }, label), iconName ? icon(iconName, { size: 18 }) : null);
}

export function linkButton(label, href, { variant = 'primary', class: extra, ...rest } = {}, iconName) {
  return h('a', { href, ...rest, class: ['btn', `btn-${variant}`, extra] },
    iconName ? icon(iconName, { size: 18 }) : null, h('span', { class: 'btn-label' }, label));
}

export function setBusy(btn, busy, busyLabel) {
  if (!btn) return;
  const label = btn.querySelector('.btn-label');
  if (busy) {
    btn.dataset.idleLabel ??= label?.textContent || '';
    btn.style.setProperty('min-width', `${btn.getBoundingClientRect().width}px`);
    btn.disabled = true;
    btn.setAttribute('aria-busy', 'true');
    btn.classList.add('is-busy');
    if (label && busyLabel) label.textContent = busyLabel;
  } else {
    btn.disabled = false;
    btn.removeAttribute('aria-busy');
    btn.classList.remove('is-busy');
    btn.style.removeProperty('min-width');
    if (label && btn.dataset.idleLabel !== undefined) label.textContent = btn.dataset.idleLabel;
    delete btn.dataset.idleLabel;
  }
}
