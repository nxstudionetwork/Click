import { authApi } from './endpoints';
import { createHttpClient, type HttpClient } from './http';
import type { Session } from './types';

/**
 * Shared Click session wiring for every app.
 *
 * The access token lives in memory only (never localStorage) to limit XSS impact.
 * The refresh token is an httpOnly cookie the browser sends to /api/v1/auth/.
 */
export interface SessionStore {
  get(): string | null;
  set(token: string | null): void;
  subscribe(fn: (token: string | null) => void): () => void;
}

export interface ClickClient {
  http: HttpClient;
  session: SessionStore;
  /** Single-flight refresh: concurrent 401s share one refresh request. Resolves null when signed out. */
  refreshSession(): Promise<Session | null>;
  /**
   * The same single refresh request, but rejecting on failure so the caller can tell "signed out" from "offline".
   * Refresh tokens rotate, so every refresh in an app must share one request or the second looks like token reuse.
   */
  restoreSession(): Promise<Session>;
}

export function createClickClient(options: { baseUrl: string; clientId: string }): ClickClient {
  let accessToken: string | null = null;
  let refreshInFlight: Promise<Session | null> | null = null;
  const listeners = new Set<(token: string | null) => void>();

  const session: SessionStore = {
    get: () => accessToken,
    set(token) {
      accessToken = token;
      listeners.forEach((fn) => fn(token));
    },
    subscribe(fn) {
      listeners.add(fn);
      return () => {
        listeners.delete(fn);
      };
    },
  };

  const http = createHttpClient({
    ...options,
    getAccessToken: session.get,
    refreshAccessToken: () => refreshSession().then((s) => s?.access ?? null),
  });
  const auth = authApi(http);

  let rawInFlight: Promise<Session> | null = null;
  function rawRefresh(): Promise<Session> {
    rawInFlight ??= auth.refresh().finally(() => {
      rawInFlight = null;
    });
    return rawInFlight;
  }

  function restoreSession(): Promise<Session> {
    return rawRefresh().then((s) => {
      session.set(s.access);
      return s;
    });
  }

  function refreshSession(): Promise<Session | null> {
    refreshInFlight ??= rawRefresh()
      .then(
        (s) => {
          session.set(s.access);
          return s;
        },
        () => {
          session.set(null);
          return null;
        },
      )
      .finally(() => {
        refreshInFlight = null;
      });
    return refreshInFlight;
  }

  return { http, session, refreshSession, restoreSession };
}
