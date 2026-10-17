// /admin/invite#token=...: the fragment is removed at once and only sent in POST bodies.
import { h, replace, button, setBusy } from '../../lib/dom.js';
import { post, bootstrap, useAnonymousCsrf, ApiError } from '../../lib/api.js';
import { startGoogle, inlineAlert } from '../core.js';
import { formatDateTime } from '../../lib/format.js';

let held = null;

export default async function invite({ main }) {
  const token = new URLSearchParams(location.hash.slice(1)).get('token');
  if (location.hash) history.replaceState(null, '', '/admin/invite');
  if (token) held = token;
  const card = h('div', { class: 'login-card' });
  replace(main, card);
  const done = (title, body, tone = 'error') => {
    replace(card,
      h('img', { class: 'login-mark', src: '/media/clarke-mark.png', alt: '', width: 54, height: 64 }),
      h('h1', { class: 'form-title-sm', tabindex: '-1' }, title),
      body ? inlineAlert(body, tone) : null,
      h('p', { class: 'small' }, h('a', { href: '/admin/login' }, 'Go to staff sign-in')));
    card.querySelector('h1').focus({ preventScroll: true });
  };
  if (!held) { done('Invitation link incomplete', 'Open the full link from your invitation email, or ask an Admin for a new one.'); return; }
  replace(card, h('p', { class: 'muted', role: 'status' }, 'Checking your invitation…'));
  let info;
  try {
    useAnonymousCsrf();
    await bootstrap({ force: true });
    info = await post('/auth/invitations/inspect', { token: held });
  } catch (error) {
    if (error instanceof ApiError && error.code === 'INVITE_UNAVAILABLE') { held = null; done('Invitation unavailable', 'This invitation has expired, was already used or was withdrawn. Ask an Admin for a new one.'); return; }
    done('Couldn’t check the invitation', error.message);
    return;
  }
  const slot = h('div', { class: 'form-alert-slot' });
  const go = button('Continue with Google', { variant: 'primary', class: 'btn-large' }, 'arrow');
  go.addEventListener('click', async () => {
    setBusy(go, true, 'Opening Google');
    try { await startGoogle({ returnTo: '/admin/requests', inviteToken: held }); } catch (error) { setBusy(go, false); replace(slot, inlineAlert(error.message)); }
  });
  replace(card,
    h('img', { class: 'login-mark', src: '/media/clarke-mark.png', alt: '', width: 54, height: 64 }),
    h('h1', { class: 'form-title-sm', tabindex: '-1' }, 'You’re invited to the staff area'),
    h('p', null, `Role: ${info.role === 'admin' ? 'Admin' : 'Viewer'}. `, info.expiresAt ? `This invitation expires ${formatDateTime(info.expiresAt)}.` : ''),
    h('p', { class: 'muted' }, info.message || 'Sign in with the Google account this invitation was sent to.'),
    slot,
    h('div', { class: 'form-actions' }, go));
  card.querySelector('h1').focus({ preventScroll: true });
}
