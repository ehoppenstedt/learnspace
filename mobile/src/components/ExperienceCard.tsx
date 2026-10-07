import { Ionicons } from '@expo/vector-icons';
import { Link } from 'expo-router';
import { useTranslation } from 'react-i18next';
import { Pressable, StyleSheet, Text, View, useWindowDimensions } from 'react-native';

import type { ExperienceCard as Card } from '@/lib/api/types';
import { formatDistance, formatMoney, formatSessionDate } from '@/lib/utils/format';
import { colors, radius, space, type } from '@/theme/tokens';

import { PhotoCarousel } from './PhotoCarousel';

/** Photo-first listing card: the image does the selling, the text answers what/where/when/how much. */
export function ExperienceCard({ item }: { item: Card }) {
  const { t, i18n } = useTranslation();
  const { width } = useWindowDimensions();
  const cardWidth = width - space.xl * 2;
  const lang = i18n.language;
  const distance = formatDistance(item.distance_m);
  const place = [item.area, distance].filter(Boolean).join(' · ');
  const scarce = item.seats_left !== null && item.seats_left > 0 && item.seats_left <= 5;

  return (
    <Link href={`/experience/${item.id}`} asChild>
      <Pressable style={styles.card} accessibilityLabel={`${item.title}, ${formatMoney(item.price.total_cents, lang)}`}>
        <View>
          <PhotoCarousel media={item.media} width={cardWidth} height={Math.round(cardWidth * 0.95)} rounded={radius.lg} />
          {item.offering_type !== 'single' ? (
            <View style={styles.pill}>
              <Text style={styles.pillText}>{item.offering_type === 'course' ? t('feed.course') : t('feed.dropin')}</Text>
            </View>
          ) : null}
        </View>
        <View style={styles.meta}>
          <View style={styles.titleRow}>
            <Text style={[type.bodyStrong, { flex: 1 }]} numberOfLines={1}>{item.title}</Text>
            <View style={styles.rating}>
              <Ionicons name="star" size={13} color={colors.star} />
              <Text style={type.small}>
                {' '}{item.rating_avg ? Number(item.rating_avg).toFixed(2) : t('feed.new')}
              </Text>
            </View>
          </View>
          {place ? <Text style={type.small} numberOfLines={1}>{place}</Text> : null}
          {item.next_session_at ? (
            <Text style={type.small}>
              {formatSessionDate(item.next_session_at, lang)}
              {scarce ? <Text style={{ color: colors.danger }}>{` · ${t('feed.seatsLeft', { count: item.seats_left ?? 0 })}`}</Text> : null}
            </Text>
          ) : null}
          <Text style={[type.body, { marginTop: 4 }]}>
            <Text style={{ fontWeight: '700' }}>{formatMoney(item.price.total_cents, lang)} MXN</Text>
            <Text style={{ color: colors.textMuted }}> {t('feed.total')}</Text>
          </Text>
        </View>
      </Pressable>
    </Link>
  );
}

const styles = StyleSheet.create({
  card: { marginHorizontal: space.xl, marginBottom: space.xxl },
  meta: { marginTop: space.md, gap: 2 },
  titleRow: { flexDirection: 'row', alignItems: 'center' },
  rating: { flexDirection: 'row', alignItems: 'center', marginLeft: space.sm },
  pill: {
    position: 'absolute', top: space.md, left: space.md, backgroundColor: colors.white, borderRadius: radius.pill,
    paddingHorizontal: 12, paddingVertical: 6,
  },
  pillText: { fontSize: 13, fontWeight: '600', color: colors.text },
});
