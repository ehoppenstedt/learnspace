import { DEFAULT_FILTERS, activeFilterCount, feedQuery, sanitizeFilters } from '../filters';

describe('feedQuery', () => {
  it('serializes GPS origin and filters', () => {
    const q = feedQuery(
      { ...DEFAULT_FILTERS, categories: ['art', 'music'], days: [4, 2], time_from: '19:00', time_to: '21:00' },
      { kind: 'gps', lat: 19.419412345, lng: -99.161712345 },
      ' acuarela ',
    );
    expect(q).toEqual({
      radius_km: 10, lat: 19.41941, lng: -99.16171, q: 'acuarela', category: 'art,music', dow: '2,4',
      time_from: '19:00', time_to: '21:00',
    });
  });

  it('uses area slug for manual location', () => {
    const q = feedQuery(DEFAULT_FILTERS, { kind: 'area', slug: 'condesa', name: 'Condesa', lat: 1, lng: 2 }, '');
    expect(q).toEqual({ radius_km: 10, area: 'condesa' });
  });
});

describe('activeFilterCount', () => {
  it('counts groups', () => {
    expect(activeFilterCount(DEFAULT_FILTERS)).toBe(0);
    expect(activeFilterCount({ ...DEFAULT_FILTERS, categories: ['a', 'b'], price_max_cents: 50000, days: [2] })).toBe(3);
  });
});

describe('sanitizeFilters', () => {
  it('falls back per field on garbage', () => {
    expect(sanitizeFilters(null)).toEqual(DEFAULT_FILTERS);
    expect(sanitizeFilters({ radius_km: 999, days: [0, 2, 9], time_from: '19:00:00', modality: 'x' })).toEqual({
      ...DEFAULT_FILTERS, days: [2], time_from: '19:00',
    });
  });
});
