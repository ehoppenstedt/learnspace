import { Ionicons } from '@expo/vector-icons';
import { router } from 'expo-router';
import { useTranslation } from 'react-i18next';
import { Pressable, ScrollView, StyleSheet, Text, View } from 'react-native';

import { Button, Chip, Section } from '@/components/ui';
import { usePendingReviews, useUnreadCount } from '@/lib/api/hooks';
import { useAuth } from '@/lib/auth/AuthContext';
import { setLanguage } from '@/lib/i18n';
import { colors, radius, space, type } from '@/theme/tokens';

export default function ProfileScreen() {
  const { t, i18n } = useTranslation();
  const { isLoggedIn, me, signOut } = useAuth();
  const unread = useUnreadCount(isLoggedIn);
  const pending = usePendingReviews(isLoggedIn);
  const owed = (pending.data?.reviews.length ?? 0) + (pending.data?.conduct_ratings.length ?? 0);

  if (!isLoggedIn) {
    return (
      <View style={{ padding: space.xl }}>
        <Text style={type.title}>{t('profile.guestTitle')}</Text>
        <Text style={[type.body, { marginVertical: space.lg }]}>{t('profile.guestBody')}</Text>
        <Button title={t('profile.login')} onPress={() => router.push('/auth')} />
        <LanguagePicker current={i18n.language} />
      </View>
    );
  }

  return (
    <ScrollView contentContainerStyle={{ paddingHorizontal: space.xl, paddingBottom: 48 }}>
      <View style={styles.hero}>
        <View style={styles.avatar}><Text style={styles.initial}>{(me?.first_name || '?')[0]}</Text></View>
        <View style={{ flex: 1, marginLeft: space.lg }}>
          <Text style={type.title}>{me?.first_name} {me?.last_name}</Text>
          <Text style={type.small}>{me?.email}</Text>
        </View>
      </View>

      {!me?.profile_complete ? (
        <Button title={t('auth.completeTitle')} onPress={() => router.push('/auth/complete-profile')} style={{ marginBottom: space.lg }} />
      ) : null}

      <Pressable style={styles.providerCard} onPress={() => router.push(me?.is_provider ? '/provider' : '/provider/become')}>
        <View style={{ flex: 1 }}>
          <Text style={type.bodyStrong}>{me?.is_provider ? t('profile.providerPanel') : t('profile.becomeProvider')}</Text>
          {!me?.is_provider ? <Text style={type.small}>{t('profile.becomeProviderHint')}</Text> : null}
        </View>
        <Ionicons name="chevron-forward" size={20} color={colors.text} />
      </Pressable>

      <Row icon="calendar-outline" label={t('profile.bookings')} onPress={() => router.push('/bookings')} />
      <Row icon="chatbubbles-outline" label={t('profile.messages')} count={unread.data?.unread} onPress={() => router.push('/inbox')} />
      {owed ? <Row icon="star-outline" label={t('profile.pendingReviews')} count={owed} onPress={() => router.push('/reviews/pending')} /> : null}
      <Row icon="heart-outline" label={t('profile.interests')} onPress={() => router.push('/profile/interests')} />
      <Row icon="notifications-outline" label={t('settings.notifications')} onPress={() => router.push('/profile/notifications')} />
      <Row icon="card-outline" label={t('settings.cards')} onPress={() => router.push('/profile/cards')} />
      <Row icon="ribbon-outline" label={t('profile.conduct')} value={me?.conduct_score ? Number(me.conduct_score).toFixed(1) : t('profile.conductNew')}
        onPress={() => router.push('/profile/conduct')} />
      <Row icon="shield-outline" label={t('profile.privacy')} onPress={() => router.push('/profile/privacy')} />
      <LanguagePicker current={i18n.language} />
      <Section last>
        <Button title={t('auth.logout')} variant="ghost" onPress={async () => { await signOut(); router.back(); }} />
      </Section>
    </ScrollView>
  );
}

function LanguagePicker({ current }: { current: string }) {
  const { t } = useTranslation();
  return (
    <Section title={t('profile.language')}>
      <View style={{ flexDirection: 'row' }}>
        <Chip label="Español" selected={current === 'es'} onPress={() => setLanguage('es')} />
        <Chip label="English" selected={current === 'en'} onPress={() => setLanguage('en')} />
      </View>
    </Section>
  );
}

function Row({ icon, label, value, count, onPress }: { icon: string; label: string; value?: string; count?: number; onPress?: () => void }) {
  return (
    <Pressable style={styles.row} onPress={onPress} disabled={!onPress}>
      <Ionicons name={icon as never} size={22} color={colors.text} />
      <Text style={[type.body, { flex: 1, marginLeft: space.md }]}>{label}</Text>
      {count ? <View style={styles.count}><Text style={styles.countText}>{count}</Text></View> : null}
      {value ? <Text style={type.small}>{value}</Text> : <Ionicons name="chevron-forward" size={18} color={colors.textMuted} />}
    </Pressable>
  );
}

const styles = StyleSheet.create({
  hero: { flexDirection: 'row', alignItems: 'center', paddingVertical: space.xl },
  avatar: { width: 64, height: 64, borderRadius: 32, backgroundColor: colors.text, alignItems: 'center', justifyContent: 'center' },
  initial: { color: colors.white, fontSize: 26, fontWeight: '700' },
  count: { minWidth: 22, height: 22, borderRadius: 11, backgroundColor: colors.brand, alignItems: 'center', justifyContent: 'center', paddingHorizontal: 6, marginRight: space.sm },
  countText: { color: colors.white, fontSize: 12, fontWeight: '700' },
  providerCard: {
    flexDirection: 'row', alignItems: 'center', padding: space.lg, borderRadius: radius.lg, borderWidth: 1,
    borderColor: colors.border, marginBottom: space.lg,
  },
  row: {
    flexDirection: 'row', alignItems: 'center', paddingVertical: space.lg,
    borderBottomWidth: StyleSheet.hairlineWidth, borderBottomColor: colors.hairline,
  },
});
