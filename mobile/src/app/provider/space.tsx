import { Ionicons } from '@expo/vector-icons';
import { useQueryClient } from '@tanstack/react-query';
import { router } from 'expo-router';
import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { ScrollView, StyleSheet, Text, View } from 'react-native';
import { MapView, type Region } from '@/components/map';

import { Button, Field } from '@/components/ui';
import { ApiError, api } from '@/lib/api/client';
import { CDMX_CENTER, useLocation } from '@/lib/state/LocationContext';
import { colors, radius, space, type } from '@/theme/tokens';

/** New space: the pin stays centered while the map moves, so placing it precisely is easy. */
export default function NewSpace() {
  const { t } = useTranslation();
  const qc = useQueryClient();
  const { origin } = useLocation();
  const start = origin ?? CDMX_CENTER;
  const [region, setRegion] = useState<Region>({ latitude: start.lat, longitude: start.lng, latitudeDelta: 0.01, longitudeDelta: 0.01 });
  const [name, setName] = useState('');
  const [address, setAddress] = useState('');
  const [reference, setReference] = useState('');
  const [about, setAbout] = useState('');
  const [error, setError] = useState<string>();
  const [busy, setBusy] = useState(false);

  const save = async () => {
    setBusy(true);
    setError(undefined);
    try {
      await api('/provider/spaces', {
        method: 'POST',
        body: { name, address_line: address, address_reference: reference, about, lat: region.latitude, lng: region.longitude },
      });
      await qc.invalidateQueries({ queryKey: ['provider', 'spaces'] });
      router.back();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : t('errors.network'));
    } finally {
      setBusy(false);
    }
  };

  return (
    <ScrollView contentContainerStyle={{ padding: space.xl, paddingBottom: 60 }} keyboardShouldPersistTaps="handled">
      <View style={styles.map}>
        <MapView style={StyleSheet.absoluteFill} initialRegion={region} onRegionChangeComplete={setRegion} />
        <View pointerEvents="none" style={styles.pin}>
          <Ionicons name="location" size={40} color={colors.brand} />
        </View>
      </View>
      <Text style={[type.caption, { marginBottom: space.lg }]}>{t('space.pin')}</Text>
      <Field label={t('space.name')} value={name} onChangeText={setName} />
      <Field label={t('space.address')} hint={t('space.addressHint')} value={address} onChangeText={setAddress} />
      <Field label={t('space.reference')} value={reference} onChangeText={setReference} />
      <Field label={t('space.about')} value={about} onChangeText={setAbout} multiline />
      {error ? <Text style={{ color: colors.danger, marginBottom: space.md }}>{error}</Text> : null}
      <Button title={t('common.save')} onPress={save} loading={busy} disabled={!name.trim() || address.trim().length < 5} />
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  map: { height: 240, borderRadius: radius.lg, overflow: 'hidden', marginBottom: space.sm },
  pin: { position: 'absolute', top: '50%', left: '50%', marginLeft: -20, marginTop: -40 },
});
