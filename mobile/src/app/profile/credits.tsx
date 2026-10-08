import { useTranslation } from 'react-i18next';
import { FlatList, Text, View } from 'react-native';

import { useCredits } from '@/lib/api/hooks';
import { formatMoney, formatSessionDate } from '@/lib/utils/format';
import { colors, radius, space, type } from '@/theme/tokens';

export default function CreditsScreen() {
  const { t, i18n } = useTranslation();
  const credits = useCredits();
  const lang = i18n.language;
  return (
    <FlatList
      data={credits.data?.entries ?? []}
      keyExtractor={(e) => e.id}
      contentContainerStyle={{ padding: space.xl }}
      ListHeaderComponent={
        <View style={{ alignItems: 'center', padding: space.xl, backgroundColor: colors.surface, borderRadius: radius.lg, marginBottom: space.xl }}>
          <Text style={type.small}>{t('credits.balance')}</Text>
          <Text style={{ fontSize: 40, fontWeight: '700', color: colors.text, marginVertical: space.xs }}>
            {formatMoney(credits.data?.balance_cents ?? 0, lang)} MXN
          </Text>
          <Text style={[type.caption, { textAlign: 'center' }]}>{t('credits.explain')}</Text>
        </View>
      }
      ListEmptyComponent={credits.data ? <Text style={[type.body, { textAlign: 'center' }]}>{t('credits.empty')}</Text> : null}
      renderItem={({ item }) => (
        <View style={{ flexDirection: 'row', paddingVertical: space.md, borderBottomWidth: 1, borderBottomColor: colors.hairline }}>
          <View style={{ flex: 1 }}>
            <Text style={type.bodyStrong}>{t(`credits.kind.${item.kind}`)}</Text>
            <Text style={type.caption}>{[item.experience, formatSessionDate(item.date, lang).split(' · ')[0]].filter(Boolean).join(' · ')}</Text>
          </View>
          <Text style={[type.bodyStrong, { color: item.amount_cents > 0 ? colors.success : colors.text }]}>
            {item.amount_cents > 0 ? '+' : '−'} {formatMoney(Math.abs(item.amount_cents), lang)}
          </Text>
        </View>
      )}
    />
  );
}
