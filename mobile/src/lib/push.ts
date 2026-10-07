import Constants from 'expo-constants';
import * as Device from 'expo-device';
import * as Notifications from 'expo-notifications';
import { router, type Href } from 'expo-router';
import { Platform } from 'react-native';

import { api } from './api/client';

Notifications.setNotificationHandler({
  handleNotification: async () => ({ shouldShowBanner: true, shouldShowList: true, shouldPlaySound: true, shouldSetBadge: false }),
});

/** Registers this phone for push after login. Silent no-op on simulators or without an EAS project id. */
export async function registerForPush(): Promise<void> {
  const projectId = (Constants.expoConfig?.extra?.eas as { projectId?: string } | undefined)?.projectId;
  if (!Device.isDevice || !projectId || Platform.OS === 'web') return;
  const current = await Notifications.getPermissionsAsync();
  const granted = current.granted || (await Notifications.requestPermissionsAsync()).granted;
  if (!granted) return;
  if (Platform.OS === 'android') {
    await Notifications.setNotificationChannelAsync('default', { name: 'default', importance: Notifications.AndroidImportance.DEFAULT });
  }
  const token = await Notifications.getExpoPushTokenAsync({ projectId });
  await api('/me/devices', { method: 'POST', body: { expo_token: token.data, platform: Platform.OS } }).catch(() => undefined);
}

/** Tapping a notification opens the related booking. */
export function listenForNotificationTaps(): () => void {
  const sub = Notifications.addNotificationResponseReceivedListener((response) => {
    const url = response.notification.request.content.data?.url;
    if (typeof url === 'string' && url.startsWith('learnspace://')) {
      router.push(url.replace('learnspace://', '/') as Href);
    }
  });
  return () => sub.remove();
}
