export type Filters = {
  categories: string[];
  price_min_cents: number | null;
  price_max_cents: number | null;
  radius_km: number;
  days: number[]; // ISO weekday, 1 = Monday
  time_from: string | null; // "HH:MM"
  time_to: string | null;
  modality: 'in_person' | 'online' | null;
  language: string | null;
};

export const DEFAULT_FILTERS: Filters = {
  categories: [],
  price_min_cents: null,
  price_max_cents: null,
  radius_km: 10,
  days: [],
  time_from: null,
  time_to: null,
  modality: null,
  language: null,
};

export type Origin = { kind: 'gps'; lat: number; lng: number } | { kind: 'area'; slug: string; name: string; lat: number; lng: number };

/** Builds the /experiences query string params from UI state. */
export function feedQuery(filters: Filters, origin: Origin | null, q: string) {
  const params: Record<string, string | number> = { radius_km: filters.radius_km };
  if (origin?.kind === 'gps') {
    params.lat = Number(origin.lat.toFixed(5));
    params.lng = Number(origin.lng.toFixed(5));
  } else if (origin?.kind === 'area') {
    params.area = origin.slug;
  }
  if (q.trim()) params.q = q.trim();
  if (filters.categories.length) params.category = filters.categories.join(',');
  if (filters.price_min_cents !== null) params.price_min = filters.price_min_cents;
  if (filters.price_max_cents !== null) params.price_max = filters.price_max_cents;
  if (filters.days.length) params.dow = [...filters.days].sort().join(',');
  if (filters.time_from) params.time_from = filters.time_from;
  if (filters.time_to) params.time_to = filters.time_to;
  if (filters.modality) params.modality = filters.modality;
  if (filters.language) params.language = filters.language;
  return params;
}

/** Number of active filters (shown as a badge on the filter button). Categories count once. */
export function activeFilterCount(f: Filters): number {
  return [
    f.categories.length > 0,
    f.price_min_cents !== null || f.price_max_cents !== null,
    f.radius_km !== DEFAULT_FILTERS.radius_km,
    f.days.length > 0 || f.time_from !== null || f.time_to !== null,
    f.modality !== null,
    f.language !== null,
  ].filter(Boolean).length;
}

/** Validates a server/disk payload, falling back to defaults per field. */
export function sanitizeFilters(raw: unknown): Filters {
  const r = (raw && typeof raw === 'object' ? raw : {}) as Record<string, unknown>;
  const time = (v: unknown) => (typeof v === 'string' && /^\d{2}:\d{2}/.test(v) ? v.slice(0, 5) : null);
  const num = (v: unknown) => (typeof v === 'number' && Number.isFinite(v) && v >= 0 ? v : null);
  return {
    categories: Array.isArray(r.categories) ? r.categories.filter((c): c is string => typeof c === 'string') : [],
    price_min_cents: num(r.price_min_cents),
    price_max_cents: num(r.price_max_cents),
    radius_km: typeof r.radius_km === 'number' && r.radius_km >= 1 && r.radius_km <= 50 ? r.radius_km : DEFAULT_FILTERS.radius_km,
    days: Array.isArray(r.days) ? r.days.filter((d): d is number => Number.isInteger(d) && d >= 1 && d <= 7) : [],
    time_from: time(r.time_from),
    time_to: time(r.time_to),
    modality: r.modality === 'in_person' || r.modality === 'online' ? r.modality : null,
    language: typeof r.language === 'string' && r.language ? r.language : null,
  };
}
