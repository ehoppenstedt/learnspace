import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Alert, Modal, Pressable, ScrollView, StyleSheet, Text, View } from 'react-native';

import { Button, Chip, Field } from '@/components/ui';
import { ApiError, api } from '@/lib/api/client';
import type { ReportTarget } from '@/lib/api/types';
import { colors, radius, space, type } from '@/theme/tokens';

const REASONS: Record<ReportTarget, string[]> = {
  experience: ['misleading', 'inappropriate', 'safety', 'fraud', 'off_platform_payment', 'other'],
  review: ['inappropriate', 'harassment', 'spam', 'misleading', 'other'],
  message: ['harassment', 'inappropriate', 'off_platform_payment', 'fraud', 'spam', 'safety', 'other'],
  user: ['harassment', 'safety', 'fraud', 'off_platform_payment', 'spam', 'other'],
};

export function ReportSheet({ target, id, onClose }: { target: ReportTarget; id: string; onClose: () => void }) {
  const { t } = useTranslation();
  const [reason, setReason] = useState<string | null>(null);
  const [details, setDetails] = useState('');
  const [busy, setBusy] = useState(false);

  const send = async () => {
    if (!reason) return;
    setBusy(true);
    try {
      await api('/reports', { method: 'POST', body: { target_type: target, target_id: id, reason_code: reason, details } });
      Alert.alert(t('report.thanks'));
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
        <ScrollView keyboardShouldPersistTaps="handled">
          <Text style={type.title}>{t(`report.title.${target}`)}</Text>
          <Text style={[type.small, { marginVertical: space.md }]}>{t('report.body')}</Text>
          <View style={{ flexDirection: 'row', flexWrap: 'wrap' }}>
            {REASONS[target].map((r) => (
              <Chip key={r} label={t(`report.reasons.${r}`)} selected={reason === r} onPress={() => setReason(r)} />
            ))}
          </View>
          <Field label={t('report.details')} value={details} onChangeText={setDetails} multiline maxLength={2000} />
          <Button title={t('report.send')} variant="dark" onPress={send} loading={busy} disabled={!reason} />
          <Button title={t('common.cancel')} variant="ghost" onPress={onClose} />
        </ScrollView>
      </View>
    </Modal>
  );
}

const styles = StyleSheet.create({
  backdrop: { flex: 1, backgroundColor: colors.overlay },
  sheet: {
    backgroundColor: colors.bg, padding: space.xl, paddingBottom: space.xxxl, maxHeight: '85%',
    borderTopLeftRadius: radius.xl, borderTopRightRadius: radius.xl,
  },
});
