import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState, type ReactNode } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { ApiError, type PartnerState, type Session, type User } from '@click/api';
import { api, session } from '../lib/api';
import { currentIdToken, firebaseSignOut, isPhoneAuthConfigured } from '../firebase/phoneAuth';
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
  /** Exchange a verified Firebase ID token for a Click session and load the partner. */
  completeSignIn: (idToken: string) => Promise<PartnerState>;
  /** Replace the cached partner state after an onboarding write. */
  setPartnerState: (state: PartnerState) => void;
  logout: () => Promise<void>;
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

  // Restore: 1) Click session cookie (no Firebase download needed), 2) an existing Firebase session.
  useEffect(() => {
    let cancelled = false;
    (async () => {
      setBootError(null);
      try {
        const restored = await api.auth.refresh();
        if (!cancelled) apply(restored);
        return;
      } catch (err) {
        if (isUnreachable(err)) {
          if (!cancelled) { setBootError(OFFLINE); setStatus('signed_out'); }
          return;
        }
      }
      if (isPhoneAuthConfigured()) {
        try {
          const idToken = await currentIdToken();
          if (idToken) {
            const s = await api.auth.firebase(idToken);
            if (!cancelled) apply(s);
            return;
          }
        } catch {
          // Expired/invalid Firebase session: fall through to sign-in.
        }
      }
      if (!cancelled) apply(null);
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
    completeSignIn: async (idToken) => {
      const s = await api.auth.firebase(idToken);
      session.set(s.access);
      const state = await api.partner.me();
      queryClient.setQueryData(PARTNER_QUERY_KEY, state);
      phoneFlow.clear();
      setUser(s.user);
      setStatus('signed_in');
      return state;
    },
    setPartnerState: (state) => queryClient.setQueryData(PARTNER_QUERY_KEY, state),
    logout: async () => {
      signingOut.current = true;
      try {
        await Promise.allSettled([api.auth.logout(), firebaseSignOut()]);
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
