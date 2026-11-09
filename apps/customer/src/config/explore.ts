/**
 * Explore banners. Each time Explore opens, the next banner in this list is shown (a deterministic rotation,
 * remembered per device), never a random pick and never an auto-advancing carousel.
 *
 * Imagery is real: the supplied Click. app icon (assets/, see public/brand/) or the licensed service photographs
 * already in the app (public/media/onboarding/, see CREDITS.md). Later, backend campaigns (seasonal, partner,
 * personalised) can supply items of this same shape; the page does not change.
 */
import type { IconName } from '../components/ui';
import type { Theme } from './services';

export interface ExploreBanner {
  id: string;
  eyebrow: string;
  title: string;
  /** Second line of the headline (rendered on its own line). */
  titleAccent?: string;
  subtitle: string;
  theme: Theme;
  /** 'brand' shows the Click. icon; otherwise a service photograph name from public/media/onboarding. */
  visual: 'brand' | 'food' | 'shopping' | 'market' | 'entertainment' | 'groceries' | 'rides';
  icons?: IconName[];
  /** Optional call to action; it must point at a real route. */
  action?: { label: string; to: string };
}

export const EXPLORE_BANNERS: ExploreBanner[] = [
  { id: 'everything', eyebrow: 'Click.', title: 'Everything you need.', titleAccent: 'One Click. away.', subtitle: 'Food. Rides. Shopping. Entertainment. Services. More.', theme: 'default', visual: 'brand', icons: ['food', 'ride', 'shop', 'film', 'wrench'] },
  { id: 'discover', eyebrow: 'Food', title: 'Discover more.', titleAccent: 'Do more.', subtitle: 'Kitchens near you, from breakfast dosas to late-night desserts.', theme: 'food', visual: 'food', action: { label: 'Order food', to: '/food' } },
  { id: 'everyday', eyebrow: 'Shopping', title: 'Food. Rides.', titleAccent: 'Shopping. More.', subtitle: 'Gadgets, fashion and home, delivered by Click.', theme: 'shopping', visual: 'shopping', action: { label: 'Start shopping', to: '/shopping' } },
  { id: 'connected', eyebrow: 'Click. Buzz', title: 'Your world.', titleAccent: 'Connected by Click.', subtitle: 'Instants from places and shows near you, each one a tap from done.', theme: 'buzz', visual: 'market', action: { label: 'Watch Buzz', to: '/buzz' } },
  { id: 'new', eyebrow: 'Showtime', title: 'There’s always', titleAccent: 'something new on Click.', subtitle: 'Pick a show, choose your seats, and you’re in.', theme: 'movies', visual: 'entertainment', action: { label: 'Book a show', to: '/showtime' } },
  { id: 'possibilities', eyebrow: 'Offers', title: 'One app.', titleAccent: 'Countless possibilities.', subtitle: 'Live offers from stores and kitchens across Click.', theme: 'offers', visual: 'groceries', action: { label: 'See offers', to: '/offers' } },
];

const KEY = 'click.exploreBanner';

/** The banner for this opening of Explore (reads the device's rotation position). */
export function currentBannerIndex(count = EXPLORE_BANNERS.length): number {
  try {
    const n = Number.parseInt(localStorage.getItem(KEY) ?? '0', 10);
    return Number.isFinite(n) && n >= 0 ? n % count : 0;
  } catch {
    return 0;
  }
}

/** Advance the rotation so the next opening shows the following banner. Idempotent for the same index. */
export function advanceBanner(shownIndex: number, count = EXPLORE_BANNERS.length) {
  try { localStorage.setItem(KEY, String((shownIndex + 1) % count)); } catch { /* storage unavailable: always the first banner */ }
}
