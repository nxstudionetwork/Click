import type { HttpClient } from './http';
import type {
  Address, AddressInput, AssistantMessage, Cart, Notification, NotificationCategory, OfferWithStore, OrderDetail,
  OrderSummary, Paginated, PartnerLocationInput, PartnerProfileInput, PartnerState, PartnerType, PlaceOrderInput, ProductDetail, ReorderResult, RewardsSummary, SearchResults, SearchScope,
  Session, Store, StoreCategory, StoreMenu, StoreQuery, StoreType, SupportCategory, SupportTicket, User, WishlistItem,
} from './types';

/** Auth is shared across every Click app. */
export const authApi = (http: HttpClient) => ({
  register: (input: { email: string; password: string; fullName?: string }) =>
    http.request<Session>('/auth/register', { method: 'POST', body: input, auth: false }),
  login: (input: { email: string; password: string }) =>
    http.request<Session>('/auth/login', { method: 'POST', body: input, auth: false }),
  /** Exchange a Firebase ID token (phone sign-in) for a Click session. The server verifies it. */
  firebase: (idToken: string) =>
    http.request<Session>('/auth/firebase', { method: 'POST', body: { idToken }, auth: false }),
  refresh: () => http.request<Session>('/auth/refresh', { method: 'POST', auth: false }),
  logout: () => http.request<void>('/auth/logout', { method: 'POST', auth: false }),
  me: () => http.request<User>('/me'),
  updateMe: (input: Partial<Pick<User, 'fullName' | 'phone'>>) => http.request<User>('/me', { method: 'PATCH', body: input }),
});

/** Public catalogue endpoints beyond store discovery. */
export const catalogApi = (http: HttpClient) => ({
  product: (id: string) => http.request<ProductDetail>(`/products/${encodeURIComponent(id)}`, { auth: false }),
  search: (q: string, scope: SearchScope = 'all', signal?: AbortSignal) =>
    http.request<SearchResults>('/search', { query: { q, scope }, auth: false, signal }),
  offers: (type?: StoreType) => http.request<Paginated<OfferWithStore>>('/offers', { query: { type }, auth: false }),
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
    list: (opts: { page?: number; type?: StoreType } = {}) =>
      http.request<Paginated<OrderSummary>>('/customer/orders', { query: { page: opts.page, type: opts.type } }),
    reorder: (id: string) => http.request<ReorderResult>(`/customer/orders/${id}/reorder`, { method: 'POST' }),
    get: (id: string) => http.request<OrderDetail>(`/customer/orders/${id}`),
    place: (input: PlaceOrderInput) => http.request<OrderDetail>('/customer/orders', { method: 'POST', body: input }),
    cancel: (id: string, reason = '') =>
      http.request<OrderDetail>(`/customer/orders/${id}/cancel`, { method: 'POST', body: { reason } }),
  },
  wishlist: {
    list: () => http.request<WishlistItem[]>('/customer/wishlist'),
    add: (target: { storeId: string } | { productId: string }) =>
      http.request<WishlistItem>('/customer/wishlist', { method: 'POST', body: target }),
    remove: (id: string) => http.request<void>(`/customer/wishlist/${id}`, { method: 'DELETE' }),
  },
  notifications: {
    list: (opts: { page?: number; category?: NotificationCategory; unread?: boolean } = {}) =>
      http.request<Paginated<Notification>>('/customer/notifications', {
        query: { page: opts.page, category: opts.category, unread: opts.unread ? 'true' : undefined },
      }),
    summary: () => http.request<{ unread: number }>('/customer/notifications/summary'),
    markRead: (id: string) => http.request<Notification>(`/customer/notifications/${id}/read`, { method: 'POST' }),
    markAllRead: () => http.request<{ updated: number }>('/customer/notifications/read-all', { method: 'POST' }),
  },
  rewards: () => http.request<RewardsSummary>('/customer/rewards'),
  support: {
    list: () => http.request<Paginated<SupportTicket>>('/customer/support/tickets'),
    get: (id: string) => http.request<SupportTicket>(`/customer/support/tickets/${id}`),
    create: (input: { category: SupportCategory; subject: string; message: string; orderId?: string | null }) =>
      http.request<SupportTicket>('/customer/support/tickets', { method: 'POST', body: input }),
  },
  assistant: {
    send: (messages: AssistantMessage[]) =>
      http.request<{ message: AssistantMessage }>('/customer/assistant/messages', { method: 'POST', body: { messages } }),
  },
});

/** Click Partner App. The server resolves the partner from the signed-in user; no partner IDs are sent. */
export const partnerApi = (http: HttpClient) => ({
  catalog: () => http.request<{ types: PartnerType[] }>('/partner/categories', { auth: false }),
  me: () => http.request<PartnerState>('/partner/me'),
  chooseCategory: (input: { partnerType: string; category: string }) =>
    http.request<PartnerState>('/partner/onboarding/category', { method: 'POST', body: input }),
  saveProfile: (input: PartnerProfileInput) =>
    http.request<PartnerState>('/partner/onboarding/profile', { method: 'PATCH', body: input }),
  saveLocation: (input: PartnerLocationInput) =>
    http.request<PartnerState>('/partner/onboarding/location', { method: 'PATCH', body: input }),
  submit: () => http.request<PartnerState>('/partner/onboarding/submit', { method: 'POST' }),
});
