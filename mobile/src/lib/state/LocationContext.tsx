import AsyncStorage from '@react-native-async-storage/async-storage';
import * as Location from 'expo-location';
import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from 'react';

import type { Origin } from '../utils/filters';

const MANUAL_KEY = 'ls.manualArea';
export const CDMX_CENTER = { lat: 19.4326, lng: -99.1332 };

type Permission = 'unknown' | 'granted' | 'denied';

type LocationState = {
  origin: Origin | null;
  permission: Permission;
  resolving: boolean;
  requestGps: () => Promise<boolean>;
  setManualArea: (area: { slug: string; name: string; lat: number; lng: number }) => Promise<void>;
};

const LocationContext = createContext<LocationState | null>(null);

export function LocationProvider({ children }: { children: ReactNode }) {
  const [origin, setOrigin] = useState<Origin | null>(null);
  const [permission, setPermission] = useState<Permission>('unknown');
  const [resolving, setResolving] = useState(true);

  const requestGps = useCallback(async () => {
    setResolving(true);
    try {
      const { status } = await Location.requestForegroundPermissionsAsync();
      if (status !== 'granted') {
        setPermission('denied');
        return false;
      }
      setPermission('granted');
      const last = await Location.getLastKnownPositionAsync({ maxAge: 5 * 60_000 });
      const pos = last ?? (await Location.getCurrentPositionAsync({ accuracy: Location.Accuracy.Balanced }));
      setOrigin({ kind: 'gps', lat: pos.coords.latitude, lng: pos.coords.longitude });
      await AsyncStorage.removeItem(MANUAL_KEY).catch(() => undefined);
      return true;
    } catch {
      setPermission('denied');
      return false;
    } finally {
      setResolving(false);
    }
  }, []);

  const setManualArea = useCallback(async (area: { slug: string; name: string; lat: number; lng: number }) => {
    setOrigin({ kind: 'area', ...area });
    await AsyncStorage.setItem(MANUAL_KEY, JSON.stringify(area)).catch(() => undefined);
  }, []);

  useEffect(() => {
    (async () => {
      // A manually chosen area wins over GPS until the user asks for GPS again.
      const saved = await AsyncStorage.getItem(MANUAL_KEY).catch(() => null);
      if (saved) {
        try {
          setOrigin({ kind: 'area', ...JSON.parse(saved) });
          setResolving(false);
          return;
        } catch {
          // fall through to GPS
        }
      }
      await requestGps();
    })();
  }, [requestGps]);

  const value = useMemo(
    () => ({ origin, permission, resolving, requestGps, setManualArea }),
    [origin, permission, resolving, requestGps, setManualArea],
  );
  return <LocationContext.Provider value={value}>{children}</LocationContext.Provider>;
}

export function useLocation(): LocationState {
  const ctx = useContext(LocationContext);
  if (!ctx) throw new Error('useLocation must be used inside LocationProvider');
  return ctx;
}
