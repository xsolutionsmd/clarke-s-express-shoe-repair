// /admin/emails/outbox/{id} (Admin): one email with a sandboxed preview, attempts and a
// retry that requires explicit acknowledgement when an earlier send may have gone out.
import { h, replace, setBusy } from '../../lib/dom.js';
import { get, post, ApiError } from '../../lib/api.js';
import { uuid } from '../../lib/store.js';
import { pageHead, panel, badge, showError, inlineAlert, when } from '../core.js';
import { OUTBOX_STATUS, KIND } from './emails.js';

const POLICY = {
  demo_recipient_blocked: 'Demo mode: this recipient isn’t on the private test list, so the email was saved as a preview and not sent.',
  delivery_disabled: 'Email delivery was off when this was created, so it was saved as a preview and not sent.',
};

export default async function outbox({ main, params, sessionExpired }) {
  const ctx = { sessionExpired };
  const id = params[0];
  let mail = await get(`/admin/outbox/${encodeURIComponent(id)}`);
  const view = h('div');
  let retryKey = null;

  function draw() {
    const [label, tone] = OUTBOX_STATUS[mail.status] || [mail.status, 'neutral'];
    const tabs = h('div', { class: 'segmented preview-tabs', role: 'radiogroup', 'aria-label': 'Preview format' },
      h('label', null, h('input', { type: 'radio', name: 'previewFormat', value: 'html', checked: true }), h('span', null, 'Formatted')),
      h('label', null, h('input', { type: 'radio', name: 'previewFormat', value: 'text' }), h('span', null, 'Plain text')));
    // Server-rendered, escaped template HTML in a fully sandboxed frame: no scripts,
    // forms, navigation or same-origin access.
    const frame = mail.bodyHtml ? h('iframe', { class: 'mail-frame', title: 'Email preview', sandbox: '', referrerpolicy: 'no-referrer', loading: 'lazy' }) : null;
    if (frame) frame.srcdoc = mail.bodyHtml;
    const text = h('pre', { class: 'message-preview', hidden: Boolean(frame) }, mail.bodyText || '');
    tabs.addEventListener('change', () => {
      const mode = tabs.querySelector('input:checked').value;
      if (frame) frame.hidden = mode !== 'html';
      text.hidden = mode !== 'text' && Boolean(frame);
    });
    const slot = h('div', { class: 'form-alert-slot' });
    const ack = h('input', { type: 'checkbox', id: 'retry-ack' });
    const retry = h('button', { type: 'button', class: 'btn btn-primary btn-small' }, h('span', { class: 'btn-label' }, 'Retry sending'));
    retry.addEventListener('click', async () => {
      replace(slot);
      if (mail.retryNeedsDuplicateAcknowledgement && !ack.checked) { replace(slot, inlineAlert('Tick the box to confirm you accept a possible duplicate email.')); ack.focus(); return; }
      retryKey ||= uuid();
      setBusy(retry, true, 'Queuing');
      try {
        await post(`/admin/outbox/${encodeURIComponent(id)}/retry`, { expectedVersion: mail.version, acknowledgePossibleDuplicate: Boolean(mail.retryNeedsDuplicateAcknowledgement && ack.checked) }, { idempotencyKey: retryKey });
        retryKey = null;
        mail = await get(`/admin/outbox/${encodeURIComponent(id)}`);
        draw();
        replace(view.querySelector('.form-alert-slot'), inlineAlert('Queued for sending. Check back for the result.', 'ok'));
      } catch (error) {
        setBusy(retry, false);
        if (error instanceof ApiError && error.code === 'EMAIL_NOT_RETRYABLE') { replace(slot, inlineAlert('This email can no longer be retried.')); return; }
        if (error instanceof ApiError && error.code === 'SENDER_DISCONNECTED') { replace(slot, inlineAlert('Connect the Gmail sender and turn on delivery, then retry.')); return; }
        showError(slot, error, ctx, { onReload: async () => { retryKey = null; mail = await get(`/admin/outbox/${encodeURIComponent(id)}`); draw(); } });
      }
    });
    const retryPanel = mail.canRetry
      ? panel('Retry',
        mail.retryNeedsDuplicateAcknowledgement ? inlineAlert('This email may already have been delivered: the connection dropped after it was handed to Google. Sending again could create a duplicate.', 'info') : null,
        mail.retryNeedsDuplicateAcknowledgement ? h('label', { class: 'check-inline', for: 'retry-ack' }, ack, ' I understand this may send a duplicate email.') : null,
        h('div', { class: 'form-actions' }, retry), slot)
      : panel('Retry', h('p', { class: 'muted' }, mail.bodyPurged ? 'The message body has been deleted under the retention policy, so it can’t be resent.'
        : mail.status === 'sent' ? 'Google accepted this email. Inbox delivery is confirmed only by the recipient.'
          : mail.status === 'preview_only' ? 'Previews are never sent later, even if demo mode, the test list or the sender changes.'
          : mail.status === 'cancelled' ? 'This email was cancelled because a newer message replaced it or the sender was disconnected.'
          : mail.lastError?.message || 'This email can’t be retried right now.'), slot);
    replace(view,
      pageHead(mail.subject || KIND[mail.kind] || 'Email', { back: { href: '/admin/emails', label: 'Email log' }, actions: badge(label, tone) }),
      h('div', { class: 'detail-grid' },
        h('div', { class: 'detail-main' },
          panel('Preview',
            mail.policyReason ? inlineAlert(POLICY[mail.policyReason] || 'Saved as a preview, not sent.', 'info') : null,
            mail.bodyPurged ? h('p', { class: 'muted' }, 'The message body was deleted after the retention period.') : h('div', { class: 'stack' }, frame ? tabs : null, frame, text))),
        h('div', { class: 'detail-side' },
          panel('Details', h('dl', { class: 'kv' },
            h('dt', null, 'Type'), h('dd', null, KIND[mail.kind] || mail.kind),
            h('dt', null, 'To'), h('dd', null, mail.recipient),
            h('dt', null, 'Created'), h('dd', null, when(mail.createdAt)),
            h('dt', null, 'Sent'), h('dd', null, when(mail.sentAt) || '—'),
            h('dt', null, 'Next try'), h('dd', null, when(mail.nextAttemptAt) || '—'),
            h('dt', null, 'Attempts'), h('dd', null, String(mail.attemptCount ?? 0))),
            mail.lastError ? inlineAlert(mail.lastError.message) : null,
            mail.requestId ? h('p', null, h('a', { href: `/admin/requests/${encodeURIComponent(mail.requestId)}`, 'data-nav': '' }, 'Open the request')) : null),
          retryPanel,
          panel('Attempts', (mail.attempts || []).length ? h('ol', { class: 'event-list' }, mail.attempts.map(a => h('li', null,
            h('div', { class: 'event-head' }, h('strong', null, `Attempt ${a.number}`), badge(a.result, a.result === 'sent' ? 'ready' : a.result === 'failed' ? 'danger' : 'neutral')),
            h('p', { class: 'small muted' }, when(a.startedAt), a.errorCode ? ` · ${a.errorCode}` : '')))) : h('p', { class: 'muted' }, 'No send attempts.')))));
  }
  draw();
  replace(main, view);
}
