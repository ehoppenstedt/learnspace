import { useQueryClient } from '@tanstack/react-query';
import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Alert, Modal, Pressable, ScrollView, StyleSheet, Text, View } from 'react-native';

import { Stars } from '@/components/Stars';
import { Badge, Button, Field } from '@/components/ui';
import { ApiError, api } from '@/lib/api/client';
import { useMyConduct } from '@/lib/api/hooks';
import type { ConductRatingItem } from '@/lib/api/types';
import { formatSessionDate } from '@/lib/utils/format';
import { colors, radius, space, type } from '@/theme/tokens';

export default function MyConduct() {
  const { t, i18n } = useTranslation();
  const conduct = useMyConduct();
  const [appealing, setAppealing] = useState<ConductRatingItem | null>(null);
  const data = conduct.data;

  return (
    <ScrollView contentContainerStyle={{ padding: space.xl, paddingBottom: 48 }}>
      <View style={styles.hero}>
        <Text style={type.small}>{t('conduct.score')}</Text>
        <Text style={styles.score}>{data?.score ? Number(data.score).toFixed(1) : '—'}</Text>
        {data?.score ? <Stars value={Number(data.score)} size={18} /> : null}
        <Text style={[type.caption, { marginTop: space.md, textAlign: 'center' }]}>{t('conduct.explain')}</Text>
      </View>
      {data && !data.ratings.length ? <Text style={[type.body, { textAlign: 'center' }]}>{t('conduct.none')}</Text> : null}
      {data?.ratings.map((r) => (
        <View key={r.id} style={[styles.card, r.excluded && { opacity: 0.55 }]}>
          <View style={{ flexDirection: 'row', justifyContent: 'space-between' }}>
            <Text style={[type.bodyStrong, { flex: 1 }]}>{r.experience}</Text>
            <Text style={type.caption}>{formatSessionDate(r.date, i18n.language).split(' · ')[0]}</Text>
          </View>
          <Row label={t('conduct.respect')} value={r.respect} />
          <Row label={t('conduct.punctuality')} value={r.punctuality} />
          {r.appeal ? (
            <View style={{ marginTop: space.sm }}>
              <Badge label={t(`conduct.appealStatus.${r.appeal.status}`)} bg={colors.surface} fg={colors.text} />
              {r.appeal.decision_note ? <Text style={[type.small, { marginTop: 4 }]}>{r.appeal.decision_note}</Text> : null}
            </View>
          ) : r.excluded ? (
            <Badge label={t('conduct.excluded')} bg={colors.surface} fg={colors.text} />
          ) : (
            <Button title={t('conduct.appeal')} variant="ghost" onPress={() => setAppealing(r)} style={{ alignSelf: 'flex-start', paddingHorizontal: 0, height: 40 }} />
          )}
        </View>
      ))}
      {appealing ? <AppealSheet rating={appealing} onClose={() => setAppealing(null)} /> : null}
    </ScrollView>
  );
}

function Row({ label, value }: { label: string; value: number }) {
  return (
    <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', marginTop: space.sm }}>
      <Text style={type.small}>{label}</Text>
      <Stars value={value} />
    </View>
  );
}

function AppealSheet({ rating, onClose }: { rating: ConductRatingItem; onClose: () => void }) {
  const { t } = useTranslation();
  const qc = useQueryClient();
  const [statement, setStatement] = useState('');
  const [busy, setBusy] = useState(false);
  const send = async () => {
    setBusy(true);
    try {
      await api(`/me/conduct/${rating.id}/appeal`, { method: 'POST', body: { statement } });
      qc.invalidateQueries({ queryKey: ['me', 'conduct'] });
      Alert.alert(t('conduct.appealSent'));
      onClose();
    } catch (err) {
      Alert.alert(err instanceof ApiError ? err.message : t('errors.network'));
    } finally {
      setBusy(false);
    }
  };
  return (
    <Modal transparent animationType="slide" onRequestClose={onClose}>
      <Pressable style={styles.backdrop} onPress={onClose} />
      <View style={styles.sheet}>
        <Text style={type.title}>{t('conduct.appealTitle')}</Text>
        <Text style={[type.small, { marginVertical: space.md }]}>{t('conduct.appealHint')}</Text>
        <Field label={rating.experience} value={statement} onChangeText={setStatement} multiline maxLength={2000} />
        <Button title={t('conduct.appealSend')} variant="dark" onPress={send} loading={busy} disabled={statement.trim().length < 20} />
        <Button title={t('common.cancel')} variant="ghost" onPress={onClose} />
      </View>
    </Modal>
  );
}

const styles = StyleSheet.create({
  hero: { alignItems: 'center', paddingVertical: space.xl, marginBottom: space.lg, borderRadius: radius.lg, backgroundColor: colors.surface, paddingHorizontal: space.lg },
  score: { fontSize: 48, fontWeight: '700', color: colors.text, marginVertical: space.xs },
  card: { borderWidth: 1, borderColor: colors.border, borderRadius: radius.md, padding: space.md, marginBottom: space.md },
  backdrop: { flex: 1, backgroundColor: colors.overlay },
  sheet: { backgroundColor: colors.bg, padding: space.xl, paddingBottom: space.xxxl, borderTopLeftRadius: radius.xl, borderTopRightRadius: radius.xl },
});
