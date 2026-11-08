/**
 * Click API data contract (camelCase JSON from the Django API).
 * Mirrors backend serializers; any change here must match the backend.
 * Money values are decimal strings (e.g. "249.00") to avoid float rounding.
 */

export type UUID = string;
export type Money = string;
export type ISODateTime = string;

export type StoreType = 'restaurant' | 'grocery' | 'retail';
export type Dietary = 'veg' | 'non_veg' | 'vegan' | 'unspecified';

export interface Paginated<T> {
  results: T[];
  count: number;
  page: number;
  pageSize: number;
  hasNext: boolean;
}

export interface ApiErrorBody {
  code: string;
  message: string;
  details?: Record<string, unknown>;
}

// --- Identity ---------------------------------------------------------
export type Role = 'customer' | 'partner' | 'staff';

export interface User {
  id: UUID;
  /** Null for phone-only identities (Click Partner signs in with a Firebase-verified phone). */
  email: string | null;
  fullName: string;
  phone: string;
  roles: Role[];
  /** Public Click Customer ID, e.g. CLK-CS-7K2QXM (null for non-customers). */
  customerCode: string | null;
  phoneVerified: boolean;
  avatarUrl: string | null;
  createdAt: ISODateTime;
}

export interface DevLoginInfo {
  enabled: boolean;
  customer: { name: string; email: string; customerCode: string } | null;
  hint?: string;
}

export type IdentityExchangeResult =
  | ({ status: 'authenticated' } & Session)
  | { status: 'profile_required'; signupToken: string; phoneNumber: string; expiresIn: number };

export interface SignupInput {
  signupToken: string;
  fullName: string;
  email: string;
  addresses: AddressInput[];
}

export interface Session {
  user: User;
  access: string;
}

// --- Discovery ----------------------------------------------------------
export interface StoreCategory {
  id: UUID;
  name: string;
  slug: string;
  storeType: StoreType;
}

export interface StoreOffer {
  id: UUID;
  title: string;
  description: string;
  endsAt: ISODateTime | null;
}

export interface OfferWithStore extends StoreOffer {
  store: { id: UUID; slug: string; name: string; storeType: StoreType; imageUrl: string; isOpen: boolean };
}

export interface Store {
  id: UUID;
  slug: string;
  name: string;
  storeType: StoreType;
  description: string;
  imageUrl: string;
  categories: StoreCategory[];
  city: string;
  locality: string;
  ratingAverage: string;
  ratingCount: number;
  priceLevel: 1 | 2 | 3 | 4;
  deliveryTimeMin: number;
  deliveryTimeMax: number;
  deliveryFee: Money;
  minOrderAmount: Money;
  currency: string;
  isOpen: boolean;
  offers: StoreOffer[];
  /** Kilometres from the queried point; only present for location queries (lat/lng), otherwise null. */
  distanceKm: number | null;
}

export interface StoreQuery {
  type?: StoreType;
  search?: string;
  category?: string;
  city?: string;
  open?: boolean;
  page?: number;
  /** Customer's point: returns only stores with known coordinates within `radius` km (default 10), nearest first. */
  lat?: number;
  lng?: number;
  radius?: number;
  sort?: 'popular' | 'rating' | 'new' | 'distance';
}

export interface Product {
  id: UUID;
  storeId: UUID;
  categoryId: UUID | null;
  name: string;
  description: string;
  imageUrl: string;
  price: Money;
  compareAtPrice: Money | null;
  discountPercent: number | null;
  brand: string;
  unitLabel: string;
  dietary: Dietary;
  /** False when switched off by the store or out of stock. */
  isAvailable: boolean;
  lowStock: boolean;
  isFeatured: boolean;
}

export interface ProductStore {
  id: UUID;
  slug: string;
  name: string;
  storeType: StoreType;
  imageUrl: string;
  isOpen: boolean;
  currency: string;
  deliveryTimeMin: number;
  deliveryTimeMax: number;
}

export interface ProductWithStore extends Product {
  store: ProductStore;
  categoryName: string | null;
}

export interface ProductDetail extends ProductWithStore {
  related: ProductWithStore[];
}

export type SearchScope = 'all' | StoreType | 'products' | 'events';

