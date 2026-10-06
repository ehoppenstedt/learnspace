import { router } from 'expo-router';
import { useTranslation } from 'react-i18next';
import { Alert, ScrollView, Text } from 'react-native';

import { Button, Section } from '@/components/ui';
import { ApiError, api } from '@/lib/api/client';
import { useAuth } from '@/lib/auth/AuthContext';
import { space, type } from '@/theme/tokens';

export default function Privacy() {
  const { t } = useTranslation();
  const { signOut } = useAuth();

  const exportData = async () => {
    await api('/me/data-export', { method: 'POST' });
    Alert.alert(t('settings.exportSent'));
  };

  const deleteAccount = () =>
    Alert.alert(t('settings.delete'), t('settings.deleteConfirm'), [
      { text: t('common.cancel'), style: 'cancel' },
      {
        text: t('settings.delete'), style: 'destructive', onPress: async () => {
          try {
            await api('/me', { method: 'DELETE' });
            await signOut();
            router.dismissAll();
          } catch (err) {
            const blockers = err instanceof ApiError ? (err.fields.blockers as string[] | undefined) : undefined;
            Alert.alert(blockers ? t('settings.deleteBlocked', { items: blockers.join(', ') }) : t('errors.generic'));
          }
        },
      },
    ]);

  return (
    <ScrollView contentContainerStyle={{ paddingHorizontal: space.xl }}>
      <Section>
        <Text style={[type.small, { marginBottom: space.md }]}>LFPDPPP</Text>
        <Button title={t('settings.export')} variant="secondary" icon="download-outline" onPress={exportData} />
      </Section>
      <Section last>
        <Button title={t('settings.delete')} variant="ghost" onPress={deleteAccount} />
      </Section>
    </ScrollView>
  );
}
