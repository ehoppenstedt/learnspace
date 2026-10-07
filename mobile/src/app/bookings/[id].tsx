import { Ionicons } from '@expo/vector-icons';
import { useQueryClient } from '@tanstack/react-query';
import { Image } from 'expo-image';
import * as Linking from 'expo-linking';
import * as WebBrowser from 'expo-web-browser';
import { Stack, useLocalSearchParams } from 'expo-router';
import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { ActivityIndicator, Alert, Modal, Platform, Pressable, ScrollView, StyleSheet, Text, View, useWindowDimensions } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';

import { MapView, Marker } from '@/components/map';
import { Badge, Button, Section } from '@/components/ui';
import { ApiError, api } from '@/lib/api/client';
import { useBooking } from '@/lib/api/hooks';
import type { Booking, CancellationQuote } from '@/lib/api/types';
import { formatMoney, formatSessionDate, formatTimeRange, seatsLabel } from '@/lib/utils/format';
import { colors, radius, space, type } from '@/theme/tokens';

export default function BookingDetail() {
  const { id, fresh } = useLocalSearchParams<{ id: string; fresh?: string }>();
  const { t, i18n } = useTranslation();
  const lang = i18n.language;
  const { width } = useWindowDimensions();
  const query = useBooking(id, true);
  const [quote, setQuote] = useState<CancellationQuote | null>(null);

  if (!query.data) return <ActivityIndicator style={{ marginTop: 80 }} />;
  const b = query.data;
  const settling = b.status === 'pending_payment';
  const loc = b.location;

  const openQuote = async () => {
    try {
      setQuote(await api<CancellationQuote>(`/bookings/${b.id}/cancellation-quote`));
    } catch (err) {
      Alert.alert(err instanceof ApiError ? err.message : t('errors.network'));
    }
  };

  const directions = () => {
    if (!loc || loc.approximate) return;
    const q = encodeURIComponent(loc.address_line);
    Linking.openURL(Platform.OS === 'ios' ? `http://maps.apple.com/?daddr=${q}` : `https://www.google.com/maps/dir/?api=1&destination=${q}`);
  };

  return (
    <SafeAreaView style={{ flex: 1, backgroundColor: colors.bg }} edges={['bottom']}>
      <Stack.Screen options={{ title: b.code }} />
      <ScrollView contentContainerStyle={{ paddingBottom: 40 }}>
        <Image source={b.experience.cover?.urls?.w1600} style={{ width, height: width * 0.6, backgroundColor: b.experience.cover?.color ?? colors.surface }} contentFit="cover" />
        <View style={{ paddingHorizontal: space.xl }}>
          <View style={{ paddingTop: space.xl }}>
            {fresh && b.status === 'confirmed' ? <Text style={[type.title, { color: colors.success, marginBottom: space.sm }]}>{t('bookings.confirmedTitle')}</Text> : null}
            <Badge label={t(`bookings.status.${b.status}`)} bg={colors.surface} fg={colors.text} />
            <Text style={[type.display, { marginTop: space.md }]}>{b.experience.title}</Text>
            <Text style={type.small}>{b.provider.display_name} · {seatsLabel(b.seats, lang)} · {t('bookings.code')} {b.code}</Text>
            {settling ? (
              <View style={{ flexDirection: 'row', alignItems: 'center', marginTop: space.md }}>
                <ActivityIndicator /><Text style={[type.small, { marginLeft: space.sm }]}>{t('book.processing')}</Text>
              </View>
            ) : null}
            {b.status === 'pending_approval' ? <Text style={[type.small, { marginTop: space.md }]}>{t('book.approvalNote')}</Text> : null}
          </View>

          <Section>
            {b.sessions.map((s) => (
              <View key={s.id} style={styles.sessionRow}>
                <Ionicons name="calendar-outline" size={20} color={colors.text} />
                <Text style={[type.body, { marginLeft: space.md }]}>
                  {formatSessionDate(s.starts_at, lang).split(' · ')[0]} · {formatTimeRange(s.starts_at, s.ends_at, lang)}
                </Text>
              </View>
            ))}
            {b.calendar_url && b.status === 'confirmed' ? (
              <Button title={t('bookings.addToCalendar')} variant="secondary" icon="calendar" onPress={() => Linking.openURL(b.calendar_url!)} style={{ marginTop: space.md }} />
            ) : null}
          </Section>

          {loc ? (
            <Section title={t('bookings.address')}>
              {loc.approximate ? (
                <Text style={type.small}>{t('bookings.addressHidden')}</Text>
              ) : (
                <>
                  <Text style={type.bodyStrong}>{loc.space_name}</Text>
                  <Text style={type.body}>{loc.address_line}</Text>
                  {loc.address_reference ? <Text style={type.small}>{loc.address_reference}</Text> : null}
                </>
              )}
              <View style={styles.map}>
                <MapView style={StyleSheet.absoluteFill} initialRegion={{ latitude: loc.lat, longitude: loc.lng, latitudeDelta: 0.01, longitudeDelta: 0.01 }}>
                  {!loc.approximate ? <Marker coordinate={{ latitude: loc.lat, longitude: loc.lng }} /> : null}
                </MapView>
              </View>
              {!loc.approximate ? <Button title={t('bookings.directions')} variant="ghost" icon="navigate" onPress={directions} /> : null}
            </Section>
          ) : null}

          <Section>
            <Button title={t('bookings.messageSoon')} variant="secondary" icon="chatbubble-outline" disabled />
          </Section>

          <Section title={t('bookings.paid')} last={!b.can_cancel}>
            <PriceRow label={t('book.listed', { price: formatMoney(b.price.listed_cents / b.seats, lang), seats: seatsLabel(b.seats, lang) })} value={formatMoney(b.price.listed_cents, lang)} />
            <PriceRow label={t('book.fee')} value={formatMoney(b.price.fee_cents, lang)} />
            <PriceRow label={t('book.total')} value={formatMoney(b.price.total_cents, lang)} strong />
            {b.refunded_cents ? <PriceRow label={t('bookings.refunded')} value={`− ${formatMoney(b.refunded_cents, lang)}`} /> : null}
            {['confirmed', 'completed', 'no_show', 'cancelled'].includes(b.status) ? (
              <Button title={t('testmode.receipt')} variant="ghost" icon="document-text-outline" onPress={async () => {
                const { url } = await api<{ url: string }>(`/bookings/${b.id}/receipt`);
                await WebBrowser.openBrowserAsync(url);
              }} />
            ) : null}
          </Section>

          {b.can_cancel ? (
            <Section last>
              <Button title={t('bookings.cancel')} variant="ghost" onPress={openQuote} />
            </Section>
          ) : null}
        </View>
      </ScrollView>
      {quote ? <CancelSheet booking={b} quote={quote} onClose={() => setQuote(null)} /> : null}
    </SafeAreaView>
  );
}

