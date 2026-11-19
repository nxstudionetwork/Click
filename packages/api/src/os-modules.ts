/**
 * Click Business OS — one small client shape for module workspaces (Identity & Access, Finance, Procurement, …).
 * Every module exposes the same REST conventions under /os/<module>/…, so screens share one typed helper instead of
 * a hand-written client per module. The server decides what each caller may see; nothing here filters data.
 */
import type { HttpClient, Query } from './http';
import type { Paginated } from './types';

type Any = any; // eslint-disable-line @typescript-eslint/no-explicit-any

export interface OSNavSection { key: string; label: string; items: { key: string; label: string; path: string }[] }

export const osModuleApi = (http: HttpClient, base: string) => {
  const url = (path: string) => `${base}/${path.replace(/^\//, '')}`.replace(/\/$/, '');
  return {
    base,
    nav: () => http.request<{ sections: OSNavSection[] }>(url('nav')),
    get: <T = Any>(path: string, query: Query = {}) => http.request<T>(url(path), { query }),
    list: <T = Any>(path: string, query: Query = {}) => http.request<Paginated<T> & Any>(url(path), { query }),
    post: <T = Any>(path: string, body: Record<string, unknown> | FormData = {}) => http.request<T>(url(path), { method: 'POST', body }),
    patch: <T = Any>(path: string, body: Record<string, unknown> = {}) => http.request<T>(url(path), { method: 'PATCH', body }),
    del: (path: string) => http.request<void>(url(path), { method: 'DELETE' }),
    blob: (path: string, query: Query = {}) => {
      const qs = new URLSearchParams(Object.entries(query).filter(([, v]) => v !== undefined && v !== null && v !== '')
        .map(([k, v]) => [k, String(v)]));
      return http.blob!(`${url(path)}${qs.toString() ? `?${qs}` : ''}`);
    },
  };
};
export type OSModuleApi = ReturnType<typeof osModuleApi>;
