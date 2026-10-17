// /admin/team (Admin): members, roles, removal (never the last Admin) and email-bound
// invitations. A suppressed demo invite still gets an Admin-only copyable link.
import { h, replace, button, setBusy, uid } from '../../lib/dom.js';
import { get, post, patch, del, ApiError } from '../../lib/api.js';
import { uuid } from '../../lib/store.js';
import { textField, choiceGroup, setError } from '../../lib/fields.js';
import { pageHead, panel, badge, showError, inlineAlert, confirmDialog, emptyState, pager, when, memberId, copyText, logout } from '../core.js';

const ROLE = { admin: 'Admin', viewer: 'Viewer' };
const INVITE_STATE = { pending: ['Pending', 'wait'], accepted: ['Accepted', 'ready'], expired: ['Expired', 'muted'], revoked: ['Withdrawn', 'muted'] };

export default async function team({ main, navigate, sessionExpired }) {
  const ctx = { sessionExpired };
  const membersBox = h('div');
  const invitesBox = h('div');
  const membersSlot = h('div', { class: 'form-alert-slot' });
  let members = []; let membersCursor = null;
  let invites = []; let invitesCursor = null;

  async function loadMembers(more = false) {
    const page = await get('/admin/team/members', { query: { limit: 50, cursor: more ? membersCursor : undefined } });
    members = more ? [...members, ...page.items] : page.items;
    membersCursor = page.nextCursor;
    drawMembers();
  }
  async function loadInvites(more = false) {
    const page = await get('/admin/team/invitations', { query: { limit: 25, cursor: more ? invitesCursor : undefined } });
    invites = more ? [...invites, ...page.items] : page.items;
    invitesCursor = page.nextCursor;
    drawInvites();
  }

  function drawMembers() {
    replace(membersBox, h('ul', { class: 'member-list' }, members.map(m => {
      const self = m.id === memberId();
      const roleId = uid('role');
      const role = h('select', { id: roleId, disabled: !m.active }, h('option', { value: 'admin' }, 'Admin'), h('option', { value: 'viewer' }, 'Viewer'));
      role.value = m.role;
      const saveRole = button('Save role', { variant: 'secondary', class: 'btn-small', hidden: true });
      role.addEventListener('change', () => { saveRole.hidden = role.value === m.role; });
      saveRole.addEventListener('click', async () => {
        if (self && role.value !== 'admin') {
          const ok = await confirmDialog({ title: 'Change your own role to Viewer?', body: 'You’ll be signed out and lose access to settings, team and email.', confirmLabel: 'Change my role', danger: true });
          if (!ok) { role.value = m.role; saveRole.hidden = true; return; }
        }
        setBusy(saveRole, true, 'Saving');
        try {
          await patch(`/admin/team/members/${encodeURIComponent(m.id)}`, { expectedVersion: m.version, role: role.value }, { idempotencyKey: uuid() });
          if (self) { await logout(); navigate('/admin/login?signedOut=1', { replaceState: true }); return; }
          replace(membersSlot, inlineAlert(`${m.email} is now ${ROLE[role.value]}. Their open sessions were signed out.`, 'ok'));
          await loadMembers();
        } catch (error) {
          setBusy(saveRole, false);
          memberError(error);
        }
      });
      const remove = button(self ? 'Leave team' : 'Remove', { variant: 'quiet', class: 'btn-small', hidden: !m.active });
      remove.addEventListener('click', async () => {
        const ok = await confirmDialog({
          title: self ? 'Remove yourself from the team?' : `Remove ${m.email}?`,
          body: self ? 'You’ll be signed out immediately.' : 'They lose access right away. Their past activity stays in the audit log.',
          confirmLabel: 'Remove', danger: true,
        });
        if (!ok) return;
        setBusy(remove, true);
        try {
          await del(`/admin/team/members/${encodeURIComponent(m.id)}`, { expectedVersion: m.version }, { idempotencyKey: uuid() });
          if (self) { await logout(); navigate('/admin/login?signedOut=1', { replaceState: true }); return; }
          replace(membersSlot, inlineAlert(`${m.email} was removed.`, 'ok'));
          await loadMembers();
        } catch (error) { setBusy(remove, false); memberError(error); }
      });
      return h('li', { class: 'member-row' },
        h('div', { class: 'member-main' },
          h('p', { class: 'member-email' }, m.email, self ? ' (you)' : ''),
          h('p', { class: 'small muted' }, m.active ? (m.googleBound ? `Joined ${when(m.joinedAt)}` : 'Hasn’t signed in yet') : 'Removed'),
          h('span', { class: 'badge-row' }, badge(ROLE[m.role], m.role === 'admin' ? 'ready' : 'neutral'), m.active ? null : badge('Inactive', 'muted'))),
        m.active ? h('div', { class: 'member-actions' }, h('label', { class: 'visually-hidden', for: roleId }, `Role for ${m.email}`), h('div', { class: 'select-wrap' }, role), saveRole, remove) : null);
    })), pager(membersCursor, () => loadMembers(true)));
  }

  function memberError(error) {
    if (error instanceof ApiError && error.code === 'LAST_ADMIN') {
      replace(membersSlot, inlineAlert('You can’t remove or demote the last Admin who has signed in. Invite another Admin and let them sign in first.'));
      return;
    }
    showError(membersSlot, error, ctx, { onReload: () => loadMembers() });
  }

  function drawInvites() {
    if (!invites.length) { replace(invitesBox, emptyState('No invitations', 'Invite staff by email below.')); return; }
    replace(invitesBox, h('ul', { class: 'member-list' }, invites.map(inv => {
      const [label, tone] = INVITE_STATE[inv.state] || [inv.state, 'neutral'];
      const revoke = inv.state === 'pending' ? button('Withdraw', { variant: 'quiet', class: 'btn-small' }) : null;
      revoke?.addEventListener('click', async () => {
        const ok = await confirmDialog({ title: `Withdraw the invitation for ${inv.email}?`, body: 'The link stops working and any unsent invitation email is cancelled.', confirmLabel: 'Withdraw', danger: true });
        if (!ok) return;
        setBusy(revoke, true);
        try { await del(`/admin/team/invitations/${encodeURIComponent(inv.id)}`, { expectedVersion: inv.version }); await loadInvites(); } catch (error) { setBusy(revoke, false); showError(inviteSlot, error, ctx, { onReload: () => loadInvites() }); }
      });
      return h('li', { class: 'member-row' },
        h('div', { class: 'member-main' },
          h('p', { class: 'member-email' }, inv.email),
          h('p', { class: 'small muted' }, `${ROLE[inv.role]} · sent ${when(inv.createdAt)} · ${inv.state === 'pending' ? `expires ${when(inv.expiresAt)}` : label}`),
          badge(label, tone)),
        revoke ? h('div', { class: 'member-actions' }, revoke) : null);
    })), pager(invitesCursor, () => loadInvites(true)));
  }

  // Invite form
  const email = textField({ name: 'inviteEmail', label: 'Email', type: 'email', help: 'They must sign in with the Google account for this exact address.', attrs: { autocomplete: 'off', maxlength: 254 } });
  const role = choiceGroup({ name: 'inviteRole', legend: 'Role', segmented: true, value: 'viewer', options: [['viewer', 'Viewer', 'Requests only'], ['admin', 'Admin', 'Everything']] });
  const inviteSlot = h('div', { class: 'form-alert-slot' });
  const inviteResult = h('div');
  const send = h('button', { type: 'submit', class: 'btn btn-primary btn-small' }, h('span', { class: 'btn-label' }, 'Send invitation'));
  const form = h('form', { class: 'stack', novalidate: true }, email.wrap, role.wrap, inviteSlot, h('div', { class: 'form-actions' }, send), inviteResult);
  let inviteKey = null; let invitePayload = null;
  form.addEventListener('submit', async event => {
    event.preventDefault();
    replace(inviteSlot); replace(inviteResult);
    setError(email.input, null);
    const value = email.input.value.trim();
    if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(value)) { setError(email.input, 'Enter a valid email address.'); email.input.focus(); return; }
    const body = { email: value, role: role.inputs.find(i => i.checked).value };
    const text = JSON.stringify(body);
    if (text !== invitePayload) { inviteKey = uuid(); invitePayload = text; }
    setBusy(send, true, 'Sending');
    try {
      const result = await post('/admin/team/invitations', body, { idempotencyKey: inviteKey });
      inviteKey = null; invitePayload = null;
      email.input.value = '';
      const copy = button('Copy invitation link', { variant: 'secondary', class: 'btn-small' }, 'copy');
      copy.addEventListener('click', () => copyText(result.inviteUrl, copy));
      const delivery = result.deliveryState === 'preview_only'
        ? 'Demo mode: no email was sent to this address. Copy the link and share it yourself.'
        : result.deliveryState === 'pending' || result.deliveryState === 'queued' ? 'An invitation email is queued. Check the email log for delivery.' : 'Copy the link to share it yourself if needed.';
      replace(inviteResult, inlineAlert(`Invitation created for ${result.invitation.email}. It expires ${when(result.invitation.expiresAt)}. ${delivery}`, 'ok',
        h('div', { class: 'stack' }, h('p', { class: 'small muted' }, 'The link works only for that Google account. Treat it like a key.'), h('div', { class: 'form-actions' }, copy))));
      await loadInvites();
    } catch (error) {
      if (error instanceof ApiError && error.code === 'MEMBER_EXISTS') { replace(inviteSlot, inlineAlert('That person is already an active member.')); return; }
      if (error instanceof ApiError && error.fields?.email) { setError(email.input, error.fields.email); email.input.focus(); return; }
      showError(inviteSlot, error, ctx);
    } finally { setBusy(send, false); }
  });

  await Promise.all([loadMembers(), loadInvites()]);
  replace(main,
    pageHead('Team', { sub: 'Everyone signs in with Google. Viewers handle requests; Admins also manage hours, notices, settings, team and email.' }),
    h('div', { class: 'detail-grid' },
      h('div', { class: 'detail-main' }, panel('Members', membersSlot, membersBox), panel('Invitations', invitesBox)),
      h('div', { class: 'detail-side' }, panel('Invite someone', form))));
}
