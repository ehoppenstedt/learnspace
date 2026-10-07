// Web preview only (development). Native builds use tokenStore.ts (Keychain/Keystore).
const ACCESS = 'ls.access';
const REFRESH = 'ls.refresh';

export const tokenStore = {
  async getAccess(): Promise<string | null> {
    return globalThis.localStorage?.getItem(ACCESS) ?? null;
  },
  async getRefresh(): Promise<string | null> {
    return globalThis.localStorage?.getItem(REFRESH) ?? null;
  },
  async set(access: string, refresh: string): Promise<void> {
    globalThis.localStorage?.setItem(ACCESS, access);
    globalThis.localStorage?.setItem(REFRESH, refresh);
  },
  async clear(): Promise<void> {
    globalThis.localStorage?.removeItem(ACCESS);
    globalThis.localStorage?.removeItem(REFRESH);
  },
};
