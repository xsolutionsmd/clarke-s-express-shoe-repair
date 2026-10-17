// Draft photo uploads: one XHR per file with real transfer progress, then server-side
// conversion polled 1s, 2s, then every 5s (paused while the tab is hidden). Files are
// never written to browser storage; after a refresh the list shows "Photo attached".
import { uploadFile, get, del, ApiError } from '../lib/api.js';
import { h, icon, replace, announce } from '../lib/dom.js';
import { uuid } from '../lib/store.js';
import { bytes } from '../lib/format.js';

const PREVIEWABLE = new Set(['image/jpeg', 'image/png', 'image/webp']);
const HEIC = /\.(heic|heif)$/i;
const ALLOWED_EXT = /\.(jpe?g|png|webp|heic|heif)$/i;
const POLL = [1000, 2000, 5000];

export class PhotoManager {
  constructor({ list, notice, input, dropzone, limits, ensureDraft, onDraftLost, onChange }) {
    this.list = list;
    this.notice = notice;
    this.input = input;
    this.dropzone = dropzone;
    this.limits = limits;
    this.ensureDraft = ensureDraft;
    this.onDraftLost = onDraftLost;
    this.onChange = onChange;
    this.items = [];
    this.active = 0;
    this.waiters = [];
    input.addEventListener('change', () => { this.add([...input.files]); input.value = ''; });
    this.bindDrop();
    document.addEventListener('visibilitychange', () => { if (!document.hidden) this.items.forEach(item => this.resumePoll(item)); });
  }

  setLimits(limits) { this.limits = limits; this.renderNotice(); }

  bindDrop() {
    const zone = this.dropzone;
    const stop = event => { event.preventDefault(); event.stopPropagation(); };
    zone.addEventListener('dragenter', event => { stop(event); zone.classList.add('is-dragging'); });
    zone.addEventListener('dragover', event => { stop(event); zone.classList.add('is-dragging'); });
    zone.addEventListener('dragleave', event => { if (!zone.contains(event.relatedTarget)) zone.classList.remove('is-dragging'); });
    zone.addEventListener('drop', event => {
      stop(event);
      zone.classList.remove('is-dragging');
      if (event.dataTransfer?.files?.length) this.add([...event.dataTransfer.files]);
    });
  }

  // Items that hold (or will hold) one of the draft's photo slots.
  slotItems() { return this.items.filter(i => i.state !== 'local-rejected'); }

  restore(saved) {
    for (const s of saved || []) {
      const item = { ...s, localId: s.localId || uuid(), file: null, url: null, progress: null };
      if (!item.photoId && ['queued', 'uploading'].includes(item.state)) item.state = 'interrupted';
      if (item.state === 'failed' && !item.photoId) item.state = 'interrupted';
      this.items.push(item);
    }
    this.render();
  }

  // Reconcile against GET /drafts/{id} photo metadata after a reload.
  reconcile(serverPhotos) {
    const byId = new Map((serverPhotos || []).map(p => [p.photoId, p]));
    for (const item of this.items) {
      if (!item.photoId) continue;
      const p = byId.get(item.photoId);
      if (!p || p.state === 'deleted') { item.state = 'expired'; continue; }
      this.applyServer(item, p);
    }
    // Photos the server knows about but this tab lost track of still occupy slots.
    for (const p of serverPhotos || []) {
      if (p.state === 'deleted' || this.items.some(i => i.photoId === p.photoId)) continue;
      const item = { localId: uuid(), photoId: p.photoId, key: null, name: 'Photo', size: p.bytes, type: p.mediaType, file: null, url: null };
      this.applyServer(item, p);
      this.items.push(item);
    }
    this.items.forEach(item => this.resumePoll(item));
    this.changed();
  }

  applyServer(item, p) {
    item.state = p.state === 'ready' ? 'ready' : p.state === 'rejected' ? 'rejected' : 'processing';
    item.error = p.error?.message || null;
    if (p.bytes) item.outBytes = p.bytes;
  }

