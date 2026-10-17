// Tab-scoped persistence (sessionStorage only, per docs/API.md). Every record is
// schema-versioned with an absolute expiry; unreadable or expired entries are dropped.
const PREFIX = 'clarke.';

function storage() {
  try {
    const s = window.sessionStorage;
    const probe = `${PREFIX}probe`;
    s.setItem(probe, '1');
    s.removeItem(probe);
    return s;
  } catch {
    return null;
  }
}

const memory = new Map();

export function read(key, version) {
  const s = storage();
  const raw = s ? s.getItem(PREFIX + key) : memory.get(key);
  if (!raw) return null;
  try {
    const record = JSON.parse(raw);
    if (record.v !== version || typeof record.expires !== 'number' || record.expires < Date.now()) {
      remove(key);
      return null;
    }
    return record.data;
  } catch {
    remove(key);
    return null;
  }
}

export function write(key, version, data, ttlMs, { keepExpiry = false } = {}) {
  const s = storage();
  let expires = Date.now() + ttlMs;
  if (keepExpiry) {
    try {
      const prior = JSON.parse((s ? s.getItem(PREFIX + key) : memory.get(key)) || 'null');
      if (prior && prior.v === version && prior.expires > Date.now()) expires = prior.expires;
    } catch { /* replaced below */ }
  }
  const raw = JSON.stringify({ v: version, expires, data });
  try {
    if (s) s.setItem(PREFIX + key, raw); else memory.set(key, raw);
  } catch {
    memory.set(key, raw);
  }
}

export function remove(key) {
  const s = storage();
  try { s?.removeItem(PREFIX + key); } catch { /* ignore */ }
  memory.delete(key);
}

export function keys(prefix) {
  const s = storage();
  const found = new Set();
  if (s) for (let i = 0; i < s.length; i += 1) {
    const k = s.key(i);
    if (k?.startsWith(PREFIX + prefix)) found.add(k.slice(PREFIX.length));
  }
  for (const k of memory.keys()) if (k.startsWith(prefix)) found.add(k);
  return [...found];
}

// RFC 4122 v4 from getRandomValues (randomUUID is unavailable on plain-HTTP test origins).
export function uuid() {
  const b = crypto.getRandomValues(new Uint8Array(16));
  b[6] = (b[6] & 0x0f) | 0x40;
  b[8] = (b[8] & 0x3f) | 0x80;
  const hex = [...b].map(x => x.toString(16).padStart(2, '0')).join('');
  return `${hex.slice(0, 8)}-${hex.slice(8, 12)}-${hex.slice(12, 16)}-${hex.slice(16, 20)}-${hex.slice(20)}`;
}

export const HOUR = 3600 * 1000;
