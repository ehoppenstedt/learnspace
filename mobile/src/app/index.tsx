import { Ionicons } from '@expo/vector-icons';
import { router } from 'expo-router';
import { useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { ActivityIndicator, FlatList, Pressable, RefreshControl, StyleSheet, Text, View } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';

import { ExperienceCard } from '@/components/ExperienceCard';
import { FeedMap } from '@/components/FeedMap';
import { SearchHeader } from '@/components/SearchHeader';
import { Button, Centered, ErrorState } from '@/components/ui';
import { useConfig, useFeed } from '@/lib/api/hooks';
import { useFilters } from '@/lib/state/FiltersContext';
import { useLocation } from '@/lib/state/LocationContext';
import { useDebounced } from '@/lib/utils/useDebounced';
import { colors, radius, shadow, space, type } from '@/theme/tokens';

export default function FeedScreen() {
  const { t } = useTranslation();
  const [mode, setMode] = useState<'list' | 'map'>('list');
  const { origin, resolving } = useLocation();
  const { filters, setFilters, query } = useFilters();
  const debouncedQuery = useDebounced(query, 350);
  const config = useConfig();
  const feed = useFeed(filters, origin, debouncedQuery, !resolving);
  const items = useMemo(() => feed.data?.pages.flatMap((p) => p.results) ?? [], [feed.data]);

  const placeLabel = origin?.kind === 'area' ? t('feed.near', { place: origin.name }) : origin ? t('feed.nearYou') : t('feed.setLocation');

  return (
    <SafeAreaView style={styles.screen} edges={['top']}>
      <SearchHeader categories={config.data?.categories ?? []} placeLabel={placeLabel} />
      {mode === 'map' ? (
        <FeedMap />
      ) : feed.isError ? (
        <ErrorState message={t('errors.network')} onRetry={() => feed.refetch()} />
      ) : (
        <FlatList
          data={items}
          keyExtractor={(e) => e.id}
          renderItem={({ item }) => <ExperienceCard item={item} />}
          contentContainerStyle={{ paddingTop: space.xl, paddingBottom: 120 }}
          onEndReachedThreshold={0.6}
          onEndReached={() => feed.hasNextPage && !feed.isFetchingNextPage && feed.fetchNextPage()}
          refreshControl={<RefreshControl refreshing={feed.isRefetching} onRefresh={() => feed.refetch()} />}
          ListEmptyComponent={
            feed.isLoading || resolving ? (
              <View style={{ paddingTop: 80 }}><ActivityIndicator /></View>
            ) : (
              <Centered>
                <Ionicons name="compass-outline" size={40} color={colors.textMuted} />
                <Text style={[type.body, { textAlign: 'center', marginVertical: space.md }]}>{t('feed.empty')}</Text>
                <Button
                  title={t('feed.emptyCta')}
                  variant="secondary"
                  onPress={() => setFilters({ ...filters, radius_km: Math.min(filters.radius_km * 2, 50), categories: [], days: [], time_from: null, time_to: null })}
                />
              </Centered>
            )
          }
          ListFooterComponent={feed.isFetchingNextPage ? <ActivityIndicator style={{ margin: space.xl }} /> : null}
        />
      )}
      <Pressable
        onPress={() => setMode(mode === 'list' ? 'map' : 'list')}
        style={[styles.toggle, shadow.floating]}
        accessibilityRole="button"
      >
        <Text style={styles.toggleText}>{mode === 'list' ? t('feed.map') : t('feed.list')}</Text>
        <Ionicons name={mode === 'list' ? 'map' : 'list'} size={16} color={colors.white} style={{ marginLeft: 6 }} />
      </Pressable>
      {!origin && !resolving ? (
        <Pressable style={styles.locationBanner} onPress={() => router.push('/location')}>
          <Ionicons name="location-outline" size={18} color={colors.text} />
          <Text style={[type.smallStrong, { marginLeft: 6 }]}>{t('location.denied')}</Text>
        </Pressable>
      ) : null}
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  screen: { flex: 1, backgroundColor: colors.bg },
  toggle: {
    position: 'absolute', bottom: 36, alignSelf: 'center', flexDirection: 'row', alignItems: 'center',
    backgroundColor: colors.text, paddingHorizontal: 20, height: 48, borderRadius: radius.pill,
  },
  toggleText: { color: colors.white, fontWeight: '600', fontSize: 15 },
  locationBanner: {
    position: 'absolute', top: 160, left: space.xl, right: space.xl, flexDirection: 'row', alignItems: 'center',
    backgroundColor: colors.brandSoft, borderRadius: radius.md, padding: space.md,
  },
});
