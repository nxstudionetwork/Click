import type { HttpClient } from './http';
import type {
  Address, AddressInput, Cart, OrderDetail, OrderSummary, Paginated, PlaceOrderInput, Session, Store,
  StoreCategory, StoreMenu, StoreQuery, StoreType, User,
} from './types';

/** Auth is shared across every Click app. */
export const authApi = (http: HttpClient) => ({
  register: (input: { email: string; password: string; fullName?: string }) =>
    http.request<Session>('/auth/register', { method: 'POST', body: input, auth: false }),
  login: (input: { email: string; password: string }) =>
    http.request<Session>('/auth/login', { method: 'POST', body: input, auth: false }),
  refresh: () => http.request<Session>('/auth/refresh', { method: 'POST', auth: false }),
  logout: () => http.request<void>('/auth/logout', { method: 'POST', auth: false }),
  me: () => http.request<User>('/me'),
});

/** Public discovery. The customer app may swap this for a mock source (same interface). */
export interface StoresSource {
  list(query: StoreQuery): Promise<Paginated<Store>>;
  get(slug: string): Promise<Store>;
  menu(slug: string): Promise<StoreMenu>;
  categories(type: StoreType): Promise<StoreCategory[]>;
}

export const storesApi = (http: HttpClient): StoresSource => ({
  list: (query) =>
    http.request('/stores', { query: { ...query, open: query.open ? 'true' : undefined }, auth: false }),
  get: (slug) => http.request(`/stores/${encodeURIComponent(slug)}`, { auth: false }),
  menu: (slug) => http.request(`/stores/${encodeURIComponent(slug)}/menu`, { auth: false }),
  categories: (type) => http.request('/store-categories', { query: { type }, auth: false }),
});

export const customerApi = (http: HttpClient) => ({
  addresses: {
    list: () => http.request<Address[]>('/customer/addresses'),
    create: (input: AddressInput) => http.request<Address>('/customer/addresses', { method: 'POST', body: input }),
    update: (id: string, input: Partial<AddressInput>) =>
      http.request<Address>(`/customer/addresses/${id}`, { method: 'PATCH', body: input }),
    remove: (id: string) => http.request<void>(`/customer/addresses/${id}`, { method: 'DELETE' }),
  },
  cart: {
    get: () => http.request<Cart>('/customer/cart'),
    clear: () => http.request<Cart>('/customer/cart', { method: 'DELETE' }),
    addItem: (input: { productId: string; quantity: number; note?: string }) =>
      http.request<Cart>('/customer/cart/items', { method: 'POST', body: input }),
    updateItem: (id: string, input: { quantity: number; note?: string }) =>
      http.request<Cart>(`/customer/cart/items/${id}`, { method: 'PATCH', body: input }),
    removeItem: (id: string) => http.request<Cart>(`/customer/cart/items/${id}`, { method: 'DELETE' }),
  },
  orders: {
    list: (page = 1) => http.request<Paginated<OrderSummary>>('/customer/orders', { query: { page } }),
    get: (id: string) => http.request<OrderDetail>(`/customer/orders/${id}`),
    place: (input: PlaceOrderInput) => http.request<OrderDetail>('/customer/orders', { method: 'POST', body: input }),
    cancel: (id: string, reason = '') =>
      http.request<OrderDetail>(`/customer/orders/${id}/cancel`, { method: 'POST', body: { reason } }),
  },
});
