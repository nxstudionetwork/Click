import { authApi, catalogApi, createHttpClient, customerApi, eventsApi, storesApi, type Session } from '@click/api';

/**
 * Access token lives in memory only (never localStorage) to limit XSS impact.
 * The refresh token is an httpOnly cookie the browser sends to /api/v1/auth/.
 */
let accessToken: string | null = null;
let refreshInFlight: Promise<Session | null> | null = null;
const listeners = new Set<(token: string | null) => void>();

export const session = {
  get: () => accessToken,
  set(token: string | null) {
    accessToken = token;
    listeners.forEach((fn) => fn(token));
  },
  subscribe(fn: (token: string | null) => void) {
    listeners.add(fn);
    return () => {
      listeners.delete(fn);
    };
  },
};

export const http = createHttpClient({
  baseUrl: import.meta.env.VITE_API_BASE_URL ?? '/api/v1',
  clientId: 'customer-web',
  getAccessToken: session.get,
  refreshAccessToken: () => refreshSession().then((s) => s?.access ?? null),
});

export const api = {
  auth: authApi(http),
  stores: storesApi(http),
  catalog: catalogApi(http),
  events: eventsApi(http),
  customer: customerApi(http),
};

/** Single-flight refresh: concurrent 401s share one refresh request. */
export function refreshSession(): Promise<Session | null> {
  refreshInFlight ??= api.auth
    .refresh()
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
