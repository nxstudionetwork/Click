/**
 * Click API data contract (camelCase JSON from the Django API).
 * Mirrors backend serializers; any change here must match the backend.
 * Money values are decimal strings (e.g. "249.00") to avoid float rounding.
 */

export type UUID = string;
export type Money = string;
export type ISODateTime = string;

export type StoreType = 'restaurant' | 'grocery' | 'retail' | 'pharmacy';
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
  /** Null for phone-only identities (Click Partner signs in with an OTP-verified phone). */
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
  /** '' = display-only; otherwise the server can apply it at checkout. */
  discountType: '' | 'percent' | 'flat' | 'free_delivery';
  discountValue: Money;
  maxDiscount: Money | null;
  minOrderAmount: Money;
  isRedeemable: boolean;
}

/** An offer of the cart's store, with whether it applies now (decided server-side) and the saving if it does. */
export interface CartOffer {
  id: UUID;
  storeId: UUID;
  title: string;
  description: string;
  minOrderAmount: Money;
  endsAt: ISODateTime | null;
  problem: string | null;
  saving?: Money | null;
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
  sort?: 'popular' | 'rating' | 'new' | 'distance' | 'eta' | 'price_low' | 'price_high';
  /** Only stores without non-vegetarian items. */
  veg?: boolean;
  minRating?: number;
  /** Only stores with a live offer. */
  offers?: boolean;
  /** Price level 1–4 or lower. */
  maxPrice?: number;
}

