import { useQuery, useQueryClient } from '@tanstack/react-query';
import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from 'react';

import { api, setOnSessionExpired } from '../api/client';
import type { Me, Session } from '../api/types';
import { tokenStore } from './tokenStore';

type AuthState = {
  ready: boolean;
  isLoggedIn: boolean;
  me: Me | undefined;
  signIn: (session: Session) => Promise<void>;
  signOut: () => Promise<void>;
  refreshMe: () => Promise<unknown>;
};

const AuthContext = createContext<AuthState | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const queryClient = useQueryClient();
  const [ready, setReady] = useState(false);
  const [isLoggedIn, setLoggedIn] = useState(false);

  useEffect(() => {
    tokenStore
      .getAccess()
      .catch(() => null)
      .then((token) => {
        setLoggedIn(Boolean(token));
        setReady(true);
      });
  }, []);

  const meQuery = useQuery({
    queryKey: ['me'],
    queryFn: () => api<Me>('/me'),
    enabled: isLoggedIn,
    staleTime: 60_000,
  });

  const signOut = useCallback(async () => {
    const refresh = await tokenStore.getRefresh();
    if (refresh) api('/auth/logout', { method: 'POST', body: { refresh }, auth: false }).catch(() => undefined);
    await tokenStore.clear();
    setLoggedIn(false);
    queryClient.removeQueries({ queryKey: ['me'] });
    queryClient.removeQueries({ queryKey: ['provider'] });
  }, [queryClient]);

  useEffect(() => {
    setOnSessionExpired(() => {
      tokenStore.clear().then(() => setLoggedIn(false));
    });
  }, []);

  const signIn = useCallback(
    async (session: Session) => {
      await tokenStore.set(session.access, session.refresh);
      queryClient.setQueryData(['me'], session.user);
      setLoggedIn(true);
    },
    [queryClient],
  );

  const value = useMemo<AuthState>(
    () => ({ ready, isLoggedIn, me: meQuery.data, signIn, signOut, refreshMe: meQuery.refetch }),
    [ready, isLoggedIn, meQuery.data, meQuery.refetch, signIn, signOut],
  );
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthState {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error('useAuth must be used inside AuthProvider');
  return ctx;
}
