import { Ionicons } from '@expo/vector-icons';
import { useQueryClient } from '@tanstack/react-query';
import { Image } from 'expo-image';
import { router, Stack, useLocalSearchParams } from 'expo-router';
import { useEffect, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { ActivityIndicator, Alert, Pressable, ScrollView, StyleSheet, Text, View } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';

import { TestPaymentSheet, type TestOutcome } from '@/components/TestPaymentSheet';
import { Button } from '@/components/ui';
import { ApiError, api } from '@/lib/api/client';
import { useConfig, useExperience } from '@/lib/api/hooks';
import type { CheckoutResponse, Hold } from '@/lib/api/types';
import { buyOnAppStore } from '@/lib/iap';
import { collectPayment } from '@/lib/payments';
import { formatCountdown, formatMoney, formatSessionDate, formatTimeRange, seatsLabel } from '@/lib/utils/format';
import { colors, radius, space, type } from '@/theme/tokens';

type Target = { kind: 'session' | 'cohort'; id: string; seatsLeft: number };

/** Select date -> seats -> review (price breakdown, hold timer, policy) -> pay. */
export default function BookScreen() {
  const { id } = useLocalSearchParams<{ id: string }>();
  const { t, i18n } = useTranslation();
  const lang = i18n.language;
  const qc = useQueryClient();
  const experience = useExperience(id);
  const config = useConfig();
  const [target, setTarget] = useState<Target | null>(null);
  const [seats, setSeats] = useState(1);
  const [hold, setHold] = useState<Hold | null>(null);
  const [busy, setBusy] = useState(false);
  const [now, setNow] = useState(() => Date.now());
  const paid = useRef(false);
  const [testSheet, setTestSheet] = useState<{ amount: number; store?: boolean; resolve: (o: TestOutcome) => void } | null>(null);

  // Countdown tick while a hold is active.
  useEffect(() => {
    if (!hold) return;
    const timer = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(timer);
  }, [hold]);

  // Leaving without paying gives the seats back immediately instead of after 10 minutes.
  useEffect(() => () => {
    if (hold && !paid.current) api(`/holds/${hold.hold_id}`, { method: 'DELETE' }).catch(() => undefined);
  }, [hold]);

  if (experience.isLoading || !experience.data) {
    return <ActivityIndicator style={{ marginTop: 80 }} />;
  }
  const e = experience.data;
  const sessions = e.upcoming.sessions ?? [];
  const cohorts = e.upcoming.cohorts ?? [];
  const remainingMs = hold ? new Date(hold.expires_at).getTime() - now : 0;
  const expired = Boolean(hold) && remainingMs <= 0;
  const maxSeats = Math.min(6, target?.seatsLeft ?? 1);

  const createHold = async () => {
    if (!target) return;
    setBusy(true);
    try {
      const body = target.kind === 'session' ? { session_id: target.id, seats } : { cohort_id: target.id, seats };
      setHold(await api<Hold>('/holds', { method: 'POST', body }));
      setNow(Date.now());
    } catch (err) {
      Alert.alert(err instanceof ApiError && err.code === 'seat_unavailable' ? t('book.soldOut') : (err as Error).message);
      qc.invalidateQueries({ queryKey: ['experience', id] });
    } finally {
      setBusy(false);
    }
  };

  const payNow = async () => {
    if (!hold) return;
    setBusy(true);
    try {
      const res = await api<CheckoutResponse>('/bookings', { method: 'POST', body: { hold_id: hold.hold_id } });
      const sheet = res.payment_sheet;
      const toPay = hold.price.total_cents - res.credit_applied_cents;
      if (res.app_store?.test_mode) {
        // App Store test mode (no Apple account yet): stand-in purchase sheet, the API simulates Apple.
        const outcome = await new Promise<TestOutcome>((resolve) => setTestSheet({ amount: res.app_store!.amount_cents, store: true, resolve }));
        setTestSheet(null);
        if (outcome === 'cancelled') return Alert.alert(t('book.paymentCancelled'));
        await api(`/dev/app-store/${res.booking.id}/simulate`, { method: 'POST', body: {} });
      } else if (res.app_store) {
        const purchase = await buyOnAppStore(res.app_store.product_id, res.app_store.app_account_token);
        if (purchase.outcome === 'cancelled') return Alert.alert(t('book.paymentCancelled'));
        if (purchase.outcome === 'error') return Alert.alert(t('appstore.error'));
        await api(`/bookings/${res.booking.id}/app-store-transaction`, { method: 'POST', body: { signed_transaction: purchase.signedTransaction } });
        await purchase.finish(); // only after our server verified it, so an interrupted purchase is retried
      } else if (sheet?.gateway === 'fake') {
        // Test mode (no Stripe account yet): a stand-in sheet, then the API simulates the processor's webhook.
        const outcome = await new Promise<TestOutcome>((resolve) => setTestSheet({ amount: toPay, resolve }));
        setTestSheet(null);
        if (outcome === 'cancelled') return;
        await api(`/dev/payments/${res.booking.id}/simulate`, { method: 'POST', body: outcome === 'failed' ? { outcome: 'failed' } : {} });
        if (outcome === 'failed') return Alert.alert(t('testmode.declined'));
      } else if (sheet) {
        const result = await collectPayment(sheet, config.data?.brand ?? 'learnspace');
        if (result.outcome === 'cancelled') return Alert.alert(t('book.paymentCancelled'));
        if (result.outcome === 'error') return Alert.alert(result.message);
      }
      paid.current = true;
      qc.invalidateQueries({ queryKey: ['bookings'] });
      router.replace({ pathname: '/bookings/[id]', params: { id: res.booking.id, fresh: '1' } });
    } catch (err) {
      Alert.alert(err instanceof ApiError ? err.message : t('errors.network'));
    } finally {
      setBusy(false);
    }
  };

  const unit = e.price.total_cents; // total per seat already includes the fee
  return (
    <SafeAreaView style={{ flex: 1, backgroundColor: colors.bg }} edges={['bottom']}>
      <Stack.Screen options={{ title: hold ? t('book.review') : cohorts.length ? t('book.chooseGroup') : t('book.chooseDate') }} />
      <ScrollView contentContainerStyle={{ padding: space.xl, paddingBottom: 40 }}>
        <View style={styles.header}>
          <Image source={e.media[0]?.urls?.w400} style={[styles.thumb, { backgroundColor: e.media[0]?.color ?? colors.surface }]} />
          <View style={{ flex: 1, marginLeft: space.md }}>
            <Text style={type.bodyStrong} numberOfLines={2}>{e.title}</Text>
            <Text style={type.small}>{e.provider.display_name}</Text>
          </View>
        </View>

        {!hold ? (
          <>
            {sessions.length === 0 && cohorts.length === 0 ? <Text style={type.body}>{t('book.noDates')}</Text> : null}
            {sessions.map((s) => (
              <Option key={s.id} selected={target?.id === s.id} disabled={s.seats_left === 0}
                title={formatSessionDate(s.starts_at, lang)} subtitle={formatTimeRange(s.starts_at, s.ends_at, lang)}
                right={t('book.seatsLeft', { count: s.seats_left })}
                onPress={() => { setTarget({ kind: 'session', id: s.id, seatsLeft: s.seats_left }); setSeats(1); }} />
            ))}
            {cohorts.map((c) => (
              <Option key={c.id} selected={target?.id === c.id} disabled={c.seats_left === 0}
                title={c.label || formatSessionDate(c.sessions[0].starts_at, lang)}
                subtitle={c.sessions.map((s) => formatSessionDate(s.starts_at, lang)).join('\n')}
                right={t('book.seatsLeft', { count: c.seats_left })}
                onPress={() => { setTarget({ kind: 'cohort', id: c.id, seatsLeft: c.seats_left }); setSeats(1); }} />
            ))}
            {target ? (
              <View style={styles.seatsRow}>
                <Text style={type.bodyStrong}>{t('book.seats')}</Text>
                <View style={styles.stepper}>
                  <Stepper icon="remove" disabled={seats <= 1} onPress={() => setSeats(seats - 1)} />
                  <Text style={[type.heading, { minWidth: 32, textAlign: 'center' }]}>{seats}</Text>
                  <Stepper icon="add" disabled={seats >= maxSeats} onPress={() => setSeats(seats + 1)} />
                </View>
              </View>
            ) : null}
          </>
        ) : (
          <>
            {config.data?.features.payments_test_mode ? (
              <View style={[styles.timer, { backgroundColor: '#FFF4D6' }]}>
                <Ionicons name="flask-outline" size={18} color={colors.warning} />
                <Text style={[type.smallStrong, { marginLeft: space.sm, color: colors.warning, flex: 1 }]}>{t('testmode.banner')}</Text>
              </View>
            ) : null}
            <View style={[styles.timer, expired && { backgroundColor: '#FDE2E1' }]}>
              <Ionicons name="time-outline" size={18} color={expired ? colors.danger : colors.brand} />
              <Text style={[type.smallStrong, { marginLeft: space.sm, color: expired ? colors.danger : colors.brand }]}>
                {expired ? t('book.holdExpired') : t('book.holdTimer', { time: formatCountdown(remainingMs) })}
              </Text>
            </View>
            <View style={styles.breakdown}>
              <Row label={t('book.listed', { price: formatMoney(hold.price.listed_cents / hold.seats, lang), seats: seatsLabel(hold.seats, lang) })}
                value={formatMoney(hold.price.listed_cents, lang)} />
              <Row label={t('book.fee')} value={formatMoney(hold.price.fee_cents, lang)} />
              {hold.price.store_surcharge_cents ? (
                <Row label={t('appstore.surcharge')} value={formatMoney(hold.price.store_surcharge_cents, lang)} />
              ) : null}
              <View style={styles.divider} />
              <Row label={t('book.total')} value={formatMoney(hold.price.total_cents, lang)} strong />
              {hold.credit_available_cents > 0 ? (
                <Row label={t('credits.willUse')} value={`− ${formatMoney(Math.min(hold.credit_available_cents, hold.price.total_cents), lang)}`} />
              ) : null}
            </View>
            {hold.channel === 'app_store' ? (
              <View style={[styles.timer, { marginTop: space.lg, marginBottom: 0, backgroundColor: colors.surface }]}>
                <Ionicons name="logo-apple" size={18} color={colors.text} />
                <Text style={[type.small, { marginLeft: space.sm, flex: 1, color: colors.text }]}>{t('appstore.note')}</Text>
              </View>
            ) : null}
            {e.cancellation_policy ? (
              <View style={{ marginTop: space.xl }}>
                <Text style={type.bodyStrong}>{t('book.policyTitle')}</Text>
                <Text style={[type.small, { marginTop: space.xs }]}>{e.cancellation_policy.description}</Text>
              </View>
            ) : null}
          </>
        )}
      </ScrollView>

      <View style={styles.footer}>
        {!hold ? (
          <>
            <View style={{ flex: 1 }}>
              <Text style={type.bodyStrong}>{formatMoney(unit * seats, lang)} MXN</Text>
              <Text style={type.caption}>{formatMoney(unit, lang)} {t('book.perSeat')}</Text>
            </View>
            <Button title={t('common.continue')} onPress={createHold} loading={busy} disabled={!target} style={{ minWidth: 150 }} />
          </>
        ) : expired ? (
          <Button title={t('common.back')} variant="dark" onPress={() => setHold(null)} style={{ flex: 1 }} />
        ) : (
          <Button title={hold.credit_available_cents > 0
            ? t('book.pay', { total: `${formatMoney(Math.max(hold.price.total_cents - hold.credit_available_cents, 0), lang)} MXN` })
            : t('book.pay', { total: `${formatMoney(hold.price.total_cents, lang)} MXN` })} onPress={payNow}
            loading={busy} style={{ flex: 1 }} />
        )}
      </View>
      {testSheet ? <TestPaymentSheet amountCents={testSheet.amount} store={testSheet.store} onResult={testSheet.resolve} /> : null}
    </SafeAreaView>
  );
}

function Option({ title, subtitle, right, selected, disabled, onPress }: {
  title: string; subtitle: string; right: string; selected: boolean; disabled: boolean; onPress: () => void;
}) {
  return (
    <Pressable onPress={onPress} disabled={disabled} accessibilityRole="radio" accessibilityState={{ checked: selected, disabled }}
      accessibilityLabel={`${title}, ${right}`}
      style={[styles.option, selected && styles.optionSelected, disabled && { opacity: 0.4 }]}>
      <View style={{ flex: 1 }}>
        <Text style={type.bodyStrong}>{title}</Text>
        <Text style={type.small}>{subtitle}</Text>
      </View>
      <Text style={type.caption}>{right}</Text>
    </Pressable>
  );
}

function Stepper({ icon, onPress, disabled }: { icon: 'add' | 'remove'; onPress: () => void; disabled: boolean }) {
  return (
    <Pressable onPress={onPress} disabled={disabled} style={[styles.stepBtn, disabled && { opacity: 0.3 }]}
      accessibilityRole="button" accessibilityLabel={icon === 'add' ? '+1' : '-1'}>
      <Ionicons name={icon} size={20} color={colors.text} />
    </Pressable>
  );
}

function Row({ label, value, strong }: { label: string; value: string; strong?: boolean }) {
  return (
    <View style={styles.row}>
      <Text style={strong ? type.bodyStrong : type.body}>{label}</Text>
      <Text style={strong ? type.bodyStrong : type.body}>{value}</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  header: { flexDirection: 'row', alignItems: 'center', paddingBottom: space.xl, marginBottom: space.lg, borderBottomWidth: StyleSheet.hairlineWidth, borderBottomColor: colors.hairline },
  thumb: { width: 72, height: 72, borderRadius: radius.md },
  option: { flexDirection: 'row', alignItems: 'center', borderWidth: 1, borderColor: colors.border, borderRadius: radius.md, padding: space.lg, marginBottom: space.md },
  optionSelected: { borderColor: colors.text, borderWidth: 2 },
  seatsRow: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', marginTop: space.lg },
  stepper: { flexDirection: 'row', alignItems: 'center' },
  stepBtn: { width: 40, height: 40, borderRadius: 20, borderWidth: 1, borderColor: colors.border, alignItems: 'center', justifyContent: 'center' },
  timer: { flexDirection: 'row', alignItems: 'center', backgroundColor: colors.brandSoft, borderRadius: radius.md, padding: space.md, marginBottom: space.xl },
  breakdown: { gap: space.md },
  row: { flexDirection: 'row', justifyContent: 'space-between' },
  divider: { height: StyleSheet.hairlineWidth, backgroundColor: colors.border },
  footer: {
    flexDirection: 'row', alignItems: 'center', gap: space.md, paddingHorizontal: space.xl, paddingTop: space.md,
    borderTopWidth: StyleSheet.hairlineWidth, borderTopColor: colors.hairline,
  },
});
