// /admin/login: Google is the only sign-in. Callback failures arrive as ?error=<code>.
import { h, icon, replace, button, setBusy } from '../../lib/dom.js';
import { ApiError } from '../../lib/api.js';
import { loadSession, startGoogle, safeReturnTo, inlineAlert, session } from '../core.js';

export const LOGIN_ERRORS = {
  signin_cancelled: 'Sign-in was cancelled. Try again when you’re ready.',
  signin_expired: 'The sign-in took too long and expired. Try again.',
  account_not_invited: 'That Google account hasn’t been invited. Ask an Admin to invite you, then sign in with that account.',
  invite_unavailable: 'That invitation is no longer available. Ask an Admin for a new one.',
  invite_account_mismatch: 'That Google account doesn’t match the invitation. Sign in with the account the invitation was sent to.',
  google_unavailable: 'Google sign-in is unavailable right now. Try again shortly.',
  sender_permission_denied: 'Gmail permission wasn’t granted, so the sender wasn’t connected. Sign in and try again from Emails.',
};

export default async function login({ main, navigate }) {
  const params = new URLSearchParams(location.search);
  const code = params.get('error');
  const returnTo = safeReturnTo(params.get('returnTo') || '/admin/requests');
  const signedOut = params.has('signedOut');
  if (location.search) history.replaceState(null, '', '/admin/login');

  if (!signedOut && !code) {
    try {
      await loadSession();
      navigate(returnTo, { replaceState: true });
      return;
    } catch (error) {
      session.data = null;
      if (!(error instanceof ApiError) || error.status !== 401) { /* show the sign-in card anyway */ }
    }
  }

  const slot = h('div', { class: 'form-alert-slot' });
  if (code) replace(slot, inlineAlert(LOGIN_ERRORS[code] || 'Sign-in didn’t complete. Try again.'));
  else if (signedOut) replace(slot, inlineAlert('You’re signed out. Unsaved staff drafts on this device were cleared.', 'ok'));
  const go = button('Continue with Google', { variant: 'primary', class: 'btn-large' }, 'arrow');
  go.addEventListener('click', async () => {
    setBusy(go, true, 'Opening Google');
    replace(slot);
    try {
      await startGoogle({ returnTo });
    } catch (error) {
      setBusy(go, false);
      const message = error instanceof ApiError && error.code === 'INTEGRATION_UNAVAILABLE'
        ? 'Google sign-in isn’t set up for this environment yet.'
        : error instanceof ApiError && error.code === 'RATE_LIMITED' ? 'Too many sign-in attempts. Wait a few minutes and try again.' : error.message;
      replace(slot, inlineAlert(message));
    }
  });
  replace(main, h('div', { class: 'login-card' },
    h('img', { class: 'login-mark', src: '/media/clarke-mark.png', alt: '', width: 54, height: 64 }),
    h('h1', { class: 'form-title-sm', tabindex: '-1' }, 'Staff sign-in'),
    h('p', { class: 'muted' }, 'Sign in with the Google account the shop invited. There are no passwords here.'),
    slot,
    h('div', { class: 'form-actions' }, go),
    h('p', { class: 'small' }, h('a', { href: '/' }, icon('arrow-left', { size: 16 }), ' Back to the website'))));
  main.querySelector('h1').focus({ preventScroll: true });
  document.title = 'Staff sign-in | Clarke’s Express';
}
