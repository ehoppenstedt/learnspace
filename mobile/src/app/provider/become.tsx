import { useQueryClient } from '@tanstack/react-query';
import * as ImagePicker from 'expo-image-picker';
import { router } from 'expo-router';
import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { ScrollView, Text, View } from 'react-native';

import { Badge, Button, Chip, Field, Section } from '@/components/ui';
import { ApiError, api } from '@/lib/api/client';
import { useConfig, useProviderProfile, useVerificationDocs } from '@/lib/api/hooks';
import type { ProviderProfile } from '@/lib/api/types';
import { useAuth } from '@/lib/auth/AuthContext';
import { uploadAsset } from '@/lib/utils/upload';
import { colors, space, type } from '@/theme/tokens';

/** Become a provider: public profile + government ID upload (admin verifies before anything goes live). */
export default function BecomeProvider() {
  const { t } = useTranslation();
  const qc = useQueryClient();
  const { me, refreshMe } = useAuth();
  const config = useConfig();
  const isProvider = Boolean(me?.is_provider);
  const profile = useProviderProfile(isProvider);
  const docs = useVerificationDocs(isProvider);
  const [form, setForm] = useState<Partial<ProviderProfile>>({});
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string>();
  const value = { ...profile.data, ...form };

  const activate = async () => {
    setBusy(true);
    try {
      await api('/provider/activate', { method: 'POST' });
      await refreshMe();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : t('errors.network'));
    } finally {
      setBusy(false);
    }
  };

  const saveProfile = async () => {
    setBusy(true);
    try {
      await api('/provider/profile', { method: 'PATCH', body: form });
      await qc.invalidateQueries({ queryKey: ['provider', 'profile'] });
      setForm({});
    } catch (e) {
      setError(e instanceof ApiError ? e.message : t('errors.network'));
    } finally {
      setBusy(false);
    }
  };

  const uploadId = async () => {
    const picked = await ImagePicker.launchImageLibraryAsync({ mediaTypes: ['images'], quality: 0.9 });
    if (picked.canceled || !picked.assets[0]) return;
    setBusy(true);
    setError(undefined);
    try {
      const media = await uploadAsset(picked.assets[0], 'document');
      await api('/provider/verification-docs', { method: 'POST', body: { doc_type: 'government_id', media_id: media.id } });
      await qc.invalidateQueries({ queryKey: ['provider'] });
    } catch (e) {
      setError(e instanceof ApiError ? e.message : t('errors.generic'));
    } finally {
      setBusy(false);
    }
  };

  if (!isProvider) {
    return (
      <View style={{ padding: space.xl }}>
        <Text style={type.display}>{t('provider.becomeTitle', { brand: config.data?.brand ?? 'learnspace' })}</Text>
        <Text style={[type.body, { marginVertical: space.lg }]}>{t('provider.becomeBody')}</Text>
        {error ? <Text style={{ color: colors.danger, marginBottom: space.md }}>{error}</Text> : null}
        <Button title={t('provider.activate')} onPress={activate} loading={busy} />
      </View>
    );
  }

  const status = profile.data?.verification_status;
  const latestId = docs.data?.find((d) => d.doc_type === 'government_id');
  return (
    <ScrollView contentContainerStyle={{ paddingHorizontal: space.xl, paddingBottom: 60 }}>
      <Section title={t('provider.idTitle')}>
        {status === 'verified' ? (
          <Badge label={t('provider.idVerified')} bg="#E3F6EC" fg={colors.success} />
        ) : latestId?.status === 'pending' ? (
          <Badge label={t('provider.idPending')} bg="#FFF4D6" fg={colors.warning} />
        ) : (
          <>
            {status === 'rejected' ? <Badge label={t('provider.idRejected')} bg="#FDE2E1" fg={colors.danger} /> : null}
            <Text style={[type.body, { marginVertical: space.md }]}>{t('provider.idBody')}</Text>
            <Button title={t('provider.uploadId')} icon="id-card-outline" variant="secondary" onPress={uploadId} loading={busy} />
          </>
        )}
      </Section>
      <Section last>
        <Field label={t('provider.displayName')} value={value.display_name ?? ''} onChangeText={(v) => setForm({ ...form, display_name: v })} />
        <Text style={[type.smallStrong, { marginBottom: space.sm }]}>{t('provider.kind')}</Text>
        <View style={{ flexDirection: 'row', marginBottom: space.lg }}>
          {(['individual', 'school', 'studio'] as const).map((k) => (
            <Chip key={k} selected={value.kind === k} onPress={() => setForm({ ...form, kind: k })}
              label={t(k === 'individual' ? 'provider.kindIndividual' : k === 'school' ? 'provider.kindSchool' : 'provider.kindStudio')} />
          ))}
        </View>
        <Field label={t('provider.aboutMe')} value={value.about_me ?? ''} onChangeText={(v) => setForm({ ...form, about_me: v })} multiline />
        {value.kind !== 'individual' ? (
          <Field label={t('provider.aboutSchool')} value={value.about_school ?? ''} onChangeText={(v) => setForm({ ...form, about_school: v })} multiline />
        ) : null}
        {error ? <Text style={{ color: colors.danger, marginBottom: space.md }}>{error}</Text> : null}
        <Button title={t('common.save')} onPress={saveProfile} loading={busy} disabled={!Object.keys(form).length} />
        <Button title={t('provider.myExperiences')} variant="ghost" onPress={() => router.replace('/provider')} />
      </Section>
    </ScrollView>
  );
}