function CancelSheet({ booking, quote, onClose }: { booking: Booking; quote: CancellationQuote; onClose: () => void }) {
  const { t, i18n } = useTranslation();
  const qc = useQueryClient();
  const [busy, setBusy] = useState(false);
  const lang = i18n.language;

  const confirm = async () => {
    setBusy(true);
    try {
      const res = await api<{ refund_cents: number }>(`/bookings/${booking.id}/cancel`, { method: 'POST', body: { quote_token: quote.quote_token } });
      Alert.alert(t('cancel.done', { amount: `${formatMoney(res.refund_cents, lang)} MXN` }));
      qc.invalidateQueries({ queryKey: ['booking', booking.id] });
      qc.invalidateQueries({ queryKey: ['bookings'] });
      onClose();
    } catch (err) {
      Alert.alert(err instanceof ApiError ? err.message : t('errors.network'));
      onClose();
    } finally {
      setBusy(false);
    }
  };

  return (
    <Modal transparent animationType="slide" onRequestClose={onClose}>
      <Pressable style={styles.backdrop} onPress={onClose} />
      <View style={styles.sheet}>
        <Text style={type.title}>{t('cancel.title')}</Text>
        {quote.not_charged ? (
          <Text style={[type.body, { marginVertical: space.lg }]}>{t('cancel.notCharged')}</Text>
        ) : (
          <View style={{ marginVertical: space.lg, gap: space.sm }}>
            <Text style={type.small}>{t('cancel.refund')}</Text>
            <Text style={type.display}>{formatMoney(quote.refund_cents, lang)} MXN</Text>
            <PriceRow label={t('cancel.listedPart')} value={formatMoney(quote.listed_refund_cents, lang)} />
            <PriceRow label={t('cancel.feePart')} value={formatMoney(quote.fee_refund_cents, lang)} />
            {quote.refund_cents === 0 ? <Text style={type.small}>{t('cancel.noRefund')}</Text> : null}
            {quote.fee_refund_cents === 0 && quote.refund_cents > 0 ? <Text style={type.small}>{t('cancel.feeRetained')}</Text> : null}
          </View>
        )}
        <Button title={t('cancel.confirm')} variant="dark" onPress={confirm} loading={busy} />
        <Button title={t('cancel.keep')} variant="ghost" onPress={onClose} />
      </View>
    </Modal>
  );
}

function PriceRow({ label, value, strong }: { label: string; value: string; strong?: boolean }) {
  return (
    <View style={{ flexDirection: 'row', justifyContent: 'space-between', marginBottom: space.xs }}>
      <Text style={strong ? type.bodyStrong : type.body}>{label}</Text>
      <Text style={strong ? type.bodyStrong : type.body}>{value}</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  sessionRow: { flexDirection: 'row', alignItems: 'center', paddingVertical: space.sm },
  map: { height: 180, borderRadius: radius.lg, overflow: 'hidden', marginTop: space.md },
  backdrop: { flex: 1, backgroundColor: colors.overlay },
  sheet: { backgroundColor: colors.bg, padding: space.xl, paddingBottom: space.xxxl, borderTopLeftRadius: radius.xl, borderTopRightRadius: radius.xl },
});
