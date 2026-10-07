import DateTimePicker from '@react-native-community/datetimepicker';
import { useQueryClient } from '@tanstack/react-query';
import { router, useLocalSearchParams } from 'expo-router';
import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Alert, Platform, Pressable, ScrollView, StyleSheet, Switch, Text, View } from 'react-native';

import { Button, Chip, Field, Section } from '@/components/ui';
import { ApiError, api } from '@/lib/api/client';
import { useProviderExperience, useProviderSessions } from '@/lib/api/hooks';
import type { ProviderSession } from '@/lib/api/types';
import { formatSessionDate, formatTimeRange } from '@/lib/utils/format';
import { colors, radius, space, type } from '@/theme/tokens';

const DURATIONS = [60, 90, 120, 180];

function ymd(d: Date) {
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
}
function defaultStart(): Date {
  const d = new Date(Date.now() + 86_400_000);
  d.setHours(19, 0, 0, 0);
  return d;
}
function isoWeekday(d: Date) {
  return ((d.getDay() + 6) % 7) + 1;
}
function hm(d: Date) {
  return `${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}`;
}

/** Device time is assumed to be Mexico City (launch market); the server stores UTC. */
export default function SessionsScreen() {
  const { id } = useLocalSearchParams<{ id: string }>();
  const { t, i18n } = useTranslation();
  const qc = useQueryClient();
  const experience = useProviderExperience(id);
  const sessions = useProviderSessions(id);
  const isCourse = experience.data?.offering_type === 'course';

  const [start, setStart] = useState(defaultStart);
  const [duration, setDuration] = useState(120);
  const [repeat, setRepeat] = useState(isCourse);
  const [days, setDays] = useState<number[]>(() => [isoWeekday(defaultStart())]);
  const [until, setUntil] = useState(() => new Date(defaultStart().getTime() + 27 * 86_400_000));
  const [capacity, setCapacity] = useState('');
  const [label, setLabel] = useState('');
  const [picker, setPicker] = useState<'date' | 'time' | 'until' | null>(null);
  const [busy, setBusy] = useState(false);
  const dayLabels = t('filters.days', { returnObjects: true }) as string[];

  const create = async () => {
    setBusy(true);
    const end = new Date(start.getTime() + duration * 60_000);
    const body = repeat || isCourse
      ? { recurrence: { days, start_time: hm(start), duration_minutes: duration, from_date: ymd(start), until_date: ymd(until) } }
      : { sessions: [{ starts_at: start.toISOString(), ends_at: end.toISOString() }] };
    try {
      const created = await api<ProviderSession[]>(`/provider/experiences/${id}/sessions`, {
        method: 'POST',
        body: { ...body, ...(capacity ? { capacity: Number(capacity) } : {}), ...(isCourse ? { label } : {}) },
      });
      Alert.alert(t('sessions.created', { count: created.length }));
      qc.invalidateQueries({ queryKey: ['provider'] });
    } catch (e) {
      Alert.alert(e instanceof ApiError ? e.message : t('errors.network'));
    } finally {
      setBusy(false);
    }
  };

  const remove = async (s: ProviderSession) => {
    try {
      await api(`/provider/sessions/${s.id}`, { method: 'DELETE' });
      qc.invalidateQueries({ queryKey: ['provider'] });
    } catch (e) {
      Alert.alert(e instanceof ApiError ? e.message : t('errors.network'));
    }
  };

  return (
    <ScrollView contentContainerStyle={{ paddingHorizontal: space.xl, paddingBottom: 60 }}>
      <Section title={t('sessions.add')}>
        {isCourse ? <Text style={[type.small, { marginBottom: space.md }]}>{t('sessions.courseHint')}</Text> : null}
        <View style={{ flexDirection: 'row', gap: space.md }}>
          <Box label={t('sessions.date')} value={formatSessionDate(start.toISOString(), i18n.language).split(' · ')[0]} onPress={() => setPicker('date')} />
          <Box label={t('sessions.start')} value={hm(start)} onPress={() => setPicker('time')} />
        </View>
        <Text style={styles.label}>{t('sessions.duration')}</Text>
        <View style={styles.wrap}>
          {DURATIONS.map((d) => <Chip key={d} label={t('sessions.minutes', { n: d })} selected={duration === d} onPress={() => setDuration(d)} />)}
        </View>
        {!isCourse ? (
          <View style={styles.switchRow}>
            <Text style={type.body}>{t('sessions.repeat')}</Text>
            <Switch value={repeat} onValueChange={setRepeat} />
          </View>
        ) : null}
        {repeat || isCourse ? (
          <>
            <Text style={styles.label}>{t('sessions.days')}</Text>
            <View style={styles.wrap}>
              {dayLabels.map((d, i) => (
                <Chip key={d} label={d} selected={days.includes(i + 1)} onPress={() => setDays(days.includes(i + 1) ? days.filter((x) => x !== i + 1) : [...days, i + 1])} />
              ))}
            </View>
            <Box label={t('sessions.until')} value={formatSessionDate(until.toISOString(), i18n.language).split(' · ')[0]} onPress={() => setPicker('until')} />
          </>
        ) : null}
        {isCourse ? <Field label={t('sessions.label')} value={label} onChangeText={setLabel} style={{ marginTop: space.md }} /> : null}
        <Field label={t('sessions.capacity')} value={capacity} onChangeText={(v) => setCapacity(v.replace(/\D/g, ''))}
          keyboardType="number-pad" placeholder={String(experience.data?.default_capacity ?? 10)} style={{ marginTop: space.md }} />
        <Button title={t('sessions.create')} onPress={create} loading={busy} disabled={(repeat || isCourse) && !days.length} />
        {picker ? (
          <DateTimePicker
            mode={picker === 'time' ? 'time' : 'date'}
            value={picker === 'until' ? until : start}
            minimumDate={new Date()}
            minuteInterval={15}
            display={Platform.OS === 'ios' ? 'inline' : 'default'}
            onChange={(event, date) => {
              if (Platform.OS !== 'ios') setPicker(null);
              if (event.type !== 'set' || !date) return;
              if (picker === 'until') setUntil(date);
              else if (picker === 'date') {
                const next = new Date(date);
                next.setHours(start.getHours(), start.getMinutes(), 0, 0);
                setStart(next);
              } else {
                const next = new Date(start);
                next.setHours(date.getHours(), date.getMinutes(), 0, 0);
                setStart(next);
              }
            }}
          />
        ) : null}
      </Section>

      <Section title={t('sessions.title')} last>
        {(sessions.data ?? []).length === 0 ? <Text style={type.small}>{t('sessions.empty')}</Text> : null}
        {(sessions.data ?? []).map((s) => (
          <View key={s.id} style={styles.sessionRow}>
            <Pressable style={{ flex: 1 }} onPress={() => router.push(`/provider/roster/${s.id}`)}>
              <Text style={type.bodyStrong}>{formatSessionDate(s.starts_at, i18n.language).split(' · ')[0]}</Text>
              <Text style={type.small}>{formatTimeRange(s.starts_at, s.ends_at, i18n.language)} · {s.seats_booked}/{s.capacity}</Text>
            </Pressable>
            {s.seats_booked === 0 ? <Button title={t('common.delete')} variant="ghost" onPress={() => remove(s)} /> : null}
          </View>
        ))}
      </Section>
    </ScrollView>
  );
}

function Box({ label, value, onPress }: { label: string; value: string; onPress: () => void }) {
  return (
    <Pressable style={styles.box} onPress={onPress}>
      <Text style={type.caption}>{label}</Text>
      <Text style={type.bodyStrong}>{value}</Text>
    </Pressable>
  );
}

const styles = StyleSheet.create({
  label: { ...type.smallStrong, marginTop: space.lg, marginBottom: space.sm },
  wrap: { flexDirection: 'row', flexWrap: 'wrap' },
  box: { flex: 1, borderWidth: 1, borderColor: colors.border, borderRadius: radius.md, padding: space.md, marginTop: space.sm },
  switchRow: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', marginTop: space.lg },
  sessionRow: { flexDirection: 'row', alignItems: 'center', paddingVertical: space.md, borderBottomWidth: StyleSheet.hairlineWidth, borderBottomColor: colors.hairline },
});
