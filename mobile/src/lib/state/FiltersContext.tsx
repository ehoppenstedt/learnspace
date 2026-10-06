import AsyncStorage from '@react-native-async-storage/async-storage';
import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState, type ReactNode } from 'react';

import { api } from '../api/client';
import { useAuth } from '../auth/AuthContext';
import { DEFAULT_FILTERS, sanitizeFilters, type Filters } from '../utils/filters';

const KEY = 'ls.filters';

type FiltersState = {
  filters: Filters;
  setFilters: (f: Filters) => void;
  query: string;
  setQuery: (q: string) => void;
};

const FiltersContext = createContext<FiltersState | null>(null);

/**
 * Guests: filters persist on the device. Logged in: they persist to the profile
 * (server wins on login, so the same filters follow the user across devices).
 */
export function FiltersProvider({ children }: { children: ReactNode }) {
  const { isLoggedIn } = useAuth();
  const [filters, setLocal] = useState<Filters>(DEFAULT_FILTERS);
  const [query, setQuery] = useState('');
  const loadedFor = useRef<'guest' | 'user' | null>(null);

  useEffect(() => {
    const mode = isLoggedIn ? 'user' : 'guest';
    if (loadedFor.current === mode) return;
    loadedFor.current = mode;
    (async () => {
      if (isLoggedIn) {
        try {
          const server = await api<Record<string, unknown>>('/me/filters');
          if (server && Object.keys(server).length) {
            setLocal(sanitizeFilters(server));
            return;
          }
          // First login: promote the guest's local filters to the profile.
          const local = await AsyncStorage.getItem(KEY);
          if (local) await api('/me/filters', { method: 'PUT', body: sanitizeFilters(JSON.parse(local)) });
        } catch {
          // keep current filters
        }
      } else {
        const local = await AsyncStorage.getItem(KEY).catch(() => null);
        if (local) setLocal(sanitizeFilters(JSON.parse(local)));
      }
    })();
  }, [isLoggedIn]);

  const setFilters = useCallback(
    (next: Filters) => {
      setLocal(next);
      AsyncStorage.setItem(KEY, JSON.stringify(next)).catch(() => undefined);
      if (isLoggedIn) api('/me/filters', { method: 'PUT', body: next }).catch(() => undefined);
    },
    [isLoggedIn],
  );

  const value = useMemo(() => ({ filters, setFilters, query, setQuery }), [filters, setFilters, query]);
  return <FiltersContext.Provider value={value}>{children}</FiltersContext.Provider>;
}

export function useFilters(): FiltersState {
  const ctx = useContext(FiltersContext);
  if (!ctx) throw new Error('useFilters must be used inside FiltersProvider');
  return ctx;
}
