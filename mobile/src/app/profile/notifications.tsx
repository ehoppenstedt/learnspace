import { useQueryClient } from '@tanstack/react-query';
import { useTranslation } from 'react-i18next';
import { ScrollView, StyleSheet, Switch, Text, View } from 'react-native';

import { api } from '@/lib/api/client';
import { useNotificationPrefs } from '@/lib/api/hooks';
import type { NotificationPrefs } from '@/lib/api/types';
import { colors, space, type } from '@/theme/tokens';

export default function NotificationSettings() {
  const { t } = useTranslation();
  const qc = useQueryClient();
  const prefs = useNotificationPrefs();
  const value = prefs.data ?? { push: true, email: true, reminders: true };
  const update = async (patch: Partial<NotificationPrefs>) => {
    const next = { ...value, ...patch };
    qc.setQueryData(['me', 'prefs'], next);
    await api('/me/notification-prefs', { method: 'PUT', body: next });
  };
  return (
    <ScrollView contentContainerStyle={{ padding: space.xl }}>
      <Row label={t('settings.push')} value={value.push} onChange={(v) => update({ push: v })} />
      <Row label={t('settings.email')} value={value.email} onChange={(v) => update({ email: v })} />
      <Row label={t('settings.reminders')} hint={t('settings.remindersHint')} value={value.reminders} onChange={(v) => update({ reminders: v })} />
    </ScrollView>
  );
}

function Row({ label, hint, value, onChange }: { label: string; hint?: string; value: boolean; onChange: (v: boolean) => void }) {
  return (
    <View style={styles.row}>
      <View style={{ flex: 1 }}>
        <Text style={type.body}>{label}</Text>
        {hint ? <Text style={type.caption}>{hint}</Text> : null}
      </View>
      <Switch value={value} onValueChange={onChange} trackColor={{ true: colors.brand }} />
    </View>
  );
}

const styles = StyleSheet.create({
  row: { flexDirection: 'row', alignItems: 'center', paddingVertical: space.lg, borderBottomWidth: StyleSheet.hairlineWidth, borderBottomColor: colors.hairline },
});
