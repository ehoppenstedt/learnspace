import Constants from 'expo-constants';

/** API base URL: EXPO_PUBLIC_API_URL wins, then app.json "extra.apiUrl". */
export const API_URL: string =
  process.env.EXPO_PUBLIC_API_URL ?? (Constants.expoConfig?.extra?.apiUrl as string | undefined) ?? 'http://localhost:8000/api/v1';

export const GOOGLE_WEB_CLIENT_ID: string | undefined =
  process.env.EXPO_PUBLIC_GOOGLE_WEB_CLIENT_ID ?? (Constants.expoConfig?.extra?.googleWebClientId as string | undefined);
export const GOOGLE_IOS_CLIENT_ID: string | undefined =
  process.env.EXPO_PUBLIC_GOOGLE_IOS_CLIENT_ID ?? (Constants.expoConfig?.extra?.googleIosClientId as string | undefined);
