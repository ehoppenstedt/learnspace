import { useLocalSearchParams } from 'expo-router';
import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { ScrollView, Text, View } from 'react-native';

import { Button, Checkbox, Chip, Field } from '@/components/ui';
import { ApiError, api } from '@/lib/api/client';
import { useConfig } from '@/lib/api/hooks';
import type { Me } from '@/lib/api/types';
import { useAuth } from '@/lib/auth/AuthContext';
import { finishAuth } from '@/lib/auth/finish';
import { ageOn, maskDob, parseDob } from '@/lib/utils/format';
import { colors, space, type } from '@/theme/tokens';

const LANGS = [
  ['es', 'Español'], ['en', 'English'], ['fr', 'Français'], ['pt', 'Português'], ['de', 'Deutsch'], ['nah', 'Náhuatl'],
] as const;

export default function CompleteProfile() {
  const { t } = useTranslation();
  const { next } = useLocalSearchParams<{ next?: string }>();
  const { me, refreshMe } = useAuth();
  const config = useConfig();
  const [first, setFirst] = useState(me?.first_name ?? '');
  const [last, setLast] = useState(me?.last_name ?? '');
  const [email, setEmail] = useState(me?.email ?? '');
  const [dob, setDob] = useState('');
  const [langs, setLangs] = useState<string[]>([]);
  const [consentLangs, setConsentLangs] = useState(false);
  const [access, setAccess] = useState('');
  const [consentAccess, setConsentAccess] = useState(false);
  const [privacy, setPrivacy] = useState(false);
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [loading, setLoading] = useState(false);

  const dobIso = parseDob(dob);
  const dobError = dob.length === 10 && !dobIso ? t('auth.invalidDate')
    : dobIso && ageOn(dobIso, new Date()) < 18 ? t('auth.mustBeAdult') : undefined;

  const valid = first.trim() && last.trim() && email.includes('@') && dobIso && !dobError && privacy
    && (!langs.length || consentLangs) && (!access.trim() || consentAccess);

  const submit = async () => {
    setLoading(true);
    setErrors({});
    try {
      await api<Me>('/me/complete-profile', {
        method: 'POST',
        body: {
          first_name: first, last_name: last, email, date_of_birth: dobIso, accept_privacy_notice: privacy,
          ...(langs.length ? { fluent_languages: langs, consent_fluent_languages: consentLangs } : {}),
          ...(access.trim() ? { accessibility_needs: access.trim(), consent_accessibility: consentAccess } : {}),
        },
      });
      await refreshMe();
      finishAuth(next);
    } catch (e) {
      if (e instanceof ApiError) {
        const fieldErrors: Record<string, string> = {};
        for (const key of Object.keys(e.fields)) fieldErrors[key] = e.fieldMessage(key) ?? e.message;
        setErrors(Object.keys(fieldErrors).length ? fieldErrors : { form: e.message });
      } else {
        setErrors({ form: t('errors.network') });
      }
    } finally {
      setLoading(false);
    }
  };

  return (
    <ScrollView contentContainerStyle={{ padding: space.xl, paddingBottom: 60 }} keyboardShouldPersistTaps="handled">
      <Text style={type.title}>{t('auth.completeTitle')}</Text>
      <Text style={[type.small, { marginTop: space.sm, marginBottom: space.xl }]}>{t('auth.completeHint')}</Text>
      <Field label={t('auth.firstName')} value={first} onChangeText={setFirst} autoComplete="given-name" error={errors.first_name} />
      <Field label={t('auth.lastName')} value={last} onChangeText={setLast} autoComplete="family-name" error={errors.last_name} />
      <Field label={t('auth.email')} value={email} onChangeText={setEmail} keyboardType="email-address" autoCapitalize="none" error={errors.email} />
      <Field
        label={t('auth.dob')} value={dob} onChangeText={(v) => setDob(maskDob(v))} keyboardType="number-pad"
        placeholder="DD/MM/AAAA" maxLength={10} error={dobError ?? errors.date_of_birth}
      />

      <Text style={[type.heading, { marginTop: space.lg, marginBottom: space.md }]}>{t('auth.optionalTitle')}</Text>
      <Text style={[type.smallStrong, { marginBottom: space.sm }]}>{t('auth.languages')}</Text>
      <View style={{ flexDirection: 'row', flexWrap: 'wrap' }}>
        {LANGS.map(([code, label]) => (
          <Chip key={code} label={label} selected={langs.includes(code)}
            onPress={() => setLangs(langs.includes(code) ? langs.filter((l) => l !== code) : [...langs, code])} />
        ))}
      </View>
      {langs.length ? <Checkbox checked={consentLangs} onChange={setConsentLangs} label={t('auth.consentLanguages')} /> : null}

      <Field label={t('auth.accessibility')} hint={t('auth.accessibilityHint')} value={access} onChangeText={setAccess} multiline style={{ marginTop: space.md }} />
      {access.trim() ? <Checkbox checked={consentAccess} onChange={setConsentAccess} label={t('auth.consentAccessibility')} /> : null}

      <View style={{ height: space.lg }} />
      <Checkbox checked={privacy} onChange={setPrivacy} label={t('auth.privacy')} />
      <Text style={[type.caption, { marginBottom: space.lg }]}>
        {config.data?.legal.entity} · RFC {config.data?.legal.rfc} · v{config.data?.legal.privacy_notice_version}
      </Text>
      {errors.form ? <Text style={{ color: colors.danger, marginBottom: space.md }}>{errors.form}</Text> : null}
      <Button title={t('common.continue')} onPress={submit} loading={loading} disabled={!valid} />
    </ScrollView>
  );
}
