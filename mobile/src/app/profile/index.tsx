import { Ionicons } from '@expo/vector-icons';
import { router } from 'expo-router';
import { useTranslation } from 'react-i18next';
import { Pressable, ScrollView, StyleSheet, Text, View } from 'react-native';

import { Button, Chip, Section } from '@/components/ui';
import { useAuth } from '@/lib/auth/AuthContext';
import { setLanguage } from '@/lib/i18n';
import { colors, radius, space, type } from '@/theme/tokens';

export default function ProfileScreen() {
  const { t, i18n } = useTranslation();
  const { isLoggedIn, me, signOut } = useAuth();

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

      <Row icon="heart-outline" label={t('profile.interests')} onPress={() => router.push('/profile/interests')} />
      <Row icon="ribbon-outline" label={t('profile.conduct')} value={me?.conduct_score ?? t('profile.conductNew')} />
      <Row icon="shield-outline" label={t('profile.privacy')} value={t('common.comingSoon')} />
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

function Row({ icon, label, value, onPress }: { icon: string; label: string; value?: string; onPress?: () => void }) {
  return (
    <Pressable style={styles.row} onPress={onPress} disabled={!onPress}>
      <Ionicons name={icon as never} size={22} color={colors.text} />
      <Text style={[type.body, { flex: 1, marginLeft: space.md }]}>{label}</Text>
      {value ? <Text style={type.small}>{value}</Text> : <Ionicons name="chevron-forward" size={18} color={colors.textMuted} />}
    </Pressable>
  );
}

const styles = StyleSheet.create({
  hero: { flexDirection: 'row', alignItems: 'center', paddingVertical: space.xl },
  avatar: { width: 64, height: 64, borderRadius: 32, backgroundColor: colors.text, alignItems: 'center', justifyContent: 'center' },
  initial: { color: colors.white, fontSize: 26, fontWeight: '700' },
  providerCard: {
    flexDirection: 'row', alignItems: 'center', padding: space.lg, borderRadius: radius.lg, borderWidth: 1,
    borderColor: colors.border, marginBottom: space.lg,
  },
  row: {
    flexDirection: 'row', alignItems: 'center', paddingVertical: space.lg,
    borderBottomWidth: StyleSheet.hairlineWidth, borderBottomColor: colors.hairline,
  },
});
