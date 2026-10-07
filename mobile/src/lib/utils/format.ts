/** Pure formatting helpers (unit-tested). */

export function formatMoney(cents: number, lang = 'es'): string {
  const pesos = cents / 100;
  const whole = Number.isInteger(pesos);
  const formatted = new Intl.NumberFormat(lang === 'en' ? 'en-US' : 'es-MX', {
    minimumFractionDigits: whole ? 0 : 2,
    maximumFractionDigits: 2,
  }).format(pesos);
  return `$${formatted}`;
}

export function formatDistance(meters: number | null | undefined): string | null {
  if (meters === null || meters === undefined) return null;
  if (meters < 1000) return `${Math.max(100, Math.round(meters / 100) * 100)} m`;
  const km = meters / 1000;
  // Mexico uses a decimal point, same as English.
  return `${km < 10 ? km.toFixed(1) : Math.round(km)} km`;
}

const TZ = 'America/Mexico_City';

export function formatSessionDate(iso: string, lang = 'es'): string {
  const d = new Date(iso);
  const locale = lang === 'en' ? 'en-US' : 'es-MX';
  const day = new Intl.DateTimeFormat(locale, { weekday: 'short', day: 'numeric', month: 'short', timeZone: TZ }).format(d);
  const time = new Intl.DateTimeFormat(locale, { hour: '2-digit', minute: '2-digit', hour12: false, timeZone: TZ }).format(d);
  return `${capitalize(day.replace(/\./g, ''))} · ${time}`;
}

export function formatTimeRange(startIso: string, endIso: string, lang = 'es'): string {
  const locale = lang === 'en' ? 'en-US' : 'es-MX';
  const fmt = new Intl.DateTimeFormat(locale, { hour: '2-digit', minute: '2-digit', hour12: false, timeZone: TZ });
  return `${fmt.format(new Date(startIso))}–${fmt.format(new Date(endIso))}`;
}

export function capitalize(s: string): string {
  return s ? s[0].toUpperCase() + s.slice(1) : s;
}

/** "17/05/1990" -> "1990-05-17" (null if impossible date). */
export function parseDob(input: string): string | null {
  const m = /^(\d{2})\/(\d{2})\/(\d{4})$/.exec(input.trim());
  if (!m) return null;
  const [, dd, mm, yyyy] = m;
  const d = new Date(Date.UTC(Number(yyyy), Number(mm) - 1, Number(dd)));
  if (d.getUTCFullYear() !== Number(yyyy) || d.getUTCMonth() !== Number(mm) - 1 || d.getUTCDate() !== Number(dd)) return null;
  return `${yyyy}-${mm}-${dd}`;
}

/** Inserts slashes while typing a date: "1705" -> "17/05". */
export function maskDob(raw: string): string {
  const digits = raw.replace(/\D/g, '').slice(0, 8);
  if (digits.length <= 2) return digits;
  if (digits.length <= 4) return `${digits.slice(0, 2)}/${digits.slice(2)}`;
  return `${digits.slice(0, 2)}/${digits.slice(2, 4)}/${digits.slice(4)}`;
}

export function ageOn(dobIso: string, today: Date): number {
  const [y, m, d] = dobIso.split('-').map(Number);
  let age = today.getFullYear() - y;
  if (today.getMonth() + 1 < m || (today.getMonth() + 1 === m && today.getDate() < d)) age -= 1;
  return age;
}

export function pesosToCents(input: string): number | null {
  const clean = input.replace(/[$,\s]/g, '');
  if (!/^\d+(\.\d{1,2})?$/.test(clean)) return null;
  return Math.round(Number(clean) * 100);
}

/** Mirrors the server: fee = round_half_up(listed * bps / 10000). Display only; the server is authoritative. */
export function previewTotal(listedCents: number, feeBps: number) {
  const fee = Math.floor((listedCents * feeBps + 5000) / 10000);
  return { listed_cents: listedCents, fee_cents: fee, total_cents: listedCents + fee };
}

/** 573000 ms -> "9:33" for the seat-hold countdown. */
export function formatCountdown(ms: number): string {
  const total = Math.max(0, Math.ceil(ms / 1000));
  return `${Math.floor(total / 60)}:${String(total % 60).padStart(2, '0')}`;
}

/** Sum the listed part of a price for N seats (display only; the server computes the real breakdown). */
export function seatsLabel(seats: number, lang = 'es'): string {
  return lang === 'en' ? `${seats} spot${seats === 1 ? '' : 's'}` : `${seats} lugar${seats === 1 ? '' : 'es'}`;
}
