import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import type { Session, User } from '@click/api';
import { api, refreshSession, session } from '../lib/api';

type Status = 'loading' | 'authenticated' | 'anonymous';

interface AuthValue {
  status: Status;
  user: User | null;
  login: (email: string, password: string) => Promise<void>;
  register: (input: { email: string; password: string; fullName: string }) => Promise<void>;
  logout: () => Promise<void>;
  /** DEVELOPMENT ONLY. */
  devLogin: () => Promise<void>;
  /** Starts a Click session returned by phone sign-in (identity exchange/signup). */
  startSession: (session: Session) => void;
  /** Replace the cached user after a profile update. */
  refreshUser: (user: User) => void;
}

const AuthContext = createContext<AuthValue | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [status, setStatus] = useState<Status>('loading');
  const queryClient = useQueryClient();

  const apply = useCallback((s: Session | null) => {
    session.set(s?.access ?? null);
    setUser(s?.user ?? null);
    setStatus(s ? 'authenticated' : 'anonymous');
  }, []);

  // Restore the session from the httpOnly refresh cookie on load.
  useEffect(() => {
    refreshSession().then(apply);
  }, [apply]);

  // If a refresh fails mid-session (expired/revoked), drop to anonymous.
  useEffect(() => session.subscribe((t) => { if (!t) { setUser(null); setStatus('anonymous'); } }), []);

  const value = useMemo<AuthValue>(() => ({
    status,
    user,
    login: async (email, password) => apply(await api.auth.login({ email, password })),
    register: async (input) => apply(await api.auth.register(input)),
    logout: async () => {
      await api.auth.logout().catch(() => undefined);
      apply(null);
      queryClient.removeQueries({ queryKey: ['customer'] });
    },
    refreshUser: setUser,
    devLogin: async () => apply(await api.auth.devLogin()),
    startSession: (s) => apply(s),
  }), [status, user, apply, queryClient]);

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthValue {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error('useAuth must be used inside <AuthProvider>');
  return ctx;
}