export interface SearchResults {
  query: string;
  stores: Store[];
  products: ProductWithStore[];
  events: ClickEvent[];
}

export interface MenuCategory {
  id: UUID;
  name: string;
  products: Product[];
}

export interface StoreMenu {
  storeId: UUID;
  categories: MenuCategory[];
}

// --- Customer -------------------------------------------------------------
export type AddressLabel = 'home' | 'work' | 'college' | 'family' | 'other';

export interface Address {
  id: UUID;
  label: AddressLabel;
  recipientName: string;
  phone: string;
  line1: string;
  line2: string;
  landmark: string;
  city: string;
  state: string;
  postalCode: string;
  country: string;
  latitude: string | null;
  longitude: string | null;
  deliveryInstructions: string;
  isDefault: boolean;
  createdAt: ISODateTime;
}

export type AddressInput = Omit<Address, 'id' | 'createdAt' | 'latitude' | 'longitude' | 'deliveryInstructions'> &
  Partial<Pick<Address, 'latitude' | 'longitude' | 'deliveryInstructions'>>;

export interface CartTotals {
  subtotal: Money;
  deliveryFee: Money;
  tax: Money;
  total: Money;
}

export interface CartItem {
  id: UUID;
  product: Product;
  quantity: number;
  note: string;
  lineTotal: Money;
}

export interface CartStore {
  id: UUID;
  slug: string;
  name: string;
  imageUrl: string;
  deliveryFee: Money;
  minOrderAmount: Money;
  currency: string;
  isOpen: boolean;
  deliveryTimeMin: number;
  deliveryTimeMax: number;
}

export interface Cart {
  id: UUID;
  store: CartStore | null;
  items: CartItem[];
  itemCount: number;
  totals: CartTotals;
}

// --- Orders -----------------------------------------------------------------
export type OrderStatus =
  | 'placed'
  | 'confirmed'
  | 'preparing'
  | 'ready'
  | 'out_for_delivery'
  | 'delivered'
  | 'cancelled';

export type PaymentMethod = 'cash_on_delivery' | 'pay_at_venue' | 'wallet';
export type PaymentStatus = 'pending' | 'authorized' | 'captured' | 'failed' | 'cancelled' | 'refunded';

export interface OrderSummary {
  id: UUID;
  number: string;
  status: OrderStatus;
  store: { id: UUID; slug: string; name: string; storeType: StoreType; imageUrl: string };
  total: Money;
  currency: string;
  itemCount: number;
  itemNames: string[];
  /** Number of distinct products (itemCount is total quantity). */
  lineCount: number;
  paymentStatus: PaymentStatus | null;
  createdAt: ISODateTime;
}

export interface OrderItem {
  id: UUID;
  productId: UUID | null;
  productName: string;
  unitPrice: Money;
  quantity: number;
  lineTotal: Money;
  note: string;
}

export interface OrderStatusEvent {
  fromStatus: OrderStatus | '';
  toStatus: OrderStatus;
  note: string;
  createdAt: ISODateTime;
}

export interface Payment {
  id: UUID;
  method: PaymentMethod;
  status: PaymentStatus;
  amount: Money;
  currency: string;
  createdAt: ISODateTime;
}

export interface OrderDetail extends OrderSummary {
  items: OrderItem[];
  events: OrderStatusEvent[];
  payments: Payment[];
  deliveryAddress: Omit<Address, 'id' | 'createdAt' | 'isDefault'>;
  customerNote: string;
  subtotal: Money;
  deliveryFee: Money;
  tax: Money;
  discount: Money;
  estimatedDeliveryAt: ISODateTime | null;
  cancelledAt: ISODateTime | null;
  deliveredAt: ISODateTime | null;
  canCancel: boolean;
}

export interface PlaceOrderInput {
  addressId: UUID;
  paymentMethod: PaymentMethod;
  idempotencyKey: UUID;
  customerNote?: string;
}

export interface ReorderResult {
  cart: Cart;
  skipped: string[];
}

// --- Engagement -------------------------------------------------------------
export interface WishlistItem {
  id: UUID;
  kind: 'store' | 'product';
  store: Store | null;
  product: ProductWithStore | null;
  createdAt: ISODateTime;
}

