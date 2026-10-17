// Client for /api/v1 (docs/API.md). Handles the anonymous/staff CSRF token, the common
// error envelope, idempotency keys and a single safe CSRF refresh. Callers never see raw
// HTML or stack traces: unknown failures become a sanitized ApiError.
const BASE = '/api/v1';

const FALLBACK = {
  network: 'We couldn’t reach the shop’s website. Check your connection and try again.',
  offline: 'You appear to be offline. Your details are kept on this page; try again when you’re back online.',
  413: 'That file is too large to send. Photos can be up to 10 MB each.',
  429: 'Too many attempts in a short time. Please wait a moment and try again.',
  500: 'Something went wrong on our side. Your details are kept; please try again.',
  502: 'The website is briefly unavailable. Your details are kept; please try again.',
  503: 'The website is busy right now. Your details are kept; please try again shortly.',
  504: 'The website took too long to answer. Your details are kept; please try again.',
  default: 'Something went wrong. Please try again.',
};

export class ApiError extends Error {
  constructor({ status = 0, code = 'NETWORK', message, fields = {}, retryable = false, requestId = null, details = {}, retryAfter = null }) {
    super(message || FALLBACK[status] || FALLBACK.default);
    this.name = 'ApiError';
    this.status = status;
    this.code = code;
    this.fields = fields || {};
    this.retryable = retryable;
    this.requestId = requestId;
    this.details = details || {};
    this.retryAfter = retryAfter;
  }
  get network() { return this.status === 0; }
}

let csrfToken = null;
let csrfMode = 'public';
let bootstrapPromise = null;
let staffRefresher = null;

export function setStaffCsrf(token, refresher) {
  csrfToken = token;
  csrfMode = 'staff';
  if (refresher) staffRefresher = refresher;
}

export function useAnonymousCsrf() {
  csrfMode = 'public';
  csrfToken = null;
  bootstrapPromise = null;
}

export function bootstrap({ force = false } = {}) {
  if (!bootstrapPromise || force) {
    bootstrapPromise = request('/bootstrap', { csrf: false }).then(data => {
      if (csrfMode === 'public') csrfToken = data.csrfToken;
      return data;
    }).catch(error => {
      bootstrapPromise = null;
      throw error;
    });
  }
  return bootstrapPromise;
}

async function refreshCsrf() {
  if (csrfMode === 'staff' && staffRefresher) {
    csrfToken = await staffRefresher();
  } else {
    await bootstrap({ force: true });
  }
}

function retryAfterSeconds(response, details) {
  const header = Number(response?.headers?.get('Retry-After'));
  if (Number.isFinite(header) && header > 0) return header;
  const fromBody = Number(details?.retryAfterSeconds);
  return Number.isFinite(fromBody) && fromBody > 0 ? fromBody : null;
}

function errorFrom(status, body, response) {
  const e = body && typeof body === 'object' && body.error && typeof body.error === 'object' ? body.error : null;
  if (!e) return new ApiError({ status, code: `HTTP_${status}`, retryable: status >= 500 || status === 429, retryAfter: retryAfterSeconds(response, null) });
  return new ApiError({
    status,
    code: typeof e.code === 'string' ? e.code : `HTTP_${status}`,
    message: typeof e.message === 'string' && e.message ? e.message : undefined,
    fields: e.fields && typeof e.fields === 'object' ? e.fields : {},
    retryable: Boolean(e.retryable),
    requestId: typeof e.requestId === 'string' ? e.requestId : null,
    details: e.details && typeof e.details === 'object' ? e.details : {},
    retryAfter: retryAfterSeconds(response, e.details),
  });
}

function networkError() {
  const offline = typeof navigator !== 'undefined' && navigator.onLine === false;
  return new ApiError({ status: 0, code: offline ? 'OFFLINE' : 'NETWORK', message: offline ? FALLBACK.offline : FALLBACK.network, retryable: true });
}

