// /admin/emails (Admin): Gmail sender connection, test message, disconnect and the
// outbox list. Separate from staff sign-in: signing out never disconnects the sender.
import { h, icon, replace, button, setBusy, uid } from '../../lib/dom.js';
import { get, post, ApiError } from '../../lib/api.js';
import { uuid } from '../../lib/store.js';
import { textField, setError } from '../../lib/fields.js';
import { pageHead, panel, badge, showError, inlineAlert, confirmDialog, emptyState, loadingState, pager, when, redirectToGoogle, viewState } from '../core.js';

export const OUTBOX_STATUS = {
  pending: ['Waiting to send', 'neutral'], sending: ['Sending', 'neutral'], sent: ['Sent', 'ready'], retry_wait: ['Will retry', 'wait'],
  failed: ['Failed', 'danger'], uncertain: ['Uncertain', 'warn'], preview_only: ['Preview only', 'muted'], cancelled: ['Cancelled', 'muted'],
};
export const KIND = {
  customer_received: 'Request received', staff_new_request: 'New request alert', customer_estimate: 'Estimate', customer_needs_visit: 'Please bring it in',
  customer_not_repairable: 'Can’t repair', customer_ready: 'Ready for pickup', staff_customer_response: 'Customer reply alert', team_invite: 'Team invitation',
  connection_test: 'Connection test', staff_new_ticket: 'New ticket alert',
};
const CONN = { disconnected: ['Not connected', 'muted'], connected: ['Connected', 'ready'], reconnect_required: ['Reconnect needed', 'danger'], degraded: ['Having trouble', 'warn'] };