export type NotificationCategory =
  | 'orders' | 'rides' | 'deliveries' | 'payments' | 'wallet' | 'bookings' | 'offers' | 'rewards' | 'support' | 'system';

export interface Notification {
  id: UUID;
  category: NotificationCategory;
  title: string;
  body: string;
  linkPath: string;
  isRead: boolean;
  createdAt: ISODateTime;
}

export interface RewardTransaction {
  id: UUID;
  kind: 'earn' | 'redeem' | 'expire' | 'adjust';
  points: number;
  description: string;
  orderId: UUID | null;
  expiresAt: ISODateTime | null;
  createdAt: ISODateTime;
}

export interface RewardsSummary {
  balance: number;
  earned: number;
  used: number;
  history: RewardTransaction[];
  rules: { pointsPer100: number; expiryDays: number; redemptionAvailable: boolean };
}

export type SupportCategory = 'order' | 'payment' | 'delivery' | 'ride' | 'account' | 'service' | 'other';
export type SupportStatus = 'open' | 'in_progress' | 'awaiting_customer' | 'resolved' | 'closed';

export interface SupportTicket {
  id: UUID;
  reference: string;
  category: SupportCategory;
  subject: string;
  message: string;
  status: SupportStatus;
  orderId: UUID | null;
  orderNumber: string | null;
  createdAt: ISODateTime;
  resolvedAt: ISODateTime | null;
}

export interface AssistantMessage {
  role: 'user' | 'assistant';
  content: string;
}

/** Structured results Buddy attaches to a reply — always real Click records. */
export type BuddyCard =
  | { type: 'store'; store: Store }
  | { type: 'product'; product: ProductWithStore }
  | { type: 'event'; event: ClickEvent }
  | { type: 'order'; order: OrderSummary }
  | { type: 'booking'; booking: Booking }
  | { type: 'offer'; offer: OfferWithStore };

export type BuddyAction = { label: string; path: string } | { label: string; prompt: string };

export interface BuddyReply {
  message: AssistantMessage;
  cards: BuddyCard[];
  actions: BuddyAction[];
  mode: 'basic' | 'provider';
}

export interface AssistantCapabilities {
  mode: 'basic' | 'provider' | 'unavailable';
  /** Speech-to-text is configured on the server (Buddy GO / voice search can record). */
  voice: boolean;
  /** Image recognition is configured on the server (camera search beyond QR). */
  visualSearch: boolean;
}

// --- Buzz -------------------------------------------------------------------
/** One actionable Click. Buzz instant. Built from real Click records; media is never generated. */
export interface BuzzItem {
  id: string;
  kind: 'offer' | 'event' | 'store' | 'post';
  theme: 'food' | 'grocery' | 'shopping' | 'movies' | 'services' | 'ride' | 'parcel';
  title: string;
  body: string;
  tag: string;
  source: { name: string; handle: string };
  mediaUrl: string;
  mediaType: 'image' | 'video' | '';
  action: { label: string; path: string };
  publishedAt: string;
}

// --- Wallet -----------------------------------------------------------------
export interface WalletTransaction {
  id: UUID;
  kind: 'topup' | 'refund' | 'promo' | 'payment' | 'adjustment';
  amount: Money;
  currency: string;
  description: string;
  createdAt: ISODateTime;
}

export interface WalletSummary {
  balance: Money;
  currency: string;
  transactions: WalletTransaction[];
  topUpAvailable: boolean;
}

// --- Bookings (movies & events) ------------------------------------------------
export interface Venue {
  id: UUID;
  slug: string;
  name: string;
  kind: 'cinema' | 'theatre' | 'arena' | 'club';
  city: string;
  locality: string;
  address: string;
}

export interface ClickEvent {
  id: UUID;
  slug: string;
  kind: 'movie' | 'event';
  status: 'now_showing' | 'coming_soon';
  title: string;
  tagline: string;
  description: string;
  posterUrl: string;
  languages: string[];
  genres: string[];
  certification: string;
  durationMinutes: number | null;
  releaseDate: string | null;
  cast: string;
  ratingAverage: string;
  ratingCount: number;
  nextShowAt: ISODateTime | null;
}

