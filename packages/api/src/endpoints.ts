import type { HttpClient } from './http';
import type {
  DevLoginInfo, IdentityExchangeResult, SignupInput,
  Address, AddressInput, AssistantCapabilities, AssistantMessage, BuzzItem, ProfileSummary, Ride, RidePlaceResult, RideQuote, RideRequestInput, RideSummary, RideTripInput, Booking, BuddyReply, ClickEvent, EventDetail, ShowSeatMap, WalletSummary, Cart, Notification, NotificationCategory, OfferWithStore, OrderDetail,
  OrderSummary, Paginated, PartnerAvailability, PartnerEarnings, PartnerHome, PartnerLocationInput, PartnerNotification, PartnerProfileInput, PartnerState, PartnerType, PartnerWork, WorkItem, PlaceOrderInput, ProductDetail, ReorderResult, RewardsSummary, SearchResults, SearchScope,
  Session, Store, StoreCategory, StoreMenu, StoreQuery, StoreRecommendation, StoreType, SupportCategory, SupportTicket, User, WishlistItem,
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
  /** Exchange a phone-OTP provider credential (e.g. Firebase ID token) for a Click session or a signup token. */
  exchangeIdentity: (input: { provider: string; token: string }) =>
    http.request<IdentityExchangeResult>('/auth/identity/exchange', { method: 'POST', body: input, auth: false }),
  /** Click Partner: create the phone-only Click account for a newly verified phone (token from exchangeIdentity). */
  partnerSignup: (signupToken: string) =>
    http.request<Session & { status: 'authenticated' }>('/auth/identity/partner-signup', { method: 'POST', body: { signupToken }, auth: false }),
  completeSignup: (input: SignupInput) =>
    http.request<Session & { status: 'authenticated' }>('/auth/identity/signup', { method: 'POST', body: input, auth: false }),
  uploadAvatar: (file: Blob) => {
    const form = new FormData();
    form.append('image', file, 'avatar');
    return http.request<User>('/me/avatar', { method: 'POST', body: form });
  },
  removeAvatar: () => http.request<User>('/me/avatar', { method: 'DELETE' }),
  /** DEVELOPMENT ONLY: 404 unless the backend runs with DEBUG. */
  devLoginInfo: () => http.request<DevLoginInfo>('/auth/dev-login', { auth: false }),
  devLogin: () => http.request<Session>('/auth/dev-login', { method: 'POST', auth: false }),
  updateMe: (input: Partial<Pick<User, 'fullName' | 'phone'>>) => http.request<User>('/me', { method: 'PATCH', body: input }),
});

/** Public catalogue endpoints beyond store discovery. */
export const catalogApi = (http: HttpClient) => ({
  product: (id: string) => http.request<ProductDetail>(`/products/${encodeURIComponent(id)}`, { auth: false }),
  search: (q: string, scope: SearchScope = 'all', signal?: AbortSignal) =>
    http.request<SearchResults>('/search', { query: { q, scope }, auth: false, signal }),
  offers: (type?: StoreType) => http.request<Paginated<OfferWithStore>>('/offers', { query: { type }, auth: false }),
  /** Click. Buzz: actionable instants from real offers, shows and stores. */
  buzz: (limit = 12) => http.request<{ results: BuzzItem[] }>('/buzz', { query: { limit }, auth: false }),
});

/** Movies & live events (public discovery). */
export const eventsApi = (http: HttpClient) => ({
  list: (q: { kind?: 'movie' | 'event'; status?: 'now_showing' | 'coming_soon'; city?: string; search?: string } = {}) =>
    http.request<Paginated<ClickEvent>>('/events', { query: q, auth: false }),
  get: (slug: string, city?: string) => http.request<EventDetail>(`/events/${encodeURIComponent(slug)}`, { query: { city }, auth: false }),
  seatMap: (showId: string) => http.request<ShowSeatMap>(`/shows/${showId}`, { auth: false }),
});

/** Public discovery. The customer app may swap this for a mock source (same interface). */
export interface StoresSource {
  list(query: StoreQuery): Promise<Paginated<Store>>;
  get(slug: string): Promise<Store>;
  menu(slug: string): Promise<StoreMenu>;
  categories(type: StoreType): Promise<StoreCategory[]>;
}

