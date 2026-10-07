import { Ionicons } from '@expo/vector-icons';
import { Image } from 'expo-image';
import { router } from 'expo-router';
import { useTranslation } from 'react-i18next';
import { ActivityIndicator, FlatList, Pressable, StyleSheet, Text, View } from 'react-native';

import { Badge, Button, Centered } from '@/components/ui';
import { useExperienceAction, useOnboarding, useProviderBookings, useProviderExperiences, useProviderProfile } from '@/lib/api/hooks';
import type { ProviderExperience } from '@/lib/api/types';
import { useAuth } from '@/lib/auth/AuthContext';
import { formatMoney } from '@/lib/utils/format';
import { colors, radius, space, statusColors, type } from '@/theme/tokens';

export default function ManageExperiences() {
  const { t } = useTranslation();
  const { me } = useAuth();
  const list = useProviderExperiences(Boolean(me?.is_provider));
  const profile = useProviderProfile(Boolean(me?.is_provider));
  const verified = profile.data?.verification_status === 'verified';
  const onboarding = useOnboarding(Boolean(me?.is_provider));
  const requests = useProviderBookings('pending_approval', Boolean(me?.is_provider));

  return (
    <FlatList
      data={list.data ?? []}
      keyExtractor={(e) => e.id}
      contentContainerStyle={{ padding: space.xl, paddingBottom: 80 }}
      refreshing={list.isRefetching}
      onRefresh={() => list.refetch()}
      ListHeaderComponent={
        <View style={{ marginBottom: space.lg }}>
          {!verified && profile.data ? (
            <Pressable style={styles.banner} onPress={() => router.push('/provider/become')}>
              <Ionicons name="id-card-outline" size={20} color={colors.warning} />
              <Text style={[type.smallStrong, { flex: 1, marginLeft: space.sm }]}>{t('provider.idTitle')}</Text>
              <Ionicons name="chevron-forward" size={18} color={colors.text} />
            </Pressable>
          ) : null}
          {onboarding.data && !onboarding.data.ready_to_publish ? (
            <Pressable style={styles.banner} onPress={() => router.push('/provider/payments')}>
              <Ionicons name="wallet-outline" size={20} color={colors.warning} />
              <Text style={[type.smallStrong, { flex: 1, marginLeft: space.sm }]}>{t('ops.paymentsTitle')}</Text>
              <Ionicons name="chevron-forward" size={18} color={colors.text} />
            </Pressable>
          ) : null}
          <View style={styles.tools}>
            <Tool icon="hourglass-outline" label={`${t('ops.requests')}${requests.data?.length ? ` (${requests.data.length})` : ''}`} onPress={() => router.push('/provider/requests')} />
            <Tool icon="cash-outline" label={t('ops.earnings')} onPress={() => router.push('/provider/earnings')} />
            <Tool icon="wallet-outline" label={t('ops.paymentsTitle')} onPress={() => router.push('/provider/payments')} />
            <Tool icon="star-outline" label={t('ops.reviews')} onPress={() => router.push('/provider/reviews')} />
            <Tool icon="chatbubbles-outline" label={t('inbox.title')} onPress={() => router.push('/inbox')} />
          </View>
          <Button title={t('provider.newExperience')} icon="add" onPress={() => router.push('/provider/experience/new')} />
        </View>
      }
      ListEmptyComponent={list.isLoading ? <ActivityIndicator /> : <Centered><Text style={type.body}>{t('provider.empty')}</Text></Centered>}
      renderItem={({ item }) => <Row item={item} />}
    />
  );
}

function Row({ item }: { item: ProviderExperience }) {
  const { t, i18n } = useTranslation();
  const action = useExperienceAction();
  const cover = item.media.find((m) => m.urls)?.urls?.w400;
  const sc = statusColors[item.status];
  return (
    <Pressable style={styles.row} onPress={() => router.push(`/provider/experience/${item.id}`)}>
      <Image source={cover} style={[styles.thumb, { backgroundColor: item.media[0]?.color ?? colors.surface }]} contentFit="cover" />
      <View style={{ flex: 1, marginLeft: space.md }}>
        <Text style={type.bodyStrong} numberOfLines={2}>{item.title || t('provider.status.draft')}</Text>
        <Text style={type.small}>{formatMoney(item.listed_price_cents, i18n.language)} · {item.sessions_upcoming} {t('provider.sessions').toLowerCase()}</Text>
        <View style={{ flexDirection: 'row', gap: space.sm, marginTop: space.sm, flexWrap: 'wrap' }}>
          <Badge label={t(`provider.status.${item.status}`)} bg={sc.bg} fg={sc.fg} />
          {item.pending_changes ? (
            <Badge
              label={item.pending_changes.review_status === 'pending' ? t('provider.pendingReview') : t('provider.pendingChanges')}
              bg={colors.brandSoft} fg={colors.brand}
            />
          ) : null}
        </View>
      </View>
      {item.status === 'live' || item.status === 'paused' ? (
        <Pressable
          hitSlop={8}
          onPress={() => action.mutate({ id: item.id, action: item.status === 'live' ? 'pause' : 'resume' })}
          accessibilityLabel={item.status === 'live' ? t('provider.pause') : t('provider.resume')}
        >
          <Ionicons name={item.status === 'live' ? 'pause-circle-outline' : 'play-circle-outline'} size={28} color={colors.text} />
        </Pressable>
      ) : null}
    </Pressable>
  );
}

function Tool({ icon, label, onPress }: { icon: string; label: string; onPress: () => void }) {
  return (
    <Pressable style={styles.tool} onPress={onPress}>
      <Ionicons name={icon as never} size={22} color={colors.text} />
      <Text style={[type.caption, { color: colors.text, marginTop: 4, textAlign: 'center' }]} numberOfLines={2}>{label}</Text>
    </Pressable>
  );
}

const styles = StyleSheet.create({
  tools: { flexDirection: 'row', gap: space.sm, marginBottom: space.lg },
  tool: { flex: 1, alignItems: 'center', borderWidth: 1, borderColor: colors.border, borderRadius: radius.md, padding: space.md },
  row: { flexDirection: 'row', alignItems: 'center', paddingVertical: space.md, borderBottomWidth: StyleSheet.hairlineWidth, borderBottomColor: colors.hairline },
  thumb: { width: 84, height: 84, borderRadius: radius.md },
  banner: {
    flexDirection: 'row', alignItems: 'center', backgroundColor: '#FFF4D6', padding: space.md, borderRadius: radius.md, marginBottom: space.lg,
  },
});
