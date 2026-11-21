import type { HttpClient } from './http';
import type { CheckoutResult } from './types';
import type {
  BuyAgainRow, DeliveryChoice, FindEverythingResult, GroceriesHome, GroceryBasket, GroceryCheckoutInput, GroceryListing,
  GroceryProductDetail, GrocerySearchResult, GroceryStorePage, GrocerySuggestions, GroceryReorderResult, RunningLowRow, ShoppingList,
} from './groceries';

/** Where to deliver: the customer's own saved address (preferred) or a point. */
export type GroceryAt = { address?: string | null; lat?: number; lng?: number };
const at = (a?: GroceryAt) => ({ address: a?.address ?? undefined, lat: a?.lat, lng: a?.lng });

/** Click. Groceries: local-vendor discovery (public), basket & checkout, buy again, alerts and shopping lists. */
export const groceriesApi = (http: HttpClient) => ({
  home: (where?: GroceryAt) => http.request<GroceriesHome>('/groceries/home', { query: at(where) }),
  search: (params: Record<string, string | number | undefined>, where?: GroceryAt) =>
    http.request<GrocerySearchResult>('/groceries/search', { query: { ...params, ...at(where) } }),
  suggest: (text: string, where?: GroceryAt) => http.request<GrocerySuggestions>('/groceries/suggest', { query: { q: text, ...at(where) } }),
  store: (slug: string, where?: GroceryAt) => http.request<GroceryStorePage>(`/groceries/stores/${encodeURIComponent(slug)}`, { query: at(where) }),
  storeProducts: (slug: string, params: Record<string, string | number | undefined>, where?: GroceryAt) =>
    http.request<{ count: number; page: number; hasMore: boolean; results: GroceryListing[] }>(
      `/groceries/stores/${encodeURIComponent(slug)}/products`, { query: { ...params, ...at(where) } }),
  product: (id: string, where?: GroceryAt) => http.request<GroceryProductDetail>(`/groceries/products/${id}`, { query: at(where) }),

  basket: (address?: string | null) => http.request<GroceryBasket>('/customer/groceries/basket', { query: { address: address ?? undefined } }),
  quote: (addressId: string | null, delivery: Record<string, DeliveryChoice>) =>
    http.request<GroceryBasket>('/customer/groceries/basket/quote', { method: 'POST', body: { addressId, delivery } }),
  acknowledgePrices: (address?: string | null) =>
    http.request<GroceryBasket>('/customer/groceries/basket/acknowledge-prices', { method: 'POST', query: { address: address ?? undefined }, body: {} }),
  checkout: (input: GroceryCheckoutInput) => http.request<CheckoutResult>('/customer/groceries/checkout', { method: 'POST', body: input }),
  buyAgain: (address?: string | null) =>
    http.request<{ results: BuyAgainRow[]; runningLow: RunningLowRow[] }>('/customer/groceries/buy-again', { query: { address: address ?? undefined } }),
  reorder: (orderId: string) => http.request<GroceryReorderResult>(`/customer/groceries/orders/${orderId}/reorder`, { method: 'POST', body: {} }),
  alert: (target: { productId?: string; storeId?: string }) => http.request<{ ok: boolean }>('/customer/groceries/alerts', { method: 'POST', body: target }),
  clearRecent: () => http.request<void>('/customer/groceries/recent-searches', { method: 'DELETE' }),
  lists: {
    all: () => http.request<{ results: ShoppingList[] }>('/customer/groceries/lists'),
    get: (id: string) => http.request<ShoppingList>(`/customer/groceries/lists/${id}`),
    create: (input: { name?: string; items?: string[] }) => http.request<ShoppingList>('/customer/groceries/lists', { method: 'POST', body: input }),
    rename: (id: string, name: string) => http.request<ShoppingList>(`/customer/groceries/lists/${id}`, { method: 'PATCH', body: { name } }),
    remove: (id: string) => http.request<void>(`/customer/groceries/lists/${id}`, { method: 'DELETE' }),
    addItem: (id: string, input: { text: string; quantity?: number }) =>
      http.request<ShoppingList>(`/customer/groceries/lists/${id}/items`, { method: 'POST', body: input }),
    updateItem: (id: string, itemId: string, input: { text?: string; quantity?: number; isDone?: boolean }) =>
      http.request<ShoppingList>(`/customer/groceries/lists/${id}/items/${itemId}`, { method: 'PATCH', body: input }),
    removeItem: (id: string, itemId: string) => http.request<ShoppingList>(`/customer/groceries/lists/${id}/items/${itemId}`, { method: 'DELETE' }),
    find: (id: string, address?: string | null) =>
      http.request<FindEverythingResult>(`/customer/groceries/lists/${id}/find`, { method: 'POST', query: { address: address ?? undefined }, body: {} }),
  },
});
