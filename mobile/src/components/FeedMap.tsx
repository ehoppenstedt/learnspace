import { router } from 'expo-router';
import { useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { StyleSheet, Text, View } from 'react-native';
import { MapView, Marker, type Region } from '@/components/map';

import { useMapPins, type Bbox } from '@/lib/api/hooks';
import { useFilters } from '@/lib/state/FiltersContext';
import { CDMX_CENTER, useLocation } from '@/lib/state/LocationContext';
import { formatMoney } from '@/lib/utils/format';
import { colors, radius, shadow } from '@/theme/tokens';

function toBbox(r: Region): Bbox {
  // Clamp to the server's 2-degree limit.
  const dLng = Math.min(r.longitudeDelta, 1.9) / 2;
  const dLat = Math.min(r.latitudeDelta, 1.9) / 2;
  return [r.longitude - dLng, r.latitude - dLat, r.longitude + dLng, r.latitude + dLat];
}

/** Map of approximate locations. Price pins, like the list shows: total price. */
export function FeedMap() {
  const { i18n } = useTranslation();
  const { origin } = useLocation();
  const { filters, query } = useFilters();
  const initial = useMemo<Region>(() => {
    const c = origin ?? CDMX_CENTER;
    return { latitude: c.lat, longitude: c.lng, latitudeDelta: 0.08, longitudeDelta: 0.08 };
  }, [origin]);
  const [bbox, setBbox] = useState<Bbox>(toBbox(initial));
  const pins = useMapPins(filters, query, bbox);

  return (
    <View style={{ flex: 1 }}>
      <MapView
        style={StyleSheet.absoluteFill}
        initialRegion={initial}
        showsUserLocation={origin?.kind === 'gps'}
        onRegionChangeComplete={(r) => setBbox(toBbox(r))}
        toolbarEnabled={false}
      >
        {(pins.data?.results ?? []).map((p) => (
          <Marker key={p.id} coordinate={{ latitude: p.lat, longitude: p.lng }} onPress={() => router.push(`/experience/${p.id}`)} tracksViewChanges={false}>
            <View style={[styles.pin, shadow.card]}>
              <Text style={styles.pinText}>{formatMoney(p.total_cents, i18n.language)}</Text>
            </View>
          </Marker>
        ))}
      </MapView>
    </View>
  );
}

const styles = StyleSheet.create({
  pin: { backgroundColor: colors.white, borderRadius: radius.pill, paddingHorizontal: 10, paddingVertical: 6 },
  pinText: { fontWeight: '700', fontSize: 13, color: colors.text },
});
