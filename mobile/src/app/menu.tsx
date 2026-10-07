import { Ionicons } from '@expo/vector-icons';
import { router, type Href } from 'expo-router';
import { useTranslation } from 'react-i18next';
import { Pressable, StyleSheet, Text, View } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';

import { useAuth } from '@/lib/auth/AuthContext';
import { colors, radius, shadow, space, type } from '@/theme/tokens';

/** The top-right "+" menu: create, manage, profile. */
export default function MenuScreen() {
  const { t } = useTranslation();
  const { isLoggedIn, me } = useAuth();

  const go = (target: Href, needsProvider = false) => {
    router.back();
    if (!isLoggedIn) return router.push({ pathname: '/auth', params: { next: String(target) } });
    if (needsProvider && !me?.is_provider) return router.push('/provider/become');
    router.push(target);
  };

  return (
    <Pressable style={styles.backdrop} onPress={() => router.back()}>
      <SafeAreaView edges={['top']}>
        <View style={[styles.sheet, shadow.floating]}>
          <Item icon="add-circle-outline" label={t('menu.create')} onPress={() => go('/provider/experience/new', true)} />
          <Item icon="albums-outline" label={t('menu.manage')} onPress={() => go('/provider', true)} />
          <Item icon="person-circle-outline" label={t('menu.profile')} onPress={() => { router.back(); router.push('/profile'); }} last />
        </View>
      </SafeAreaView>
    </Pressable>
  );
}

function Item({ icon, label, onPress, last }: { icon: string; label: string; onPress: () => void; last?: boolean }) {
  return (
    <Pressable onPress={onPress} style={[styles.item, !last && styles.divider]} accessibilityRole="menuitem">
      <Ionicons name={icon as never} size={22} color={colors.text} />
      <Text style={[type.body, { marginLeft: space.md, flex: 1 }]}>{label}</Text>
    </Pressable>
  );
}

const styles = StyleSheet.create({
  backdrop: { flex: 1, backgroundColor: 'rgba(0,0,0,0.25)' },
  sheet: { marginTop: 64, marginHorizontal: space.lg, alignSelf: 'flex-end', width: 300, backgroundColor: colors.bg, borderRadius: radius.lg, paddingVertical: space.xs },
  item: { flexDirection: 'row', alignItems: 'center', paddingHorizontal: space.lg, paddingVertical: space.lg },
  divider: { borderBottomWidth: StyleSheet.hairlineWidth, borderBottomColor: colors.hairline },
});
