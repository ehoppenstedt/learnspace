import { router, useLocalSearchParams } from 'expo-router';
import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Text, View } from 'react-native';

import { Button, Field } from '@/components/ui';
import { ApiError, api } from '@/lib/api/client';
import { space, type } from '@/theme/tokens';

/** For users who signed in with email/Apple/Google: phone must be verified before booking. */
export default function VerifyPhone() {
  const { t } = useTranslation();
  const { next } = useLocalSearchParams<{ next?: string }>();
  const [phone, setPhone] = useState('');
  const [error, setError] = useState<string>();
  const [loading, setLoading] = useState(false);

  const send = async () => {
    setLoading(true);
    setError(undefined);
    try {
      const res = await api<{ challenge_id: string }>('/me/phone', { method: 'POST', body: { phone } });
      router.push({ pathname: '/auth/otp', params: { challenge: res.challenge_id, destination: phone, channel: 'sms', mode: 'verify_phone', next: next ?? '' } });
    } catch (e) {
      setError(e instanceof ApiError ? e.message : t('errors.network'));
    } finally {
      setLoading(false);
    }
  };

  return (
    <View style={{ padding: space.xl }}>
      <Text style={[type.title, { marginBottom: space.xl }]}>{t('auth.verifyPhoneTitle')}</Text>
      <Field label={t('auth.phone')} hint={t('auth.phoneHint')} value={phone} onChangeText={setPhone} keyboardType="phone-pad" placeholder="55 1234 5678" error={error} />
      <Button title={t('common.continue')} onPress={send} loading={loading} disabled={phone.trim().length < 8} />
    </View>
  );
}
