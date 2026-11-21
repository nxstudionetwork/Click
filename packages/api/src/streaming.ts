import type { HttpClient } from './http';

/** Click. Live: series, films and live channels (separate from Showtime's cinema bookings). */
export interface LiveCard {
  slug: string; kind: 'series' | 'film' | 'show'; kindLabel: string; title: string; genres: string[]; language: string; maturity: string;
  year: number | null; posterUrl: string; backdropUrl: string; accent: string; synopsis: string; episodes: number | null;
}
export interface LiveEpisode {
  id: string; season: number; number: number; name: string; synopsis: string; durationSeconds: number; thumbnailUrl: string;
  releasedAt: string | null; progress: { positionSeconds: number; finished: boolean } | null;
}
export interface LiveChannelInfo { slug: string; name: string; description: string; category: string; nowPlaying: string; accent: string; isLive: boolean }
export interface LiveHome {
  featured: LiveCard | null; live: LiveChannelInfo[];
  continueWatching: (LiveCard & { episode: LiveEpisode; percent: number })[]; watchlist: LiveCard[];
  rails: { id: string; title: string; items: LiveCard[] }[];
}
export interface LiveTitle extends LiveCard {
  credits: string; inWatchlist: boolean; playNext: LiveEpisode | null;
  seasons: { number: number; name: string; episodes: LiveEpisode[] }[];
}
export interface LivePlay { episode: LiveEpisode; videoUrl: string; title: LiveCard; credits: string; next: LiveEpisode | null; resumeAt: number }

export const streamingApi = (http: HttpClient) => ({
  home: () => http.request<LiveHome>('/live/home'),
  title: (slug: string) => http.request<LiveTitle>(`/live/titles/${encodeURIComponent(slug)}`),
  play: (episodeId: string) => http.request<LivePlay>(`/live/play/${encodeURIComponent(episodeId)}`),
  channel: (slug: string) => http.request<LiveChannelInfo & { streamUrl: string | null }>(`/live/channels/${encodeURIComponent(slug)}`),
  search: (q: string) => http.request<{ results: LiveCard[] }>('/live/search', { query: { q } }),
  progress: (episode: string, position: number, duration: number) =>
    http.request<{ positionSeconds: number; finished: boolean }>('/customer/live/progress', { method: 'POST', body: { episode, position, duration } }),
  watchlist: (slug: string) => http.request<{ inWatchlist: boolean }>(`/customer/live/watchlist/${encodeURIComponent(slug)}`, { method: 'POST' }),
});
