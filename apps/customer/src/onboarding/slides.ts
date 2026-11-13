import type { IconName } from '../components/ui';

/** Onboarding visuals (licensed photography in public/media/onboarding; see CREDITS.md). */
export interface Slide { key: string; title: string; caption: string; icon: IconName; tile: string; alt: string; tint: string }

export const SLIDES: Slide[] = [
  { key: 'food', title: 'Food', caption: 'Favourite kitchens, delivered hot', icon: 'food', tile: 'food', alt: 'Plates of freshly cooked dishes on a table', tint: '#c2410c' },
  { key: 'groceries', title: 'Groceries', caption: 'Fresh produce in minutes', icon: 'grocery', tile: 'grocery', alt: 'Shelves stocked with fresh vegetables', tint: '#237a35' },
  { key: 'shopping', title: 'Shopping', caption: 'Everything for you and your home', icon: 'shop', tile: 'shopping', alt: 'Shopper carrying shopping bags', tint: '#2b2ba8' },
  { key: 'rides', title: 'Rides', caption: 'Get around the city', icon: 'ride', tile: 'ride', alt: 'Driver at the wheel at sunset', tint: '#0b6b7a' },
  { key: 'parcels', title: 'Parcels', caption: 'Send and receive across town', icon: 'parcel', tile: 'parcel', alt: 'A parcel being handed over at the door', tint: '#b35c00' },
  { key: 'entertainment', title: 'Showtime', caption: 'Your seat is waiting', icon: 'ticket', tile: 'movies', alt: 'Audience watching a film in a cinema', tint: '#b4203f' },
  { key: 'services', title: 'Services', caption: 'Trusted help at home', icon: 'wrench', tile: 'services', alt: 'Professional cleaning a window', tint: '#1864ab' },
  { key: 'market', title: 'Local markets', caption: 'Support the shops around you', icon: 'pin', tile: 'grocery', alt: 'A colourful local fruit and vegetable market', tint: '#5f3dc4' },
];

export const slideSrc = (key: string, w: 640 | 1280) => `/media/onboarding/${key}-${w}.webp`;
export const slideSrcSet = (key: string) => `${slideSrc(key, 640)} 640w, ${slideSrc(key, 1280)} 1280w`;
