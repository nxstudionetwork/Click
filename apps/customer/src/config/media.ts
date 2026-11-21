/**
 * Service imagery. Real photographs only (licensed Unsplash photos already shipped with the app, see
 * public/media/onboarding/CREDITS.md). They illustrate a *service*, never a specific store or product: a store
 * without its own photo keeps the neutral monogram placeholder rather than borrowing a stock photo.
 */
import type { Theme } from './services';

const PHOTO: Partial<Record<Theme, string>> = {
  food: 'food', grocery: 'groceries', shopping: 'shopping', ride: 'rides', parcel: 'parcels',
  movies: 'entertainment', services: 'services', buzz: 'market', default: 'market',
};

/** Responsive `src`/`srcSet` for a service's photograph, or null when the service has none. */
export function servicePhoto(theme: Theme): { src: string; srcSet: string } | null {
  const name = PHOTO[theme];
  if (!name) return null;
  const base = `/media/onboarding/${name}`;
  return { src: `${base}-640.webp`, srcSet: `${base}-640.webp 640w, ${base}-1280.webp 1280w` };
}
