import { Image } from 'expo-image';
import { useState } from 'react';
import { FlatList, StyleSheet, View, type NativeScrollEvent, type NativeSyntheticEvent } from 'react-native';

import type { Media } from '@/lib/api/types';
import { colors } from '@/theme/tokens';

type Props = {
  media: Media[];
  width: number;
  height: number;
  rounded?: number;
  size?: 'w400' | 'w800' | 'w1600';
  onPressItem?: () => void;
};

/** Swipeable, paged photo strip. Shows the poster for videos; the dominant color fills while loading. */
export function PhotoCarousel({ media, width, height, rounded = 0, size = 'w800' }: Props) {
  const [index, setIndex] = useState(0);
  const onScroll = (e: NativeSyntheticEvent<NativeScrollEvent>) => {
    const i = Math.round(e.nativeEvent.contentOffset.x / width);
    if (i !== index) setIndex(i);
  };
  const items = media.length ? media : [{ id: 'placeholder', kind: 'image', color: colors.surface, width: null, height: null } as Media];
  return (
    <View style={{ width, height, borderRadius: rounded, overflow: 'hidden', backgroundColor: items[0].color }}>
      <FlatList
        data={items}
        keyExtractor={(m) => m.id}
        horizontal
        pagingEnabled
        showsHorizontalScrollIndicator={false}
        onScroll={onScroll}
        scrollEventThrottle={32}
        renderItem={({ item }) => (
          <Image
            source={item.kind === 'video' ? item.poster_url ?? undefined : item.urls?.[size]}
            style={{ width, height, backgroundColor: item.color }}
            contentFit="cover"
            transition={200}
            recyclingKey={item.id}
            accessibilityIgnoresInvertColors
          />
        )}
      />
      {items.length > 1 ? (
        <View style={styles.dots} pointerEvents="none">
          {items.slice(0, 5).map((m, i) => (
            <View key={m.id} style={[styles.dot, i === Math.min(index, 4) && styles.dotActive]} />
          ))}
        </View>
      ) : null}
    </View>
  );
}

const styles = StyleSheet.create({
  dots: { position: 'absolute', bottom: 12, alignSelf: 'center', flexDirection: 'row' },
  dot: { width: 6, height: 6, borderRadius: 3, marginHorizontal: 3, backgroundColor: 'rgba(255,255,255,0.6)' },
  dotActive: { backgroundColor: colors.white, transform: [{ scale: 1.2 }] },
});
