// New York wall-clock <-> explicit-offset RFC3339, for the notice editor. A local time
// that occurs twice (fall back) must be chosen explicitly; one that never occurs (spring
// forward) is rejected. No UTC-offset guessing.
import { TZ } from './format.js';

const wall = new Intl.DateTimeFormat('en-CA', {
  timeZone: TZ, year: 'numeric', month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit', hourCycle: 'h23',
});

export function wallOf(date) {
  const p = Object.fromEntries(wall.formatToParts(date).map(x => [x.type, x.value]));
  return `${p.year}-${p.month}-${p.day}T${p.hour}:${p.minute}`;
}

export function instantToLocal(iso) {
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? '' : wallOf(d);
}

// Offsets (as "-04:00"/"-05:00") under which `local` is a real New York wall time.
export function offsetsFor(local) {
  if (!/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}$/.test(local || '')) return [];
  return ['-04:00', '-05:00'].filter(offset => {
    const d = new Date(`${local}:00${offset}`);
    return !Number.isNaN(d.getTime()) && wallOf(d) === local;
  });
}

export function offsetOf(iso) {
  const local = instantToLocal(iso);
  const options = offsetsFor(local);
  if (options.length === 1) return options[0];
  const t = new Date(iso).getTime();
  return options.find(o => new Date(`${local}:00${o}`).getTime() === t) || options[0] || null;
}

export const toRfc = (local, offset) => `${local}:00${offset}`;
