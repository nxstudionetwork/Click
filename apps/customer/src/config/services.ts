/**
 * The Click service catalogue — the single source of truth for which services
 * exist, which are live, and where they route. Home, Explore, the sidebar and
 * search scopes all read from here, so launching a service is a config change
 * plus its feature routes, not a redesign.
 */
import type { StoreType } from '@click/api';
import type { IconName } from '../components/ui';

export type ServiceStatus = 'live' | 'soon';

export interface ClickService {
  id: string;
  name: string;
  tagline: string;
  icon: IconName;
  path: string;
  status: ServiceStatus;
  /** Commerce services browse stores of this type through the shared catalogue. */
  storeType?: StoreType;
}

export const SERVICES: ClickService[] = [
  { id: 'food', name: 'Food', tagline: 'Restaurants near you', icon: 'food', path: '/food', status: 'live', storeType: 'restaurant' },
  { id: 'groceries', name: 'Groceries', tagline: 'Daily essentials, fast', icon: 'grocery', path: '/groceries', status: 'live', storeType: 'grocery' },
  { id: 'shopping', name: 'Shopping', tagline: 'Electronics, fashion, home', icon: 'shop', path: '/shopping', status: 'live', storeType: 'retail' },
  { id: 'rides', name: 'Rides', tagline: 'Get around the city', icon: 'ride', path: '/rides', status: 'soon' },
  { id: 'deliveries', name: 'Deliveries', tagline: 'Send parcels across town', icon: 'parcel', path: '/deliveries', status: 'soon' },
  { id: 'tickets', name: 'Tickets', tagline: 'Events, shows and more', icon: 'ticket', path: '/tickets', status: 'soon' },
  { id: 'services', name: 'Services', tagline: 'Home & local professionals', icon: 'wrench', path: '/services', status: 'soon' },
];

export const serviceById = (id: string) => SERVICES.find((s) => s.id === id);
export const serviceForStoreType = (t: StoreType) => SERVICES.find((s) => s.storeType === t)!;

export const STORE_TYPE_LABEL: Record<StoreType, { singular: string; plural: string }> = {
  restaurant: { singular: 'restaurant', plural: 'restaurants' },
  grocery: { singular: 'grocery store', plural: 'grocery stores' },
  retail: { singular: 'shop', plural: 'shops' },
};
