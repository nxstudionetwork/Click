import type { Cart, CartItem, ISODateTime, Money, UUID } from './types';

/** Contracts for Click. Groceries (apps/groceries on the backend). */

export type StoreState = 'open' | 'closing_soon' | 'closed' | 'unavailable';
export interface GroceryStoreStatus { state: StoreState; label: string; closesAt: ISODateTime | null; opensAt: ISODateTime | null; detail: string }
export interface GroceryBadge { code: 'local' | 'verified' | 'popular' | 'fresh'; label: string }

export interface GroceryListing {
  id: UUID;
  itemId: UUID;
  name: string;
  brand: string;
  size: string;
  category: { slug: string; name: string };
  price: Money;
  /** Seller's genuine MRP / reference price, only when higher than the price. */
  mrp: Money | null;
  discountPercent: number | null;
  dealEndsAt: ISODateTime | null;
  perUnit: string | null;
  inStock: boolean;
  orderable: boolean;
  stockLeft: number | null;
  imageUrl: string;
  imageCredit: string;
  dietary: string;
  attributes: string[];
  variableWeight: boolean;
  freshToday: boolean;
  receivedOn: string | null;
  rating: { average: string; count: number } | null;
  store: { id: UUID; slug: string; name: string; etaLabel: string; isOpen: boolean };
  /** Search only: how many other nearby stores list this exact item. */
  otherStores?: number;
}

export interface GroceryStoreCard {
  id: UUID;
  slug: string;
  name: string;
  imageUrl: string;
  locality: string;
  categories: string[];
  rating: { average: string; count: number } | null;
  status: GroceryStoreStatus;
  distanceKm: number | null;
  etaLabel: string;
  etaMin: number | null;
  etaMax: number | null;
  fast: boolean;
  deliveryFee: Money | null;
  freeDeliveryAbove: Money | null;
  minOrder: Money | null;
  deliverable: boolean;
  canSchedule: boolean;
  reason: string;
  offer: string | null;
  badges: GroceryBadge[];
  currency: string;
}

export interface GroceryCategoryChip { slug: string; name: string; icon: string; imageUrl?: string; section?: string; count?: number }
export interface GroceryOffer {
  id: UUID; title: string; description: string; redeemable: boolean; minOrder: Money | null; endsAt: ISODateTime | null;
  store: { id: UUID; slug: string; name: string };
}
export interface BuyAgainRow { listing: GroceryListing; times: number; lastBought: ISODateTime | null; lastPrice: Money; sameStore: boolean }
export interface RunningLowRow { listing: GroceryListing; usualDays: number; daysSince: number }

export interface GroceriesHome {
  hasLocation: boolean;
  stores: GroceryStoreCard[];
  categories: GroceryCategoryChip[];
  sections: { code: string; title: string; items: GroceryListing[] }[];
  offers: GroceryOffer[];
  deals: GroceryListing[];
  fast: GroceryStoreCard[];
  local: GroceryStoreCard[];
  freshToday: number;
  buyAgain: BuyAgainRow[];
  runningLow: RunningLowRow[];
}

export interface GrocerySearchResult {
  query: string;
  count: number;
  page: number;
  pageSize: number;
  hasMore: boolean;
  sort: string;
  hasLocation: boolean;
  results: GroceryListing[];
  stores: GroceryStoreCard[];
  categories: GroceryCategoryChip[];
  facets: { brands: string[]; categories: { slug: string; name: string }[] };
}
export interface GrocerySuggestions {
  products?: GroceryListing[]; stores?: GroceryStoreCard[]; brands?: string[]; categories?: GroceryCategoryChip[];
  recent?: string[]; popular?: string[];
}

export interface DeliverySlot { start: ISODateTime; end: ISODateTime; day: string; label: string; remaining: number }
export interface DeliveryOption {
  mode: 'fast' | 'standard' | 'scheduled';
  label: string;
  available: boolean;
  reason: string;
  fee: Money | null;
  etaMin: number | null;
  etaMax: number | null;
  summary: string;
  slots: DeliverySlot[];
}

export interface GroceryStorePage extends Omit<GroceryStoreCard, 'categories'> {
  description: string;
  coverUrl: string;
  about: string;
  address: string;
  supportPhone: string;
  policies: string;
  freshnessNote: string;
  hours: { day: string; weekday: number; opens: string; closes: string }[];
  deliveryOptions: DeliveryOption[];
  categories: (GroceryCategoryChip & { count: number })[];
  popular: GroceryListing[];
  offers: GroceryOffer[];
  reviews: { rating: number; comment: string; createdAt: ISODateTime; author: string }[];
  alertSet: boolean;
  verified: boolean;
  productCount: number;
}

export interface GroceryProductDetail extends GroceryListing {
  description: string;
  ingredients: string;
  nutrition: Record<string, string>;
  imageSource: string;
  pricingNote: string;
  delivery: { status: GroceryStoreStatus; etaLabel: string; deliverable: boolean; reason: string; distanceKm: number | null };
  compare: (GroceryListing & { distanceKm: number | null })[];
  together: (GroceryListing & { togetherOrders: number })[];
  similar: GroceryListing[];
  reviews: { id: UUID; rating: number; title: string; body: string; createdAt: ISODateTime; author: string }[];
  alertSet: boolean;
}

export type DeliveryChoice = { mode: DeliveryOption['mode']; slotStart?: string | null };
export interface BasketStore {
  storeId: UUID;
  status: GroceryStoreStatus;
  distanceKm: number | null;
  options: DeliveryOption[];
  choice: DeliveryChoice | null;
  problem: string;
  subtotal: Money;
  deliveryFee: Money;
  tax: Money;
  discount: Money;
  total: Money;
  offerTitle: string;
  minimumRemaining: Money | null;
  freeDeliveryRemaining: Money | null;
}
export type BasketItem = CartItem & { listing?: GroceryListing | null };
export interface GroceryBasket {
  cart: Omit<Cart, 'items'> & { items: BasketItem[] };
  grocery: {
    stores: BasketStore[];
    priceChanges: { itemId: UUID; name: string; from: Money; to: Money }[];
    unavailable: { itemId: UUID; name: string; reason: string; alternatives: GroceryListing[] }[];
    total: Money;
    ready: boolean;
    hasLocation: boolean;
  } | null;
}
export type Substitution = 'none' | 'similar' | 'store_choice';
export interface GroceryCheckoutInput {
  addressId: UUID;
  paymentMethod: 'cash_on_delivery' | 'wallet';
  idempotencyKey: string;
  substitution: Substitution;
  substitutionNote?: string;
  customerNote?: string;
  delivery: Record<UUID, DeliveryChoice>;
}

export interface ShoppingList {
  id: UUID; name: string; updatedAt: ISODateTime;
  items: { id: UUID; text: string; quantity: number; isDone: boolean; itemId: UUID | null }[];
}
export interface FindStorePlan {
  store: { id: UUID; slug: string; name: string; etaLabel: string; distanceKm: number | null; status: GroceryStoreStatus; deliveryFee: Money | null; minOrder: Money | null };
  items: { lineId: UUID; text: string; quantity: number; listing: GroceryListing }[];
  found: number;
  subtotal: Money;
  estimatedTotal: Money;
}
export interface FindEverythingResult {
  hasLocation: boolean;
  lines: number;
  best: FindStorePlan | null;
  complete: boolean;
  split: FindStorePlan[];
  stores: FindStorePlan[];
  missing: { lineId: UUID; text: string }[];
}
export interface GroceryReorderResult { added: string[]; skipped: string[]; priceChanges: { name: string; from: Money; to: Money }[] }
