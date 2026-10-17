// Formatting in the shop's time zone. The server is the source of truth for state;
// these helpers only render values it returns.
export const TZ = 'America/New_York';

const dateFmt = new Intl.DateTimeFormat('en-US', { timeZone: TZ, weekday: 'short', month: 'short', day: 'numeric' });
const dateYearFmt = new Intl.DateTimeFormat('en-US', { timeZone: TZ, month: 'short', day: 'numeric', year: 'numeric' });
const dateTimeFmt = new Intl.DateTimeFormat('en-US', { timeZone: TZ, month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit' });
const longFmt = new Intl.DateTimeFormat('en-US', { timeZone: TZ, weekday: 'long', month: 'long', day: 'numeric', hour: 'numeric', minute: '2-digit' });

const valid = d => d instanceof Date && !Number.isNaN(d.getTime());
const asDate = value => (value instanceof Date ? value : new Date(value));

export function formatDate(value) {
  const d = asDate(value);
  return valid(d) ? dateYearFmt.format(d) : '';
}

export function formatShortDate(value) {
  const d = asDate(value);
  return valid(d) ? dateFmt.format(d) : '';
}

export function formatDateTime(value) {
  const d = asDate(value);
  return valid(d) ? dateTimeFmt.format(d) : '';
}

export function formatLongDateTime(value) {
  const d = asDate(value);
  return valid(d) ? longFmt.format(d) : '';
}

// Local date-only values (YYYY-MM-DD) are New York calendar dates; render without shifting.
export function formatLocalDate(ymd) {
  const m = /^(\d{4})-(\d{2})-(\d{2})$/.exec(ymd || '');
  if (!m) return '';
  const d = new Date(Date.UTC(+m[1], +m[2] - 1, +m[3], 12));
  return new Intl.DateTimeFormat('en-US', { timeZone: 'UTC', weekday: 'short', month: 'short', day: 'numeric', year: 'numeric' }).format(d);
}

export function addDays(ymd, days) {
  const m = /^(\d{4})-(\d{2})-(\d{2})$/.exec(ymd || '');
  if (!m) return null;
  const d = new Date(Date.UTC(+m[1], +m[2] - 1, +m[3] + days));
  return d.toISOString().slice(0, 10);
}

export function todayInShop() {
  const parts = new Intl.DateTimeFormat('en-CA', { timeZone: TZ, year: 'numeric', month: '2-digit', day: '2-digit' }).formatToParts(new Date());
  const get = type => parts.find(p => p.type === type)?.value;
  return `${get('year')}-${get('month')}-${get('day')}`;
}

export function money(cents) {
  if (!Number.isInteger(cents)) return '';
  return new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD' }).format(cents / 100);
}

export function moneyRange(min, max) {
  if (!Number.isInteger(min)) return '';
  return Number.isInteger(max) && max !== min ? `${money(min)} – ${money(max)}` : money(min);
}

// Parse "45", "45.5", "$1,234.50" into integer cents without floating point drift.
export function parseCents(text) {
  const clean = String(text ?? '').trim().replace(/[$,\s]/g, '');
  const m = /^(\d{1,7})(?:\.(\d{1,2}))?$/.exec(clean);
  if (!m) return null;
  return Number(m[1]) * 100 + Number((m[2] || '').padEnd(2, '0'));
}

export function centsToInput(cents) {
  return Number.isInteger(cents) ? (cents / 100).toFixed(2) : '';
}

export function formatPhone(e164) {
  const m = /^\+1(\d{3})(\d{3})(\d{4})$/.exec(e164 || '');
  return m ? `${m[1]}-${m[2]}-${m[3]}` : (e164 || '');
}

// Reference display: accept compact or hyphenated input; the server normalizes too.
export function normalizeReference(text) {
  return String(text || '').toUpperCase().replace(/\s+/g, '').trim();
}

const DAY_NAMES = ['Sunday', 'Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday'];
export { DAY_NAMES };

export function clock(hhmm) {
  const m = /^(\d{2}):(\d{2})$/.exec(hhmm || '');
  if (!m) return '';
  const hour = Number(m[1]);
  const minute = m[2];
  const suffix = hour < 12 ? 'am' : 'pm';
  const h12 = hour % 12 === 0 ? 12 : hour % 12;
  return minute === '00' ? `${h12} ${suffix}` : `${h12}:${minute} ${suffix}`;
}

// Group a Sunday-indexed weekly rule into readable rows, Monday first.
export function hoursRows(days) {
  if (!Array.isArray(days) || days.length !== 7) return [];
  const order = [1, 2, 3, 4, 5, 6, 0];
  const rows = [];
  const closed = [];
  for (const index of order) {
    const day = days[index];
    if (!day) { closed.push(index); continue; }
    const text = `${clock(day.open)} – ${clock(day.close)}`;
    const last = rows[rows.length - 1];
    if (last && last.text === text && last.lastIndex === order[order.indexOf(index) - 1]) {
      last.to = DAY_NAMES[index];
      last.lastIndex = index;
    } else rows.push({ from: DAY_NAMES[index], to: null, text, lastIndex: index });
  }
  const out = rows.map(r => ({ days: r.to ? `${r.from} – ${r.to}` : r.from, text: r.text }));
  const names = closed.sort((a, b) => a - b).map(i => DAY_NAMES[i]);
  if (names.length) out.push({ days: names.length === 2 ? `${names[0]} and ${names[1]}` : names.join(', '), text: 'Closed' });
  return out;
}

export function bytes(n) {
  if (!Number.isFinite(n)) return '';
  if (n < 1024 * 1024) return `${Math.max(1, Math.round(n / 1024))} KB`;
  return `${(n / (1024 * 1024)).toFixed(1)} MB`;
}
