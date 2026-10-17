// Live location state from GET /api/v1/locations. The server decides open/closed; the
// browser only refreshes when the data's validUntil passes or the tab becomes visible.
// When data is stale or unavailable the UI says "Call before visiting", never "Open".
import { get } from './api.js';
import { h, icon, replace, $$ } from './dom.js';
import { LOCATIONS } from './constants.js';
import { hoursRows } from './format.js';

export const STATIC = {
  bel_air: {
    id: 'bel_air', name: 'Bel Air', visitMode: 'walk_in', repairWorkHere: true,
    address: '23 South Main St. (REAR), Burns Alley, Bel Air, MD 21014',
    directionsNote: 'Behind Boyd Fulford Pharmacy and The Main Street Tower Restaurant. Public parking is in front of the rear shop.',
    phoneHref: LOCATIONS.bel_air.tel, smsHref: null,
  },
  dundalk: {
    id: 'dundalk', name: 'Dundalk', visitMode: 'appointment_only', repairWorkHere: false,
    address: '6920 Holabird Ave., Dundalk, MD 21222',
    directionsNote: 'By appointment. Call or text to arrange a visit. All repairs are performed in Bel Air.',
    phoneHref: LOCATIONS.dundalk.tel, smsHref: LOCATIONS.dundalk.sms,
  },
};

// Verified Maps destinations live in the HTML footer; read them rather than duplicating URLs.
function staticMaps(id) {
  return document.querySelector(`[data-maps="${id}"]`)?.getAttribute('href') || null;
}

export function fallbackLocations() {
  return ['bel_air', 'dundalk'].map(id => ({
    ...STATIC[id], mapsHref: staticMaps(id), weeklyHours: null, activeNotice: null,
    state: id === 'dundalk' ? 'appointment_only' : 'unknown',
    stateText: id === 'dundalk' ? 'By appointment, call or text 443-386-3800' : 'Call before visiting',
  }));
}

let current = null;
let timer = 0;
let inflight = null;
const listeners = new Set();

function emit(payload) {
  for (const fn of listeners) fn(payload);
}

function isFresh() {
  return current && Date.parse(current.validUntil) > Date.now();
}

async function load() {
  if (inflight) return inflight;
  inflight = get('/locations').then(data => {
    if (!data || !Array.isArray(data.locations)) throw new Error('bad data');
    current = data;
    emit({ data, stale: false });
    schedule();
    return data;
  }).catch(() => {
    current = null;
    emit({ data: null, stale: true });
    window.clearTimeout(timer);
    timer = window.setTimeout(load, 60000);
    return null;
  }).finally(() => { inflight = null; });
  return inflight;
}

function schedule() {
  window.clearTimeout(timer);
  if (!current || document.hidden) return;
  const due = Date.parse(current.validUntil) - Date.now();
  // A stale "open" must never linger: mark stale at expiry, then refetch.
  timer = window.setTimeout(() => {
    if (!isFresh()) emit({ data: null, stale: true });
    load();
  }, Math.min(Math.max(due, 5000), 5 * 60000));
}

document.addEventListener('visibilitychange', () => {
  if (document.hidden) { window.clearTimeout(timer); return; }
  if (!isFresh()) load(); else schedule();
});

export function watchLocations(fn) {
  listeners.add(fn);
  if (isFresh()) fn({ data: current, stale: false }); else load();
  return () => listeners.delete(fn);
}

export function locationsList(payload) {
  return payload?.data?.locations?.length ? payload.data.locations : fallbackLocations();
}

export function findLocation(payload, id) {
  return locationsList(payload).find(l => l.id === id) || fallbackLocations().find(l => l.id === id);
}

export function stateView(loc, stale) {
  if (loc.id === 'dundalk' || loc.visitMode === 'appointment_only') {
    return { tone: 'appointment', text: 'By appointment, call or text 443-386-3800' };
  }
  if (stale || !loc.state || loc.state === 'unknown') return { tone: 'unknown', text: 'Call before visiting' };
  const tone = { open: 'open', closing_soon: 'soon', closed: 'closed', closed_notice: 'notice' }[loc.state] || 'unknown';
  return { tone, text: loc.stateText || 'Call before visiting' };
}