  draftLost() {
    // Draft expired or vanished: files still in memory are re-queued to a new draft.
    for (const item of this.items) {
      if (item.state === 'local-rejected') continue;
      window.clearTimeout(item.pollTimer);
      item.photoId = null;
      item.key = uuid();
      if (item.file) { item.state = 'queued'; item.error = null; } else { item.state = 'expired'; item.error = null; }
    }
    this.pump();
    this.changed();
  }

  add(files) {
    const limits = this.limits;
    let skipped = 0;
    for (const file of files) {
      const typeOk = limits.mimeTypes.includes(file.type) || ALLOWED_EXT.test(file.name || '');
      const item = { localId: uuid(), key: uuid(), photoId: null, name: file.name || 'Photo', size: file.size, type: file.type, file, url: null, progress: null, error: null };
      if (this.slotItems().length >= limits.maxFiles) { skipped += 1; continue; }
      if (!typeOk) { item.state = 'local-rejected'; item.error = 'This file type can’t be used. Choose a JPEG, PNG, WebP or HEIC photo.'; }
      else if (file.size > limits.maxBytesEach) { item.state = 'local-rejected'; item.error = `This photo is ${bytes(file.size)}. Photos can be up to 10 MB each; try a smaller export.`; }
      else if (file.size === 0) { item.state = 'local-rejected'; item.error = 'This file is empty. Choose another photo.'; }
      else {
        item.state = 'queued';
        if (PREVIEWABLE.has(file.type)) item.url = URL.createObjectURL(file);
      }
      this.items.push(item);
    }
    if (skipped) {
      this.message(`You can add up to ${limits.maxFiles} photos. ${skipped === 1 ? 'One photo was' : `${skipped} photos were`} not added; remove one to make room.`);
    } else this.message(null);
    this.pump();
    this.changed();
  }

  message(text) {
    this.extraMessage = text;
    this.renderNotice();
  }

  renderNotice() {
    const full = this.slotItems().length >= this.limits.maxFiles;
    const text = this.extraMessage || (full ? `You’ve added ${this.limits.maxFiles} photos, the most for one request.` : '');
    replace(this.notice, text ? [icon('alert', { size: 16 }), text] : []);
    this.notice.hidden = !text;
    this.input.disabled = full;
    this.input.closest('.file-button')?.classList.toggle('is-disabled', full);
    this.input.closest('.file-button')?.querySelector('.btn')?.setAttribute('aria-disabled', String(full));
  }

  pump() {
    for (const item of this.items) {
      if (this.active >= 2) break;
      if (item.state === 'queued') this.upload(item);
    }
  }

  async upload(item) {
    this.active += 1;
    item.state = 'uploading';
    item.progress = 0;
    item.error = null;
    this.changed();
    try {
      const draft = await this.ensureDraft();
      item.abort = new AbortController();
      const data = await uploadFile(`/drafts/${encodeURIComponent(draft.id)}/photos`, item.file, {
        draftToken: draft.token, idempotencyKey: item.key, signal: item.abort.signal,
        onProgress: fraction => { item.progress = fraction; this.renderItem(item); },
      });
      item.photoId = data.photoId;
      this.applyServer(item, data);
      announce(`${item.name} uploaded${item.state === 'processing' ? ', converting' : ''}.`);
      if (item.state === 'processing') this.poll(item, 0);
    } catch (error) {
      if (error?.name === 'AbortError') { /* removed by the customer */ }
      else this.uploadFailed(item, error);
    } finally {
      item.abort = null;
      this.active -= 1;
      this.changed();
      this.pump();
    }
  }

