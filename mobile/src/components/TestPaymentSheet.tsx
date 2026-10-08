import { Ionicons } from '@expo/vector-icons';
import { useTranslation } from 'react-i18next';
import { Modal, Pressable, StyleSheet, Text, View } from 'react-native';

import { formatMoney } from '@/lib/utils/format';
import { colors, radius, space, type } from '@/theme/tokens';

import { Button } from './ui';

export type TestOutcome = 'succeeded' | 'failed' | 'cancelled';

/**
 * Stand-in for Stripe's payment sheet while there is no Stripe account (user testing).
 * Never collects card data: the test card is fixed and shown, not typed.
 */
export function TestPaymentSheet({ amountCents, onResult, store = false }: { amountCents: number; onResult: (o: TestOutcome) => void; store?: boolean }) {
  const { t, i18n } = useTranslation();
  const amount = `${formatMoney(amountCents, i18n.language)} MXN`;
  return (
    <Modal transparent animationType="slide" onRequestClose={() => onResult('cancelled')}>
      <Pressable style={styles.backdrop} onPress={() => onResult('cancelled')} accessibilityLabel={t('common.cancel')} />
      <View style={styles.sheet}>
        <View style={styles.banner}>
          <Ionicons name="flask-outline" size={16} color={colors.warning} />
          <Text style={[type.smallStrong, { color: colors.warning, marginLeft: 6, flex: 1 }]}>{t('testmode.banner')}</Text>
        </View>
        <Text style={type.title}>{store ? t('appstore.sheetTitle') : t('testmode.sheetTitle')}</Text>
        <Text style={[type.display, { marginVertical: space.md }]}>{amount}</Text>
        <View style={styles.card}>
          <Ionicons name={store ? 'logo-apple' : 'card'} size={22} color={colors.text} />
          <Text style={[type.body, { marginLeft: space.md, flex: 1 }]}>{store ? 'App Store · Sandbox' : 'VISA •••• 4242'}</Text>
          <Text style={type.caption}>{t('testmode.testCard')}</Text>
        </View>
        <Button title={store ? t('appstore.buy', { amount }) : t('testmode.pay', { amount })} variant={store ? 'dark' : 'primary'}
          onPress={() => onResult('succeeded')} />
        {store ? (
          <Button title={t('common.cancel')} variant="ghost" onPress={() => onResult('cancelled')} />
        ) : (
          <Button title={t('testmode.decline')} variant="ghost" onPress={() => onResult('failed')} />
        )}
      </View>
    </Modal>
  );
}

const styles = StyleSheet.create({
  backdrop: { flex: 1, backgroundColor: colors.overlay },
  sheet: { backgroundColor: colors.bg, padding: space.xl, paddingBottom: space.xxxl, borderTopLeftRadius: radius.xl, borderTopRightRadius: radius.xl },
  banner: { flexDirection: 'row', alignItems: 'center', backgroundColor: '#FFF4D6', borderRadius: radius.sm, padding: space.sm, marginBottom: space.lg },
  card: { flexDirection: 'row', alignItems: 'center', borderWidth: 1, borderColor: colors.border, borderRadius: radius.md, padding: space.lg, marginBottom: space.lg },
});
