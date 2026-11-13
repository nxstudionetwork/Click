/**
 * Data-driven Home: which "moment" sections appear depends on local time and day, and each section is a query
 * against the real catalogue. Adding a moment (e.g. "Late-night cravings") is a config change, not a component.
 */
import type { StoreQuery } from '@click/api';
import type { IconName } from '../components/ui';
import type { Theme } from './services';

export type Daypart = 'morning' | 'afternoon' | 'evening' | 'night';

export interface HomeMoment {
  id: string;
  title: string;
  subtitle: string;
  icon: IconName;
  theme: Theme;
  /** Real store query; the section hides itself when it returns nothing. */
  query: StoreQuery;
  /** "See all" destination. */
  to: string;
}

export function daypart(d: Date = new Date()): Daypart {
  const h = d.getHours();
  return h >= 5 && h < 11 ? 'morning' : h >= 11 && h < 16 ? 'afternoon' : h >= 16 && h < 22 ? 'evening' : 'night';
}

export function greetingFor(d: Date = new Date()): string {
  const h = d.getHours();
  return h >= 5 && h < 12 ? 'Good morning' : h >= 12 && h < 17 ? 'Good afternoon' : 'Good evening';
}

const MOMENTS: Record<Daypart, HomeMoment[]> = {
  morning: [
    { id: 'breakfast', title: 'Breakfast, sorted', subtitle: 'Dosas, idlis and fresh bakes', icon: 'coffee', theme: 'food', query: { type: 'restaurant', category: 'south-indian', open: true }, to: '/food?category=south-indian' },
    { id: 'coffee', title: 'Coffee & bakes', subtitle: 'Your morning cup, delivered', icon: 'coffee', theme: 'food', query: { type: 'restaurant', category: 'cafe', open: true }, to: '/food?category=cafe' },
  ],
  afternoon: [
    { id: 'lunch', title: 'Lunch break', subtitle: 'Biryani and hearty meals', icon: 'food', theme: 'food', query: { type: 'restaurant', category: 'biryani', open: true }, to: '/food?category=biryani' },
    { id: 'healthy', title: 'Light & healthy', subtitle: 'Bowls and salads', icon: 'food', theme: 'grocery', query: { type: 'restaurant', category: 'healthy', open: true }, to: '/food?category=healthy' },
  ],
  evening: [
    { id: 'dinner', title: 'Dinner tonight', subtitle: 'North Indian favourites', icon: 'food', theme: 'food', query: { type: 'restaurant', category: 'north-indian', open: true }, to: '/food?category=north-indian' },
    { id: 'pizza', title: 'Pizza night', subtitle: 'Wood-fired and loaded', icon: 'food', theme: 'food', query: { type: 'restaurant', category: 'pizza', open: true }, to: '/food?category=pizza' },
  ],
  night: [
    { id: 'desserts', title: 'Late-night sweet tooth', subtitle: 'Desserts still open', icon: 'cake', theme: 'food', query: { type: 'restaurant', category: 'desserts', open: true }, to: '/food?category=desserts' },
  ],
};

const WEEKEND: HomeMoment = {
  id: 'weekend-shopping', title: 'Weekend shopping', subtitle: 'Fashion, home and gadgets', icon: 'shop', theme: 'shopping',
  query: { type: 'retail', sort: 'popular' }, to: '/shopping',
};

export function momentsFor(d: Date = new Date()): HomeMoment[] {
  const weekend = d.getDay() === 0 || d.getDay() === 6;
  return [...MOMENTS[daypart(d)], ...(weekend ? [WEEKEND] : [])];
}