  uploadFailed(item, error) {
    if (!(error instanceof ApiError)) { item.state = 'failed'; item.error = 'The upload stopped. Try again.'; return; }
    if (error.code === 'IDEMPOTENCY_IN_PROGRESS') {
      item.state = 'queued';
      window.setTimeout(() => this.pump(), (error.retryAfter || 2) * 1000);
      return;
    }
    if (error.code === 'DRAFT_EXPIRED' || (error.status === 404 && error.code === 'NOT_FOUND')) {
      item.state = 'queued';
      this.onDraftLost?.();
      return;
    }
    if (error.code === 'DRAFT_SUBMITTED') { item.state = 'failed'; item.error = 'This request was already sent.'; this.onDraftLost?.({ submitted: true }); return; }
    if ([413, 415, 422].includes(error.status)) {
      item.state = 'local-rejected';
      item.photoId = null;
      item.error = error.status === 413 ? 'This photo is too large. Photos can be up to 10 MB each.' : error.message;
      announce(`${item.name} could not be used.`, { assertive: true });
      return;
    }
    item.state = 'failed';
    item.error = error.code === 'UPLOAD_CAPACITY'
      ? 'The shop can’t take new photos right now. Try again later, or send the request without photos.'
      : error.code === 'RATE_LIMITED' ? 'Too many photos in a short time. Wait a moment, then retry.' : error.message;
    announce(`${item.name} did not upload.`, { assertive: true });
  }

  poll(item, step) {
    window.clearTimeout(item.pollTimer);
    if (document.hidden) { item.pollPaused = true; return; }
    item.pollPaused = false;
    item.pollTimer = window.setTimeout(async () => {
      if (!item.photoId || item.state !== 'processing') return;
      try {
        const draft = await this.ensureDraft({ existingOnly: true });
        if (!draft) return;
        const p = await get(`/drafts/${encodeURIComponent(draft.id)}/photos/${encodeURIComponent(item.photoId)}`, { draftToken: draft.token });
        this.applyServer(item, p);
        if (item.state === 'ready') announce(`${item.name} is ready.`);
        if (item.state === 'rejected') announce(`${item.name} could not be used.`, { assertive: true });
        this.changed();
      } catch (error) {
        if (error instanceof ApiError && error.code === 'DRAFT_EXPIRED') { this.onDraftLost?.(); return; }
        if (error instanceof ApiError && error.status === 404) { item.state = 'expired'; this.changed(); return; }
      }
      if (item.state === 'processing') this.poll(item, Math.min(step + 1, POLL.length - 1));
    }, POLL[step]);
  }

  resumePoll(item) {
    if (item.state === 'processing' && (item.pollPaused || !item.pollTimer)) this.poll(item, 0);
  }

  async remove(item) {
    window.clearTimeout(item.pollTimer);
    if (item.abort) item.abort.abort();
    if (item.photoId && !['expired', 'local-rejected'].includes(item.state)) {
      item.removing = true;
      this.renderItem(item);
      try {
        const draft = await this.ensureDraft({ existingOnly: true });
        if (draft) await del(`/drafts/${encodeURIComponent(draft.id)}/photos/${encodeURIComponent(item.photoId)}`, undefined, { draftToken: draft.token });
      } catch (error) {
        const gone = error instanceof ApiError && (error.status === 404 || error.code === 'DRAFT_EXPIRED');
        if (!gone) {
          item.removing = false;
          item.error = 'Couldn’t remove this photo. Check your connection and try again.';
          this.changed();
          return;
        }
      }
    }
    if (item.url) URL.revokeObjectURL(item.url);
    this.items = this.items.filter(i => i !== item);
    this.message(null);
    announce(`${item.name} removed.`);
    this.changed();
    this.pump();
    this.list.closest('.form-section')?.querySelector('.file-button input')?.focus();
  }

  retry(item) {
    item.state = 'queued';
    item.error = null;
    this.changed();
    this.pump();
  }

  // Submission readiness.
  pending() { return this.items.some(i => ['queued', 'uploading', 'processing'].includes(i.state)); }
  blocking() { return this.items.filter(i => ['rejected', 'failed', 'interrupted', 'expired'].includes(i.state)); }
  readyIds() { return this.items.filter(i => i.state === 'ready' && i.photoId).map(i => i.photoId); }