export interface Show {
  id: UUID;
  startsAt: ISODateTime;
  language: string;
  format: string;
  screen: string;
  price: Money;
  premiumPrice: Money;
  currency: string;
  venue: Venue;
  seatsLeft: number | null;
}

export interface EventDetail extends ClickEvent {
  shows: Show[];
}

export interface SeatRow {
  row: string;
  tier: 'standard' | 'premium';
  seats: { label: string; available: boolean }[];
}

export interface ShowSeatMap extends Show {
  event: ClickEvent;
  layout: { rows: SeatRow[]; maxPerBooking: number };
}

export interface Booking {
  id: UUID;
  reference: string;
  status: 'confirmed' | 'cancelled';
  event: ClickEvent;
  show: Show;
  seats: { label: string; tier: string; price: Money }[];
  subtotal: Money;
  convenienceFee: Money;
  tax: Money;
  total: Money;
  currency: string;
  payments: Payment[];
  canCancel: boolean;
  createdAt: ISODateTime;
  cancelledAt: ISODateTime | null;
}

// --- Click Partner -------------------------------------------------------------
export type PartnerStatus =
  | 'draft' | 'profile_completed' | 'verification_pending' | 'verified' | 'active' | 'rejected' | 'suspended' | 'inactive';

export type OnboardingStep = 'category' | 'profile' | 'location' | 'review' | 'complete';

export type PartnerFieldKind = 'text' | 'textarea' | 'number' | 'select' | 'multiselect' | 'time';

export interface PartnerFieldOption {
  value: string;
  label: string;
}

/** A category-specific onboarding field, defined centrally on the server. */
export interface PartnerField {
  key: string;
  label: string;
  kind: PartnerFieldKind;
  required: boolean;
  options?: PartnerFieldOption[];
  placeholder?: string;
  help?: string;
  min?: number;
  max?: number;
  maxLength?: number;
  maxItems?: number;
  default?: string | string[] | number;
}

export interface PartnerHomeModule {
  key: string;
  label: string;
  empty: string;
}

export interface PartnerCategoryConfiguration {
  tagline: string;
  identity: { individual: boolean; businessNameLabel: string; businessNameHelp?: string };
  fields: PartnerField[];
  location: { title?: string; addressLabel?: string; serviceArea: boolean; serviceRadius: boolean };
  home: { availabilityLabel?: string; modules: PartnerHomeModule[] };
}

export interface PartnerCategory {
  slug: string;
  name: string;
  description: string;
  icon: string;
  imageUrl: string;
  configuration: PartnerCategoryConfiguration;
}

export interface PartnerType {
  slug: string;
  name: string;
  description: string;
  icon: string;
  imageUrl: string;
  tagline: string;
  categories: PartnerCategory[];
}

export type PartnerDetails = Record<string, string | number | string[]>;

export interface PartnerAddress {
  line1: string;
  line2: string;
  landmark: string;
  city: string;
  state: string;
  postalCode: string;
  country: string;
  latitude: string | null;
  longitude: string | null;
  serviceArea: string;
  serviceRadiusKm: number | null;
}

export interface Partner {
  /** Permanent Click Partner ID (CLK-PT-000001). Null until the profile is submitted. */
  partnerCode: string | null;
  status: PartnerStatus;
  statusLabel: string;
  isVerified: boolean;
  onboardingStep: OnboardingStep;
  partnerType: { slug: string; name: string; icon: string };
  category: PartnerCategory;
  businessName: string;
  isAvailable: boolean;
  verifiedPhone: string;
  profile: { contactName: string; email: string; description: string; details: PartnerDetails };
  address: PartnerAddress | null;
  profileCompletedAt: ISODateTime | null;
  createdAt: ISODateTime;
}

export interface PartnerState {
  partner: Partner | null;
  onboardingStep: OnboardingStep;
}

export interface PartnerProfileInput {
  businessName: string;
  contactName?: string;
  email?: string;
  description?: string;
  details: PartnerDetails;
}

export interface PartnerLocationInput {
  line1: string;
  line2?: string;
  landmark?: string;
  city: string;
  state: string;
  postalCode: string;
  latitude?: number | null;
  longitude?: number | null;
  serviceArea?: string;
  serviceRadiusKm?: number | null;
}
