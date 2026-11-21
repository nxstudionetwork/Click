import { ApiError, createClickClient, osApi, osHomeApi, osModuleApi, peopleApi } from '@click/api';

/**
 * Business OS has its own session (separate cookie `click_os_refresh`, refreshed at /os/auth/refresh) so being signed
 * in to the customer or partner app never signs anyone in here, and vice versa.
 */
const client = createClickClient({
  baseUrl: import.meta.env.VITE_API_BASE_URL ?? '/api/v1',
  clientId: 'business-os',
  refresh: (http) => osApi(http).auth.refresh(),
});

export const { http, session, refreshSession, restoreSession } = client;
export const api = osApi(http);
export const home = osHomeApi(http);
export const people = peopleApi(http);
export const access = osModuleApi(http, '/os/access');
export const finance = osModuleApi(http, '/os/finance');
export const procurement = osModuleApi(http, '/os/procurement');

export function apiMessage(err: unknown): string {
  if (err instanceof ApiError) return err.message;
  if (err instanceof Error) return err.message;
  return 'Something went wrong. Please try again.';
}

export function errorCode(err: unknown): string | null {
  return err instanceof ApiError ? err.code : null;
}

export function fieldErrors(err: unknown): Record<string, string> {
  return err instanceof ApiError ? err.fieldErrors() : {};
}
