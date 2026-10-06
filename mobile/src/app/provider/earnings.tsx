import { useTranslation } from 'react-i18next';
import { FlatList, StyleSheet, Text, View } from 'react-native';

import { Badge } from '@/components/ui';
import { useEarnings } from '@/lib/api/hooks';
import { formatMoney, formatSessionDate } from '@/lib/utils/format';
import { colors, radius, space, type } from '@/theme/tokens';

export default function Earnings() {
  const { t, i18n } = useTranslation();
  const lang = i18n.language;
  const data = useEarnings();
  const totals = data.data?.totals;
  return (
    <FlatList
      data={data.data?.transfers ?? []}
      keyExtractor={(x) => x.id}
      contentContainerStyle={{ padding: space.xl }}
      ListHeaderComponent={
        <View style={styles.tiles}>
          <Tile label={t('ops.upcomingPay')} value={formatMoney(totals?.upcoming_cents ?? 0, lang)} />
          <Tile label={t('ops.onHold')} value={formatMoney(totals?.on_hold_cents ?? 0, lang)} />
          <Tile label={t('ops.paid')} value={formatMoney(totals?.paid_cents ?? 0, lang)} />
        </View>
      }
      renderItem={({ item }) => (
        <View style={styles.row}>
          <View style={{ flexDirection: 'row', justifyContent: 'space-between' }}>
            <Text style={[type.bodyStrong, { flex: 1 }]} numberOfLines={1}>{item.experience}</Text>
            <Text style={type.bodyStrong}>{formatMoney(item.net_cents, lang)}</Text>
          </View>
          <Text style={type.caption}>
            {item.booking_code} · {t('ops.gross')} {formatMoney(item.gross_cents, lang)} · {t('ops.withheld')} {formatMoney(item.isr_withheld_cents + item.iva_withheld_cents, lang)}
          </Text>
          <View style={{ flexDirection: 'row', gap: space.sm, marginTop: 4 }}>
            <Badge label={t(`ops.transferStatus.${item.status}`)} bg={colors.surface} fg={colors.text} />
            <Text style={type.caption}>{formatSessionDate(item.sent_at ?? item.release_at, lang)}</Text>
          </View>
        </View>
      )}
    />
  );
}

function Tile({ label, value }: { label: string; value: string }) {
  return (
    <View style={styles.tile}>
      <Text style={type.caption}>{label}</Text>
      <Text style={type.heading}>{value}</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  tiles: { flexDirection: 'row', gap: space.sm, marginBottom: space.xl },
  tile: { flex: 1, backgroundColor: colors.surface, borderRadius: radius.md, padding: space.md },
  row: { paddingVertical: space.md, borderBottomWidth: StyleSheet.hairlineWidth, borderBottomColor: colors.hairline },
});
