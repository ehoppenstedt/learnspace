import { useQueryClient } from '@tanstack/react-query';
import { router, Stack, useLocalSearchParams } from 'expo-router';
import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Alert, ScrollView, Text } from 'react-native';

import { StarInput } from '@/components/Stars';
import { Button, Field } from '@/components/ui';
import { ApiError, api } from '@/lib/api/client';
import { space, type } from '@/theme/tokens';

/** Host rates a learner's conduct after class (booking id in the route, learner name as a param). */
export default function RateLearner() {
  const { id, name } = useLocalSearchParams<{ id: string; name?: string }>();
  const { t } = useTranslation();
  const qc = useQueryClient();
  const [respect, setRespect] = useState(0);
  const [punctuality, setPunctuality] = useState(0);
  const [note, setNote] = useState('');
  const [busy, setBusy] = useState(false);

  const send = async () => {
    setBusy(true);
    try {
      await api(`/provider/bookings/${id}/conduct-rating`, { method: 'POST', body: { respect, punctuality, admin_note: note } });
      qc.invalidateQueries({ queryKey: ['me', 'pending-reviews'] });
      Alert.alert(t('conduct.sent'));
      router.back();
    } catch (err) {
      Alert.alert(err instanceof ApiError ? err.message : t('errors.network'));
    } finally {
      setBusy(false);
    }
  };

  return (
    <ScrollView contentContainerStyle={{ padding: space.xl, paddingBottom: 48 }} keyboardShouldPersistTaps="handled">
      <Stack.Screen options={{ title: t('conduct.rateTitle', { name: name ?? '' }) }} />
      <StarInput label={t('conduct.respect')} hint={t('conduct.respectHint')} value={respect} onChange={setRespect} />
      <StarInput label={t('conduct.punctuality')} hint={t('conduct.punctualityHint')} value={punctuality} onChange={setPunctuality} />
      <Field label={t('conduct.note')} hint={t('conduct.noteHint')} value={note} onChangeText={setNote} multiline maxLength={2000} style={{ marginTop: space.lg }} />
      <Text style={[type.small, { marginBottom: space.lg }]}>{t('conduct.blind')}</Text>
      <Button title={t('conduct.send')} onPress={send} loading={busy} disabled={!respect || !punctuality} />
    </ScrollView>
  );
}
