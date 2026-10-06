import { Ionicons } from '@expo/vector-icons';
import { router } from 'expo-router';
import { useTranslation } from 'react-i18next';
import { Pressable, ScrollView, StyleSheet, Text, TextInput, View } from 'react-native';

import type { Category } from '@/lib/api/types';
import { useFilters } from '@/lib/state/FiltersContext';
import { activeFilterCount } from '@/lib/utils/filters';
import { colors, radius, shadow, space } from '@/theme/tokens';

/** Search pill with the filter button on its right edge, "+" menu top-right, and a category strip. */
export function SearchHeader({ categories, placeLabel }: { categories: Category[]; placeLabel: string }) {
  const { t } = useTranslation();
  const { filters, setFilters, query, setQuery } = useFilters();
  const count = activeFilterCount(filters);
  const selected = filters.categories;

  const toggleCategory = (slug: string | null) => {
    if (slug === null) return setFilters({ ...filters, categories: [] });
    const next = selected.includes(slug) ? selected.filter((s) => s !== slug) : [...selected, slug];
    setFilters({ ...filters, categories: next });
  };

  return (
    <View style={styles.wrap}>
      <View style={styles.topRow}>
        <View style={[styles.search, shadow.card]}>
          <Ionicons name="search" size={20} color={colors.text} />
          <View style={{ flex: 1, marginLeft: space.md }}>
            <TextInput
              value={query}
              onChangeText={setQuery}
              placeholder={t('feed.searchPlaceholder')}
              placeholderTextColor={colors.text}
              style={styles.input}
              returnKeyType="search"
              accessibilityLabel={t('feed.searchPlaceholder')}
            />
            <Pressable onPress={() => router.push('/location')} hitSlop={6}>
              <Text style={styles.place} numberOfLines={1}>{placeLabel} ▾</Text>
            </Pressable>
          </View>
          <Pressable
            onPress={() => router.push('/filters')}
            style={[styles.filterBtn, count > 0 && { borderColor: colors.text, borderWidth: 2 }]}
            accessibilityLabel={t('filters.title')}
            hitSlop={6}
          >
            <Ionicons name="options-outline" size={20} color={colors.text} />
            {count > 0 ? (
              <View style={styles.badge}><Text style={styles.badgeText}>{count}</Text></View>
            ) : null}
          </Pressable>
        </View>
        <Pressable onPress={() => router.push('/menu')} style={[styles.plus, shadow.card]} accessibilityLabel="+" hitSlop={6}>
          <Ionicons name="add" size={26} color={colors.text} />
        </Pressable>
      </View>
      <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={styles.cats}>
        <CategoryTab label={t('feed.all')} icon="apps-outline" active={selected.length === 0} onPress={() => toggleCategory(null)} />
        {categories.map((c) => (
          <CategoryTab key={c.slug} label={c.name} icon={c.icon} active={selected.includes(c.slug)} onPress={() => toggleCategory(c.slug)} />
        ))}
      </ScrollView>
    </View>
  );
}

function CategoryTab({ label, icon, active, onPress }: { label: string; icon: string; active: boolean; onPress: () => void }) {
  return (
    <Pressable onPress={onPress} style={[styles.cat, active && styles.catActive]} accessibilityRole="tab" accessibilityState={{ selected: active }}>
      <Ionicons name={icon as never} size={24} color={active ? colors.text : colors.textMuted} />
      <Text style={[styles.catText, active && { color: colors.text, fontWeight: '600' }]} numberOfLines={1}>{label}</Text>
    </Pressable>
  );
}

const styles = StyleSheet.create({
  wrap: { backgroundColor: colors.bg, borderBottomWidth: StyleSheet.hairlineWidth, borderBottomColor: colors.hairline },
  topRow: { flexDirection: 'row', alignItems: 'center', paddingHorizontal: space.xl, paddingTop: space.sm },
  search: {
    flex: 1, flexDirection: 'row', alignItems: 'center', backgroundColor: colors.bg, borderRadius: radius.pill,
    paddingLeft: space.lg, paddingRight: 6, height: 60, borderWidth: StyleSheet.hairlineWidth, borderColor: colors.border,
  },
  input: { fontSize: 15, fontWeight: '600', color: colors.text, padding: 0 },
  place: { fontSize: 12, color: colors.textMuted, marginTop: 2 },
  filterBtn: {
    width: 44, height: 44, borderRadius: 22, borderWidth: 1, borderColor: colors.border, alignItems: 'center', justifyContent: 'center',
  },
  badge: {
    position: 'absolute', top: -2, right: -2, minWidth: 18, height: 18, borderRadius: 9, backgroundColor: colors.text,
    alignItems: 'center', justifyContent: 'center', paddingHorizontal: 4,
  },
  badgeText: { color: colors.white, fontSize: 11, fontWeight: '700' },
  plus: {
    width: 48, height: 48, borderRadius: 24, marginLeft: space.md, backgroundColor: colors.bg, alignItems: 'center',
    justifyContent: 'center', borderWidth: StyleSheet.hairlineWidth, borderColor: colors.border,
  },
  cats: { paddingHorizontal: space.lg, paddingTop: space.lg },
  cat: { alignItems: 'center', marginHorizontal: space.md, paddingBottom: space.md, borderBottomWidth: 2, borderBottomColor: 'transparent', maxWidth: 96 },
  catActive: { borderBottomColor: colors.text },
  catText: { fontSize: 12, color: colors.textMuted, marginTop: 6 },
});
