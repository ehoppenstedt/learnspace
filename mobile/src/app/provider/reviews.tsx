import { useTranslation } from 'react-i18next';
import { FlatList, Text, View } from 'react-native';

import { Stars } from '@/components/Stars';
import { Badge, Centered } from '@/components/ui';
import { useProviderReviews } from '@/lib/api/hooks';
import { formatSessionDate } from '@/lib/utils/format';
import { colors, radius, space, type } from '@/theme/tokens';

/** Published reviews of my experiences, including the private notes learners left only for me. */
export default function ProviderReviews() {
  const { t, i18n } = useTranslation();
  const reviews = useProviderReviews();
  return (
    <FlatList
      data={reviews.data ?? []}
      keyExtractor={(r) => r.id}
      contentContainerStyle={{ padding: space.xl, flexGrow: 1 }}
      ListEmptyComponent={reviews.data ? <Centered><Text style={type.body}>{t('reviews.empty')}</Text></Centered> : null}
      renderItem={({ item }) => (
        <View style={{ borderWidth: 1, borderColor: colors.border, borderRadius: radius.md, padding: space.md, marginBottom: space.md }}>
          <View style={{ flexDirection: 'row', justifyContent: 'space-between' }}>
            <Text style={[type.bodyStrong, { flex: 1 }]}>{item.author} · {item.experience}</Text>
            <Text style={type.caption}>{formatSessionDate(item.date, i18n.language).split(' · ')[0]}</Text>
          </View>
          <View style={{ marginVertical: space.sm }}><Stars value={item.overall} /></View>
          {item.hidden ? <Badge label={t('reviews.hidden')} bg={colors.surface} fg={colors.text} /> : null}
          {item.text ? <Text style={type.body}>{item.text}</Text> : null}
          {item.private_feedback ? (
            <View style={{ backgroundColor: colors.brandSoft, borderRadius: radius.sm, padding: space.sm, marginTop: space.sm }}>
              <Text style={type.smallStrong}>{t('reviews.privateFeedback')}</Text>
              <Text style={type.small}>{item.private_feedback}</Text>
            </View>
          ) : null}
        </View>
      )}
    />
  );
}
