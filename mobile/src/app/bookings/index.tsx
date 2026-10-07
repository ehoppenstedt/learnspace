import { router } from 'expo-router';
import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { ActivityIndicator, FlatList, Text, View } from 'react-native';

import { BookingCard } from '@/components/BookingCard';
import { Button, Centered, Chip } from '@/components/ui';
import { useBookings } from '@/lib/api/hooks';
import { space, type } from '@/theme/tokens';

export default function BookingsScreen() {
  const { t } = useTranslation();
  const [scope, setScope] = useState<'upcoming' | 'past'>('upcoming');
  const list = useBookings(scope);
  return (
    <FlatList
      data={list.data ?? []}
      keyExtractor={(b) => b.id}
      contentContainerStyle={{ padding: space.xl, flexGrow: 1 }}
      refreshing={list.isRefetching}
      onRefresh={() => list.refetch()}
      ListHeaderComponent={
        <View style={{ flexDirection: 'row', marginBottom: space.lg }}>
          <Chip label={t('bookings.upcoming')} selected={scope === 'upcoming'} onPress={() => setScope('upcoming')} />
          <Chip label={t('bookings.past')} selected={scope === 'past'} onPress={() => setScope('past')} />
        </View>
      }
      renderItem={({ item }) => <BookingCard booking={item} />}
      ListEmptyComponent={
        list.isLoading ? <ActivityIndicator /> : (
          <Centered>
            <Text style={[type.body, { marginBottom: space.lg }]}>{t('bookings.empty')}</Text>
            <Button title={t('bookings.explore')} variant="secondary" onPress={() => router.navigate('/')} />
          </Centered>
        )
      }
    />
  );
}
