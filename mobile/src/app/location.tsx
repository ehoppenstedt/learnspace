import { Ionicons } from '@expo/vector-icons';
import { router } from 'expo-router';
import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { FlatList, Pressable, StyleSheet, Text, TextInput, View } from 'react-native';

import { useAreas } from '@/lib/api/hooks';
import { useLocation } from '@/lib/state/LocationContext';
import { useDebounced } from '@/lib/utils/useDebounced';
import { colors, radius, space, type } from '@/theme/tokens';

export default function LocationScreen() {
  const { t } = useTranslation();
  const { requestGps, setManualArea, permission } = useLocation();
  const [q, setQ] = useState('');
  const areas = useAreas(useDebounced(q, 250));

  return (
    <View style={{ flex: 1, backgroundColor: colors.bg, padding: space.xl }}>
      <Pressable
        style={styles.gps}
        onPress={async () => {
          if (await requestGps()) router.back();
        }}
      >
        <Ionicons name="navigate" size={20} color={colors.text} />
        <Text style={[type.bodyStrong, { marginLeft: space.md }]}>{t('location.useGps')}</Text>
      </Pressable>
      {permission === 'denied' ? <Text style={[type.small, { marginBottom: space.lg }]}>{t('location.denied')}</Text> : null}
      <View style={styles.search}>
        <Ionicons name="search" size={18} color={colors.textMuted} />
        <TextInput value={q} onChangeText={setQ} placeholder={t('location.search')} placeholderTextColor={colors.textSubtle}
          style={{ flex: 1, marginLeft: space.sm, fontSize: 16, color: colors.text }} autoFocus />
      </View>
      <FlatList
        data={areas.data ?? []}
        keyExtractor={(a) => a.slug}
        keyboardShouldPersistTaps="handled"
        renderItem={({ item }) => (
          <Pressable
            style={styles.row}
            onPress={async () => {
              await setManualArea({ slug: item.slug, name: item.name, lat: item.centroid.lat, lng: item.centroid.lng });
              router.back();
            }}
          >
            <View style={styles.pinIcon}><Ionicons name="location-outline" size={18} color={colors.text} /></View>
            <View>
              <Text style={type.bodyStrong}>{item.name}</Text>
              <Text style={type.small}>{item.borough}, {item.city}</Text>
            </View>
          </Pressable>
        )}
        ListFooterComponent={<Text style={[type.caption, { marginTop: space.lg }]}>{t('location.cdmxOnly')}</Text>}
      />
    </View>
  );
}

const styles = StyleSheet.create({
  gps: { flexDirection: 'row', alignItems: 'center', paddingVertical: space.lg, marginBottom: space.md },
  search: {
    flexDirection: 'row', alignItems: 'center', borderWidth: 1, borderColor: colors.border, borderRadius: radius.md,
    paddingHorizontal: space.md, height: 50, marginBottom: space.md,
  },
  row: { flexDirection: 'row', alignItems: 'center', paddingVertical: space.md },
  pinIcon: { width: 44, height: 44, borderRadius: radius.sm, backgroundColor: colors.surface, alignItems: 'center', justifyContent: 'center', marginRight: space.md },
});
