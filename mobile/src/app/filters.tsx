import DateTimePicker from '@react-native-community/datetimepicker';
import { router } from 'expo-router';
import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Platform, Pressable, ScrollView, StyleSheet, Text, TextInput, View } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';

import { Button, Chip, Section } from '@/components/ui';
import { useConfig } from '@/lib/api/hooks';
import { useFilters } from '@/lib/state/FiltersContext';
import { DEFAULT_FILTERS, type Filters } from '@/lib/utils/filters';
import { pesosToCents } from '@/lib/utils/format';
import { colors, radius, space, type } from '@/theme/tokens';

const RADII = [2, 5, 10, 20, 50];

function toDate(hhmm: string | null, fallback: string): Date {
  const [h, m] = (hhmm ?? fallback).split(':').map(Number);
  const d = new Date();
  d.setHours(h, m, 0, 0);
  return d;
}

function toHHMM(d: Date): string {
  return `${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}`;
}

export default function FiltersScreen() {
  const { t } = useTranslation();
  const config = useConfig();
  const { filters, setFilters } = useFilters();
  const [draft, setDraft] = useState<Filters>(filters);
  const [priceMin, setPriceMin] = useState(draft.price_min_cents !== null ? String(draft.price_min_cents / 100) : '');
  const [priceMax, setPriceMax] = useState(draft.price_max_cents !== null ? String(draft.price_max_cents / 100) : '');
  const [picker, setPicker] = useState<'from' | 'to' | null>(null);
  const dayLabels = t('filters.days', { returnObjects: true }) as string[];

  const toggle = <T,>(list: T[], value: T) => (list.includes(value) ? list.filter((v) => v !== value) : [...list, value]);

  const apply = () => {
    setFilters({ ...draft, price_min_cents: pesosToCents(priceMin), price_max_cents: pesosToCents(priceMax) });
    router.back();
  };

  return (
    <SafeAreaView style={{ flex: 1, backgroundColor: colors.bg }} edges={['bottom']}>
      <ScrollView contentContainerStyle={{ paddingHorizontal: space.xl }}>
        <Section title={t('filters.categories')}>
          <View style={styles.wrap}>
            {(config.data?.categories ?? []).map((c) => (
              <Chip key={c.slug} label={c.name} icon={c.icon as never} selected={draft.categories.includes(c.slug)}
                onPress={() => setDraft({ ...draft, categories: toggle(draft.categories, c.slug) })} />
            ))}
          </View>
        </Section>

        <Section title={t('filters.price')}>
          <View style={{ flexDirection: 'row', gap: space.md }}>
            <PriceBox label={t('filters.min')} value={priceMin} onChange={setPriceMin} />
            <PriceBox label={t('filters.max')} value={priceMax} onChange={setPriceMax} />
          </View>
        </Section>

        <Section title={t('filters.radius')}>
          <View style={styles.wrap}>
            {RADII.map((km) => (
              <Chip key={km} label={t('filters.km', { n: km })} selected={draft.radius_km === km} onPress={() => setDraft({ ...draft, radius_km: km })} />
            ))}
          </View>
        </Section>

        <Section title={t('filters.when')}>
          <View style={styles.wrap}>
            {dayLabels.map((label, i) => (
              <Chip key={label} label={label} selected={draft.days.includes(i + 1)} onPress={() => setDraft({ ...draft, days: toggle(draft.days, i + 1) })} />
            ))}
          </View>
          <View style={{ flexDirection: 'row', gap: space.md, marginTop: space.md }}>
            <TimeBox label={t('filters.from')} value={draft.time_from} onPress={() => setPicker('from')} onClear={() => setDraft({ ...draft, time_from: null })} />
            <TimeBox label={t('filters.to')} value={draft.time_to} onPress={() => setPicker('to')} onClear={() => setDraft({ ...draft, time_to: null })} />
          </View>
          {picker ? (
            <DateTimePicker
              mode="time"
              value={toDate(picker === 'from' ? draft.time_from : draft.time_to, picker === 'from' ? '18:00' : '21:00')}
              minuteInterval={15}
              display={Platform.OS === 'ios' ? 'spinner' : 'default'}
              onChange={(event, date) => {
                if (Platform.OS !== 'ios') setPicker(null);
                if (event.type === 'set' && date) setDraft({ ...draft, [picker === 'from' ? 'time_from' : 'time_to']: toHHMM(date) });
              }}
            />
          ) : null}
        </Section>

        {config.data?.features.online_experiences ? (
          <Section title={t('filters.modality')}>
            <View style={styles.wrap}>
              <Chip label={t('filters.any')} selected={draft.modality === null} onPress={() => setDraft({ ...draft, modality: null })} />
              <Chip label={t('filters.inPerson')} selected={draft.modality === 'in_person'} onPress={() => setDraft({ ...draft, modality: 'in_person' })} />
              <Chip label={t('filters.online')} selected={draft.modality === 'online'} onPress={() => setDraft({ ...draft, modality: 'online' })} />
            </View>
          </Section>
        ) : null}

        <Section title={t('filters.language')} last>
          <View style={styles.wrap}>
            <Chip label={t('filters.any')} selected={draft.language === null} onPress={() => setDraft({ ...draft, language: null })} />
            <Chip label="Español" selected={draft.language === 'es'} onPress={() => setDraft({ ...draft, language: 'es' })} />
            <Chip label="English" selected={draft.language === 'en'} onPress={() => setDraft({ ...draft, language: 'en' })} />
          </View>
        </Section>
      </ScrollView>
      <View style={styles.footer}>
        <Button title={t('common.clear')} variant="ghost" onPress={() => { setDraft(DEFAULT_FILTERS); setPriceMin(''); setPriceMax(''); }} />
        <Button title={t('common.apply')} variant="dark" onPress={apply} />
      </View>
    </SafeAreaView>
  );
}

function PriceBox({ label, value, onChange }: { label: string; value: string; onChange: (v: string) => void }) {
  return (
    <View style={styles.box}>
      <Text style={type.caption}>{label}</Text>
      <View style={{ flexDirection: 'row', alignItems: 'center' }}>
        <Text style={type.body}>$</Text>
        <TextInput value={value} onChangeText={onChange} keyboardType="numeric" style={[type.body, { flex: 1, padding: 0, marginLeft: 2 }]} />
      </View>
    </View>
  );
}

function TimeBox({ label, value, onPress, onClear }: { label: string; value: string | null; onPress: () => void; onClear: () => void }) {
  return (
    <Pressable style={styles.box} onPress={onPress} onLongPress={onClear}>
      <Text style={type.caption}>{label}</Text>
      <Text style={type.body}>{value ?? '—'}</Text>
    </Pressable>
  );
}

const styles = StyleSheet.create({
  wrap: { flexDirection: 'row', flexWrap: 'wrap' },
  box: { flex: 1, borderWidth: 1, borderColor: colors.border, borderRadius: radius.md, padding: space.md },
  footer: {
    flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', paddingHorizontal: space.xl, paddingTop: space.md,
    borderTopWidth: StyleSheet.hairlineWidth, borderTopColor: colors.hairline,
  },
});
