import type { HttpClient } from './http';
import type { Dietary, Money, UUID, WorkItem } from './types';

/**
 * Click Partner — Restaurant mode (/partner/restaurant/* on the backend, apps/orders/restaurant.py).
 * The server resolves the restaurant from the signed-in partner; `store` only picks among the partner's own stores.
 */


export type RestaurantState = 'open' | 'busy' | 'paused' | 'closed';

export interface RestaurantOperations {
  state: RestaurantState;
  label: string;
  prepTimeMinutes: number;
  busyExtraMinutes: number;
  busyUntil: string | null;
  pausedUntil: string | null;
  pauseReason: string;
  deliveryWindow: string;
  busyChoices: number[];
  pauseChoices: number[];
  pauseReasons: { key: string; label: string }[];
}

export interface MenuOption { id?: UUID; name: string; priceDelta: Money; isAvailable?: boolean }
export interface MenuOptionGroup { id?: UUID; name: string; minSelect: number; maxSelect: number; options: MenuOption[] }

export interface MenuItem {
  id: UUID; categoryId: UUID | null; name: string; description: string; imageUrl: string; price: Money; dietary: Dietary;
  isAvailable: boolean; isActive: boolean; isFeatured: boolean; position: number; unitsSold: number;
  ratingAverage: number; ratingCount: number; optionGroups: MenuOptionGroup[];
}

export interface PartnerMenuCategory { id: UUID; name: string; position: number; isActive: boolean; items: MenuItem[] }

export interface RestaurantStore {
  id: UUID; name: string; slug: string; city: string; locality: string; imageUrl: string; isAcceptingOrders: boolean;
  operations: RestaurantOperations; stores: { id: UUID; name: string }[];
}

export interface RestaurantMenu {
  store: RestaurantStore;
  categories: PartnerMenuCategory[];
  uncategorised: MenuItem[];
  counts: { items: number; available: number; unavailable: number; hidden: number };
  dietary: { key: Dietary; label: string }[];
}

export interface MenuItemInput {
  name?: string; categoryId?: UUID; price?: string; description?: string; imageUrl?: string; dietary?: Dietary;
  isAvailable?: boolean; isFeatured?: boolean; isActive?: boolean; optionGroups?: MenuOptionGroup[];
}

export type OperationInput =
  | { action: 'prep_time'; minutes: number }
  | { action: 'busy'; minutes: number; forMinutes: number }
  | { action: 'not_busy' }
  | { action: 'pause'; forMinutes: number; reason: string }
  | { action: 'resume' };

export interface KitchenCard extends WorkItem {
  kitchen: {
    lines: { quantity: number; name: string; options: string; note: string }[];
    note: string; orderType: string; placedAt: string; readyBy: string | null; late: boolean; readyAt: string | null; handover: string;
  };
}
export interface KitchenBoard {
  columns: { key: 'new' | 'accepted' | 'preparing' | 'ready'; label: string; items: KitchenCard[] }[];
  prepTimeMinutes: number;
  operations: RestaurantOperations;
}

export interface RestaurantOrders {
  items: WorkItem[]; page: number; pageSize: number; total: number; hasMore: boolean;
  filters: { key: string; label: string; count: number | null }[];
}

export type OfferState = 'pending' | 'rejected' | 'paused' | 'ended' | 'scheduled' | 'live' | 'inactive';
export interface RestaurantOffer {
  id: UUID; title: string; description: string; discountType: '' | 'percent' | 'flat' | 'free_delivery'; discountValue: Money;
  maxDiscount: Money | null; minOrderAmount: Money; startsAt: string | null; endsAt: string | null; state: OfferState;
  stateLabel: string; reviewNote: string; createdByPartner: boolean;
}
export interface OfferInput {
  title: string; description?: string; discountType: 'percent' | 'flat' | 'free_delivery'; discountValue?: string;
  maxDiscount?: string; minOrderAmount?: string; startsAt?: string; endsAt: string;
}

export interface RestaurantInsights {
  days: number;
  sales: { today: Money; week: Money; month: Money };
  orders: { total: number; completed: number; cancelled: number; rejected: number; averageValue: Money | null };
  money: { grossSales: Money; discounts: Money; orderValue: Money };
  operations: { averagePrepMinutes: number | null; onTimeRate: number | null; targetMinutes: number; acceptanceRate: number | null; cancellationRate: number | null };
  menu: { bestSellers: { name: string; quantity: number; revenue: Money }[]; notSelling: string[]; unavailable: string[] };
  customers: {
    rating: number | null; ratings: number; storeRating: number | null; repeatCustomers: number; customers: number;
    recentFeedback: { rating: number; comment: string; at: string }[];
  };
  note: string;
}

const R = '/partner/restaurant';

export const restaurantApi = (http: HttpClient) => ({
  menu: (store?: UUID) => http.request<RestaurantMenu>(`${R}/menu`, { query: { store } }),
  createCategory: (name: string, store?: UUID) =>
    http.request<Omit<PartnerMenuCategory, 'items'>>(`${R}/menu/categories`, { method: 'POST', body: { name }, query: { store } }),
  updateCategory: (id: UUID, body: { name?: string; isActive?: boolean }, store?: UUID) =>
    http.request<Omit<PartnerMenuCategory, 'items'>>(`${R}/menu/categories/${id}`, { method: 'PATCH', body, query: { store } }),
  deleteCategory: (id: UUID, store?: UUID) => http.request<void>(`${R}/menu/categories/${id}`, { method: 'DELETE', query: { store } }),
  reorderCategories: (ids: UUID[], store?: UUID) =>
    http.request<{ ok: true }>(`${R}/menu/categories/order`, { method: 'POST', body: { ids }, query: { store } }),
  createItem: (body: MenuItemInput, store?: UUID) => http.request<MenuItem>(`${R}/menu/items`, { method: 'POST', body, query: { store } }),
  updateItem: (id: UUID, body: MenuItemInput, store?: UUID) =>
    http.request<MenuItem>(`${R}/menu/items/${id}`, { method: 'PATCH', body, query: { store } }),
  reorderItems: (categoryId: UUID, ids: UUID[], store?: UUID) =>
    http.request<{ ok: true }>(`${R}/menu/items/order`, { method: 'POST', body: { categoryId, ids }, query: { store } }),
  operations: (store?: UUID) => http.request<RestaurantOperations>(`${R}/operations`, { query: { store } }),
  operate: (body: OperationInput, store?: UUID) =>
    http.request<RestaurantOperations>(`${R}/operations`, { method: 'POST', body, query: { store } }),
  kitchen: (store?: UUID) => http.request<KitchenBoard>(`${R}/kitchen`, { query: { store } }),
  orders: (q: { status?: string; q?: string; date?: string; page?: number; store?: UUID }) =>
    http.request<RestaurantOrders>(`${R}/orders`, { query: q }),
  offers: (store?: UUID) => http.request<{ offers: RestaurantOffer[] }>(`${R}/offers`, { query: { store } }),
  createOffer: (body: OfferInput, store?: UUID) => http.request<RestaurantOffer>(`${R}/offers`, { method: 'POST', body, query: { store } }),
  setOfferPaused: (id: UUID, paused: boolean, store?: UUID) =>
    http.request<RestaurantOffer>(`${R}/offers/${id}/${paused ? 'pause' : 'resume'}`, { method: 'POST', query: { store } }),
  insights: (days: 1 | 7 | 30, store?: UUID) => http.request<RestaurantInsights>(`${R}/insights`, { query: { days, store } }),
});
