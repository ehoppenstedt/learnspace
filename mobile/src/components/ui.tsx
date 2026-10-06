import { Ionicons } from '@expo/vector-icons';
import type { ComponentProps, ReactNode } from 'react';
import { ActivityIndicator, Pressable, StyleSheet, Text, TextInput, View, type TextInputProps, type ViewStyle } from 'react-native';

import { colors, radius, space, type } from '@/theme/tokens';

type IconName = ComponentProps<typeof Ionicons>['name'];

export function Button({
  title, onPress, variant = 'primary', loading, disabled, icon, style,
}: {
  title: string; onPress?: () => void; variant?: 'primary' | 'secondary' | 'ghost' | 'dark';
  loading?: boolean; disabled?: boolean; icon?: IconName; style?: ViewStyle;
}) {
  const v = variants[variant];
  return (
    <Pressable
      accessibilityRole="button"
      onPress={onPress}
      disabled={disabled || loading}
      style={({ pressed }) => [styles.button, v.container, pressed && { opacity: 0.85 }, (disabled || loading) && { opacity: 0.45 }, style]}
    >
      {loading ? (
        <ActivityIndicator color={v.text.color} />
      ) : (
        <View style={styles.row}>
          {icon ? <Ionicons name={icon} size={18} color={v.text.color} style={{ marginRight: space.sm }} /> : null}
          <Text style={[styles.buttonText, v.text]}>{title}</Text>
        </View>
      )}
    </Pressable>
  );
}

const variants = {
  primary: { container: { backgroundColor: colors.brand }, text: { color: colors.white } },
  dark: { container: { backgroundColor: colors.text }, text: { color: colors.white } },
  secondary: { container: { backgroundColor: colors.bg, borderWidth: 1, borderColor: colors.text }, text: { color: colors.text } },
  ghost: { container: { backgroundColor: 'transparent' }, text: { color: colors.text, textDecorationLine: 'underline' as const } },
};

export function Chip({ label, selected, onPress, icon }: { label: string; selected?: boolean; onPress?: () => void; icon?: IconName }) {
  return (
    <Pressable
      accessibilityRole="button"
      accessibilityState={{ selected }}
      onPress={onPress}
      style={[styles.chip, selected && styles.chipSelected]}
    >
      {icon ? <Ionicons name={icon} size={16} color={selected ? colors.white : colors.text} style={{ marginRight: 6 }} /> : null}
      <Text style={[styles.chipText, selected && { color: colors.white }]}>{label}</Text>
    </Pressable>
  );
}

export function Field({ label, error, hint, ...props }: TextInputProps & { label: string; error?: string; hint?: string }) {
  return (
    <View style={{ marginBottom: space.lg }}>
      <Text style={styles.label}>{label}</Text>
      <TextInput
        placeholderTextColor={colors.textSubtle}
        accessibilityLabel={label}
        accessibilityHint={hint}
        {...props}
        style={[styles.input, props.multiline && { minHeight: 110, textAlignVertical: 'top' }, error ? { borderColor: colors.danger } : null, props.style]}
      />
      {error ? <Text style={styles.error}>{error}</Text> : hint ? <Text style={styles.hint}>{hint}</Text> : null}
    </View>
  );
}

export function Section({ title, children, last }: { title?: string; children: ReactNode; last?: boolean }) {
  return (
    <View style={[styles.section, last && { borderBottomWidth: 0 }]}>
      {title ? <Text style={[type.title, { fontSize: 20, marginBottom: space.md }]}>{title}</Text> : null}
      {children}
    </View>
  );
}

export function Checkbox({ checked, onChange, label }: { checked: boolean; onChange: (v: boolean) => void; label: string }) {
  return (
    <Pressable accessibilityRole="checkbox" accessibilityState={{ checked }} onPress={() => onChange(!checked)} style={styles.checkRow}>
      <View style={[styles.checkbox, checked && { backgroundColor: colors.text, borderColor: colors.text }]}>
        {checked ? <Ionicons name="checkmark" size={16} color={colors.white} /> : null}
      </View>
      <Text style={[type.small, { flex: 1, color: colors.text }]}>{label}</Text>
    </Pressable>
  );
}

export function Badge({ label, bg, fg }: { label: string; bg: string; fg: string }) {
  return (
    <View style={{ backgroundColor: bg, borderRadius: radius.pill, paddingHorizontal: 10, paddingVertical: 4, alignSelf: 'flex-start' }}>
      <Text style={{ color: fg, fontSize: 12, fontWeight: '600' }}>{label}</Text>
    </View>
  );
}

export function Centered({ children }: { children: ReactNode }) {
  return <View style={{ flex: 1, alignItems: 'center', justifyContent: 'center', padding: space.xl }}>{children}</View>;
}

export function ErrorState({ onRetry, message }: { onRetry?: () => void; message: string }) {
  return (
    <Centered>
      <Ionicons name="cloud-offline-outline" size={36} color={colors.textMuted} />
      <Text style={[type.body, { textAlign: 'center', marginVertical: space.md }]}>{message}</Text>
      {onRetry ? <Button title="↻" variant="secondary" onPress={onRetry} style={{ minWidth: 120 }} /> : null}
    </Centered>
  );
}

const styles = StyleSheet.create({
  row: { flexDirection: 'row', alignItems: 'center' },
  button: { height: 52, borderRadius: radius.md, alignItems: 'center', justifyContent: 'center', paddingHorizontal: space.xl },
  buttonText: { fontSize: 16, fontWeight: '600' },
  chip: {
    flexDirection: 'row', alignItems: 'center', paddingHorizontal: 14, height: 38, borderRadius: radius.pill,
    borderWidth: 1, borderColor: colors.border, marginRight: space.sm, marginBottom: space.sm, backgroundColor: colors.bg,
  },
  chipSelected: { backgroundColor: colors.text, borderColor: colors.text },
  chipText: { fontSize: 14, fontWeight: '500', color: colors.text },
  label: { ...type.smallStrong, marginBottom: 6 },
  input: {
    borderWidth: 1, borderColor: colors.border, borderRadius: radius.md, paddingHorizontal: space.lg, paddingVertical: 14,
    fontSize: 16, color: colors.text, backgroundColor: colors.bg,
  },
  error: { color: colors.danger, fontSize: 13, marginTop: 6 },
  hint: { ...type.caption, marginTop: 6 },
  section: { paddingVertical: space.xl, borderBottomWidth: StyleSheet.hairlineWidth, borderBottomColor: colors.hairline },
  checkRow: { flexDirection: 'row', alignItems: 'flex-start', marginBottom: space.md },
  checkbox: {
    width: 22, height: 22, borderRadius: 6, borderWidth: 1.5, borderColor: colors.textMuted, marginRight: space.md,
    alignItems: 'center', justifyContent: 'center', marginTop: 1,
  },
});
