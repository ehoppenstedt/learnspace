import { Image } from 'expo-image';
import { router } from 'expo-router';
import { useTranslation } from 'react-i18next';
import { Pressable, StyleSheet, Text, View } from 'react-native';

import type { Booking } from '@/lib/api/types';
import { formatSessionDate } from '@/lib/utils/format';
import { colors, radius, space, type } from '@/theme/tokens';

import { Badge } from './ui';

const BADGE: Record<string, { bg: string; fg: string }> = {
  confirmed: { bg: '#E3F6EC', fg: colors.success },
  pending_approval: { bg: '#FFF4D6', fg: colors.warning },
  pending_payment: { bg: '#FFF4D6', fg: colors.warning },
  completed: { bg: '#F1F1F1', fg: colors.textMuted },
  cancelled: { bg: '#F1F1F1', fg: colors.textMuted },
  declined: { bg: '#FDE2E1', fg: colors.danger },
  payment_failed: { bg: '#FDE2E1', fg: colors.danger },
  no_show: { bg: '#FDE2E1', fg: colors.danger },
};

/** Photo-led row: the class picture first, then when and where. */
export function BookingCard({ booking }: { booking: Booking }) {
  const { t, i18n } = useTranslation();
  const cover = booking.experience.cover;
  const badge = BADGE[booking.status] ?? BADGE.completed;
  return (
    <Pressable style={styles.card} onPress={() => router.push(`/bookings/${booking.id}`)}>
      <Image source={cover?.urls?.w800} style={[styles.image, { backgroundColor: cover?.color ?? colors.surface }]} contentFit="cover" />
      <View style={{ padding: space.lg, gap: 4 }}>
        <View style={{ flexDirection: 'row', gap: space.sm, flexWrap: 'wrap' }}>
          <Badge label={t(`bookings.status.${booking.status}`)} bg={badge.bg} fg={badge.fg} />
          {booking.review_pending ? <Badge label={t('bookings.reviewPending')} bg={colors.brandSoft} fg={colors.brand} /> : null}
        </View>
        <Text style={type.heading} numberOfLines={2}>{booking.experience.title}</Text>
        <Text style={type.small}>{formatSessionDate(booking.starts_at, i18n.language)} · {booking.location?.neighborhood ?? ''}</Text>
      </View>
    </Pressable>
  );
}

const styles = StyleSheet.create({
  card: { borderRadius: radius.lg, backgroundColor: colors.bg, borderWidth: StyleSheet.hairlineWidth, borderColor: colors.border, overflow: 'hidden', marginBottom: space.xl },
  image: { width: '100%', aspectRatio: 2 },
});
