/**
 * The Click service catalogue: the single source of truth for which services
 * exist, which are live, where they route, how they're grouped in the Menu hub
 * and which visual theme they use. Launching a service is a config change plus
 * its feature routes, not a redesign.
 */
import type { StoreType } from '@click/api';
import type { IconName } from '../components/ui';

export type ServiceStatus = 'live' | 'soon';
export type ServiceGroup = 'everyday' | 'bookings' | 'services' | 'content';
export type Theme = 'default' | 'food' | 'grocery' | 'shopping' | 'ride' | 'parcel' | 'movies' | 'services' | 'rewards' | 'wallet' | 'buzz' | 'buddy' | 'explore' | 'profile';

export interface ClickService {
  id: string;
  name: string;
  tagline: string;
  icon: IconName;
  path: string;
  status: ServiceStatus;
  group: ServiceGroup;
  theme: Theme;
  /** Commerce services browse stores of this type through the shared catalogue. */
  storeType?: StoreType;
  /** What will exist when a 'soon' service launches (shown honestly, never as bookable). */
  upcoming?: string[];
  /** Short label for compact rows (Home quick services). Defaults to `name`. */
  short?: string;
}

export const SERVICES: ClickService[] = [
  { id: 'food', name: 'Food', tagline: 'Restaurants near you', icon: 'food', path: '/food', status: 'live', group: 'everyday', theme: 'food', storeType: 'restaurant' },
  { id: 'groceries', name: 'Groceries', tagline: 'Daily essentials, fast', icon: 'grocery', path: '/groceries', status: 'live', group: 'everyday', theme: 'grocery', storeType: 'grocery' },
  { id: 'shopping', name: 'Shopping', short: 'Shop', tagline: 'Electronics, fashion, home', icon: 'shop', path: '/shopping', status: 'live', group: 'everyday', theme: 'shopping', storeType: 'retail' },
  { id: 'rides', name: 'Rides', short: 'Ride', tagline: 'Get around the city', icon: 'ride', path: '/rides', status: 'soon', group: 'everyday', theme: 'ride',
    upcoming: ['Pickup and drop with saved places', 'Ride options with upfront fare estimates', 'Driver and vehicle details', 'Ride history and receipts'] },
  { id: 'parcels', name: 'Parcels', short: 'Parcel', tagline: 'Send packages across town', icon: 'parcel', path: '/parcels', status: 'soon', group: 'everyday', theme: 'parcel',
    upcoming: ['Sender and receiver details', 'Package size and instructions', 'Price estimate before booking', 'Delivery status and history'] },
  { id: 'movies', name: 'Movies & Events', short: 'Movies', tagline: 'Book seats for shows near you', icon: 'film', path: '/movies', status: 'live', group: 'bookings', theme: 'movies' },
  { id: 'events', name: 'Live Events', short: 'Events', tagline: 'Concerts, comedy and more', icon: 'ticket', path: '/movies?tab=events', status: 'live', group: 'bookings', theme: 'movies' },
  { id: 'experiences', name: 'Experiences', tagline: 'Tours, classes and activities', icon: 'compass', path: '/experiences', status: 'soon', group: 'bookings', theme: 'movies',
    upcoming: ['Curated local experiences', 'Date and slot selection', 'Instant confirmation'] },
  { id: 'services', name: 'Home Services', short: 'Services', tagline: 'Cleaning, repairs, professionals', icon: 'wrench', path: '/services', status: 'soon', group: 'services', theme: 'services',
    upcoming: ['Verified providers with ratings', 'Upfront pricing and estimates', 'Pick a date and time slot', 'Provider status updates and reviews'] },
  { id: 'buzz', name: 'Click. Buzz', short: 'Buzz', tagline: 'Instants you can act on', icon: 'play', path: '/buzz', status: 'live', group: 'content', theme: 'buzz' },
];

export const SERVICE_GROUPS: { id: ServiceGroup; label: string }[] = [
  { id: 'everyday', label: 'Everyday' },
  { id: 'bookings', label: 'Bookings' },
  { id: 'services', label: 'Services' },
  { id: 'content', label: 'Discover' },
];

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
  [/^\/parcels/, 'parcel'],
  [/^\/(movies|events|shows|bookings|experiences)/, 'movies'],
  [/^\/services/, 'services'],
  [/^\/rewards/, 'rewards'],
  [/^\/wallet/, 'wallet'],
  [/^\/buzz/, 'buzz'],
  [/^\/buddy/, 'buddy'],
  [/^\/(explore|search)/, 'explore'],
  [/^\/(account|settings|activity|orders|wishlist|notifications|help)/, 'profile'],
];

export function themeForPath(path: string, storeType?: StoreType): Theme {
  if (storeType) return serviceForStoreType(storeType).theme;
  return THEME_ROUTES.find(([re]) => re.test(path))?.[1] ?? 'default';
}