  settle() {
    if (!this.pending()) return Promise.resolve();
    return new Promise(resolve => this.waiters.push(resolve));
  }

  serialize() {
    return this.items.filter(i => i.state !== 'local-rejected').map(({ localId, photoId, key, name, size, type, state, error }) => ({ localId, photoId, key, name, size, type, state: state === 'uploading' ? 'queued' : state, error }));
  }

  clearAll() {
    for (const item of this.items) { window.clearTimeout(item.pollTimer); item.abort?.abort(); if (item.url) URL.revokeObjectURL(item.url); }
    this.items = [];
    this.render();
  }

  changed() {
    this.render();
    this.onChange?.();
    if (!this.pending()) { const w = this.waiters; this.waiters = []; w.forEach(fn => fn()); }
  }

  statusLine(item) {
    switch (item.state) {
      case 'queued': return { text: 'Waiting to upload' };
      case 'uploading': return { text: item.progress >= 1 ? 'Finishing upload' : `Uploading, ${Math.round((item.progress || 0) * 100)} percent`, bar: item.progress };
      case 'processing': return { text: HEIC.test(item.name) || /hei[cf]/.test(item.type || '') ? 'Converting HEIC photo' : 'Preparing photo', bar: null };
      case 'ready': return { text: item.file ? `Ready, ${bytes(item.size)}` : 'Photo attached', ok: true };
      case 'rejected': return { text: item.error || 'This photo could not be read. Remove it and try another photo.', error: true };
      case 'local-rejected': return { text: item.error, error: true };
      case 'failed': return { text: item.error || 'Upload failed.', error: true, retry: Boolean(item.file) };
      case 'interrupted': return { text: 'Upload interrupted when the page reloaded. Remove it and attach the photo again.', error: true };
      case 'expired': return { text: 'This photo expired after 24 hours. Remove it and attach the photo again.', error: true };
      default: return { text: '' };
    }
  }

  renderItem(item) {
    const line = this.statusLine(item);
    const thumb = h('span', { class: 'photo-thumb', 'aria-hidden': 'true' }, item.url ? h('img', { src: item.url, alt: '' }) : icon('image'));
    const status = h('p', { class: ['photo-status', line.error ? 'is-error' : null, line.ok ? 'is-ok' : null] },
      line.error ? icon('alert', { size: 16 }) : line.ok ? icon('check', { size: 16 }) : null,
      item.removing ? 'Removing' : line.text,
      line.retry ? h('button', { type: 'button', class: 'link-button', onclick: () => this.retry(item) }, 'Retry') : null);
    const bar = item.state === 'uploading' || item.state === 'processing'
      ? h('progress', { class: 'bar', max: '1', value: line.bar === null || line.bar === undefined ? undefined : String(line.bar), 'aria-label': `${item.name} progress` })
      : null;
    const row = h('li', { class: ['photo-item', line.error ? 'is-error' : null], dataset: { localId: item.localId } },
      thumb,
      h('div', { class: 'photo-meta' }, h('p', { class: 'photo-name' }, item.name), status, bar),
      h('button', { type: 'button', class: 'icon-button', 'aria-label': `Remove ${item.name}`, disabled: item.removing, onclick: () => this.remove(item) }, icon('close', { size: 20 })));
    const old = this.list.querySelector(`[data-local-id="${item.localId}"]`);
    if (old) {
      const hadFocus = old.contains(document.activeElement) ? document.activeElement.getAttribute('aria-label') || document.activeElement.textContent : null;
      old.replaceWith(row);
      if (hadFocus) [...row.querySelectorAll('button')].find(b => (b.getAttribute('aria-label') || b.textContent) === hadFocus)?.focus();
    } else this.list.append(row);
  }

  render() {
    const ids = new Set(this.items.map(i => i.localId));
    for (const el of [...this.list.children]) if (!ids.has(el.dataset.localId)) el.remove();
    this.items.forEach(item => this.renderItem(item));
    this.list.hidden = this.items.length === 0;
    this.renderNotice();
  }
}
