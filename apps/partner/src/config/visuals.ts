import type { IconName } from '@click/ui';

/**
 * The one place that maps partner types to real photography and icons.
 * Keys are the stable type slugs served by the API; any type added later
 * without an entry here falls back to the Local Business visuals.
 */
export interface Scene {
  photo: string;
  alt: string;
  /** A short verb describing the stage of real partner work shown. */
  stage: string;
  caption: string;
}

export interface TypeVisual {
  accent: string;
  scenes: Scene[];
}

const VISUALS: Record<string, TypeVisual> = {
  transport: {
    accent: '#2563ff',
    scenes: [
      { photo: 'driving', alt: 'A driver’s hands on the steering wheel at sunset', stage: 'Drive', caption: 'Go online and start driving' },
      { photo: 'taxi', alt: 'A lit taxi sign on a cab roof at night', stage: 'Accept', caption: 'Accept ride requests nearby' },
      { photo: 'delivery-rider', alt: 'A rider on a scooter moving through city traffic', stage: 'Pick up', caption: 'Pick up and drop customers' },
    ],
  },
  food: {
    accent: '#ff8a1f',
    scenes: [
      { photo: 'chef', alt: 'A chef plating food under warm kitchen lights', stage: 'Prepare', caption: 'Receive orders and start cooking' },
      { photo: 'chef-portrait', alt: 'A smiling chef standing in a restaurant', stage: 'Serve', caption: 'Pack it fresh for delivery' },
      { photo: 'restaurant', alt: 'A bright restaurant dining room with wooden tables', stage: 'Grow', caption: 'Bring more guests to your tables' },
    ],
  },
  retail: {
    accent: '#16a34a',
    scenes: [
      { photo: 'produce', alt: 'Shelves of fresh vegetables and fruit in a grocery store', stage: 'Stock', caption: 'Show customers what’s on your shelves' },
      { photo: 'supermarket', alt: 'A long supermarket aisle lined with products', stage: 'Pick', caption: 'Pick items as orders arrive' },
      { photo: 'grocery-bags', alt: 'Paper grocery bags packed with bread, apples and bananas', stage: 'Pack', caption: 'Pack orders ready for handoff' },
    ],
  },
  logistics: {
    accent: '#12b9da',
    scenes: [
      { photo: 'warehouse', alt: 'Parcels being sorted in a large warehouse', stage: 'Sort', caption: 'Sort parcels at your hub' },
      { photo: 'delivery-rider', alt: 'A delivery rider on a scooter in traffic', stage: 'Deliver', caption: 'Move deliveries across the city' },
      { photo: 'parcel-handoff', alt: 'A parcel being handed from one person to another', stage: 'Hand off', caption: 'Hand parcels to customers' },
    ],
  },
  services: {
    accent: '#f59e0b',
    scenes: [
      { photo: 'electrician', alt: 'An electrician in a hard hat working on a meter box', stage: 'Fix', caption: 'Accept jobs that match your skills' },
      { photo: 'cleaning', alt: 'A cleaning professional wiping a window', stage: 'Serve', caption: 'Complete jobs and get rated' },
    ],
  },
  entertainment: {
    accent: '#e11d48',
    scenes: [
      { photo: 'cinema-audience', alt: 'An audience watching a film in a cinema hall', stage: 'Fill', caption: 'Fill every seat for every show' },
      { photo: 'cinema-screen', alt: 'An empty cinema screen and rows of seats', stage: 'Schedule', caption: 'Publish shows and sell tickets' },
    ],
  },
  hospitality: {
    accent: '#0ea5e9',
    scenes: [
      { photo: 'resort', alt: 'A resort deck with loungers beside a pool', stage: 'Host', caption: 'Welcome guests to your property' },
      { photo: 'hotel-night', alt: 'A hotel lit up at dusk beside its pool', stage: 'Book', caption: 'Take bookings around the clock' },
    ],
  },
  local: {
    accent: '#7c3aed',
    scenes: [
      { photo: 'shop-owner', alt: 'A shop owner serving a customer at the counter', stage: 'Sell', caption: 'Serve local customers online' },
      { photo: 'shop-counter', alt: 'A shop owner taking a card payment at the till', stage: 'Earn', caption: 'Get paid and grow with Click' },
    ],
  },
};

export const FALLBACK_VISUAL = VISUALS.local!;

export function visualFor(typeSlug: string | undefined): TypeVisual {
  return (typeSlug && VISUALS[typeSlug]) || FALLBACK_VISUAL;
}

/** The Click Partner ecosystem story used on the splash and sign-in screens: one scene per kind of partner. */
export const ECOSYSTEM_STORY: (Scene & { label: string })[] = [
  { ...VISUALS.transport!.scenes[0]!, label: 'Drivers' },
  { ...VISUALS.food!.scenes[0]!, label: 'Restaurants' },
  { ...VISUALS.retail!.scenes[2]!, label: 'Grocery & retail' },
  { ...VISUALS.logistics!.scenes[2]!, label: 'Parcel & logistics' },
  { ...VISUALS.services!.scenes[0]!, label: 'Manpower & services' },
  { ...VISUALS.entertainment!.scenes[0]!, label: 'Cinemas' },
  { ...VISUALS.hospitality!.scenes[0]!, label: 'Hotels & venues' },
  { ...VISUALS.local!.scenes[0]!, label: 'Local businesses' },
];

const ICONS: Record<string, IconName> = {
  car: 'car', auto: 'auto', bike: 'bike', fleet: 'fleet', key: 'key', bus: 'bus', food: 'food', coffee: 'coffee',
  cake: 'cake', grocery: 'grocery', shop: 'shop', device: 'device', shirt: 'shirt', parcel: 'parcel',
  warehouse: 'warehouse', wrench: 'wrench', team: 'team', sparkle: 'sparkle', home: 'home', briefcase: 'briefcase',
  ticket: 'ticket', film: 'film', hotel: 'hotel', ball: 'ball', compass: 'compass', store: 'store', bag: 'bag', plus: 'plus',
};

export const iconFor = (key: string | undefined): IconName => (key && ICONS[key]) || 'store';

export function photoSet(photo: string) {
  return {
    src: `/media/${photo}-960.webp`,
    srcSet: `/media/${photo}-480.webp 480w, /media/${photo}-960.webp 900w`,
  };
}
