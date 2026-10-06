import { GoogleSignin, isSuccessResponse } from '@react-native-google-signin/google-signin';
import * as AppleAuthentication from 'expo-apple-authentication';
import * as Crypto from 'expo-crypto';
import { router, useLocalSearchParams } from 'expo-router';
import { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Platform, ScrollView, StyleSheet, Text, View } from 'react-native';

import { Button, Field } from '@/components/ui';
import { ApiError, api } from '@/lib/api/client';
import { GOOGLE_IOS_CLIENT_ID, GOOGLE_WEB_CLIENT_ID } from '@/lib/api/config';
import type { Session } from '@/lib/api/types';
import { useAuth } from '@/lib/auth/AuthContext';
import { continueAfterLogin } from '@/lib/auth/finish';
import { colors, space, type } from '@/theme/tokens';

export default function AuthStart() {
  const { t } = useTranslation();
  const { next } = useLocalSearchParams<{ next?: string }>();
  const { signIn } = useAuth();
  const [channel, setChannel] = useState<'sms' | 'email'>('sms');
  const [destination, setDestination] = useState('');
  const [error, setError] = useState<string>();
  const [loading, setLoading] = useState(false);
  const [appleAvailable, setAppleAvailable] = useState(false);

  useEffect(() => {
    if (Platform.OS === 'ios') AppleAuthentication.isAvailableAsync().then(setAppleAvailable);
    if (GOOGLE_WEB_CLIENT_ID) GoogleSignin.configure({ webClientId: GOOGLE_WEB_CLIENT_ID, iosClientId: GOOGLE_IOS_CLIENT_ID });
  }, []);

  const requestCode = async () => {
    setError(undefined);
    setLoading(true);
    try {
      const res = await api<{ challenge_id: string }>('/auth/otp/request', {
        method: 'POST', body: { channel, destination }, auth: false,
      });
      router.push({ pathname: '/auth/otp', params: { challenge: res.challenge_id, destination, channel, next: next ?? '' } });
    } catch (e) {
      setError(e instanceof ApiError ? e.message : t('errors.network'));
    } finally {
      setLoading(false);
    }
  };

  const completeSocial = async (path: string, body: object) => {
    const session = await api<Session>(path, { method: 'POST', body, auth: false });
    await signIn(session);
    continueAfterLogin(session.user, next);
  };

  const apple = async () => {
    try {
      const rawNonce = Crypto.randomUUID();
      const hashed = await Crypto.digestStringAsync(Crypto.CryptoDigestAlgorithm.SHA256, rawNonce);
      const cred = await AppleAuthentication.signInAsync({
        requestedScopes: [AppleAuthentication.AppleAuthenticationScope.FULL_NAME, AppleAuthentication.AppleAuthenticationScope.EMAIL],
        nonce: hashed,
      });
      if (!cred.identityToken) return;
      await completeSocial('/auth/apple', {
        identity_token: cred.identityToken, nonce: rawNonce,
        first_name: cred.fullName?.givenName ?? '', last_name: cred.fullName?.familyName ?? '',
      });
    } catch (e) {
      if ((e as { code?: string }).code !== 'ERR_REQUEST_CANCELED') setError(t('errors.generic'));
    }
  };

  const google = async () => {
    try {
      await GoogleSignin.hasPlayServices();
      const res = await GoogleSignin.signIn();
      if (isSuccessResponse(res) && res.data.idToken) await completeSocial('/auth/google', { id_token: res.data.idToken });
    } catch {
      setError(t('errors.generic'));
    }
  };

  return (
    <ScrollView contentContainerStyle={styles.wrap} keyboardShouldPersistTaps="handled">
      <Text style={type.title}>{t('auth.title')}</Text>
      <View style={{ height: space.xl }} />
      {channel === 'sms' ? (
        <Field
          label={t('auth.phone')} hint={t('auth.phoneHint')} value={destination} onChangeText={setDestination}
          keyboardType="phone-pad" autoComplete="tel" placeholder="55 1234 5678" error={error}
        />
      ) : (
        <Field
          label={t('auth.email')} value={destination} onChangeText={setDestination} keyboardType="email-address"
          autoCapitalize="none" autoComplete="email" error={error}
        />
      )}
      <Button title={t('common.continue')} onPress={requestCode} loading={loading} disabled={destination.trim().length < 5} />
      <Button
        title={channel === 'sms' ? t('auth.useEmail') : t('auth.usePhone')} variant="ghost"
        onPress={() => { setChannel(channel === 'sms' ? 'email' : 'sms'); setDestination(''); setError(undefined); }}
      />
      <View style={styles.divider}>
        <View style={styles.line} /><Text style={[type.small, { marginHorizontal: space.md }]}>{t('auth.or')}</Text><View style={styles.line} />
      </View>
      {appleAvailable ? (
        <AppleAuthentication.AppleAuthenticationButton
          buttonType={AppleAuthentication.AppleAuthenticationButtonType.CONTINUE}
          buttonStyle={AppleAuthentication.AppleAuthenticationButtonStyle.BLACK}
          cornerRadius={12}
          style={{ height: 52, marginBottom: space.md }}
          onPress={apple}
        />
      ) : null}
      {GOOGLE_WEB_CLIENT_ID ? <Button title={t('auth.google')} variant="secondary" icon="logo-google" onPress={google} /> : null}
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  wrap: { padding: space.xl },
  divider: { flexDirection: 'row', alignItems: 'center', marginVertical: space.xl },
  line: { flex: 1, height: StyleSheet.hairlineWidth, backgroundColor: colors.border },
});
