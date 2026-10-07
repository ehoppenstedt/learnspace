import { ageOn, formatCountdown, formatRelative, formatDistance, formatMoney, maskDob, parseDob, pesosToCents, previewTotal, seatsLabel } from '../format';

describe('formatMoney', () => {
  it('drops centavos when whole', () => {
    expect(formatMoney(52500)).toBe('$525');
    expect(formatMoney(123456)).toBe('$1,234.56');
  });
});

describe('previewTotal mirrors server rounding', () => {
  it.each([
    [50000, 500, 2500],
    [10, 500, 1],
    [9, 500, 0],
    [12348, 1250, 1544],
  ])('listed %i at %i bps -> fee %i', (listed, bps, fee) => {
    expect(previewTotal(listed, bps).fee_cents).toBe(fee);
  });
});

describe('formatDistance', () => {
  it('rounds meters and km', () => {
    expect(formatDistance(40)).toBe('100 m');
    expect(formatDistance(640)).toBe('600 m');
    expect(formatDistance(2350)).toBe('2.4 km');
    expect(formatDistance(12_600)).toBe('13 km');
    expect(formatDistance(null)).toBeNull();
  });
});

describe('date of birth', () => {
  it('masks and parses', () => {
    expect(maskDob('17051990')).toBe('17/05/1990');
    expect(parseDob('17/05/1990')).toBe('1990-05-17');
    expect(parseDob('31/02/1990')).toBeNull();
    expect(parseDob('1990-05-17')).toBeNull();
  });
  it('computes age like the server', () => {
    expect(ageOn('2008-10-06', new Date(2026, 9, 6))).toBe(18);
    expect(ageOn('2008-10-07', new Date(2026, 9, 6))).toBe(17);
  });
});

describe('pesosToCents', () => {
  it('parses user input', () => {
    expect(pesosToCents('500')).toBe(50000);
    expect(pesosToCents('$1,250.5')).toBe(125050);
    expect(pesosToCents('12.345')).toBeNull();
    expect(pesosToCents('abc')).toBeNull();
  });
});

describe('booking helpers', () => {
  it('formats the hold countdown and never goes negative', () => {
    expect(formatCountdown(600_000)).toBe('10:00');
    expect(formatCountdown(573_100)).toBe('9:34');
    expect(formatCountdown(-5)).toBe('0:00');
  });
  it('pluralizes seats', () => {
    expect(seatsLabel(1)).toBe('1 lugar');
    expect(seatsLabel(3)).toBe('3 lugares');
    expect(seatsLabel(2, 'en')).toBe('2 spots');
  });
});

describe('formatRelative', () => {
  const now = new Date('2026-10-07T18:00:00Z'); // 12:00 in CDMX
  it('shows the time for messages from today (CDMX)', () => {
    expect(formatRelative('2026-10-07T15:05:00Z', 'es', now)).toBe('09:05');
  });
  it('shows a short date for older messages', () => {
    expect(formatRelative('2026-10-05T15:05:00Z', 'es', now)).toBe('5 oct');
  });
  it('uses the CDMX day boundary, not UTC', () => {
    // 01:00 UTC on the 8th is still the 7th in Mexico City.
    expect(formatRelative('2026-10-08T01:00:00Z', 'en', new Date('2026-10-08T02:00:00Z'))).toBe('19:00');
  });
});
