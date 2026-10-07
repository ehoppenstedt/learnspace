/**
 * Web stub so the app can be previewed in a browser during development.
 * react-native-maps has no web implementation; production targets are iOS and Android.
 */
import type { ReactNode } from 'react';
import { Text, View, type StyleProp, type ViewStyle } from 'react-native';

export type Region = { latitude: number; longitude: number; latitudeDelta: number; longitudeDelta: number };

export function MapView({ style, children }: { style?: StyleProp<ViewStyle>; children?: ReactNode; [key: string]: unknown }) {
  return (
    <View style={[{ backgroundColor: '#E8EEF1', alignItems: 'center', justifyContent: 'center' }, style]}>
      <Text style={{ color: '#6A6A6A' }}>Map preview (native only)</Text>
      {children}
    </View>
  );
}

export function Marker(_: { children?: ReactNode; [key: string]: unknown }) {
  return null;
}

export function Circle(_: Record<string, unknown>) {
  return null;
}
