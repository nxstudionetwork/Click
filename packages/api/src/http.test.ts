import { afterEach, describe, expect, it, vi } from 'vitest';
import { ApiError, createHttpClient } from './http';

const json = (status: number, body: unknown) =>
  new Response(body === null ? null : JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } });

function client(token: string | null, refresh = vi.fn(async () => null as string | null)) {
  return { http: createHttpClient({ baseUrl: '/api/v1', clientId: 'test', getAccessToken: () => token, refreshAccessToken: refresh }), refresh };
}

afterEach(() => vi.restoreAllMocks());

describe('http client', () => {
  it('sends auth + client headers and builds query strings without empty values', async () => {
    const fetchMock = vi.spyOn(globalThis, 'fetch').mockResolvedValue(json(200, { ok: true }));
    await client('tok').http.request('/stores', { query: { type: 'restaurant', search: '', page: 2 } });
    const [url, init] = fetchMock.mock.calls[0]!;
    expect(url).toBe('/api/v1/stores?type=restaurant&page=2');
    expect((init!.headers as Record<string, string>).Authorization).toBe('Bearer tok');
    expect((init!.headers as Record<string, string>)['X-Click-Client']).toBe('test');
  });

  it('parses the Click error envelope', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      json(400, { error: { code: 'validation_error', message: 'bad', details: { email: ['Taken.'] } } }),
    );
    const err = (await client(null).http.request('/x').catch((e: unknown) => e)) as ApiError;
    expect(err).toBeInstanceOf(ApiError);
    expect(err.code).toBe('validation_error');
    expect(err.fieldErrors()).toEqual({ email: 'Taken.' });
  });

  it('refreshes once on 401 and retries', async () => {
    const fetchMock = vi.spyOn(globalThis, 'fetch')
      .mockResolvedValueOnce(json(401, { error: { code: 'not_authenticated', message: 'x' } }))
      .mockResolvedValueOnce(json(200, { id: 1 }));
    const { http, refresh } = client('old', vi.fn(async () => 'new'));
    await expect(http.request('/me')).resolves.toEqual({ id: 1 });
    expect(refresh).toHaveBeenCalledTimes(1);
    expect((fetchMock.mock.calls[1]![1]!.headers as Record<string, string>).Authorization).toBe('Bearer new');
  });

  it('maps network failures to a friendly ApiError', async () => {
    vi.spyOn(globalThis, 'fetch').mockRejectedValue(new TypeError('Failed to fetch'));
    const err = (await client(null).http.request('/x').catch((e: unknown) => e)) as ApiError;
    expect(err.code).toBe('network_error');
  });
});
