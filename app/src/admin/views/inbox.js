// /admin/requests: new requests first, filters, location, search (kept out of the URL),
// cursor pagination and clear empty states. Filter state survives navigation and back.
import { h, icon, replace, button, setBusy } from '../../lib/dom.js';
import { get, ApiError } from '../../lib/api.js';
import { choiceGroup } from '../../lib/fields.js';
import { itemLabel, locationName } from '../../lib/constants.js';
import { formatShortDate, formatLocalDate } from '../../lib/format.js';
import { pageHead, statusBadge, deliveryBadges, emptyState, loadingState, inlineAlert, pager, viewState, badge } from '../core.js';

const FILTERS = [['new', 'New'], ['waiting', 'Waiting on customer'], ['in_shop', 'In shop'], ['ready', 'Ready'], ['closed', 'Closed'], ['all', 'All']];
const EMPTY_TEXT = {
  new: ['No new requests', 'New online requests and tickets appear here first.'],
  waiting: ['Nothing waiting on customers', 'Requests with an estimate, a visit request or awaiting drop-off appear here.'],
  in_shop: ['Nothing in the shop', 'Items marked in the shop or being repaired appear here.'],
  ready: ['Nothing ready for pickup', ''],
  closed: ['No closed requests', ''],
  all: ['No requests yet', ''],
};

export default async function inbox({ main, sessionExpired }) {
  const state = { filter: 'new', location: '', q: '', notRepairable: false, ...(viewState('inbox') || {}) };
  const list = h('div', { class: 'inbox-list', 'aria-live': 'polite' });
  const filters = choiceGroup({ name: 'filter', legend: 'Show', segmented: true, options: FILTERS, value: state.filter });
  filters.wrap.classList.add('inbox-filters');
  const locSelect = h('select', { id: 'inbox-location', name: 'location' },
    h('option', { value: '' }, 'Both locations'), h('option', { value: 'bel_air' }, 'Bel Air'), h('option', { value: 'dundalk' }, 'Dundalk'));
  locSelect.value = state.location;
  const search = h('input', { id: 'inbox-search', type: 'search', name: 'q', maxlength: 100, autocomplete: 'off', placeholder: 'Reference, name, email or phone', value: state.q });
  const nr = h('input', { type: 'checkbox', id: 'inbox-nr', checked: state.notRepairable });
  const nrWrap = h('label', { class: 'check-inline', for: 'inbox-nr', hidden: state.filter !== 'all' }, nr, ' Only “We can’t repair this”');
  const searchForm = h('form', { class: 'inbox-tools', role: 'search', novalidate: true },
    h('div', { class: 'field' }, h('label', { for: 'inbox-search' }, 'Search'),
      h('div', { class: 'search-row' }, search, h('button', { type: 'submit', class: 'btn btn-secondary btn-small' }, icon('search', { size: 18 }), h('span', { class: 'btn-label' }, 'Search')))),
    h('div', { class: 'field' }, h('label', { for: 'inbox-location' }, 'Location'), h('div', { class: 'select-wrap' }, locSelect, icon('chevron-down', { size: 18 }))),
    nrWrap);

  let items = [];
  let cursor = null;

  const save = () => viewState('inbox', state);
  const query = extra => ({
    filter: state.filter, location: state.location || undefined, q: state.q.trim().length >= 2 || /^CLK/i.test(state.q.trim()) ? state.q.trim() : undefined,
    status: state.filter === 'all' && state.notRepairable ? 'not_repairable' : undefined, limit: 25, ...extra,
  });

  async function load({ more = false } = {}) {
    if (!more) replace(list, loadingState('Loading requests'));
    try {
      const page = await get('/admin/requests', { query: query(more ? { cursor } : {}) });
      items = more ? [...items, ...page.items] : page.items;
      cursor = page.nextCursor;
      draw();
    } catch (error) {
      if (error instanceof ApiError && error.code === 'INVALID_CURSOR') { cursor = null; return load(); }
      if (error instanceof ApiError && error.status === 401) { sessionExpired(); replace(list, inlineAlert('Your session ended. Sign in again to see requests.', 'info')); return undefined; }
      const retry = button('Try again', { variant: 'secondary', class: 'btn-small' }, 'refresh');
      retry.addEventListener('click', () => load());
      replace(list, inlineAlert(error.message, 'error', h('div', { class: 'form-actions' }, retry)));
    }
    return undefined;
  }

  function draw() {
    if (!items.length) {
      const q = query().q;
      const [title, text] = q ? ['No matching requests', `Nothing matches “${q}” with these filters. Full references match exactly; other searches need two or more characters.`] : EMPTY_TEXT[state.filter];
      replace(list, emptyState(title, text, state.filter === 'new' && !q ? h('a', { class: 'btn btn-secondary btn-small', href: '/admin/requests/new', 'data-nav': '' }, h('span', { class: 'btn-label' }, 'Create a walk-in ticket')) : null));
      return;
    }
    replace(list,
      h('ul', { class: 'request-list' }, items.map(item => h('li', null,
        h('a', { class: 'request-row', href: `/admin/requests/${encodeURIComponent(item.id)}`, 'data-nav': '' },
          h('span', { class: 'request-main' },
            h('span', { class: 'request-name' }, item.customerName || 'Customer'),
            h('span', { class: 'request-meta' }, itemLabel(item.itemType), ' · ', locationName(item.dropoffLocation), item.source === 'walk_in' ? ' · Walk-in' : '', item.photoCount ? ` · ${item.photoCount} photo${item.photoCount === 1 ? '' : 's'}` : '')),
          h('span', { class: 'request-side' },
            statusBadge(item.status),
            item.responsePending ? badge('Customer replied', 'warn') : null,
            deliveryBadges(item.delivery),
            h('span', { class: 'request-dates' }, `Received ${formatShortDate(item.createdAt)}`, item.neededBy ? ` · Needed by ${formatLocalDate(item.neededBy)}` : ''),
            h('span', { class: 'request-ref' }, item.reference)),
          icon('chevron', { size: 20 }))))),
      pager(cursor, () => load({ more: true })));
  }

  for (const input of filters.inputs) input.addEventListener('change', () => {
    state.filter = input.value; nrWrap.hidden = state.filter !== 'all'; if (state.filter !== 'all') { state.notRepairable = false; nr.checked = false; }
    save(); load();
  });
  locSelect.addEventListener('change', () => { state.location = locSelect.value; save(); load(); });
  nr.addEventListener('change', () => { state.notRepairable = nr.checked; save(); load(); });
  searchForm.addEventListener('submit', async event => {
    event.preventDefault();
    state.q = search.value;
    save();
    const btn = searchForm.querySelector('button[type="submit"]');
    setBusy(btn, true);
    await load();
    setBusy(btn, false);
  });
  search.addEventListener('search', () => { if (!search.value && state.q) { state.q = ''; save(); load(); } });

  replace(main,
    pageHead('Requests', { actions: h('a', { class: 'btn btn-primary btn-small', href: '/admin/requests/new', 'data-nav': '' }, icon('plus', { size: 18 }), h('span', { class: 'btn-label' }, 'New ticket')) }),
    h('div', { class: 'panel panel-tools' }, filters.wrap, searchForm),
    list);
  await load();
}
