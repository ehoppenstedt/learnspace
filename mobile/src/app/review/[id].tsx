import { useQueryClient } from '@tanstack/react-query';
import { Image } from 'expo-image';
import { router, useLocalSearchParams } from 'expo-router';
import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { ActivityIndicator, Alert, KeyboardAvoidingView, Platform, ScrollView, Text, View } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';

import { StarInput } from '@/components/Stars';
import { Button, Field } from '@/components/ui';
import { ApiError, api } from '@/lib/api/client';
import { useBooking } from '@/lib/api/hooks';
import { colors, radius, space, type } from '@/theme/tokens';

/** Learner reviews a class: overall + learning + host (+ space if in person), public text, private note. */
export default function ReviewScreen() {
  const { id } = useLocalSearchParams<{ id: string }>();
  const { t } = useTranslation();
  const qc = useQueryClient();
  const booking = useBooking(id);
  const [stars, setStars] = useState({ overall: 0, learning: 0, facilitator: 0, facilities: 0 });
  const [publicText, setPublicText] = useState('');
  const [privateText, setPrivateText] = useState('');
  const [busy, setBusy] = useState(false);

  if (!booking.data) return <ActivityIndicator style={{ marginTop: 80 }} />;
  const b = booking.data;
  const inPerson = b.experience.modality !== 'online';
  const complete = stars.overall && stars.learning && stars.facilitator && (!inPerson || stars.facilities);
  const set = (k: keyof typeof stars) => (v: number) => setStars((s) => ({ ...s, [k]: v }));

  const send = async () => {
    setBusy(true);
    try {
      await api(`/bookings/${b.id}/review`, {
        method: 'POST',
        body: { ...stars, facilities: inPerson ? stars.facilities : null, public_text: publicText, private_feedback: privateText },
      });
      qc.invalidateQueries({ queryKey: ['booking', b.id] });
      qc.invalidateQueries({ queryKey: ['bookings'] });
      qc.invalidateQueries({ queryKey: ['me', 'pending-reviews'] });
      Alert.alert(t('reviews.sent'));
      router.back();
    } catch (err) {
      Alert.alert(err instanceof ApiError ? err.message : t('errors.network'));
    } finally {
      setBusy(false);
    }
  };

  return (
    <SafeAreaView style={{ flex: 1, backgroundColor: colors.bg }} edges={['bottom']}>
      <KeyboardAvoidingView style={{ flex: 1 }} behavior={Platform.OS === 'ios' ? 'padding' : undefined}>
        <ScrollView contentContainerStyle={{ padding: space.xl, paddingBottom: 48 }} keyboardShouldPersistTaps="handled">
          <View style={{ flexDirection: 'row', alignItems: 'center', marginBottom: space.lg }}>
            <Image source={b.experience.cover?.urls?.w400} style={{ width: 64, height: 64, borderRadius: radius.md, backgroundColor: b.experience.cover?.color ?? colors.surface }} />
            <View style={{ flex: 1, marginLeft: space.md }}>
              <Text style={type.heading}>{b.experience.title}</Text>
              <Text style={type.small}>{b.provider.display_name}</Text>
            </View>
          </View>
          <StarInput label={t('reviews.overall')} value={stars.overall} onChange={set('overall')} />
          <StarInput label={t('reviews.learning')} value={stars.learning} onChange={set('learning')} />
          <StarInput label={t('reviews.facilitator')} value={stars.facilitator} onChange={set('facilitator')} />
          {inPerson ? <StarInput label={t('reviews.facilities')} hint={t('reviews.facilitiesHint')} value={stars.facilities} onChange={set('facilities')} /> : null}
          <View style={{ height: space.lg }} />
          <Field label={t('reviews.publicText')} hint={t('reviews.publicHint')} value={publicText} onChangeText={setPublicText} multiline maxLength={2000} />
          <Field label={t('reviews.privateText')} hint={t('reviews.privateHint')} value={privateText} onChangeText={setPrivateText} multiline maxLength={2000} />
          <Text style={[type.small, { marginBottom: space.lg }]}>{t('reviews.blind')}</Text>
          <Button title={t('reviews.send')} onPress={send} loading={busy} disabled={!complete} />
        </ScrollView>
      </KeyboardAvoidingView>
    </SafeAreaView>
  );
}
