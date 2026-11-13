/** Recent searches: a per-device convenience (never sent anywhere). */
const KEY = 'click.recentSearches';
const MAX = 6;

export function recentSearches(): string[] {
  try {
    const v = JSON.parse(localStorage.getItem(KEY) ?? '[]');
    return Array.isArray(v) ? v.filter((s): s is string => typeof s === 'string').slice(0, MAX) : [];
  } catch {
    return [];
  }
}

export function rememberSearch(q: string) {
  const term = q.trim();
  if (!term) return;
  const next = [term, ...recentSearches().filter((s) => s.toLowerCase() !== term.toLowerCase())].slice(0, MAX);
  try { localStorage.setItem(KEY, JSON.stringify(next)); } catch { /* storage unavailable */ }
}

export function clearRecentSearches() {
  try { localStorage.removeItem(KEY); } catch { /* storage unavailable */ }
}

/** Category hints shown before typing: each maps to a real Click. destination. */
export const SEARCH_HINTS: { label: string; to: string; theme: string }[] = [
  { label: 'Biryani', to: '/search?q=biryani', theme: 'food' },
  { label: 'Pizza', to: '/search?q=pizza', theme: 'food' },
  { label: 'Groceries', to: '/groceries', theme: 'grocery' },
  { label: 'Earbuds', to: '/search?q=earbuds', theme: 'shopping' },
  { label: 'Showtime', to: '/showtime', theme: 'movies' },
  { label: 'Offers', to: '/offers', theme: 'rewards' },
];
