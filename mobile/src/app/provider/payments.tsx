import { Ionicons } from '@expo/vector-icons';
import { useQueryClient } from '@tanstack/react-query';
import { router } from 'expo-router';
import * as WebBrowser from 'expo-web-browser';
import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Alert, ScrollView, StyleSheet, Text, View } from 'react-native';

import { Button, Chip, Field, Section } from '@/components/ui';
import { ApiError, api } from '@/lib/api/client';
import { useOnboarding } from '@/lib/api/hooks';
import type { OnboardingStatus } from '@/lib/api/types';
import { colors, radius, space, type } from '@/theme/tokens';

/** Three things before publishing: verified ID, payout account (Stripe KYC), RFC. */
export default function ProviderPayments() {
  const { t } = useTranslation();
  const qc = useQueryClient();
  const status = useOnboarding();
  const [busy, setBusy] = useState(false);

  const openStripe = async () => {
    setBusy(true);
    try {
      const { url } = await api<{ url: string }>('/provider/payments/onboarding', { method: 'POST' });
      if (url.includes('/dev/fake-onboarding/')) {
        // Test mode: no Stripe account yet, so verification completes instantly.
        Alert.alert(t('testmode.kycTitle'), t('testmode.kycBody'));
        await api(`/dev/onboarding/${url.split('/').pop()}/complete`, { method: 'POST', auth: false });
      } else {
        await WebBrowser.openBrowserAsync(url);
      }
      await qc.invalidateQueries({ queryKey: ['provider', 'onboarding'] });
    } catch (err) {
      Alert.alert(err instanceof ApiError ? err.message : t('errors.network'));
    } finally {
      setBusy(false);
    }
  };

  const s = status.data;
  const done = (key: 'identity' | 'payment_account' | 'tax_profile') => Boolean(s) && !s!.missing.includes(key);
  return (
    <ScrollView contentContainerStyle={{ paddingHorizontal: space.xl, paddingBottom: 60 }}>
      {s?.ready_to_publish ? (
        <View style={styles.ready}><Ionicons name="checkmark-circle" size={22} color={colors.success} /><Text style={[type.bodyStrong, { marginLeft: space.sm }]}>{t('ops.paymentsReady')}</Text></View>
      ) : null}
      <Section>
        <Step done={done('identity')} label={t('ops.stepIdentity')} action={!done('identity') ? () => router.push('/provider/become') : undefined} />
        <Step done={done('payment_account')} label={t('ops.stepPayouts')} hint={s?.payment_account?.requirements_due.join(', ')} />
        {!done('payment_account') ? (
          <Button title={s?.payment_account ? t('ops.continueStripe') : t('ops.openStripe')} onPress={openStripe} loading={busy} style={{ marginTop: space.md }} />
        ) : null}
        <Step done={done('tax_profile')} label={t('ops.stepTax')} />
      </Section>
      <Section title={t('ops.stepTax')} last>
        <Text style={[type.small, { marginBottom: space.lg }]}>{t('ops.taxNote')}</Text>
        {/* Mounted after load so the fields start with the saved values. */}
        {s ? <TaxForm key={s.tax_profile?.rfc ?? 'new'} initial={s.tax_profile} /> : null}
      </Section>
    </ScrollView>
  );
}

function TaxForm({ initial }: { initial: OnboardingStatus['tax_profile'] }) {
  const { t } = useTranslation();
  const qc = useQueryClient();
  const [personType, setPersonType] = useState<'fisica' | 'moral'>(initial?.person_type ?? 'fisica');
  const [rfc, setRfc] = useState(initial?.rfc ?? '');
  const [legalName, setLegalName] = useState(initial?.legal_name ?? '');
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [busy, setBusy] = useState(false);

  const saveTax = async () => {
    setBusy(true);
    setErrors({});
    try {
      await api('/provider/tax-profile', { method: 'PUT', body: { person_type: personType, rfc, legal_name: legalName } });
      await qc.invalidateQueries({ queryKey: ['provider', 'onboarding'] });
    } catch (err) {
      if (err instanceof ApiError) setErrors({ rfc: err.fieldMessage('rfc') ?? '', legal_name: err.fieldMessage('legal_name') ?? '' });
    } finally {
      setBusy(false);
    }
  };

  return (
    <>
      <Text style={styles.label}>{t('ops.personType')}</Text>
      <View style={{ flexDirection: 'row', marginBottom: space.md }}>
        <Chip label={t('ops.fisica')} selected={personType === 'fisica'} onPress={() => setPersonType('fisica')} />
        <Chip label={t('ops.moral')} selected={personType === 'moral'} onPress={() => setPersonType('moral')} />
      </View>
      <Field label={t('ops.rfc')} value={rfc} onChangeText={(v) => setRfc(v.toUpperCase())} autoCapitalize="characters" maxLength={13} error={errors.rfc || undefined} />
      <Field label={t('ops.legalName')} value={legalName} onChangeText={setLegalName} error={errors.legal_name || undefined} />
      <Button title={t('ops.saveTax')} onPress={saveTax} loading={busy} disabled={rfc.length < 12 || !legalName.trim()} />
    </>
  );
}

function Step({ done, label, hint, action }: { done: boolean; label: string; hint?: string; action?: () => void }) {
  return (
    <View style={styles.step}>
      <Ionicons name={done ? 'checkmark-circle' : 'ellipse-outline'} size={24} color={done ? colors.success : colors.textSubtle} />
      <View style={{ flex: 1, marginLeft: space.md }}>
        <Text style={type.bodyStrong}>{label}</Text>
        {hint ? <Text style={type.caption}>{hint}</Text> : null}
      </View>
      {action ? <Button title="›" variant="ghost" onPress={action} /> : null}
    </View>
  );
}

const styles = StyleSheet.create({
  ready: { flexDirection: 'row', alignItems: 'center', backgroundColor: '#E3F6EC', borderRadius: radius.md, padding: space.md, marginTop: space.lg },
  step: { flexDirection: 'row', alignItems: 'center', paddingVertical: space.md },
  label: { ...type.smallStrong, marginBottom: space.sm },
});
