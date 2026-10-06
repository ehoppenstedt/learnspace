import { useMutation, useQuery } from '@tanstack/react-query';
import { router } from 'expo-router';
import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { ScrollView, Text, View } from 'react-native';

import { Button, Chip } from '@/components/ui';
import { api } from '@/lib/api/client';
import { useConfig } from '@/lib/api/hooks';
import { space, type } from '@/theme/tokens';

export default function InterestsScreen() {
  const { t } = useTranslation();
  const config = useConfig();
  const current = useQuery({ queryKey: ['me', 'interests'], queryFn: () => api<{ category_ids: number[] }>('/me/interests') });
  const [edited, setSelected] = useState<number[] | null>(null);
  const selected = edited ?? current.data?.category_ids ?? [];
  const save = useMutation({
    mutationFn: () => api('/me/interests', { method: 'PUT', body: { category_ids: selected } }),
    onSuccess: () => router.back(),
  });

  return (
    <ScrollView contentContainerStyle={{ padding: space.xl }}>
      <Text style={[type.small, { marginBottom: space.lg }]}>{t('profile.interestsHint')}</Text>
      <View style={{ flexDirection: 'row', flexWrap: 'wrap' }}>
        {(config.data?.categories ?? []).map((c) => (
          <Chip key={c.id} label={c.name} icon={c.icon as never} selected={selected.includes(c.id)}
            onPress={() => setSelected(selected.includes(c.id) ? selected.filter((i) => i !== c.id) : [...selected, c.id])} />
        ))}
      </View>
      <Button title={t('common.save')} onPress={() => save.mutate()} loading={save.isPending} style={{ marginTop: space.xl }} />
    </ScrollView>
  );
}
