import { useLocalSearchParams } from 'expo-router';
import { useEffect, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { StyleSheet, Text, TextInput, View } from 'react-native';

import { Button } from '@/components/ui';
import { ApiError, api } from '@/lib/api/client';
import type { Me, Session } from '@/lib/api/types';
import { useAuth } from '@/lib/auth/AuthContext';
import { continueAfterLogin } from '@/lib/auth/finish';
import { colors, radius, space, type } from '@/theme/tokens';

/** Shared by login and phone verification (mode=verify_phone). */
export default function OtpScreen() {
  const { t } = useTranslation();
  const params = useLocalSearchParams<{ challenge: string; destination: string; channel: string; next?: string; mode?: string }>();
  const { signIn, refreshMe } = useAuth();
  const [challenge, setChallenge] = useState(params.challenge);
  const [code, setCode] = useState('');
  const [error, setError] = useState<string>();
  const [loading, setLoading] = useState(false);
  const [cooldown, setCooldown] = useState(45);
  const input = useRef<TextInput>(null);
  const verifyPhone = params.mode === 'verify_phone';

  useEffect(() => {
    const id = setInterval(() => setCooldown((s) => Math.max(0, s - 1)), 1000);
    return () => clearInterval(id);
  }, []);

  const submit = async (value: string) => {
    setLoading(true);
    setError(undefined);
    try {
      if (verifyPhone) {
        const user = await api<Me>('/me/phone/verify', { method: 'POST', body: { challenge_id: challenge, code: value } });
        await refreshMe();
        continueAfterLogin(user, params.next || undefined);
      } else {
        const session = await api<Session>('/auth/otp/verify', { method: 'POST', body: { challenge_id: challenge, code: value }, auth: false });
        await signIn(session);
        continueAfterLogin(session.user, params.next || undefined);
      }
    } catch (e) {
      setError(e instanceof ApiError ? e.message : t('errors.network'));
      setCode('');
      input.current?.focus();
    } finally {
      setLoading(false);
    }
  };

  const resend = async () => {
    try {
      const res = verifyPhone
        ? await api<{ challenge_id: string }>('/me/phone', { method: 'POST', body: { phone: params.destination } })
        : await api<{ challenge_id: string }>('/auth/otp/request', {
            method: 'POST', body: { channel: params.channel, destination: params.destination }, auth: false,
          });
      setChallenge(res.challenge_id);
      setCooldown(45);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : t('errors.network'));
    }
  };

  return (
    <View style={{ padding: space.xl }}>
      <Text style={type.title}>{t('auth.otpTitle')}</Text>
      <Text style={[type.small, { marginTop: space.sm }]}>{t('auth.otpSent', { destination: params.destination })}</Text>
      <TextInput
        ref={input}
        value={code}
        onChangeText={(v) => {
          const digits = v.replace(/\D/g, '').slice(0, 6);
          setCode(digits);
          if (digits.length === 6) submit(digits);
        }}
        keyboardType="number-pad"
        textContentType="oneTimeCode"
        autoComplete="sms-otp"
        autoFocus
        maxLength={6}
        style={styles.code}
        accessibilityLabel={t('auth.otpTitle')}
      />
      {error ? <Text style={{ color: colors.danger, marginBottom: space.md }}>{error}</Text> : null}
      <Button title={t('common.continue')} onPress={() => submit(code)} loading={loading} disabled={code.length !== 6} />
      <Button
        title={cooldown ? t('auth.resendIn', { s: cooldown }) : t('auth.resend')}
        variant="ghost"
        disabled={cooldown > 0}
        onPress={resend}
      />
    </View>
  );
}

const styles = StyleSheet.create({
  code: {
    marginVertical: space.xl, borderWidth: 1, borderColor: colors.border, borderRadius: radius.md, height: 64,
    fontSize: 30, letterSpacing: 14, textAlign: 'center', color: colors.text,
  },
});