export default async function emails({ main, sessionExpired }) {
  const ctx = { sessionExpired };
  const params = new URLSearchParams(location.search);
  const connected = params.get('connection');
  const requestId = /^[0-9a-f-]{36}$/i.test(params.get('requestId') || '') ? params.get('requestId') : null;
  if (connected) history.replaceState(null, '', requestId ? `/admin/emails?requestId=${requestId}` : '/admin/emails');

  const connBox = h('div', { class: 'stack' });
  const connSlot = h('div', { class: 'form-alert-slot' });
  let conn = await get('/admin/email/connection');

  function drawConnection() {
    const [label, tone] = CONN[conn.state] || [conn.state, 'neutral'];
    const connect = button(conn.state === 'disconnected' ? 'Connect Gmail sender' : 'Reconnect', { variant: conn.state === 'connected' ? 'secondary' : 'primary', class: 'btn-small' });
    connect.addEventListener('click', async () => {
      setBusy(connect, true, 'Opening Google');
      try {
        const data = await post('/admin/email/connect', { expectedVersion: conn.version, returnTo: '/admin/emails' });
        redirectToGoogle(data.authorizationUrl);
      } catch (error) {
        setBusy(connect, false);
        if (error instanceof ApiError && error.code === 'INTEGRATION_UNAVAILABLE') replace(connSlot, inlineAlert('Google isn’t set up for this environment yet.'));
        else showError(connSlot, error, ctx, { onReload: reloadConnection });
      }
    });
    const disconnect = conn.state === 'disconnected' ? null : button('Disconnect', { variant: 'quiet', class: 'btn-small' });
    disconnect?.addEventListener('click', async () => {
      const ok = await confirmDialog({ title: 'Disconnect the Gmail sender?', body: 'Email delivery turns off and unsent emails are cancelled. Requests keep saving. You can reconnect later.', confirmLabel: 'Disconnect', danger: true });
      if (!ok) return;
      setBusy(disconnect, true);
      try {
        await post('/admin/email/disconnect', { expectedVersion: conn.version }, { idempotencyKey: uuid() });
        await reloadConnection();
        replace(connSlot, inlineAlert('Sender disconnected. Delivery is off.', 'ok'));
      } catch (error) { setBusy(disconnect, false); showError(connSlot, error, ctx, { onReload: reloadConnection }); }
    });
    const q = conn.queue || {};
    replace(connBox,
      h('div', { class: 'conn-head' }, badge(label, tone), conn.demoMode ? badge('Demo mode', 'demo') : null, badge(conn.deliveryEnabled ? 'Delivery on' : 'Delivery off', conn.deliveryEnabled ? 'ready' : 'muted')),
      h('dl', { class: 'kv' },
        h('dt', null, 'Sender'), h('dd', null, conn.senderEmail || 'None'),
        h('dt', null, 'Connected'), h('dd', null, when(conn.connectedAt) || '—'),
        h('dt', null, 'Last success'), h('dd', null, when(conn.lastSuccessAt) || '—'),
        h('dt', null, 'Queue'), h('dd', null, `${q.pending || 0} waiting, ${q.retryWait || 0} retrying, ${q.failed || 0} failed, ${q.uncertain || 0} uncertain, ${q.previewOnly || 0} preview only`)),
      conn.lastError ? inlineAlert(conn.lastError.message || 'The sender reported a problem.') : null,
      conn.requiresReconnect || conn.state === 'reconnect_required' ? inlineAlert('Google needs you to reconnect the sender. Requests are still saved; emails wait or fail until it’s reconnected.', 'info') : null,
      conn.demoMode ? h('p', { class: 'small muted' }, 'Demo mode: email only goes to addresses on the private test list. Everything else is saved as a preview below.') : null,
      h('div', { class: 'form-actions' }, connect, disconnect),
      connSlot);
  }
  async function reloadConnection() { conn = await get('/admin/email/connection'); drawConnection(); }
  drawConnection();
  if (connected === 'connected') replace(connSlot, inlineAlert('Gmail sender connected.', 'ok'));

  // Test message
  const recipient = textField({ name: 'testRecipient', label: 'Send a test to', type: 'email', help: 'Must be on the private test list while demo mode is on.', attrs: { autocomplete: 'off', maxlength: 254 } });
  const testSlot = h('div', { class: 'form-alert-slot' });
  const testBtn = h('button', { type: 'submit', class: 'btn btn-secondary btn-small' }, h('span', { class: 'btn-label' }, 'Send test email'));
  const testForm = h('form', { class: 'stack', novalidate: true }, recipient.wrap, testSlot, h('div', { class: 'form-actions' }, testBtn));
  let testKey = null; let testFor = null;
  testForm.addEventListener('submit', async event => {
    event.preventDefault();
    replace(testSlot);
    setError(recipient.input, null);
    const value = recipient.input.value.trim();
    if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(value)) { setError(recipient.input, 'Enter a valid email address.'); recipient.input.focus(); return; }
    if (testFor !== value) { testKey = uuid(); testFor = value; }
    setBusy(testBtn, true, 'Queuing');
    try {
      const r = await post('/admin/email/test', { recipient: value }, { idempotencyKey: testKey });
      testKey = null; testFor = null;
      replace(testSlot, inlineAlert('Test email queued. “Sent” below means Google accepted it; check the inbox to confirm it arrived.', 'ok',
        h('a', { href: `/admin/emails/outbox/${encodeURIComponent(r.outboxId)}`, 'data-nav': '' }, 'View in the email log')));
      loadOutbox();
    } catch (error) {
      if (error instanceof ApiError && error.code === 'DEMO_DESTINATION_BLOCKED') replace(testSlot, inlineAlert('Demo mode: that address isn’t on the private test list, so nothing was queued.'));
      else if (error instanceof ApiError && error.code === 'SENDER_DISCONNECTED') replace(testSlot, inlineAlert('Connect the Gmail sender first.'));
      else showError(testSlot, error, ctx);
    } finally { setBusy(testBtn, false); }
  });

  // Outbox
  const state = { status: '', ...(viewState('outbox') || {}) };
  const filterId = uid('outbox-filter');
  const filter = h('select', { id: filterId }, h('option', { value: '' }, 'All'), Object.entries(OUTBOX_STATUS).map(([v, [l]]) => h('option', { value: v }, l)));
  filter.value = state.status;
  const outboxBox = h('div');
  let rows = []; let cursor = null;
  async function loadOutbox(more = false) {
    if (!more) replace(outboxBox, loadingState());
    try {
      const page = await get('/admin/outbox', { query: { status: state.status || undefined, requestId: requestId || undefined, limit: 25, cursor: more ? cursor : undefined } });
      rows = more ? [...rows, ...page.items] : page.items;
      cursor = page.nextCursor;
      drawOutbox();
    } catch (error) {
      if (error instanceof ApiError && error.code === 'INVALID_CURSOR') { cursor = null; return loadOutbox(); }
      showError(outboxBox, error, ctx);
    }
    return undefined;
  }
  function drawOutbox() {
    if (!rows.length) { replace(outboxBox, emptyState('No emails here', state.status ? 'Nothing with this status.' : 'Emails appear here as requests come in.')); return; }
    replace(outboxBox, h('ul', { class: 'request-list' }, rows.map(r => {
      const [label, tone] = OUTBOX_STATUS[r.status] || [r.status, 'neutral'];
      return h('li', null, h('a', { class: 'request-row', href: `/admin/emails/outbox/${encodeURIComponent(r.id)}`, 'data-nav': '' },
        h('span', { class: 'request-main' }, h('span', { class: 'request-name' }, r.subject || KIND[r.kind] || r.kind), h('span', { class: 'request-meta' }, KIND[r.kind] || r.kind, ' · to ', r.recipient)),
        h('span', { class: 'request-side' }, badge(label, tone), r.lastError ? h('span', { class: 'small' }, r.lastError.message) : null, h('span', { class: 'request-dates' }, when(r.sentAt || r.createdAt))),
        icon('chevron', { size: 20 })));
    })), pager(cursor, () => loadOutbox(true)));
  }
  filter.addEventListener('change', () => { state.status = filter.value; viewState('outbox', state); loadOutbox(); });

  replace(main,
    pageHead('Emails', { sub: 'The Gmail account that sends customer and staff emails, and a log of every email.' }),
    h('div', { class: 'detail-grid' },
      h('div', { class: 'detail-main' },
        panel(requestId ? 'Email log for one request' : 'Email log',
          requestId ? h('p', { class: 'small' }, h('a', { href: `/admin/requests/${requestId}`, 'data-nav': '' }, 'Back to the request'), ' · ', h('a', { href: '/admin/emails', 'data-nav': '' }, 'Show all emails')) : null,
          h('div', { class: 'field inline-field' }, h('label', { for: filterId }, 'Status'), h('div', { class: 'select-wrap' }, filter, icon('chevron-down', { size: 18 }))),
          outboxBox)),
      h('div', { class: 'detail-side' }, panel('Sender', connBox), panel('Test', testForm))));
  await loadOutbox();
}