export async function request(path, options = {}) {
  const {
    method = 'GET', body, idempotencyKey, draftToken, bearer, signal,
    csrf = method !== 'GET', query, retryOnCsrf = true,
  } = options;
  let url = BASE + path;
  if (query) {
    const params = new URLSearchParams();
    for (const [k, v] of Object.entries(query)) if (v !== undefined && v !== null && v !== '') params.set(k, String(v));
    const qs = params.toString();
    if (qs) url += `?${qs}`;
  }
  const headers = { Accept: 'application/json' };
  if (body !== undefined) headers['Content-Type'] = 'application/json';
  if (idempotencyKey) headers['Idempotency-Key'] = idempotencyKey;
  if (draftToken) headers['X-Draft-Token'] = draftToken;
  if (bearer) headers.Authorization = `Bearer ${bearer}`;
  if (csrf) {
    if (!csrfToken) await refreshCsrf();
    headers['X-CSRF-Token'] = csrfToken;
  }
  let response;
  try {
    response = await fetch(url, {
      method, headers, signal, credentials: 'same-origin', cache: 'no-store', redirect: 'error',
      body: body === undefined ? undefined : JSON.stringify(body),
    });
  } catch (error) {
    if (error?.name === 'AbortError') throw error;
    throw networkError();
  }
  if (response.status === 204) return null;
  let parsed = null;
  const type = response.headers.get('Content-Type') || '';
  if (type.includes('application/json')) {
    try { parsed = await response.json(); } catch { parsed = null; }
  }
  if (response.ok) {
    if (!parsed || typeof parsed !== 'object' || !('data' in parsed)) {
      throw new ApiError({ status: response.status, code: 'BAD_RESPONSE', retryable: true });
    }
    return parsed.data;
  }
  const error = errorFrom(response.status, parsed, response);
  if (error.code === 'CSRF_INVALID' && csrf && retryOnCsrf) {
    await refreshCsrf();
    return request(path, { ...options, retryOnCsrf: false });
  }
  throw error;
}

export const get = (path, options) => request(path, { ...options, method: 'GET' });
export const post = (path, body, options) => request(path, { ...options, method: 'POST', body: body ?? {} });
export const patch = (path, body, options) => request(path, { ...options, method: 'PATCH', body });
export const put = (path, body, options) => request(path, { ...options, method: 'PUT', body });
export const del = (path, body, options) => request(path, { ...options, method: 'DELETE', body });

// Multipart upload of one file with progress, via XHR (fetch has no upload progress).
export function uploadFile(path, file, { draftToken, idempotencyKey, onProgress, signal } = {}) {
  const send = async (allowCsrfRetry) => {
    if (!csrfToken) await refreshCsrf();
    if (signal?.aborted) throw Object.assign(new Error('aborted'), { name: 'AbortError' });
    return new Promise((resolve, reject) => {
      const xhr = new XMLHttpRequest();
      xhr.open('POST', BASE + path);
      xhr.withCredentials = true;
      xhr.setRequestHeader('Accept', 'application/json');
      xhr.setRequestHeader('X-CSRF-Token', csrfToken);
      if (draftToken) xhr.setRequestHeader('X-Draft-Token', draftToken);
      if (idempotencyKey) xhr.setRequestHeader('Idempotency-Key', idempotencyKey);
      xhr.upload.onprogress = event => { if (event.lengthComputable) onProgress?.(event.loaded / event.total); };
      xhr.onerror = () => reject(networkError());
      xhr.ontimeout = () => reject(networkError());
      xhr.onabort = () => reject(Object.assign(new Error('aborted'), { name: 'AbortError' }));
      xhr.onload = () => {
        let parsed = null;
        if ((xhr.getResponseHeader('Content-Type') || '').includes('application/json')) {
          try { parsed = JSON.parse(xhr.responseText); } catch { parsed = null; }
        }
        const pseudo = { headers: { get: name => xhr.getResponseHeader(name) } };
        if (xhr.status >= 200 && xhr.status < 300 && parsed && 'data' in parsed) resolve(parsed.data);
        else reject(errorFrom(xhr.status, parsed, pseudo));
      };
      signal?.addEventListener('abort', () => xhr.abort(), { once: true });
      const form = new FormData();
      form.append('file', file, file.name || 'photo');
      xhr.send(form);
    }).catch(async error => {
      if (allowCsrfRetry && error instanceof ApiError && error.code === 'CSRF_INVALID') {
        await refreshCsrf();
        return send(false);
      }
      throw error;
    });
  };
  return send(true);
}

export function describeRetry(error) {
  if (!error?.retryAfter) return '';
  const minutes = Math.ceil(error.retryAfter / 60);
  return error.retryAfter < 90 ? `Try again in about ${Math.max(1, Math.round(error.retryAfter))} seconds.` : `Try again in about ${minutes} minutes.`;
}