export const storesApi = (http: HttpClient): StoresSource => ({
  list: ({ open, veg, offers, minRating, maxPrice, ...query }) =>
    http.request('/stores', {
      query: { ...query, open: open ? 'true' : undefined, veg: veg ? 'true' : undefined, offers: offers ? 'true' : undefined, min_rating: minRating, max_price: maxPrice },
      auth: false,
    }),
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
    addItem: (input: { productId: string; quantity: number; note?: string; optionIds?: string[] }) =>
      http.request<Cart>('/customer/cart/items', { method: 'POST', body: input }),
    /** Apply an offer (validated server-side) / remove it. */
    applyOffer: (offerId: string) => http.request<Cart>('/customer/cart/offer', { method: 'POST', body: { offerId } }),
    removeOffer: () => http.request<Cart>('/customer/cart/offer', { method: 'DELETE' }),
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
    review: (id: string, input: { rating: number; comment?: string }) =>
      http.request<OrderDetail>(`/customer/orders/${id}/review`, { method: 'POST', body: input }),
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
  /** Rule-based store picks for the signed-in customer, each with its reason. */
  recommendedStores: (q: { type?: StoreType; lat?: number; lng?: number; radius?: number } = {}) =>
    http.request<{ results: StoreRecommendation[] }>('/customer/recommendations/stores', { query: q }),
  /** Counts for the Profile page (no full lists). */
  profileSummary: () => http.request<ProfileSummary>('/customer/profile/summary'),
  support: {
    list: () => http.request<Paginated<SupportTicket>>('/customer/support/tickets'),
    get: (id: string) => http.request<SupportTicket>(`/customer/support/tickets/${id}`),
    create: (input: { category: SupportCategory; subject: string; message: string; orderId?: string | null }) =>
      http.request<SupportTicket>('/customer/support/tickets', { method: 'POST', body: input }),
  },
  assistant: {
    send: (messages: AssistantMessage[]) =>
      http.request<BuddyReply>('/customer/assistant/messages', { method: 'POST', body: { messages } }),
    capabilities: () => http.request<AssistantCapabilities>('/customer/assistant/capabilities'),
    /** Speech to text (503 `speech_unavailable` until a provider is configured). */
    transcribe: (audio: Blob, language = 'en-IN') => {
      const form = new FormData();
      form.append('audio', audio, 'speech');
      form.append('language', language);
      return http.request<{ text: string }>('/customer/assistant/transcribe', { method: 'POST', body: form });
    },
  },
  wallet: () => http.request<WalletSummary>('/customer/wallet'),
  rides: {
    places: (q: string) => http.request<{ results: RidePlaceResult[] }>('/customer/rides/places', { query: { q } }),
    quote: (input: RideTripInput) => http.request<RideQuote>('/customer/rides/quote', { method: 'POST', body: input }),
    request: (input: RideRequestInput) => http.request<Ride>('/customer/rides', { method: 'POST', body: input }),
    list: (page?: number) => http.request<Paginated<RideSummary>>('/customer/rides', { query: { page } }),
    get: (id: string) => http.request<Ride>(`/customer/rides/${id}`),
    cancel: (id: string, reason = '') => http.request<Ride>(`/customer/rides/${id}/cancel`, { method: 'POST', body: { reason } }),
    rate: (id: string, input: { stars: number; comment?: string; compliment?: string }) =>
      http.request<Ride>(`/customer/rides/${id}/rating`, { method: 'POST', body: input }),
    safety: (id: string, kind: 'sos' | 'share' | 'report', note = '') =>
      http.request<{ recorded: boolean }>(`/customer/rides/${id}/safety`, { method: 'POST', body: { kind, note } }),
  },
  bookings: {
    list: (when?: 'upcoming' | 'past') => http.request<Paginated<Booking>>('/customer/bookings', { query: { when } }),
    get: (id: string) => http.request<Booking>(`/customer/bookings/${id}`),
    create: (input: { showId: string; seats: string[]; paymentMethod: 'pay_at_venue' | 'wallet'; idempotencyKey: string }) =>
      http.request<Booking>('/customer/bookings', { method: 'POST', body: input }),
    cancel: (id: string) => http.request<Booking>(`/customer/bookings/${id}/cancel`, { method: 'POST' }),
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
  // Partner Home / operations
  home: () => http.request<PartnerHome>('/partner/home'),
  setAvailability: (available: boolean) =>
    http.request<PartnerState & { availability: PartnerAvailability }>('/partner/availability', { method: 'POST', body: { available } }),
  work: (view?: string) => http.request<PartnerWork>('/partner/work', { query: { view } }),
  act: (item: { kind: string; id: string }, action: string, body?: { reason?: string }) =>
    http.request<{ ok: true; item: WorkItem | null }>(`/partner/work/${item.kind}/${item.id}/${action}`, { method: 'POST', body: body ?? {} }),
  earnings: (days: 7 | 30) => http.request<PartnerEarnings>('/partner/earnings', { query: { days } }),
  notifications: () => http.request<{ unread: number; results: PartnerNotification[] }>('/partner/notifications'),
  readNotification: (id: string) => http.request<{ unread: number }>(`/partner/notifications/${id}/read`, { method: 'POST' }),
  readAllNotifications: () => http.request<{ unread: number }>('/partner/notifications/read-all', { method: 'POST' }),
  reportDriverLocation: (lat: number, lng: number) =>
    http.request<{ ok: boolean }>('/partner/driver/location', { method: 'POST', body: { lat, lng } }),
  devLoginInfo: () =>
    http.request<{ enabled: boolean; partners: { code: string; name: string; category: string }[] }>('/partner/dev-login', { auth: false }),
  devLogin: (code: string) => http.request<Session>('/partner/dev-login', { method: 'POST', body: { code }, auth: false }),
});
