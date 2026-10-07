import { Ionicons } from '@expo/vector-icons';
import { useQueryClient } from '@tanstack/react-query';
import { router, useLocalSearchParams } from 'expo-router';
import { useTranslation } from 'react-i18next';
import { Alert, FlatList, Pressable, StyleSheet, Text, View } from 'react-native';

import { Button, Centered } from '@/components/ui';
import { ApiError, api } from '@/lib/api/client';
import { usePendingReviews, useRoster } from '@/lib/api/hooks';
import { openThreadAsProvider } from '@/lib/messaging';
import type { RosterAttendee } from '@/lib/api/types';
import { formatSessionDate, formatTimeRange } from '@/lib/utils/format';
import { colors, radius, space, type } from '@/theme/tokens';

export default function Roster() {
  const { id } = useLocalSearchParams<{ id: string }>();
  const { t, i18n } = useTranslation();
  const qc = useQueryClient();
  const roster = useRoster(id);
  const session = roster.data?.session;
  const pending = usePendingReviews();
  const owed = new Set(pending.data?.conduct_ratings.map((r) => r.booking_id));
  const ended = session ? new Date(session.ends_at) <= new Date() : false;

  const mark = async (a: RosterAttendee, attendance: 'present' | 'absent') => {
    try {
      await api(`/provider/sessions/${id}/attendance`, { method: 'POST', body: { marks: [{ booking_id: a.booking_id, attendance }] } });
      qc.invalidateQueries({ queryKey: ['provider', 'roster', id] });
    } catch (err) {
      Alert.alert(err instanceof ApiError ? err.message : t('errors.network'));
    }
  };

  const cancelSession = () =>
    Alert.alert(t('ops.cancelSession'), t('ops.cancelSessionConfirm'), [
      { text: t('common.cancel'), style: 'cancel' },
      {
        text: t('ops.cancelSession'), style: 'destructive', onPress: async () => {
          try {
            await api(`/provider/sessions/${id}/cancel`, { method: 'POST', body: {} });
            qc.invalidateQueries({ queryKey: ['provider'] });
            router.back();
          } catch (err) {
            Alert.alert(err instanceof ApiError ? err.message : t('errors.network'));
          }
        },
      },
    ]);

  return (
    <FlatList
      data={roster.data?.attendees ?? []}
      keyExtractor={(a) => a.booking_id}
      contentContainerStyle={{ padding: space.xl, flexGrow: 1 }}
      ListHeaderComponent={session ? (
        <View style={{ marginBottom: space.lg }}>
          <Text style={type.title}>{formatSessionDate(session.starts_at, i18n.language).split(' · ')[0]}</Text>
          <Text style={type.small}>{formatTimeRange(session.starts_at, session.ends_at, i18n.language)} · {session.seats_booked}/{session.capacity}</Text>
        </View>
      ) : null}
      renderItem={({ item }) => (
        <View style={styles.card}>
          <View style={{ flexDirection: 'row', alignItems: 'center' }}>
            <View style={{ flex: 1 }}>
              <Text style={type.bodyStrong}>{item.learner.first_name} {item.learner.last_initial}. · {t('ops.seats', { count: item.seats })}</Text>
              <Text style={type.caption}>
                {item.learner.conduct_score ? t('ops.conduct', { score: item.learner.conduct_score, count: item.learner.conduct_count }) : t('ops.newLearner')}
                {item.learner.fluent_languages.length ? ` · ${t('ops.languages')}: ${item.learner.fluent_languages.join(', ')}` : ''}
              </Text>
            </View>
            <Toggle active={item.attendance === 'present'} icon="checkmark" label={t('ops.present')} onPress={() => mark(item, 'present')} />
            <Toggle active={item.attendance === 'absent'} icon="close" label={t('ops.absent')} onPress={() => mark(item, 'absent')} />
          </View>
          <View style={{ flexDirection: 'row', gap: space.lg, marginTop: space.sm }}>
            <Pressable onPress={() => openThreadAsProvider(item.booking_id)} style={styles.link}>
              <Ionicons name="chatbubble-outline" size={16} color={colors.text} />
              <Text style={[type.smallStrong, { marginLeft: 4 }]}>{t('ops.message')}</Text>
            </Pressable>
            {ended && owed.has(item.booking_id) ? (
              <Pressable style={styles.link}
                onPress={() => router.push({ pathname: '/provider/rate/[id]', params: { id: item.booking_id, name: item.learner.first_name } })}>
                <Ionicons name="star-outline" size={16} color={colors.brand} />
                <Text style={[type.smallStrong, { marginLeft: 4, color: colors.brand }]}>{t('ops.rate')}</Text>
              </Pressable>
            ) : null}
          </View>
          {item.learner.accessibility_needs ? (
            <View style={styles.access}>
              <Ionicons name="accessibility-outline" size={16} color={colors.brand} />
              <Text style={[type.small, { marginLeft: 6, color: colors.text, flex: 1 }]}>{item.learner.accessibility_needs}</Text>
            </View>
          ) : null}
        </View>
      )}
      ListEmptyComponent={<Centered><Text style={type.body}>{t('ops.noAttendees')}</Text></Centered>}
      ListFooterComponent={session && session.status === 'scheduled' && new Date(session.starts_at) > new Date() ? (
        <Button title={t('ops.cancelSession')} variant="ghost" onPress={cancelSession} style={{ marginTop: space.xl }} />
      ) : null}
    />
  );
}

function Toggle({ active, icon, label, onPress }: { active: boolean; icon: 'checkmark' | 'close'; label: string; onPress: () => void }) {
  return (
    <Pressable onPress={onPress} accessibilityLabel={label} accessibilityState={{ selected: active }}
      style={[styles.toggle, active && { backgroundColor: icon === 'checkmark' ? colors.success : colors.danger, borderColor: 'transparent' }]}>
      <Ionicons name={icon} size={18} color={active ? colors.white : colors.text} />
    </Pressable>
  );
}

const styles = StyleSheet.create({
  card: { borderWidth: 1, borderColor: colors.border, borderRadius: radius.md, padding: space.md, marginBottom: space.md },
  toggle: { width: 40, height: 40, borderRadius: 20, borderWidth: 1, borderColor: colors.border, alignItems: 'center', justifyContent: 'center', marginLeft: space.sm },
  link: { flexDirection: 'row', alignItems: 'center', paddingVertical: 4 },
  access: { flexDirection: 'row', alignItems: 'center', backgroundColor: colors.brandSoft, borderRadius: radius.sm, padding: space.sm, marginTop: space.sm },
});
