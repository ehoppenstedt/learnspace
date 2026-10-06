import { useQueryClient } from '@tanstack/react-query';
import { useTranslation } from 'react-i18next';
import { Alert, FlatList, StyleSheet, Text, View } from 'react-native';

import { Button, Centered } from '@/components/ui';
import { ApiError, api } from '@/lib/api/client';
import { useProviderBookings } from '@/lib/api/hooks';
import type { ProviderBooking } from '@/lib/api/types';
import { formatMoney, formatSessionDate, seatsLabel } from '@/lib/utils/format';
import { colors, radius, space, type } from '@/theme/tokens';

export default function Requests() {
  const list = useProviderBookings('pending_approval');
  return (
    <FlatList
      data={list.data ?? []}
      keyExtractor={(b) => b.id}
      contentContainerStyle={{ padding: space.xl, flexGrow: 1 }}
      refreshing={list.isRefetching}
      onRefresh={() => list.refetch()}
      renderItem={({ item }) => <RequestCard item={item} />}
      ListEmptyComponent={<Centered><Text style={type.body}>—</Text></Centered>}
    />
  );
}

function RequestCard({ item }: { item: ProviderBooking }) {
  const { t, i18n } = useTranslation();
  const qc = useQueryClient();
  const decide = async (decision: 'approve' | 'decline') => {
    try {
      await api(`/provider/bookings/${item.id}/${decision}`, { method: 'POST' });
      qc.invalidateQueries({ queryKey: ['provider'] });
    } catch (err) {
      Alert.alert(err instanceof ApiError ? err.message : t('errors.network'));
    }
  };
  const score = item.learner.conduct_score;
  return (
    <View style={styles.card}>
      <Text style={type.heading}>{item.learner.first_name}</Text>
      <Text style={[type.small, { color: score ? colors.warning : colors.textMuted }]}>
        {score ? t('ops.conduct', { score, count: item.learner.conduct_count }) : t('ops.newLearner')}
      </Text>
      <Text style={[type.body, { marginTop: space.sm }]}>{item.experience_title}</Text>
      <Text style={type.small}>{formatSessionDate(item.starts_at, i18n.language)} · {seatsLabel(item.seats, i18n.language)} · {formatMoney(item.listed_cents, i18n.language)}</Text>
      {item.approval_deadline ? <Text style={type.caption}>{t('ops.deadline', { when: formatSessionDate(item.approval_deadline, i18n.language) })}</Text> : null}
      <View style={{ flexDirection: 'row', gap: space.md, marginTop: space.lg }}>
        <Button title={t('ops.decline')} variant="secondary" onPress={() => decide('decline')} style={{ flex: 1 }} />
        <Button title={t('ops.approve')} variant="dark" onPress={() => decide('approve')} style={{ flex: 1 }} />
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  card: { borderWidth: 1, borderColor: colors.border, borderRadius: radius.lg, padding: space.lg, marginBottom: space.lg },
});
