import type { ApiErrorBody } from './types';

export class ApiError extends Error {
  readonly status: number;
  readonly code: string;
  readonly details?: Record<string, unknown>;

  constructor(status: number, body: ApiErrorBody) {
    super(body.message);
    this.name = 'ApiError';
    this.status = status;
    this.code = body.code;
    this.details = body.details;
  }

  /** Field-level validation messages, e.g. { email: ["..."] }. */
  fieldErrors(): Record<string, string> {
    if (this.code !== 'validation_error' || !this.details) return {};
    return Object.fromEntries(
      Object.entries(this.details).map(([k, v]) => [k, Array.isArray(v) ? String(v[0]) : String(v)]),
    );
  }
}

export interface HttpClientOptions {
  baseUrl: string;
  /** Identifies the calling app (customer-web, partner-web, business-os). */
  clientId: string;
  getAccessToken: () => string | null;
  /** Called once on 401; should refresh and return a new token or null. */
  refreshAccessToken: () => Promise<string | null>;
}

export type Query = Record<string, string | number | boolean | undefined>;

export interface RequestOptions {
  method?: 'GET' | 'POST' | 'PATCH' | 'DELETE';
  body?: unknown;
  query?: Query;
  auth?: boolean;
  signal?: AbortSignal;
}

export interface HttpClient {
  request<T>(path: string, opts?: RequestOptions): Promise<T>;
  clientId: string;
  baseUrl: string;
}

function buildUrl(baseUrl: string, path: string, query?: Query): string {
  const qs = new URLSearchParams();
  for (const [k, v] of Object.entries(query ?? {})) if (v !== undefined && v !== '') qs.set(k, String(v));
  const s = qs.toString();
  return `${baseUrl}${path}${s ? `?${s}` : ''}`;
}

export function createHttpClient(options: HttpClientOptions): HttpClient {
  const { baseUrl, clientId } = options;

  async function send(path: string, opts: RequestOptions, token: string | null): Promise<Response> {
    const headers: Record<string, string> = { Accept: 'application/json', 'X-Click-Client': clientId };
    if (opts.body !== undefined) headers['Content-Type'] = 'application/json';
    if (token) headers.Authorization = `Bearer ${token}`;
    return fetch(buildUrl(baseUrl, path, opts.query), {
      method: opts.method ?? 'GET',
      headers,
      body: opts.body === undefined ? undefined : JSON.stringify(opts.body),
      credentials: 'include',
      signal: opts.signal,
    });
  }

  async function request<T>(path: string, opts: RequestOptions = {}): Promise<T> {
    const useAuth = opts.auth ?? true;
    let res: Response;
    try {
      res = await send(path, opts, useAuth ? options.getAccessToken() : null);
      if (res.status === 401 && useAuth) {
        const fresh = await options.refreshAccessToken();
        if (fresh) res = await send(path, opts, fresh);
      }
    } catch (err) {
      if ((err as Error).name === 'AbortError') throw err;
      throw new ApiError(0, { code: 'network_error', message: 'Can’t reach Click right now. Check your connection.' });
    }
    if (res.status === 204) return undefined as T;
    const data = await res.json().catch(() => null);
    if (!res.ok) {
      const body: ApiErrorBody = data?.error ?? { code: 'http_error', message: `Request failed (${res.status}).` };
      throw new ApiError(res.status, body);
    }
    return data as T;
  }

  return { request, clientId, baseUrl };
}
