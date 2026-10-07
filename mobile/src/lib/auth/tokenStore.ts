import * as SecureStore from 'expo-secure-store';

const ACCESS = 'ls.access';
const REFRESH = 'ls.refresh';

// Tokens live in the OS keychain/keystore, never in AsyncStorage.
let accessCache: string | null | undefined;

export const tokenStore = {
  async getAccess(): Promise<string | null> {
    if (accessCache === undefined) accessCache = await SecureStore.getItemAsync(ACCESS);
    return accessCache;
  },
  async getRefresh(): Promise<string | null> {
    return SecureStore.getItemAsync(REFRESH);
  },
  async set(access: string, refresh: string): Promise<void> {
    accessCache = access;
    await SecureStore.setItemAsync(ACCESS, access);
    await SecureStore.setItemAsync(REFRESH, refresh);
  },
  async clear(): Promise<void> {
    accessCache = null;
    await SecureStore.deleteItemAsync(ACCESS);
    await SecureStore.deleteItemAsync(REFRESH);
  },
};
