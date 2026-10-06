import { Ionicons } from '@expo/vector-icons';
import { useQueryClient } from '@tanstack/react-query';
import { useTranslation } from 'react-i18next';
import { FlatList, StyleSheet, Text, View } from 'react-native';

import { Button } from '@/components/ui';
import { api } from '@/lib/api/client';
import { useSavedCards } from '@/lib/api/hooks';
import { colors, space, type } from '@/theme/tokens';

export default function SavedCards() {
  const { t } = useTranslation();
  const qc = useQueryClient();
  const cards = useSavedCards();
  return (
    <FlatList
      data={cards.data ?? []}
      keyExtractor={(c) => c.id}
      contentContainerStyle={{ padding: space.xl }}
      ListEmptyComponent={<Text style={type.body}>{t('settings.noCards')}</Text>}
      renderItem={({ item }) => (
        <View style={styles.row}>
          <Ionicons name="card-outline" size={24} color={colors.text} />
          <Text style={[type.body, { flex: 1, marginLeft: space.md }]}>
            {item.brand.toUpperCase()} •••• {item.last4} · {String(item.exp_month).padStart(2, '0')}/{String(item.exp_year).slice(-2)}
          </Text>
          <Button title={t('settings.remove')} variant="ghost" onPress={async () => {
            await api(`/me/payment-methods/${item.id}`, { method: 'DELETE' });
            qc.invalidateQueries({ queryKey: ['me', 'cards'] });
          }} />
        </View>
      )}
    />
  );
}

const styles = StyleSheet.create({
  row: { flexDirection: 'row', alignItems: 'center', paddingVertical: space.md, borderBottomWidth: StyleSheet.hairlineWidth, borderBottomColor: colors.hairline },
});