export interface Product {
  id: UUID;
  storeId: UUID;
  /** Pharmacy listings: prescription-only medicine. */
  requiresPrescription?: boolean;
  storeType?: StoreType;
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
  /** Customisation steps (size, add-ons). Empty when the item has none. */
  optionGroups: ProductOptionGroup[];
  /** Shopping: the listing's category in the Shopping taxonomy, and whether it is sold in variants (size, colour). */
  shopCategoryId: UUID | null;
  hasVariants: boolean;
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

export interface ProductOption { id: UUID; name: string; priceDelta: Money; isAvailable: boolean }
export interface ProductOptionGroup { id: UUID; name: string; minSelect: number; maxSelect: number; options: ProductOption[] }

export interface CartTotals {
  subtotal: Money;
  deliveryFee: Money;
  tax: Money;
  discount: Money;
  total: Money;
}

export interface CartItem {
  id: UUID;
  product: Product;
  storeId: UUID;
  variant: { id: UUID; label: string; options: Record<string, string> } | null;
  options: { id: UUID; name: string; priceDelta: Money }[];
  quantity: number;
  note: string;
  unitPrice: Money;
  lineTotal: Money;
  isAvailable: boolean;
  /** The live price differs from the one shown when the item was added (groceries require acknowledging it). */
  priceChange: { from: Money; to: Money } | null;
  requiresPrescription?: boolean;
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
  storeType: StoreType;
  freeDeliveryAbove: Money | null;
  codEnabled: boolean;
  isVerified: boolean;
}

/** A rule-based delivery window (dispatch + distance). Always shown as an estimate range, never a promise. */
export interface DeliveryEstimate {
  fromDate: string;
  toDate: string;
  basis: 'distance' | 'same_city' | 'region';
  fee: Money;
  freeAbove: Money | null;
  isEstimate: true;
}

/** The part of a cart one seller fulfils (Shopping carts can span sellers; each becomes its own order). */
export interface CartGroup {
  store: CartStore;
  itemIds: UUID[];
  subtotal: Money;
  deliveryFee: Money;
  tax: Money;
  discount: Money;
  total: Money;
  offerTitle: string;
  belowMinimum: boolean;
  freeDeliveryRemaining: Money | null;
  codAvailable: boolean;
  deliveryEstimate: DeliveryEstimate | null;
}

export type CartMode = '' | 'store' | 'marketplace' | 'basket';

export interface Cart {
  id: UUID;
  /** `store`: food/groceries from one store. `marketplace`: Shopping from any number of sellers. */
  mode: CartMode;
  /** The single store (store mode only). */
  store: CartStore | null;
  groups: CartGroup[];
  items: CartItem[];
  itemCount: number;
  totals: CartTotals;
  /** The applied offer; `problem` says why it no longer applies, if so. */
  offer: CartOffer | null;
  /** Offers of this store that can be applied at checkout. */
  offers: CartOffer[];
  /** Pharmacy carts: whether a verified prescription is needed, the one attached, and one ready to attach. */
  prescription?: { required: boolean; attached: { id: UUID; reference: string; status: string } | null; available: { id: UUID; reference: string } | null } | null;
}

// --- Orders -----------------------------------------------------------------
export type OrderStatus =
  | 'awaiting_payment'
  | 'placed'
  | 'confirmed'
  | 'preparing'
  | 'ready'
  | 'packed'
  | 'shipped'
  | 'out_for_delivery'
  | 'delivered'
  | 'cancelled';

export type PaymentMethod = 'cash_on_delivery' | 'pay_at_venue' | 'wallet' | 'upi' | 'card' | 'netbanking' | 'gift_card';
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

export type ReturnKind = 'return' | 'replacement';
export type ReturnReason = 'damaged' | 'wrong_item' | 'not_as_described' | 'size_fit' | 'defective' | 'changed_mind';
export interface ReturnRequest {
  id: UUID;
  kind: ReturnKind;
  kindLabel: string;
  reason: ReturnReason;
  reasonLabel: string;
  details: string;
  quantity: number;
  status: 'requested' | 'approved' | 'rejected' | 'refunded' | 'replaced';
  statusLabel: string;
  refundAmount: Money | null;
  resolutionNote: string;
  createdAt: ISODateTime;
  resolvedAt: ISODateTime | null;
}

export interface OrderItem {
  id: UUID;
  productId: UUID | null;
  variantId: UUID | null;
  /** Shopping: return window (days) snapshotted at purchase; null when not returnable. */
  returnDays: number | null;
  replacementOnly: boolean;
  dealPercent: number | null;
  returns: ReturnRequest[];
  returnUntil: ISODateTime | null;
  canReturn: boolean;
  /** Why it can't be returned (only for returnable items). */
  returnNote: string | null;
  productName: string;
  /** e.g. "Large · Extra cheese" (snapshot). */
  optionsSummary: string;
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
  /** Online payment (UPI / card / net banking) state, read from the payment records. */
  paymentIntent?: import('./money').PaymentIntent | null;
  items: OrderItem[];
  events: OrderStatusEvent[];
  payments: Payment[];
  deliveryAddress: Omit<Address, 'id' | 'createdAt' | 'isDefault'>;
  customerNote: string;
  subtotal: Money;
  deliveryFee: Money;
  tax: Money;
  discount: Money;
  offerTitle: string;
  estimatedDeliveryAt: ISODateTime | null;
  /** Shopping: start of the estimated delivery window. */
  estimatedDeliveryFrom: ISODateTime | null;
  cancelledAt: ISODateTime | null;
  deliveredAt: ISODateTime | null;
  canCancel: boolean;
  review: { rating: number; comment: string; createdAt: ISODateTime } | null;
  canReview: boolean;
  /** Set when the order is one seller's part of a Shopping checkout. */
  checkout: { id: UUID; number: string; orderCount: number } | null;
  /** Groceries: delivery mode/slot, substitution preference and any refund. */
  grocery?: GroceryOrderInfo | null;
}

export interface GroceryOrderInfo {
  deliveryMode: 'fast' | 'standard' | 'scheduled';
  deliveryModeLabel: string;
  slotStart: ISODateTime | null;
  slotEnd: ISODateTime | null;
  substitution: 'none' | 'similar' | 'store_choice';
  substitutionLabel: string;
  substitutionNote: string;
  distanceKm: string | null;
  etaMin: number | null;
  etaMax: number | null;
  refund: { amount: Money; to: string; status: string } | null;
  /** No live rider tracking exists: the app shows the order's status timeline only. */
  tracking: 'status_only';
}

export interface CheckoutGroup { id: UUID; number: string; total: Money; currency: string; createdAt: ISODateTime }
export interface CheckoutResult { checkout: CheckoutGroup | null; orders: OrderSummary[] }
export interface ReturnRequestInput { kind: ReturnKind; reason: ReturnReason; details?: string; quantity?: number }

export interface StoreRecommendation { store: Store; reason: string }

export interface PlaceOrderInput {
  addressId: UUID;
  paymentMethod: PaymentMethod;
  idempotencyKey: UUID;
  customerNote?: string;
  /** With paymentMethod "gift_card": one of the customer's own gift cards (checked on the server). */
  giftCardId?: UUID;
}

export interface ReorderResult {
  cart: Cart;
  skipped: string[];
}

// --- Engagement -------------------------------------------------------------
export interface WishlistItem {
  id: UUID;
  kind: 'store' | 'product' | 'provider' | 'event_provider' | 'event_package' | 'hotel' | 'travel_route' | 'attraction';
  store: Store | null;
  product: ProductWithStore | null;
  /** A saved Services professional ("My Professionals"). */
  provider?: import('./services-market').ProCard | null;
  /** A saved Click. Events team / venue, or package. */
  eventProvider?: import('./eventhub').EventProviderCard | null;
  eventPackage?: import('./eventhub').EventPackageInfo | null;
  /** A saved Click. Hotels property. */
  hotel?: Omit<import('./hotels').SavedHotel, 'favoriteId'> | null;
  /** A saved Click. Travel route (city pair). */
  travelRoute?: { id: UUID; origin: import('./travel').TravelPlace; destination: import('./travel').TravelPlace } | null;
  /** A saved temple / attraction / experience (Click. Bookings). */
  attraction?: import('./experiences').AttractionCard | null;
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
  /** Set when the request is about a Click. Parcel delivery. */
  parcelId?: UUID | null;
  parcelNumber?: string | null;
  /** Set when the request is about a Click. Services booking. */
  serviceBookingId?: UUID | null;
  /** Set when the request is about a Click. Events booking. */
  eventBookingId?: UUID | null;
  eventBookingNumber?: string | null;
  /** Set when the request is about a Click. Hotels booking. */
  hotelBookingId?: UUID | null;
  hotelBookingNumber?: string | null;
  /** Set when the request is about a Click. Travel ticket. */
  travelBookingId?: UUID | null;
  travelBookingNumber?: string | null;
  /** Set when the request is about a Click. Bookings visit (temple, attraction, experience). */
  experienceBookingId?: UUID | null;
  experienceBookingNumber?: string | null;
  serviceBookingNumber?: string | null;
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
  | { type: 'offer'; offer: OfferWithStore }
  | { type: 'grocery'; listing: import('./groceries').GroceryListing }
  | { type: 'grocery_store'; store: import('./groceries').GroceryStoreCard }
  | { type: 'hotel'; hotel: import('./hotels').HotelCard }
  | { type: 'hotel_booking'; booking: { id: UUID; number: string; property: string; checkIn: string; checkOut: string; status: string; payment: string; total: Money } }
  | { type: 'action_result'; result: import('./buddy').BuddyActionRun }
  | { type: 'journey'; journey: { id: string; mode: import('./travel').TravelMode; journeyId: UUID; fromStopId: UUID; toStopId: UUID; departsAt: ISODateTime;
      arrivesAt: ISODateTime; durationMinutes: number; lowest: Money | null; available: boolean; stops: number; operator: string; number: string; name: string;
      from: string; to: string; class: string } }
  | { type: 'attraction'; attraction: import('./experiences').AttractionCard }
  | { type: 'reservation'; reservation: import('./experiences').Reservation };

export type BuddyAction = { label: string; path: string } | { label: string; prompt: string }
  /** A typed action for the server's action layer (validated and permission-checked there). */
  | { label: string; action: string; args: Record<string, unknown>; auto?: boolean };

export interface BuddyReply {
  message: AssistantMessage;
  cards: BuddyCard[];
  actions: BuddyAction[];
  mode: 'basic' | 'provider';
}

/** GET /customer/profile/summary: counts for the signed-in customer's Profile page. */
export interface ProfileSummary {
  activity: { orders: number; bookings: number; rides: number; total: number };
  wishlist: number;
  addresses: number;
  unreadNotifications: number;
  rewardsBalance: number;
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
  kind: 'offer' | 'event' | 'trailer' | 'store' | 'product' | 'event_team' | 'post';
  theme: 'food' | 'grocery' | 'shopping' | 'movies' | 'services' | 'events' | 'hotels' | 'ride' | 'parcel';
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
  latitude: number | null;
  longitude: number | null;
  facilities: string[];
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
  backdropUrl: string;
  trailerUrl: string;
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

/** A Showtime ticket. */
export interface Booking {
  id: UUID;
  reference: string;
  status: 'confirmed' | 'cancelled';
  /** For My Tickets: upcoming, completed (the show has ended) or cancelled. */
  state: 'upcoming' | 'completed' | 'cancelled';
  event: ClickEvent;
  show: Show;
  seats: { label: string; tier: string; price: Money }[];
  concessions: { name: string; unitPrice: Money; quantity: number; lineTotal: Money }[];
  subtotal: Money;
  convenienceFee: Money;
  concessionsTotal: Money;
  tax: Money;
  discount: Money;
  offerTitle: string;
  total: Money;
  currency: string;
  payments: Payment[];
  canCancel: boolean;
  /** What cancelling would do (same rules as the server applies). Null once cancelled. */
  cancellation: { allowed: boolean; cutoffHours: number; deadline: ISODateTime; refundAmount: Money; refundMethod: string; charges: Money } | null;
  /** Signed code for the QR on the ticket; venues verify it through Click Partner. Only for upcoming tickets. */
  ticketCode: string | null;
  checkedInAt: ISODateTime | null;
  createdAt: ISODateTime;
  cancelledAt: ISODateTime | null;
}

export interface CreateBookingInput {
  holdId?: string;
  showId?: string;
  seats?: string[];
  concessions?: { id: string; quantity: number }[];
  offerId?: string | null;
  paymentMethod: 'pay_at_venue' | 'wallet';
  idempotencyKey: string;
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

// --- Rides ------------------------------------------------------------------
export interface RidePlace { label: string; address: string; lat: number; lng: number }
export interface RidePlaceResult extends RidePlace { kind: 'saved' | 'recent' | 'place' }
export interface RideTypeInfo { code: string; name: string; description: string; icon: string; seats: number }
export interface RideFare { base: Money; distance: Money; time: Money; fees: Money; subtotal: Money; discount: Money; total: Money; minimumApplied?: boolean }
export interface RideOfferInfo {
  id: UUID; title: string; description: string; discountType: 'percent' | 'flat'; discountValue: Money; maxDiscount: Money | null;
  minFare: Money; rideTypes: string[]; endsAt: ISODateTime | null;
}
export interface RideQuoteOption {
  rideType: RideTypeInfo;
  durationMinutes: number;
  /** Minutes for the nearest available driver to reach the pickup; null when no driver is available. */
  pickupEtaMinutes: number | null;
  available: boolean;
  fare: RideFare;
  offerProblem: string | null;
}
export interface RideQuote {
  distanceKm: string;
  /** "straight_line": estimated from coordinates (no road-routing or traffic provider connected). */
  estimateBasis: 'straight_line' | 'road';
  options: RideQuoteOption[];
  offers: RideOfferInfo[];
}
export type RideStatus = 'scheduled' | 'searching' | 'driver_assigned' | 'driver_arrived' | 'in_progress' | 'completed' | 'cancelled' | 'no_driver';
export interface RideDriver {
  name: string; rating: number | null; ratingCount: number; vehicleType: string; vehicleModel: string; vehicleColor: string; plate: string;
  /** Last position reported by the driver's app; `live` only when it is recent. */
  location: { lat: number; lng: number; reportedAt: ISODateTime; live: boolean } | null;
}
export interface Ride {
  id: UUID; number: string; status: RideStatus; statusLabel: string; rideType: RideTypeInfo;
  pickup: RidePlace; drop: RidePlace; stops: RidePlace[]; distanceKm: string; durationMinutes: number;
  fare: RideFare; offerTitle: string; currency: string; paymentMethod: 'cash' | 'wallet';
  payment: { method: string; status: PaymentStatus } | null; passengerName: string; scheduledFor: ISODateTime | null;
  driver: RideDriver | null; driverAssignedAt: ISODateTime | null; startedAt: ISODateTime | null; completedAt: ISODateTime | null;
  cancelledAt: ISODateTime | null; events: { toStatus: RideStatus; createdAt: ISODateTime }[];
  rating: { stars: number; comment: string } | null; canCancel: boolean; createdAt: ISODateTime;
}
export interface RideSummary {
  id: UUID; number: string; status: RideStatus; statusLabel: string; rideType: RideTypeInfo; pickupLabel: string; dropLabel: string;
  total: Money; currency: string; paymentMethod: 'cash' | 'wallet'; scheduledFor: ISODateTime | null; createdAt: ISODateTime;
}
export interface RideTripInput { pickup: RidePlace; drop: RidePlace; stops?: RidePlace[]; offerId?: string | null }
export interface RideRequestInput extends RideTripInput {
  rideType: string; paymentMethod: 'cash' | 'wallet'; idempotencyKey: string; scheduledFor?: ISODateTime | null;
  passengerName?: string; passengerPhone?: string;
}

// --- Click Partner Home (operations) -------------------------------------------------------------
/** Each Home section is loaded and fails on its own; `unavailable` means not live/connected yet (message says why). */
export type HomeSection<T> =
  | { status: 'ok'; data: T }
  | { status: 'error' | 'unavailable'; message: string };

export type WorkTone = 'urgent' | 'active' | 'info' | 'success' | 'muted';

export interface WorkAction {
  key: string;
  label: string;
  style: 'primary' | 'secondary' | 'danger';
  /** When set, the app asks the partner to confirm before sending. */
  confirm: string;
  needsReason: boolean;
}

export interface WorkItem {
  kind: 'ride' | 'order' | 'show' | 'booking' | 'stock' | string;
  id: string;
  ref: string;
  title: string;
  subtitle: string;
  status: string;
  statusLabel: string;
  tone: WorkTone;
  at: string | null;
  amount: string | null;
  currency: string;
  fields: { label: string; value: string }[];
  actions: WorkAction[];
  navigate: { lat: number; lng: number; label: string } | null;
  link: string;
}

export interface HomeMetric { key: string; label: string; value: unknown; display: string; hint: string }
export interface HomeQuickAction { key: string; label: string; icon: string; to: string; count: number | null }
export interface HomeActivity { id: string; title: string; body: string; at: string; amount: string | null; tone: WorkTone }

export interface PartnerAvailability {
  isOn: boolean;
  label: string;
  onLabel: string;
  offLabel: string;
  turnOn: string;
  turnOff: string;
  hint: string;
  canChange: boolean;
  blockedReason: string;
  confirmOff: string;
  since: string | null;
}

export interface PartnerHome {
  generatedAt: string;
  workspace: {
    kind: 'rides' | 'orders' | 'venue' | 'upcoming' | string;
    state: 'live' | 'not_connected' | 'upcoming';
    message: string;
    workNoun: string;
    location: 'live' | 'business';
    liveLocation: { reportedAt: string | null; fresh: boolean } | null;
  };
  greetingName: string;
  context: string;
  availability: PartnerAvailability;
  actionRequired: HomeSection<WorkItem[]>;
  active: HomeSection<WorkItem[]>;
  incoming: HomeSection<WorkItem[]>;
  metrics: HomeSection<HomeMetric[]>;
  earnings: HomeSection<{ label: string; today: string; todayCount: number; week: string; weekCount: number; currency: string; note: string; countLabel: string }>;
  performance: HomeSection<HomeMetric[]>;
  activity: HomeSection<HomeActivity[]>;
  quickActions: HomeQuickAction[];
  notifications: { unread: number };
}

export interface PartnerWork {
  state: 'live' | 'not_connected' | 'upcoming';
  message: string;
  views: { key: string; label: string; count: number | null }[];
  view: string;
  items: WorkItem[];
}

export interface PartnerEarnings {
  state: 'live' | 'not_connected' | 'upcoming';
  message: string;
  label: string;
  currency: string;
  total: string;
  count: number;
  countLabel: string;
  days: { date: string; amount: string; count: number }[];
  recent: { ref: string; title: string; amount: string; at: string; detail: string }[];
  note: string;
}

export interface PartnerNotification {
  id: string;
  category: 'work' | 'update' | 'account' | 'payment' | 'system';
  title: string;
  body: string;
  linkPath: string;
  read: boolean;
  createdAt: string;
}