export function noticeView(notice) {
  if (!notice?.message) return null;
  return h('div', { class: 'loc-notice', role: 'note' },
    icon('alert', { size: 18 }),
    h('p', null, h('strong', null, notice.message), notice.reopenText ? ` ${notice.reopenText}` : ''));
}

export function hoursList(weeklyHours) {
  const rows = hoursRows(weeklyHours);
  if (!rows.length) return null;
  return h('dl', { class: 'hours' }, rows.map(r => h('div', { class: 'hours-row' }, h('dt', null, r.days), h('dd', null, r.text))));
}

export function stateBadge(loc, stale) {
  const view = stateView(loc, stale);
  return h('p', { class: ['loc-state', `is-${view.tone}`] }, h('span', { class: 'loc-state-dot', 'aria-hidden': 'true' }), view.text);
}

export function actionLinks(loc) {
  const fallback = STATIC[loc.id] || {};
  const tel = loc.phoneHref || fallback.phoneHref;
  const sms = loc.smsHref || fallback.smsHref;
  const maps = loc.mapsHref || staticMaps(loc.id);
  const phone = LOCATIONS[loc.id]?.phone;
  return h('div', { class: 'loc-actions' },
    tel ? h('a', { class: 'btn btn-secondary btn-small', href: tel }, icon('phone', { size: 18 }), h('span', { class: 'btn-label' }, `Call ${phone}`)) : null,
    sms ? h('a', { class: 'btn btn-secondary btn-small', href: sms }, icon('message', { size: 18 }), h('span', { class: 'btn-label' }, 'Text')) : null,
    maps ? h('a', { class: 'btn btn-quiet btn-small', href: maps, rel: 'noopener', target: '_blank' }, icon('pin', { size: 18 }), h('span', { class: 'btn-label' }, 'Directions'), h('span', { class: 'visually-hidden' }, ' (opens Google Maps)')) : null);
}

// Compact card used inside the request form, receipts and the status page.
export function locationCard(loc, { stale = false, heading = 'h3', role } = {}) {
  return h('section', { class: 'loc-mini', 'data-location-card': loc.id },
    h('div', { class: 'loc-mini-head' },
      h(heading, { class: 'loc-mini-title' }, role ? `${role}: ${loc.name}` : loc.name),
      stateBadge(loc, stale)),
    noticeView(loc.activeNotice),
    h('p', { class: 'loc-address' }, loc.address),
    h('p', { class: 'loc-note' }, loc.directionsNote),
    loc.id === 'bel_air' && !stale ? hoursList(loc.weeklyHours) : null,
    actionLinks(loc));
}

// Hydrate the static location markup on public pages (home cards, notice band).
export function hydrateStaticLocations() {
  watchLocations(payload => {
    const list = locationsList(payload);
    for (const loc of list) {
      for (const el of $$(`[data-loc-state="${loc.id}"]`)) {
        const view = stateView(loc, payload.stale);
        el.className = `loc-state is-${view.tone}`;
        replace(el, h('span', { class: 'loc-state-dot', 'aria-hidden': 'true' }), view.text);
      }
      for (const el of $$(`[data-loc-hours="${loc.id}"]`)) {
        if (payload.stale || !loc.weeklyHours) { el.hidden = true; continue; }
        const list = hoursList(loc.weeklyHours);
        if (list) { replace(el, ...list.childNodes); el.hidden = false; }
      }
      for (const el of $$(`[data-loc-notice="${loc.id}"]`)) {
        const view = noticeView(loc.activeNotice);
        if (view) replace(el, view); else replace(el);
        el.hidden = !view;
      }
    }
    renderNoticeBand(list);
  });
}

export function renderNoticeBand(list) {
  const band = document.getElementById('notice-band');
  if (!band) return;
  const notices = [];
  for (const loc of list) {
    const n = loc.activeNotice;
    if (!n?.message) continue;
    const same = notices.find(x => x.notice.message === n.message && x.notice.reopenText === n.reopenText);
    if (same) same.names.push(loc.name); else notices.push({ notice: n, names: [loc.name] });
  }
  if (!notices.length) { band.hidden = true; replace(band); return; }
  replace(band, h('div', { class: 'notice-inner' }, notices.map(({ notice, names }) => h('p', null,
    icon('alert', { size: 18 }),
    h('span', null, h('strong', null, `${names.join(' and ')}: `), notice.message, notice.reopenText ? ` ${notice.reopenText}` : '')))));
  band.hidden = false;
}
