import { Image } from 'expo-image';
import { router } from 'expo-router';
import { useTranslation } from 'react-i18next';
import { FlatList, Pressable, StyleSheet, Text, View } from 'react-native';

import { Centered } from '@/components/ui';
import { useThreads } from '@/lib/api/hooks';
import { formatRelative } from '@/lib/utils/format';
import { colors, radius, space, type } from '@/theme/tokens';

export default function Inbox() {
  const { t, i18n } = useTranslation();
  const threads = useThreads();
  return (
    <FlatList
      data={threads.data ?? []}
      keyExtractor={(x) => x.id}
      onRefresh={() => threads.refetch()}
      refreshing={threads.isRefetching}
      contentContainerStyle={{ flexGrow: 1 }}
      ListEmptyComponent={threads.data ? <Centered><Text style={[type.body, { textAlign: 'center' }]}>{t('inbox.empty')}</Text></Centered> : null}
      renderItem={({ item }) => (
        <Pressable style={styles.row} onPress={() => router.push(`/inbox/${item.id}`)} accessibilityRole="button">
          <Image source={item.experience.cover?.urls?.w400} style={[styles.thumb, { backgroundColor: item.experience.cover?.color ?? colors.surface }]} />
          <View style={{ flex: 1, marginLeft: space.md }}>
            <View style={{ flexDirection: 'row', alignItems: 'center' }}>
              <Text style={[type.bodyStrong, { flex: 1 }]} numberOfLines={1}>{item.counterpart}</Text>
              {item.last_message ? <Text style={type.caption}>{formatRelative(item.last_message.at, i18n.language)}</Text> : null}
            </View>
            <Text style={type.caption} numberOfLines={1}>{item.experience.title}{item.booked ? ` · ${t('inbox.booked')}` : ''}</Text>
            {item.last_message ? (
              <Text style={[type.small, item.unread && { color: colors.text, fontWeight: '600' }]} numberOfLines={1}>
                {item.last_message.mine ? `${t('inbox.you')}: ` : ''}{item.last_message.body}
              </Text>
            ) : null}
          </View>
          {item.unread ? <View style={styles.dot} /> : null}
        </Pressable>
      )}
    />
  );
}

const styles = StyleSheet.create({
  row: { flexDirection: 'row', alignItems: 'center', paddingHorizontal: space.xl, paddingVertical: space.md, borderBottomWidth: StyleSheet.hairlineWidth, borderBottomColor: colors.hairline },
  thumb: { width: 56, height: 56, borderRadius: radius.md },
  dot: { width: 10, height: 10, borderRadius: 5, backgroundColor: colors.brand, marginLeft: space.sm },
});
