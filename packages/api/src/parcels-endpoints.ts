import type { HttpClient } from './http';
import type {
  ParcelBookInput, ParcelDetail, ParcelDraft, ParcelOptions, ParcelQuote, ParcelQuoteInput, ParcelSummary, SavedRecipient, SharedParcel,
} from './parcels';

/** Click. Parcel: options (public), quote, booking, tracking, cancellation, repeat, sharing and saved recipients. */
export const parcelsApi = (http: HttpClient) => ({
  options: (at?: { lat: number; lng: number } | null) => http.request<ParcelOptions>('/parcels/options', { query: { lat: at?.lat, lng: at?.lng } }),
  shared: (token: string) => http.request<SharedParcel>(`/parcels/shared/${encodeURIComponent(token)}`),
  quote: (input: ParcelQuoteInput) => http.request<ParcelQuote>('/customer/parcels/quote', { method: 'POST', body: input }),
  book: (input: ParcelBookInput) => http.request<ParcelDetail>('/customer/parcels', { method: 'POST', body: input }),
  list: (when?: 'active' | 'past') => http.request<{ results: ParcelSummary[] }>('/customer/parcels', { query: { when } }),
  get: (id: string) => http.request<ParcelDetail>(`/customer/parcels/${id}`),
  track: (ref: string) => http.request<{ id: string; number: string }>('/customer/parcels/track', { query: { ref } }),
  cancel: (id: string, reason: string) => http.request<ParcelDetail>(`/customer/parcels/${id}/cancel`, { method: 'POST', body: { reason } }),
  repeat: (id: string) => http.request<ParcelDraft>(`/customer/parcels/${id}/repeat`),
  share: (id: string) => http.request<{ token: string; expiresInDays: number }>(`/customer/parcels/${id}/share`, { method: 'POST', body: {} }),
  recipients: {
    list: () => http.request<SavedRecipient[]>('/customer/parcels/recipients'),
    create: (r: Partial<SavedRecipient>) => http.request<SavedRecipient>('/customer/parcels/recipients', { method: 'POST', body: r }),
    update: (id: string, r: Partial<SavedRecipient>) => http.request<SavedRecipient>(`/customer/parcels/recipients/${id}`, { method: 'PATCH', body: r }),
    remove: (id: string) => http.request<void>(`/customer/parcels/recipients/${id}`, { method: 'DELETE' }),
  },
});
