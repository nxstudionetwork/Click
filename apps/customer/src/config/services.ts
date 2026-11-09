/**
 * The Click service catalogue: the single source of truth for which services
 * exist, which are live, where they route and which visual theme they use. Home's quick services use
 * SERVICES; Explore uses CLICK_FEATURES (services plus the customer's personal Click. features). Launching a service is a config change plus
 * its feature routes, not a redesign.
 */
import type { StoreType } from '@click/api';
import type { IconName } from '../components/ui';

export type ServiceStatus = 'live' | 'soon';
export type Theme = 'default' | 'food' | 'grocery' | 'shopping' | 'ride' | 'parcel' | 'movies' | 'services' | 'rewards' | 'wallet' | 'buzz' | 'buddy' | 'explore' | 'profile' | 'activity' | 'offers';

export interface ClickService {
  id: string;
  name: string;
  tagline: string;
  icon: IconName;
  path: string;
  status: ServiceStatus;
  theme: Theme;
  /** Commerce services browse stores of this type through the shared catalogue. */
  storeType?: StoreType;
  /** What will exist when a 'soon' service launches (shown honestly, never as bookable). */
  upcoming?: string[];
  /** Short label for compact rows (Home quick services). Defaults to `name`. */
  short?: string;
}

export const SERVICES: ClickService[] = [
  { id: 'food', name: 'Food', tagline: 'Restaurants near you', icon: 'food', path: '/food', status: 'live', theme: 'food', storeType: 'restaurant' },
  { id: 'groceries', name: 'Groceries', tagline: 'Daily essentials, fast', icon: 'grocery', path: '/groceries', status: 'live', theme: 'grocery', storeType: 'grocery' },
  { id: 'shopping', name: 'Shopping', short: 'Shop', tagline: 'Electronics, fashion, home', icon: 'shop', path: '/shopping', status: 'live', theme: 'shopping', storeType: 'retail' },
  { id: 'rides', name: 'Rides', short: 'Ride', tagline: 'Bike, auto and cab rides', icon: 'ride', path: '/rides', status: 'live', theme: 'ride',
    upcoming: ['Pickup and drop with saved places', 'Ride options with upfront fare estimates', 'Driver and vehicle details', 'Ride history and receipts'] },
  { id: 'parcels', name: 'Parcel', short: 'Parcel', tagline: 'Send, receive and store pickup across town', icon: 'parcel', path: '/parcels', status: 'live', theme: 'parcel' },
  { id: 'movies', name: 'Showtime', tagline: 'Cinema and live shows near you', icon: 'film', path: '/showtime', status: 'live', theme: 'movies' },
  { id: 'events', name: 'Live Shows', tagline: 'Concerts, comedy, theatre and more', icon: 'ticket', path: '/showtime/search?kind=event', status: 'live', theme: 'movies' },
  { id: 'experiences', name: 'Experiences', tagline: 'Tours, classes and activities', icon: 'compass', path: '/experiences', status: 'soon', theme: 'movies',
    upcoming: ['Curated local experiences', 'Date and slot selection', 'Instant confirmation'] },
  { id: 'services', name: 'Home Services', short: 'Services', tagline: 'Cleaning, repairs, professionals', icon: 'wrench', path: '/services', status: 'soon', theme: 'services',
    upcoming: ['Verified providers with ratings', 'Upfront pricing and estimates', 'Pick a date and time slot', 'Provider status updates and reviews'] },
  { id: 'buzz', name: 'Buzz', tagline: 'Instants you can act on', icon: 'play', path: '/buzz', status: 'live', theme: 'buzz' },
];

/**
 * The customer's own Click. features (not services you buy from). Explore lists them alongside the services;
 * they need a signed-in customer and are always live.
 */
export const PERSONAL_FEATURES: ClickService[] = [
  { id: 'activity', name: 'Activity', tagline: 'Your orders and bookings', icon: 'history', path: '/activity', status: 'live', theme: 'activity' },
  { id: 'buddy', name: 'Buddy', tagline: 'Your Click. assistant', icon: 'sparkle', path: '/buddy', status: 'live', theme: 'buddy' },
  { id: 'offers', name: 'Offers', tagline: 'Live deals across Click.', icon: 'tag', path: '/offers', status: 'live', theme: 'offers' },
  { id: 'rewards', name: 'Rewards', tagline: 'Click. points on every order', icon: 'star', path: '/rewards', status: 'live', theme: 'rewards' },
  { id: 'wallet', name: 'Wallet', tagline: 'Balance, refunds and credits', icon: 'wallet', path: '/wallet', status: 'live', theme: 'wallet' },
];

/** Every Click. feature, alphabetically by its customer-facing name (computed, never hand-ordered). */
export const CLICK_FEATURES: ClickService[] = [...SERVICES, ...PERSONAL_FEATURES]
  .sort((a, b) => a.name.localeCompare(b.name, 'en', { sensitivity: 'base' }));

export const serviceById = (id: string) => SERVICES.find((s) => s.id === id);
export const serviceForStoreType = (t: StoreType) => SERVICES.find((s) => s.storeType === t)!;

export const STORE_TYPE_LABEL: Record<StoreType, { singular: string; plural: string }> = {
  restaurant: { singular: 'restaurant', plural: 'restaurants' },
  grocery: { singular: 'grocery store', plural: 'grocery stores' },
  retail: { singular: 'shop', plural: 'shops' },
};

/** Route → visual theme. Every theme shares Click's type, spacing and components; only accents change. */
const THEME_ROUTES: [RegExp, Theme][] = [
  [/^\/food/, 'food'],
  [/^\/groceries/, 'grocery'],
  [/^\/shopping/, 'shopping'],
  [/^\/(rides|ride)/, 'ride'],
  [/^\/(parcels|track)/, 'parcel'],
  [/^\/(showtime|movies|events|shows|bookings|tickets|experiences)/, 'movies'],
  [/^\/services/, 'services'],
  [/^\/rewards/, 'rewards'],
  [/^\/wallet/, 'wallet'],
  [/^\/buzz/, 'buzz'],
  [/^\/buddy/, 'buddy'],
  [/^\/(explore|search)/, 'explore'],
  [/^\/activity/, 'activity'],
  [/^\/offers/, 'offers'],
  [/^\/(account|settings|orders|wishlist|notifications|help)/, 'profile'],
];

export function themeForPath(path: string, storeType?: StoreType): Theme {
  if (storeType) return serviceForStoreType(storeType).theme;
  return THEME_ROUTES.find(([re]) => re.test(path))?.[1] ?? 'default';
}
