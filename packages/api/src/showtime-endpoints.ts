import type { HttpClient } from './http';
import type {
  SeatHold, ShowtimeCinema, ShowtimeHome, ShowtimeQuote, ShowtimeQuoteInput, ShowtimeReview, ShowtimeSearchResult, ShowtimeSuggestions,
  ShowtimeTitleDetail,
} from './showtime';

type At = { lat?: number; lng?: number };

/** Click. Showtime: discovery (public, personal touches when signed in), seat holds, quotes, interest and reviews. */
export const showtimeApi = (http: HttpClient) => ({
  home: (at?: At) => http.request<ShowtimeHome>('/showtime/home', { query: { lat: at?.lat, lng: at?.lng } }),
  search: (query: Record<string, string | number | undefined>) => http.request<ShowtimeSearchResult>('/showtime/search', { query }),
  suggest: (q: string) => http.request<ShowtimeSuggestions>('/showtime/suggest', { query: { q } }),
  cinemas: (at?: At) => http.request<{ results: ShowtimeCinema[]; locationUsed: boolean }>('/showtime/cinemas', { query: { lat: at?.lat, lng: at?.lng } }),
  title: (slug: string, q: { date?: string; format?: string; language?: string } & At = {}) =>
    http.request<ShowtimeTitleDetail>(`/showtime/titles/${encodeURIComponent(slug)}`, { query: q }),
  reviews: (slug: string, page = 1) =>
    http.request<{ results: ShowtimeReview[]; count: number; page: number; hasMore: boolean }>(`/showtime/titles/${encodeURIComponent(slug)}/reviews`, { query: { page } }),
  hold: (showId: string, seats: string[]) => http.request<SeatHold>('/customer/showtime/holds', { method: 'POST', body: { showId, seats } }),
  getHold: (id: string) => http.request<SeatHold>(`/customer/showtime/holds/${id}`),
  releaseHold: (id: string) => http.request<void>(`/customer/showtime/holds/${id}`, { method: 'DELETE' }),
  quote: (input: ShowtimeQuoteInput) => http.request<ShowtimeQuote>('/customer/showtime/quote', { method: 'POST', body: input }),
  interest: (slug: string, on: boolean) =>
    http.request<{ interested: boolean; interestCount: number }>(`/customer/showtime/titles/${encodeURIComponent(slug)}/interest`, { method: on ? 'POST' : 'DELETE' }),
  review: {
    create: (slug: string, input: { rating: number; body?: string }) =>
      http.request<ShowtimeReview>(`/customer/showtime/titles/${encodeURIComponent(slug)}/review`, { method: 'POST', body: input }),
    update: (slug: string, input: { rating: number; body?: string }) =>
      http.request<ShowtimeReview>(`/customer/showtime/titles/${encodeURIComponent(slug)}/review`, { method: 'PATCH', body: input }),
    remove: (slug: string) => http.request<void>(`/customer/showtime/titles/${encodeURIComponent(slug)}/review`, { method: 'DELETE' }),
  },
});
