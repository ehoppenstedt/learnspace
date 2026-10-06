import { Ionicons } from '@expo/vector-icons';
import { useQueryClient } from '@tanstack/react-query';
import { Image } from 'expo-image';
import * as ImagePicker from 'expo-image-picker';
import { router, Stack, useLocalSearchParams } from 'expo-router';
import { useEffect, useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { ActivityIndicator, Alert, Pressable, ScrollView, StyleSheet, Text, View } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';

import { Badge, Button, Chip, Field } from '@/components/ui';
import { ApiError, api } from '@/lib/api/client';
import { useConfig, useExperienceAction, useProviderExperience, useProviderSpaces } from '@/lib/api/hooks';
import type { Media, OfferingType, ProviderExperience } from '@/lib/api/types';
import { formatMoney, pesosToCents, previewTotal } from '@/lib/utils/format';
import { pollMedia, uploadAsset } from '@/lib/utils/upload';
import { colors, radius, space, statusColors, type } from '@/theme/tokens';

type Draft = {
  title: string;
  what_you_learn: string;
  who_its_for: string;
  category_id: number | null;
  instruction_language: string;
  offering_type: OfferingType;
  price: string; // pesos as typed
  default_capacity: string;
  space_id: string | null;
  publish_until: string | null;
};

type Tile = { key: string; media?: Media; localUri?: string; state: 'uploading' | 'processing' | 'ready' | 'rejected' };

const EMPTY: Draft = {
  title: '', what_you_learn: '', who_its_for: '', category_id: null, instruction_language: 'es', offering_type: 'single',
  price: '', default_capacity: '10', space_id: null, publish_until: null,
};

function fromServer(e: ProviderExperience): Draft {
  return {
    title: e.title, what_you_learn: e.what_you_learn, who_its_for: e.who_its_for, category_id: e.category_id,
    instruction_language: e.instruction_language, offering_type: e.offering_type,
    price: e.listed_price_cents ? String(e.listed_price_cents / 100) : '', default_capacity: String(e.default_capacity),
    space_id: e.space_id, publish_until: e.publish_until,
  };
}

/** Create / edit wizard. Six short steps; every "Next" saves, so nothing is lost. */
export default function ExperienceWizard() {
  const { id: routeId } = useLocalSearchParams<{ id: string }>();
  const { t, i18n } = useTranslation();
  const qc = useQueryClient();
  const config = useConfig();
  const [id, setId] = useState<string | undefined>(routeId === 'new' ? undefined : routeId);
  const existing = useProviderExperience(id);
  const spaces = useProviderSpaces(true);
  const action = useExperienceAction();
  const [step, setStep] = useState(0);
  const [draft, setDraft] = useState<Draft>(EMPTY);
  const [tiles, setTiles] = useState<Tile[]>([]);
  const [saving, setSaving] = useState(false);
  const [errors, setErrors] = useState<Record<string, string>>({});
  const steps = t('wizard.steps', { returnObjects: true }) as string[];
  const exp = existing.data;

  useEffect(() => {
    if (exp) {
      setDraft(fromServer(exp));
      setTiles(exp.media.map((m) => ({ key: m.id, media: m, state: m.status === 'rejected' ? 'rejected' : m.urls || m.poster_url ? 'ready' : 'processing' })));
    }
  }, [exp]);

  const listedCents = pesosToCents(draft.price) ?? 0;
  const preview = useMemo(() => previewTotal(listedCents, config.data?.fee_bps ?? 500), [listedCents, config.data?.fee_bps]);
  const set = <K extends keyof Draft>(key: K, value: Draft[K]) => setDraft((d) => ({ ...d, [key]: value }));

  const payload = () => ({
    title: draft.title.trim(), what_you_learn: draft.what_you_learn.trim(), who_its_for: draft.who_its_for.trim(),
    category_id: draft.category_id, instruction_language: draft.instruction_language, offering_type: draft.offering_type,
    listed_price_cents: listedCents, default_capacity: Number(draft.default_capacity) || 10, space_id: draft.space_id,
    publish_until: draft.publish_until,
    media_ids: tiles.filter((x) => x.media && x.state !== 'rejected').map((x) => x.media!.id),
  });

  const save = async (): Promise<string | undefined> => {
    setSaving(true);
    setErrors({});
    try {
      const body = payload();
      const saved = id
        ? await api<ProviderExperience>(`/provider/experiences/${id}`, { method: 'PATCH', body })
        : await api<ProviderExperience>('/provider/experiences', { method: 'POST', body });
      if (!id) {
        setId(saved.id);
        router.setParams({ id: saved.id });
      }
      qc.setQueryData(['provider', 'experience', saved.id], saved);
      qc.invalidateQueries({ queryKey: ['provider', 'experiences'] });
      return saved.id;
    } catch (e) {
      if (e instanceof ApiError) setErrors({ form: e.message, ...Object.fromEntries(Object.keys(e.fields).map((k) => [k, e.fieldMessage(k) ?? ''])) });
      else setErrors({ form: t('errors.network') });
      return undefined;
    } finally {
      setSaving(false);
    }
  };

  const next = async () => {
    if (await save()) setStep((s) => Math.min(s + 1, steps.length - 1));
  };

  const submit = async () => {
    const savedId = await save();
    if (!savedId) return;
    try {
      await action.mutateAsync({ id: savedId, action: 'submit' });
      Alert.alert(t('wizard.submitted'));
      router.replace('/provider');
    } catch (e) {
      if (e instanceof ApiError) {
        const fieldErrors = Object.fromEntries(Object.keys(e.fields).map((k) => [k, e.fieldMessage(k) ?? '']));
        setErrors({ form: e.message, ...fieldErrors });
        if (fieldErrors.sessions) Alert.alert(t('wizard.needDates'), '', [{ text: t('wizard.addDates'), onPress: () => router.push(`/provider/sessions/${savedId}`) }]);
      }
    }
  };

  const pickMedia = async () => {
    const max = config.data?.media.max_images ?? 10;
    const picked = await ImagePicker.launchImageLibraryAsync({
      mediaTypes: ['images', 'videos'], allowsMultipleSelection: true, selectionLimit: max, quality: 0.9,
      videoMaxDuration: config.data?.media.max_video_seconds ?? 60,
    });
    if (picked.canceled) return;
    for (const asset of picked.assets) {
      const key = asset.assetId ?? asset.uri;
      setTiles((prev) => [...prev, { key, localUri: asset.uri, state: 'uploading' }]);
      uploadAsset(asset, asset.type === 'video' ? 'video' : 'image')
        .then(async (status) => {
          setTiles((prev) => prev.map((x) => (x.key === key ? { ...x, key: status.id, state: 'processing', media: { id: status.id } as Media } : x)));
          const done = await pollMedia(status.id);
          setTiles((prev) => prev.map((x) => (x.key === status.id
            ? { ...x, state: done.status === 'ready' ? 'ready' : 'rejected', media: done.preview ?? x.media }
            : x)));
        })
        .catch(() => setTiles((prev) => prev.map((x) => (x.key === key ? { ...x, state: 'rejected' } : x))));
    }
  };

  if (id && existing.isLoading) return <ActivityIndicator style={{ marginTop: 80 }} />;
  const sc = exp ? statusColors[exp.status] : null;
  const isLive = exp?.status === 'live' || exp?.status === 'paused';
  const uploading = tiles.some((x) => x.state === 'uploading');

  return (
    <SafeAreaView style={{ flex: 1, backgroundColor: colors.bg }} edges={['bottom']}>
      <Stack.Screen options={{ title: steps[step] }} />
      <View style={styles.progress}>
        {steps.map((s, i) => <View key={s} style={[styles.progressBar, i <= step && { backgroundColor: colors.text }]} />)}
      </View>
      <ScrollView contentContainerStyle={{ padding: space.xl, paddingBottom: 40 }} keyboardShouldPersistTaps="handled">
        {exp && sc ? (
          <View style={{ marginBottom: space.lg, gap: space.sm }}>
            <Badge label={t(`provider.status.${exp.status}`)} bg={sc.bg} fg={sc.fg} />
            {isLive ? <Text style={type.small}>{t('wizard.liveEditNote')}</Text> : null}
            {exp.last_decision && exp.last_decision.review_status !== 'approved' && exp.last_decision.reviewer_note ? (
              <View style={styles.note}>
                <Text style={type.smallStrong}>{t('provider.reviewerNote')}</Text>
                <Text style={type.small}>{exp.last_decision.reviewer_note}</Text>
              </View>
            ) : null}
          </View>
        ) : null}

        {step === 0 ? (
          <>
            <Field label={t('wizard.title')} hint={t('wizard.titleHint')} value={draft.title} onChangeText={(v) => set('title', v)} maxLength={90} error={errors.title} />
            <Text style={styles.label}>{t('wizard.category')}</Text>
            <View style={styles.wrap}>
              {(config.data?.categories ?? []).map((c) => (
                <Chip key={c.id} label={c.name} icon={c.icon as never} selected={draft.category_id === c.id} onPress={() => set('category_id', c.id)} />
              ))}
            </View>
            <Text style={styles.label}>{t('wizard.offering')}</Text>
            <View style={styles.wrap}>
              {(['single', 'course', 'dropin'] as const).map((o) => (
                <Chip key={o} label={t(`wizard.${o}`)} selected={draft.offering_type === o} onPress={() => set('offering_type', o)} />
              ))}
            </View>
            <Text style={styles.label}>{t('wizard.language')}</Text>
            <View style={styles.wrap}>
              <Chip label="Español" selected={draft.instruction_language === 'es'} onPress={() => set('instruction_language', 'es')} />
              <Chip label="English" selected={draft.instruction_language === 'en'} onPress={() => set('instruction_language', 'en')} />
            </View>
            <Text style={styles.label}>{t('wizard.modality')}</Text>
            <View style={styles.wrap}>
              <Chip label={t('filters.inPerson')} selected />
              <Chip label={`${t('filters.online')} · ${t('common.comingSoon')}`} />
            </View>
          </>
        ) : null}

        {step === 1 ? (
          <>
            <Field label={t('wizard.whatYouLearn')} hint={t('wizard.whatYouLearnHint')} value={draft.what_you_learn}
              onChangeText={(v) => set('what_you_learn', v)} multiline maxLength={3000} error={errors.what_you_learn} />
            <Field label={t('wizard.whoFor')} value={draft.who_its_for} onChangeText={(v) => set('who_its_for', v)} multiline maxLength={1500} error={errors.who_its_for} />
          </>
        ) : null}

        {step === 2 ? (
          <>
            <Text style={type.heading}>{t('wizard.media')}</Text>
            <Text style={[type.small, { marginVertical: space.sm }]}>{t('wizard.mediaHint')}</Text>
            <View style={styles.grid}>
              {tiles.map((tile, i) => (
                <View key={tile.key} style={[styles.tile, i === 0 && styles.tileCover]}>
                  <Image
                    source={tile.media?.urls?.w400 ?? tile.media?.poster_url ?? tile.localUri}
                    style={StyleSheet.absoluteFill}
                    contentFit="cover"
                  />
                  {tile.state !== 'ready' ? (
                    <View style={styles.tileOverlay}>
                      <Text style={styles.tileText}>
                        {tile.state === 'uploading' ? t('wizard.uploading') : tile.state === 'processing' ? t('wizard.processing') : t('wizard.rejected')}
                      </Text>
                    </View>
                  ) : null}
                  <Pressable style={styles.remove} hitSlop={8} onPress={() => setTiles((prev) => prev.filter((x) => x.key !== tile.key))}>
                    <Ionicons name="close" size={16} color={colors.text} />
                  </Pressable>
                </View>
              ))}
              <Pressable style={[styles.tile, styles.add]} onPress={pickMedia}>
                <Ionicons name="images-outline" size={28} color={colors.text} />
                <Text style={type.smallStrong}>{t('wizard.addMedia')}</Text>
              </Pressable>
            </View>
            {errors.media_ids ? <Text style={styles.error}>{errors.media_ids}</Text> : null}
          </>
        ) : null}

        {step === 3 ? (
          <>
            <Field label={draft.offering_type === 'course' ? t('wizard.priceCourse') : t('wizard.price')} value={draft.price}
              onChangeText={(v) => set('price', v)} keyboardType="decimal-pad" placeholder="500" error={errors.listed_price_cents} />
            {listedCents > 0 ? (
              <View style={styles.pricePreview}>
                <Text style={type.body}>{t('wizard.learnersPay', { total: `${formatMoney(preview.total_cents, i18n.language)} MXN` })}</Text>
                <Text style={[type.small, { marginTop: 4 }]}>{t('wizard.youReceive', { listed: `${formatMoney(listedCents, i18n.language)} MXN` })}</Text>
              </View>
            ) : null}
            <Field label={t('wizard.capacity')} value={draft.default_capacity} onChangeText={(v) => set('default_capacity', v.replace(/\D/g, ''))} keyboardType="number-pad" />
          </>
        ) : null}

        {step === 4 ? (
          <>
            <Text style={styles.label}>{t('wizard.pickSpace')}</Text>
            {(spaces.data ?? []).map((s) => (
              <Pressable key={s.id} style={[styles.spaceRow, draft.space_id === s.id && { borderColor: colors.text, borderWidth: 2 }]} onPress={() => set('space_id', s.id)}>
                <Ionicons name="location-outline" size={20} color={colors.text} />
                <View style={{ marginLeft: space.md, flex: 1 }}>
                  <Text style={type.bodyStrong}>{s.name}</Text>
                  <Text style={type.small}>{s.location.area ?? s.neighborhood} · {s.address_line}</Text>
                </View>
              </Pressable>
            ))}
            <Button title={t('wizard.newSpace')} icon="add" variant="secondary" onPress={() => router.push('/provider/space')} />
            {errors.space_id ? <Text style={styles.error}>{errors.space_id}</Text> : null}
          </>
        ) : null}

        {step === 5 ? (
          <>
            <Text style={styles.label}>{t('wizard.publishUntil')}</Text>
            <View style={styles.wrap}>
              <Chip label={t('wizard.indefinite')} selected={!draft.publish_until} onPress={() => set('publish_until', null)} />
              <Chip label={`${t('wizard.untilDate')}: +90 d`} selected={Boolean(draft.publish_until)}
                onPress={() => set('publish_until', new Date(Date.now() + 90 * 86_400_000).toISOString())} />
            </View>
            <Text style={styles.label}>{t('wizard.policy')}</Text>
            <View style={styles.note}>
              <Text style={type.bodyStrong}>{config.data?.cancellation_policies[0]?.name}</Text>
              <Text style={type.small}>{config.data?.cancellation_policies[0]?.description}</Text>
            </View>
            <Pressable style={styles.spaceRow} onPress={async () => { const sid = await save(); if (sid) router.push(`/provider/sessions/${sid}`); }}>
              <Ionicons name="calendar-outline" size={20} color={colors.text} />
              <View style={{ marginLeft: space.md, flex: 1 }}>
                <Text style={type.bodyStrong}>{t('provider.manageSessions')}</Text>
                <Text style={type.small}>{exp?.sessions_upcoming ?? 0} {t('provider.sessions').toLowerCase()}</Text>
              </View>
              <Ionicons name="chevron-forward" size={18} color={colors.text} />
            </Pressable>
          </>
        ) : null}

        {errors.form ? <Text style={styles.error}>{errors.form}</Text> : null}
      </ScrollView>

      <View style={styles.footer}>
        <Button title={t('common.back')} variant="ghost" onPress={() => (step === 0 ? router.back() : setStep(step - 1))} />
        {step < steps.length - 1 ? (
          <Button title={t('common.next')} variant="dark" onPress={next} loading={saving} disabled={uploading} />
        ) : (
          <View style={{ flexDirection: 'row', gap: space.sm }}>
            <Button title={t('wizard.saveDraft')} variant="secondary" onPress={async () => { if (await save()) Alert.alert(t('wizard.saved')); }} loading={saving} />
            <Button title={t('wizard.submit')} onPress={submit} loading={action.isPending} disabled={exp?.status === 'in_review'} />
          </View>
        )}
      </View>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  progress: { flexDirection: 'row', gap: 4, paddingHorizontal: space.xl, paddingTop: space.sm },
  progressBar: { flex: 1, height: 3, borderRadius: 2, backgroundColor: colors.border },
  label: { ...type.smallStrong, marginTop: space.md, marginBottom: space.sm },
  wrap: { flexDirection: 'row', flexWrap: 'wrap' },
  grid: { flexDirection: 'row', flexWrap: 'wrap', gap: space.sm, marginTop: space.md },
  tile: { width: '31.5%', aspectRatio: 1, borderRadius: radius.md, overflow: 'hidden', backgroundColor: colors.surface },
  tileCover: { width: '100%', aspectRatio: 1.4 },
  tileOverlay: { ...StyleSheet.absoluteFill, backgroundColor: colors.overlay, alignItems: 'center', justifyContent: 'center' },
  tileText: { color: colors.white, fontWeight: '600', fontSize: 12 },
  remove: { position: 'absolute', top: 6, right: 6, width: 26, height: 26, borderRadius: 13, backgroundColor: colors.white, alignItems: 'center', justifyContent: 'center' },
  add: { alignItems: 'center', justifyContent: 'center', borderWidth: 1, borderStyle: 'dashed', borderColor: colors.textMuted, gap: 4 },
  pricePreview: { backgroundColor: colors.brandSoft, borderRadius: radius.md, padding: space.lg, marginBottom: space.lg },
  spaceRow: { flexDirection: 'row', alignItems: 'center', borderWidth: 1, borderColor: colors.border, borderRadius: radius.md, padding: space.lg, marginBottom: space.md },
  note: { backgroundColor: colors.surface, borderRadius: radius.md, padding: space.md, gap: 4, marginBottom: space.md },
  error: { color: colors.danger, marginTop: space.md },
  footer: {
    flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', paddingHorizontal: space.xl, paddingTop: space.md,
    borderTopWidth: StyleSheet.hairlineWidth, borderTopColor: colors.hairline,
  },
});
