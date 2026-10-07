import { Ionicons } from '@expo/vector-icons';
import { Pressable, Text, View } from 'react-native';

import { colors, space, type } from '@/theme/tokens';

/** Read-only stars, e.g. on a review card. */
export function Stars({ value, size = 14 }: { value: number; size?: number }) {
  return (
    <View style={{ flexDirection: 'row' }} accessibilityLabel={`${value}/5`}>
      {[1, 2, 3, 4, 5].map((n) => (
        <Ionicons key={n} name={n <= Math.round(value) ? 'star' : 'star-outline'} size={size} color={n <= Math.round(value) ? colors.star : colors.border} />
      ))}
    </View>
  );
}

/** One tappable 1–5 row with its label: "Overall ★★★★☆". */
export function StarInput({ label, hint, value, onChange }: { label: string; hint?: string; value: number; onChange: (v: number) => void }) {
  return (
    <View style={{ paddingVertical: space.md }}>
      <Text style={type.bodyStrong}>{label}</Text>
      {hint ? <Text style={type.caption}>{hint}</Text> : null}
      <View style={{ flexDirection: 'row', marginTop: space.sm, gap: space.sm }}>
        {[1, 2, 3, 4, 5].map((n) => (
          <Pressable key={n} onPress={() => onChange(n)} hitSlop={6} accessibilityRole="button"
            accessibilityLabel={`${label}: ${n}`} accessibilityState={{ selected: value === n }}>
            <Ionicons name={n <= value ? 'star' : 'star-outline'} size={36} color={n <= value ? colors.star : colors.textSubtle} />
          </Pressable>
        ))}
      </View>
    </View>
  );
}

/** Horizontal bar for an average sub-rating (learning, host, space). */
export function RatingBar({ label, value }: { label: string; value: string | null }) {
  if (value === null) return null;
  const pct = Math.max(0, Math.min(1, Number(value) / 5));
  return (
    <View style={{ flexDirection: 'row', alignItems: 'center', marginBottom: space.sm }}>
      <Text style={[type.small, { width: 120, color: colors.text }]}>{label}</Text>
      <View style={{ flex: 1, height: 4, borderRadius: 2, backgroundColor: colors.border, marginHorizontal: space.md }}>
        <View style={{ width: `${pct * 100}%`, height: 4, borderRadius: 2, backgroundColor: colors.text }} />
      </View>
      <Text style={type.smallStrong}>{Number(value).toFixed(1)}</Text>
    </View>
  );
}
