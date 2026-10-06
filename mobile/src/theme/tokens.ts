/**
 * Design tokens. "Show, don't tell": photography carries the page, chrome stays quiet.
 * White canvas, near-black text, one brand accent used sparingly for primary actions.
 */
export const colors = {
  brand: '#5A31F4',
  brandPressed: '#4521C9',
  brandSoft: '#EFEAFF',
  text: '#1F1F1F',
  textMuted: '#6A6A6A',
  textSubtle: '#9A9A9A',
  bg: '#FFFFFF',
  surface: '#F7F7F7',
  border: '#E6E6E6',
  hairline: '#EBEBEB',
  danger: '#C1352B',
  success: '#1B7F4B',
  warning: '#B26B00',
  overlay: 'rgba(0,0,0,0.45)',
  white: '#FFFFFF',
  star: '#1F1F1F',
};

export const space = { xs: 4, sm: 8, md: 12, lg: 16, xl: 24, xxl: 32, xxxl: 48 };

export const radius = { sm: 8, md: 12, lg: 16, xl: 24, pill: 999 };

export const type = {
  display: { fontSize: 28, fontWeight: '700' as const, letterSpacing: -0.4, color: colors.text },
  title: { fontSize: 22, fontWeight: '700' as const, letterSpacing: -0.2, color: colors.text },
  heading: { fontSize: 18, fontWeight: '600' as const, color: colors.text },
  body: { fontSize: 16, lineHeight: 23, color: colors.text },
  bodyStrong: { fontSize: 16, fontWeight: '600' as const, color: colors.text },
  small: { fontSize: 14, lineHeight: 19, color: colors.textMuted },
  smallStrong: { fontSize: 14, fontWeight: '600' as const, color: colors.text },
  caption: { fontSize: 12, color: colors.textMuted },
};

export const shadow = {
  card: {
    shadowColor: '#000',
    shadowOpacity: 0.12,
    shadowRadius: 12,
    shadowOffset: { width: 0, height: 4 },
    elevation: 4,
  },
  floating: {
    shadowColor: '#000',
    shadowOpacity: 0.18,
    shadowRadius: 16,
    shadowOffset: { width: 0, height: 6 },
    elevation: 8,
  },
};

export const statusColors: Record<string, { bg: string; fg: string }> = {
  draft: { bg: '#F1F1F1', fg: '#4A4A4A' },
  in_review: { bg: '#FFF4D6', fg: '#8A5A00' },
  changes_requested: { bg: '#FFE7DE', fg: '#A33A12' },
  live: { bg: '#E3F6EC', fg: '#1B7F4B' },
  paused: { bg: '#ECECF4', fg: '#4B4B78' },
  expired: { bg: '#F1F1F1', fg: '#6A6A6A' },
  rejected: { bg: '#FDE2E1', fg: '#A3261E' },
};
