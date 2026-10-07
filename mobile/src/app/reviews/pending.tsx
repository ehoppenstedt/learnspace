import { Ionicons } from '@expo/vector-icons';
import { router } from 'expo-router';
import { useTranslation } from 'react-i18next';
import { Pressable, ScrollView, StyleSheet, Text, View } from 'react-native';

import { Centered } from '@/components/ui';
import { usePendingReviews } from '@/lib/api/hooks';
import { formatSessionDate } from '@/lib/utils/format';
import { colors, radius, space, type } from '@/theme/tokens';

/** Everything the user still owes: class reviews (as learner) and learner ratings (as host). */
export default function PendingReviews() {
  const { t, i18n } = useTranslation();
  const pending = usePendingReviews();
  const reviews = pending.data?.reviews ?? [];
  const ratings = pending.data?.conduct_ratings ?? [];
  if (pending.data && !reviews.length && !ratings.length) {
    return <Centered><Text style={type.body}>{t('reviews.pendingEmpty')}</Text></Centered>;
  }
  const closes = (iso: string) => t('reviews.closes', { date: formatSessionDate(iso, i18n.language).split(' · ')[0] });
  return (
    <ScrollView contentContainerStyle={{ padding: space.xl }}>
      {reviews.map((r) => (
        <Item key={r.booking_id} icon="star" title={r.experience} subtitle={closes(r.closes_at)} action={t('reviews.rateClass')}
          onPress={() => router.push(`/review/${r.booking_id}`)} />
      ))}
      {ratings.map((r) => (
        <Item key={r.booking_id} icon="person" title={`${r.learner} · ${r.experience}`} subtitle={closes(r.closes_at)} action={t('reviews.rateLearner')}
          onPress={() => router.push({ pathname: '/provider/rate/[id]', params: { id: r.booking_id, name: r.learner } })} />
      ))}
    </ScrollView>
  );
}

function Item({ icon, title, subtitle, action, onPress }: { icon: 'star' | 'person'; title: string; subtitle: string; action: string; onPress: () => void }) {
  return (
    <Pressable style={styles.card} onPress={onPress} accessibilityRole="button">
      <View style={styles.icon}><Ionicons name={icon} size={18} color={colors.brand} /></View>
      <View style={{ flex: 1, marginLeft: space.md }}>
        <Text style={type.bodyStrong}>{title}</Text>
        <Text style={type.caption}>{subtitle}</Text>
      </View>
      <Text style={[type.smallStrong, { color: colors.brand }]}>{action}</Text>
    </Pressable>
  );
}

const styles = StyleSheet.create({
  card: { flexDirection: 'row', alignItems: 'center', borderWidth: 1, borderColor: colors.border, borderRadius: radius.md, padding: space.md, marginBottom: space.md },
  icon: { width: 36, height: 36, borderRadius: 18, backgroundColor: colors.brandSoft, alignItems: 'center', justifyContent: 'center' },
});
