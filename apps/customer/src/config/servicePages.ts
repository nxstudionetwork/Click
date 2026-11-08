/**
 * Main service pages (Food, Groceries, Shop) share one structure — intro, horizontal categories, search, filters,
 * discovery sections, full list — and differ only by this config. A new commerce service is a config entry here
 * plus its routes; Rides/Services will use the same building blocks with their own content.
 */
import type { StoreType } from '@click/api';
import type { IconName } from '../components/ui';

export interface ServicePageConfig {
  storeType: StoreType;
  title: string;
  /** Fixed tagline (deliberately not rotated). */
  quote: string;
  searchPlaceholder: string;
  categoriesLabel: string;
  /** Noun for the store list, e.g. "restaurants". */
  plural: string;
  /** Show the vegetarian filter (only meaningful where dishes carry diet marks). */
  vegFilter: boolean;
  /** Icon per category slug; anything unlisted uses `fallbackIcon`. */
  categoryIcons: Record<string, IconName>;
  fallbackIcon: IconName;
  dishesLabel: string;
}

export const SERVICE_PAGES: Record<StoreType, ServicePageConfig> = {
  restaurant: {
    storeType: 'restaurant', title: 'Food', quote: 'Good food. Great moments. One Click. away.',
    searchPlaceholder: 'Search restaurants, dishes & cuisines', categoriesLabel: 'Cuisines', plural: 'restaurants', vegFilter: true,
    categoryIcons: { cafe: 'coffee', bakery: 'cake', desserts: 'cake', healthy: 'heart', 'south-indian': 'food', biryani: 'food' },
    fallbackIcon: 'food', dishesLabel: 'Dishes',
  },
  grocery: {
    storeType: 'grocery', title: 'Groceries', quote: 'Fresh essentials, delivered fast. One Click. away.',
    searchPlaceholder: 'Search groceries, brands & stores', categoriesLabel: 'Categories', plural: 'stores', vegFilter: false,
    categoryIcons: {}, fallbackIcon: 'grocery', dishesLabel: 'Products',
  },
  retail: {
    storeType: 'retail', title: 'Shop', quote: 'Find what you love. One Click. away.',
    searchPlaceholder: 'Search products, brands & shops', categoriesLabel: 'Categories', plural: 'shops', vegFilter: false,
    categoryIcons: { electronics: 'device', fashion: 'shirt', 'home-kitchen': 'home', sports: 'ball', books: 'receipt' },
    fallbackIcon: 'shop', dishesLabel: 'Products',
  },
};

export type ServiceSort = '' | 'rating' | 'eta' | 'price_low' | 'price_high' | 'distance';
export const SORTS: { id: ServiceSort; label: string; needsLocation?: boolean }[] = [
  { id: '', label: 'Recommended' },
  { id: 'rating', label: 'Rating' },
  { id: 'eta', label: 'Delivery time' },
  { id: 'price_low', label: 'Price: low to high' },
  { id: 'price_high', label: 'Price: high to low' },
  { id: 'distance', label: 'Distance', needsLocation: true },
];
