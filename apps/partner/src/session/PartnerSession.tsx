import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState, type ReactNode } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { ApiError, type PartnerState, type Session, type User } from '@click/api';
import { api, session } from '../lib/api';
import { phoneAuth } from '@click/phone-auth';
import { phoneFlow } from './phoneFlow';

type Status = 'booting' | 'signed_out' | 'signed_in';

export const PARTNER_QUERY_KEY = ['partner', 'me'] as const;

interface PartnerSessionValue {
  status: Status;
  user: User | null;
  /** Set when Click itself could not be reached while restoring the session. */
  bootError: string | null;
  retryBoot: () => void;
  partner: {
    state: PartnerState | undefined;
    isLoading: boolean;
    error: unknown;
    refetch: () => void;
  };
  /** Exchange a verified phone credential for a Click session (creating the account if new) and load the partner. */
  completeSignIn: (credential: { provider: string; token: string }) => Promise<PartnerState>;
  /** Replace the cached partner state after an onboarding write. */
  setPartnerState: (state: PartnerState) => void;
  logout: () => Promise<void>;
  /** DEVELOPMENT ONLY: sign in as a seeded test partner (the endpoint is 404 outside DEBUG). */
  devSignIn: (code: string) => Promise<PartnerState>;
}

const Ctx = createContext<PartnerSessionValue | null>(null);
const OFFLINE = 'We can’t reach Click right now. Check your connection and try again.';

function isUnreachable(err: unknown) {
  return err instanceof ApiError && (err.status === 0 || err.status >= 500);
}

export function PartnerSessionProvider({ children }: { children: ReactNode }) {
  const queryClient = useQueryClient();
  const [status, setStatus] = useState<Status>('booting');
  const [user, setUser] = useState<User | null>(null);
  const [bootError, setBootError] = useState<string | null>(null);
  const [bootAttempt, setBootAttempt] = useState(0);
  const signingOut = useRef(false);

  const apply = useCallback((s: Session | null) => {
    session.set(s?.access ?? null);
    setUser(s?.user ?? null);
    setStatus(s ? 'signed_in' : 'signed_out');
  }, []);

  // Restore from the Click session cookie. Firebase is only used during OTP; it keeps no session.
  useEffect(() => {
    let cancelled = false;
    (async () => {
      setBootError(null);
      try {
        const restored = await api.auth.refresh();
        if (!cancelled) apply(restored);
      } catch (err) {
        if (cancelled) return;
        if (isUnreachable(err)) setBootError(OFFLINE);
        apply(null);
      }
    })();
    return () => { cancelled = true; };
  }, [apply, bootAttempt]);

  // If a refresh fails mid-session (expired or revoked), drop to signed out.
  useEffect(() => session.subscribe((token) => {
    if (!token && !signingOut.current) { setUser(null); setStatus((s) => (s === 'booting' ? s : 'signed_out')); }
  }), []);

  const partnerQuery = useQuery({
    queryKey: PARTNER_QUERY_KEY,
    queryFn: () => api.partner.me(),
    enabled: status === 'signed_in',
    staleTime: 60_000,
  });

  const value = useMemo<PartnerSessionValue>(() => ({
    status,
    user,
    bootError,
    retryBoot: () => { setStatus('booting'); setBootAttempt((n) => n + 1); },
    partner: {
      state: status === 'signed_in' ? partnerQuery.data : undefined,
      isLoading: status === 'signed_in' && partnerQuery.isPending,
      error: partnerQuery.error,
      refetch: () => { void partnerQuery.refetch(); },
    },
    completeSignIn: async (credential) => {
      const result = await api.auth.exchangeIdentity(credential);
      const s = result.status === 'authenticated' ? result : await api.auth.partnerSignup(result.signupToken);
      session.set(s.access);
      const state = await api.partner.me();
      queryClient.setQueryData(PARTNER_QUERY_KEY, state);
      phoneFlow.clear();
      setUser(s.user);
      setStatus('signed_in');
      return state;
    },
    setPartnerState: (state) => queryClient.setQueryData(PARTNER_QUERY_KEY, state),
    devSignIn: async (code) => {
      const s = await api.partner.devLogin(code);
      session.set(s.access);
      const state = await api.partner.me();
      queryClient.setQueryData(PARTNER_QUERY_KEY, state);
      setUser(s.user);
      setStatus('signed_in');
      return state;
    },
    logout: async () => {
      signingOut.current = true;
      try {
        await Promise.allSettled([api.auth.logout(), phoneAuth.reset()]);
      } finally {
        phoneFlow.clear();
        session.set(null);
        queryClient.clear();
        setUser(null);
        setStatus('signed_out');
        signingOut.current = false;
      }
    },
  }), [status, user, bootError, partnerQuery, queryClient]);

  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

export function usePartnerSession(): PartnerSessionValue {
  const ctx = useContext(Ctx);
  if (!ctx) throw new Error('usePartnerSession must be used inside <PartnerSessionProvider>');
  return ctx;
}
