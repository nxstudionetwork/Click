import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState, type ReactNode } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { ApiError, type OSAuthenticated, type OSContext } from '@click/api';
import { api, restoreSession, session } from '../lib/api';

/**
 * booting     → restoring from the OS refresh cookie
 * signed_out  → login screen
 * expired     → the server ended the session (idle timeout, revoked, suspended): explain, then sign in again
 * signed_in   → context (organization, roles, permissions, navigation) loaded from /os/me/context
 */
export type SessionStatus = 'booting' | 'signed_out' | 'expired' | 'signed_in';
export const CONTEXT_KEY = ['os', 'context'] as const;

export interface SessionValue {
  status: SessionStatus;
  bootError: string | null;
  retryBoot: () => void;
  context: OSContext | undefined;
  contextError: unknown;
  refetchContext: () => void;
  setContext: (ctx: OSContext) => void;
  completeSignIn: (result: OSAuthenticated) => Promise<void>;
  logout: () => Promise<void>;
}

export const SessionContext = createContext<SessionValue | null>(null);

export function OSSessionProvider({ children }: { children: ReactNode }) {
  const qc = useQueryClient();
  const [status, setStatus] = useState<SessionStatus>('booting');
  const [bootError, setBootError] = useState<string | null>(null);
  const [attempt, setAttempt] = useState(0);
  const signingOut = useRef(false);
  const signedIn = useRef(false);

  useEffect(() => {
    let cancelled = false;
    setBootError(null);
    restoreSession()
      .then(() => { if (!cancelled) setStatus('signed_in'); })
      .catch((err) => {
        if (cancelled) return;
        if (err instanceof ApiError && (err.status === 0 || err.status >= 500)) {
          setBootError('We can’t reach Click right now. Check your connection and try again.');
        }
        session.set(null);
        setStatus('signed_out');
      });
    return () => { cancelled = true; };
  }, [attempt]);

  useEffect(() => { signedIn.current = status === 'signed_in'; }, [status]);

  // A refresh failing mid-session (idle timeout, revoked elsewhere, suspended) lands on "session ended".
  useEffect(() => session.subscribe((token) => {
    if (!token && !signingOut.current && signedIn.current) {
      qc.clear();
      setStatus('expired');
    }
  }), [qc]);

  const contextQuery = useQuery({
    queryKey: CONTEXT_KEY, queryFn: api.me.context, enabled: status === 'signed_in', staleTime: 60_000, refetchOnWindowFocus: true,
  });

  const completeSignIn = useCallback(async (result: OSAuthenticated) => {
    session.set(result.access);
    const ctx = await api.me.context();
    qc.setQueryData(CONTEXT_KEY, ctx);
    setStatus('signed_in');
  }, [qc]);

  const logout = useCallback(async () => {
    signingOut.current = true;
    try {
      await api.auth.logout().catch(() => undefined);
    } finally {
      session.set(null);
      qc.clear();
      setStatus('signed_out');
      signingOut.current = false;
    }
  }, [qc]);

  const value = useMemo<SessionValue>(() => ({
    status,
    bootError,
    retryBoot: () => { setStatus('booting'); setAttempt((n) => n + 1); },
    context: status === 'signed_in' ? contextQuery.data : undefined,
    contextError: contextQuery.error,
    refetchContext: () => { void contextQuery.refetch(); },
    setContext: (ctx) => qc.setQueryData(CONTEXT_KEY, ctx),
    completeSignIn,
    logout,
  }), [status, bootError, contextQuery, qc, completeSignIn, logout]);

  return <SessionContext.Provider value={value}>{children}</SessionContext.Provider>;
}

export function useOSSession(): SessionValue {
  const v = useContext(SessionContext);
  if (!v) throw new Error('useOSSession must be used inside <OSSessionProvider>');
  return v;
}

/** The loaded context. Only valid under the signed-in shell. */
export function useOS(): OSContext {
  const { context } = useOSSession();
  if (!context) throw new Error('Business OS context not loaded');
  return context;
}
