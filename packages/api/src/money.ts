import type { HttpClient } from './http';
import type { ISODateTime, Money, UUID } from './types';

/**
 * Click. Wallet, Payments, Rewards, Offers, Notifications, Activity and Help & Support. Every balance, status and
 * eligibility here comes from the server's ledgers; the client never computes money or points itself.
 */

// --- Wallet ------------------------------------------------------------------------------------------------
export type WalletStatus = 'active' | 'restricted' | 'locked' | 'suspended' | 'closed';
export type WalletKind = 'topup' | 'refund' | 'promo' | 'cashback' | 'reward' | 'payment' | 'expiry' | 'adjustment';
export interface WalletEntry {
  id: UUID; kind: WalletKind; kindLabel: string; bucket: 'cash' | 'promo'; bucketLabel: string; amount: Money; direction: 'credit' | 'debit';
  currency: string; description: string; createdAt: ISODateTime; expiresAt: ISODateTime | null; status: string; statusLabel: string; reference: string;
  service: { service: string; label: string; reference: string; link: string; target: string; paymentId: UUID } | null;
}
export interface WalletEntryDetail extends WalletEntry {
  balanceBefore: Money; balanceAfter: Money;
  credit?: { remaining: Money; used: Money; expired: boolean; state: 'available' | 'used' | 'expired' };
  fromCredit?: { id: UUID; description: string };
  topup?: { method: string; providerReference: string; status: string };
  refund?: { originalAmount: Money; originalMethod: string; status: string; statusLabel: string; creditedAt: ISODateTime };
  reward?: { item: string; points: number };
  tickets: { id: UUID; reference: string; status: string }[];
}
export interface WalletCredit { id: UUID; kind: WalletKind; kindLabel: string; description: string; remaining: Money; expiresAt: ISODateTime | null }
export interface Wallet {
  balance: Money; currency: string; status: WalletStatus; statusLabel: string; statusReason: string;
  breakdown: { cash: Money; promo: Money }; expiring: WalletCredit[]; credits: WalletCredit[];
  limits: { minTopup: Money; maxTopup: Money; dailyTopup: Money; monthlyTopup: Money; maxBalance: Money };
  topUpAvailable: boolean; topUp: { provider: string; testMode: boolean; methods: ('upi' | 'card' | 'netbanking')[]; presets: Money[] } | null;
  eligibleServices: { code: string; label: string; path: string; wallet: boolean }[]; partialPayment: boolean; rewardsPoints: number;
  summary: { spent: Money; added: Money; refunds: Money; cashback: Money; rewards: Money; since: ISODateTime };
  lastUpdated: ISODateTime | null; transactions: WalletEntry[];
}
export type WalletFilter = '' | 'added' | 'spent' | 'refunds' | 'cashback' | 'rewards' | 'promo' | 'expired' | 'adjustments';
export interface WalletTopUp {
  id: UUID; amount: Money; method: string; status: 'created' | 'pending' | 'succeeded' | 'failed' | 'expired'; statusLabel: string; provider: string;
  providerReference: string; failureReason: string; transactionId: UUID | null; paymentId: UUID | null; createdAt: ISODateTime;
  client?: { provider: string; testMode: boolean; reference: string; instructions: string };
}
export interface WalletSecurity { status: WalletStatus; statusLabel: string; statusReason: string; events: WalletEntry[]; failedTopups: number; protections: string[] }

// --- Payments ----------------------------------------------------------------------------------------------
export type PaymentStatusCode = 'successful' | 'partly_refunded' | 'pending' | 'pay_later' | 'failed' | 'cancelled' | 'refunded';
export interface PaymentRow {
  id: UUID; reference: string; service: string; label: string; orderReference: string; link: string; method: string; methodLabel: string;
  amount: Money; currency: string; status: PaymentStatusCode; statusLabel: string; createdAt: ISODateTime;
}
export interface RefundRow {
  id: UUID; refundReference?: string; amount: Money; status: string; statusLabel: string; to: string; creditedAt: ISODateTime; reason?: string; description?: string;
  payment?: { id: UUID; reference: string; amount: Money; methodLabel: string; label: string; orderReference: string; link: string };
}
export interface PaymentDetail extends PaymentRow {
  provider: string; providerReference: string | null;
  walletEntries: { id: UUID; kind: WalletKind; kindLabel: string; amount: Money; bucket: string }[];
  refunds: RefundRow[]; breakdown: { lines: { label: string; amount: Money }[]; offer: string | null } | null; receipt: boolean;
  tickets: { id: UUID; reference: string; status: string }[]; retry: { label: string; path: string } | null;
}
export interface PaymentIntent {
  reference: string; status: 'pending' | 'succeeded' | 'failed' | 'cancelled'; amount: Money; method: string; methodLabel: string;
  orders: { id: UUID; number: string; status: string }[]; expiresAt: ISODateTime;
  client?: { provider: string; testMode: boolean; reference: string; instructions: string };
}
export interface PaymentsOverview {
  methods: { code: string; label: string; description: string; where: string; canDefault: boolean; default: boolean; detail: string }[];
  defaultMethod: string; onlineMethods: { available: boolean; testMode: boolean; methods: { code: string; label: string }[]; where: string; note: string };
  counts: { pending: number; payLater: number; failed: number; refunds: number }; recent: PaymentRow[];
}
export interface PaymentsQuery { service?: string; status?: string; period?: string; from?: string; to?: string; q?: string; page?: number }

// --- Rewards -----------------------------------------------------------------------------------------------
export interface RewardEntry {
  id: UUID; reference: string; kind: 'earn' | 'redeem' | 'expire' | 'adjust'; kindLabel: string; points: number; description: string;
  orderId: UUID | null; expiresAt: ISODateTime | null; createdAt: ISODateTime; source: { label: string; link: string } | null;
  reverses: UUID | null; reversed: boolean;
}
export interface RewardTier { code: string; name: string; minPoints: number; multiplier: string; benefits: string[] }
export interface RewardMission {
  code: string; title: string; description: string; target: number; progress: number; points: number; completed: boolean; expired: boolean;
  endsAt: ISODateTime | null; link: string;
}
export interface RewardItem {
  id: UUID; title: string; kind: string; kindLabel: string; description: string; pointsCost: number; value: Money; creditValidDays: number;
  minTier: string | null; terms: string; endsAt: ISODateTime | null; available: boolean; reason: string; affordable: boolean;
}
export interface Rewards {
  balance: number; earned: number; used: number; redeemed: number; expired: number; earnedThisMonth: number;
  expiring: { points: number; expiresAt: ISODateTime }[];
  tier: { code: string; name: string; multiplier: string; qualifyingPoints: number; next: { code: string; name: string; minPoints: number } | null; toNext: number };
  tiers: RewardTier[]; missions: RewardMission[];
  achievements: { code: string; title: string; description: string; progress: number; target: number; unlocked: boolean }[];
  catalog: RewardItem[];
  campaigns: { id: UUID; title: string; description: string; service: string; multiplier: string; startsAt: ISODateTime; endsAt: ISODateTime }[];
  history: RewardEntry[];
  rules: { pointsPer100: number; expiryDays: number; redemptionAvailable: boolean; earnOn: string[]; conversionNote: string };
}
export interface Redemption { id: UUID; title: string; points: number; value: Money; status: string; walletTransactionId: UUID | null; balance: number }

// --- Offers ------------------------------------------------------------------------------------------------
export interface Offer {
  id: string; service: string; serviceLabel: string; theme: string; kind: 'discount' | 'coupon' | 'cashback' | 'reward_boost' | 'info' | string;
  title: string; description: string; benefit: string; percent: number | null; flat: Money | null; maxDiscount: Money | null; minAmount: Money | null;
  code: string | null; startsAt: ISODateTime | null; endsAt: ISODateTime | null;
  partner: { name: string; kind: string; rating: string | null; link: string } | null; link: string; conditions: string[]; terms: string;
  newUser: boolean; badges: string[]; valueScore: number; saved: boolean; claimed: boolean;
}
export interface OffersHub {
  count: number; results: Offer[]; services: { code: string; label: string; theme: string; count: number }[];
  sections: { hero: Offer[]; picked: Offer[]; endingSoon: Offer[]; coupons: Offer[]; cashback: Offer[]; partners: Offer[]; clickOffers: Offer[]; newUser: Offer[]; bestValue: Offer[]; boosts: Offer[] };
  pickedReason: string; bestValueRule: string;
}
export interface OfferSavings {
  savedThisMonth: Money; savedThisYear: Money; offersUsed: number; cashbackEarned: Money;
  history: { service: string; title: string; saved: Money; at: ISODateTime; reference: string }[];
}
export interface MyOffers {
  saved: (Offer | { id: string; expired: true; title: string; saved: true })[];
  claimed: { offer: string; code: string; service: string; live: boolean; title: string }[];
  savings: OfferSavings;
}

// --- Notifications -----------------------------------------------------------------------------------------
export type NotificationGroup = 'orders' | 'rides' | 'bookings' | 'payments' | 'wallet' | 'offers' | 'rewards' | 'account';
export interface InboxNotification {
  id: UUID; category: string; title: string; body: string; linkPath: string; priority: '' | 'normal' | 'important' | 'urgent' | string; isRead: boolean; createdAt: ISODateTime;
}
export interface NotificationSummary { unread: number; byGroup: Record<NotificationGroup, number> }
export interface NotificationPrefs { muted: string[]; categories: { code: string; label: string; mutable: boolean }[]; note: string }

// --- Activity ----------------------------------------------------------------------------------------------
export interface ActivityRow {
  id: string; category: string; kind: string; title: string; subtitle: string; at: ISODateTime; link: string; amount: Money | null;
  status: string; tone: 'ok' | 'bad' | 'pending' | ''; reference: string;
}
export interface ActivityPage { results: ActivityRow[]; nextCursor: string | null; categories: string[] }

// --- Help & Support ----------------------------------------------------------------------------------------
export interface HelpArticleSummary { slug: string; category: string; categoryLabel: string; title: string; summary: string; popular: boolean }
export interface HelpArticle extends HelpArticleSummary {
  body: string[]; steps: string[]; action: { label: string; path: string } | null; related: HelpArticleSummary[];
}
export interface HelpHome {
  categories: { code: string; label: string; articles: number; issues: string[] }[]; popular: HelpArticleSummary[];
  contact: { email: string; phone: string; phoneCallable: boolean; hours: string | null }; articles: HelpArticleSummary[];
}
export interface SupportRelated { type: string; id: UUID; label: string; link: string; at?: ISODateTime }
export interface SupportRequest {
  id: UUID; reference: string; category: string; categoryLabel: string; issueType: string; subject: string; message: string;
  status: 'open' | 'in_progress' | 'awaiting_customer' | 'reopened' | 'resolved' | 'closed'; statusLabel: string;
  priority: 'normal' | 'important' | 'urgent'; priorityLabel: string; related: SupportRelated | null; lastUpdate: ISODateTime;
  createdAt: ISODateTime; updatedAt: ISODateTime; resolvedAt: ISODateTime | null;
}
export interface SupportMessage {
  id: UUID; sender: 'customer' | 'support' | 'system'; senderLabel: string; body: string; createdAt: ISODateTime;
  attachment: { name: string; type: string; size: number; url: string } | null;
}
export type SupportLink = 'orderId' | 'parcelId' | 'serviceBookingId' | 'eventBookingId' | 'hotelBookingId' | 'travelBookingId' | 'experienceBookingId'
  | 'rideId' | 'showBookingId' | 'paymentId' | 'walletTransactionId';
export type SupportCreate = { category: string; issueType?: string; subject: string; message: string; idempotencyKey?: string; isSafety?: boolean; urgency?: 'urgent' | 'important'; contactPreference?: 'call' | 'message' | 'email' } & Partial<Record<SupportLink, string>>;

/** The related-item type (from the API) → the field a new request sends it in. */
export const SUPPORT_LINK_FIELD: Record<string, SupportLink> = {
  order: 'orderId', parcel: 'parcelId', service_booking: 'serviceBookingId', event_booking: 'eventBookingId', hotel_booking: 'hotelBookingId',
  travel_booking: 'travelBookingId', experience_booking: 'experienceBookingId', ride: 'rideId', show_booking: 'showBookingId', payment: 'paymentId',
  wallet_transaction: 'walletTransactionId',
};

// --- Global Search ---------------------------------------------------------------------------------------------
export interface SearchHit {
  type: string; id: string; title: string; subtitle: string; link: string; group: string; service: string;
  image?: string; rating?: string | null; price?: Money | null; badge?: string; score?: number;
}
export interface GlobalSearchResult {
  query: string; count: number; top: SearchHit[]; mine: SearchHit[]; sponsored?: DiscoverCard[];
  groups: { code: string; label: string; count: number; results: SearchHit[] }[];
}
export interface SearchSuggestions {
  query: string; suggestions: SearchHit[]; mine?: SearchHit[]; recent: { id: UUID; query: string; at: ISODateTime }[]; trending?: string[];
}

// --- Reviews & Invoices --------------------------------------------------------------------------------------
export interface PendingReview {
  kind: string; kindLabel: string; targetId: UUID; title: string; subtitle: string; completedAt: ISODateTime | null; link: string; service: string;
  aspects: { code: string; label: string }[];
}
export interface MyReview { id: UUID; kind: string; kindLabel: string; title: string; rating: number; comment: string; createdAt: ISODateTime; link: string; status: string; service: string; target: string }
export interface ReviewsState { pending: PendingReview[]; mine: MyReview[] }
export interface ReviewInput { kind: string; targetId: string; rating: number; liked?: string; better?: string; aspects?: Record<string, number> }
export interface InvoiceCard {
  id: UUID | null; paymentId: UUID; number: string | null; service: string; label: string; vendor: string; reference: string; date: ISODateTime;
  amount: Money; paymentStatus: string; invoiceStatus: 'generated' | 'updated' | 'refund_document' | 'cancelled' | 'pending'; invoiceStatusLabel: string;
  link: string; refunded: string | null;
}
export interface InvoiceDetail {
  id: UUID; number: string; title: string; status: string; statusLabel: string; issuedAt: ISODateTime; service: string; label: string; reference: string; link: string;
  seller: { name: string; address?: string; partnerId?: string; gstin?: string };
  buyer: { name: string; email: string; phone: string; customerId: string; address?: string };
  lines: { description: string; quantity: number; unitPrice: Money | null; discount: Money; tax: Money | null; total: Money }[];
  totals: { subtotal: Money; discount: Money; deliveryFee: Money; fees: Money; tax: Money; total: Money; paid: Money; offer: string };
  refunds: { number: string; amount: Money; at: ISODateTime; to: string; reason: string }[];
  payment: { id: UUID; reference: string; method: string; status: string; providerReference: string | null };
  gstNote: string;
}

// --- Gift Cards & Safety ------------------------------------------------------------------------------------
export interface GiftDesign {
  id: UUID; title: string; category: string; categoryLabel: string; occasion: string; tagline: string; colors: string[];
  minAmount: Money; maxAmount: Money; presets: string[]; validityDays: number; services: { code: string; label: string }[]; terms: string;
}
export interface GiftCardView {
  id: UUID; design: GiftDesign; amount: Money; balance: Money; status: 'awaiting_payment' | 'scheduled' | 'active' | 'used' | 'expired' | 'cancelled';
  statusLabel: string; recipientName: string; message: string; delivery: 'click' | 'share'; deliveryLabel: string; deliverOn: string | null;
  deliveredAt: ISODateTime | null; expiresAt: ISODateTime | null; fromName: string; role: 'holder' | 'buyer'; redeemed: boolean; code: string; createdAt: ISODateTime;
  entries?: { id: UUID; kind: string; kindLabel: string; amount: Money; description: string; at: ISODateTime; paymentId: UUID | null }[];
  paymentIntent?: PaymentIntent | null;
}
export interface GiftPurchase {
  designId: string; amount: string; recipientName: string; recipientPhone?: string; message?: string; delivery: 'click' | 'share';
  deliverOn?: string | null; paymentMethod: string; idempotencyKey: string;
}
export interface SafetyState {
  emergencyNumber: string; support: { email: string; phone: string; phoneCallable: boolean };
  active: {
    rides: { id: UUID; number: string; title: string; status: string; driver: string | null; link: string }[];
    parcels: { id: UUID; number: string; title: string; status: string; link: string }[];
    services: { id: UUID; number: string; title: string; status: string; link: string; professional: string | null; verified: boolean; rating: string | null; jobs: number | null }[];
    trips: { id: UUID; title: string; status: string; pnr: string; link: string }[];
    stays: { id: UUID; title: string; status: string; link: string }[];
  };
  reports: { id: UUID; reference: string; subject: string; status: string; statusLabel: string; priority: string; createdAt: ISODateTime }[];
  sessions: { active: number };
}

// --- Discover --------------------------------------------------------------------------------------------------
export interface DiscoverCard {
  type: string; id: string; service: string; title: string; subtitle: string; image: string; rating: string | null; ratingCount: number | null;
  eta: string | null; offer: string | null; open: boolean; link: string; cta: string; why: string; city?: string;
  sponsored?: boolean; campaign?: string; advertiser?: string; headline?: string; token?: string;
}
export interface DiscoverFeed { city: string; service: string; sections: { code: string; title: string; subtitle: string; cards: DiscoverCard[] }[] }

// --- Pharma ----------------------------------------------------------------------------------------------------
export interface PharmaProduct {
  id: UUID; name: string; brand: string; composition: string; packSize: string; manufacturer: string; price: Money; mrp: Money | null; image: string;
  requiresPrescription: boolean; category: string; categoryLabel: string; available: boolean; maxPerOrder: number | null; description: string;
  pharmacy: { id: UUID; name: string; slug: string; open: boolean };
}
export interface Pharmacy { id: UUID; name: string; slug: string; image: string; locality: string; city: string; open: boolean; rating: string | null; ratingCount: number; eta: string; verified: boolean }
export interface PharmaHome {
  categories: { code: string; label: string; icon: string; count: number }[]; pharmacies: Pharmacy[]; trending: PharmaProduct[]; orderAgain: PharmaProduct[]; disclaimer: string;
}
export interface PrescriptionView {
  id: UUID; reference: string; status: string; statusLabel: string; note: string; pharmacistNote: string; alternativeNote: string; fileName: string; fileType: string;
  pharmacy: { id: UUID; name: string }; uploadedAt: ISODateTime; reviewedAt: ISODateTime | null; validUntil: string | null;
  approvedItems: { id: UUID; name: string }[]; order: { id: UUID; number: string } | null;
}

type Page<T> = { results: T[]; hasNext: boolean; page: number; count?: number };

export const moneyApi = (http: HttpClient) => ({
  pharma: {
    home: () => http.request<PharmaHome>('/pharma/home'),
    products: (q: { category?: string; q?: string; pharmacy?: string; rx?: string } = {}) =>
      http.request<{ results: PharmaProduct[]; count: number; disclaimer: string }>('/pharma/products', { query: { ...q } }),
    product: (id: string) => http.request<PharmaProduct & { sameComposition: PharmaProduct[]; disclaimer: string }>(`/pharma/products/${id}`),
    prescriptions: () => http.request<{ results: PrescriptionView[] }>('/customer/pharma/prescriptions'),
    upload: (file: File, pharmacyId: string, note: string) => {
      const f = new FormData(); f.append('file', file); f.append('pharmacyId', pharmacyId); if (note) f.append('note', note);
      return http.request<PrescriptionView>('/customer/pharma/prescriptions', { method: 'POST', body: f });
    },
    cancel: (id: string) => http.request<PrescriptionView>(`/customer/pharma/prescriptions/${id}`, { method: 'DELETE' }),
    file: (id: string) => { if (!http.blob) throw new Error('Downloads are not supported.'); return http.blob(`/pharma/prescriptions/${id}/file`); },
    attach: (prescriptionId: string) => http.request<{ attached: PrescriptionView }>('/customer/cart/prescription', { method: 'POST', body: { prescriptionId } }),
    refills: () => http.request<{ results: { id: UUID; everyDays: number; nextOn: string; product: PharmaProduct }[] }>('/customer/pharma/refills'),
    addRefill: (productId: string, everyDays: number) => http.request<{ id: UUID; nextOn: string }>('/customer/pharma/refills', { method: 'POST', body: { productId, everyDays } }),
    removeRefill: (id: string) => http.request<void>(`/customer/pharma/refills/${id}`, { method: 'DELETE' }),
  },
  discover: {
    feed: (q: { city?: string; service?: string } = {}) => http.request<DiscoverFeed>('/discover', { query: { city: q.city || undefined, service: q.service || undefined } }),
    track: (token: string, kind: 'impression' | 'click') => http.request<{ counted: boolean }>('/discover/events', { method: 'POST', body: { token, kind } }),
    hide: (campaign: string) => http.request<{ hidden: boolean }>('/customer/discover/hide', { method: 'POST', body: { campaign } }),
  },
  giftCards: {
    designs: () => http.request<{ categories: { code: string; label: string; designs: GiftDesign[] }[] }>('/gift-cards', { auth: false }),
    mine: () => http.request<{ held: GiftCardView[]; sent: GiftCardView[] }>('/customer/gift-cards'),
    get: (id: string) => http.request<GiftCardView>(`/customer/gift-cards/${id}`),
    buy: (input: GiftPurchase) => http.request<GiftCardView>('/customer/gift-cards', { method: 'POST', body: input }),
    redeem: (code: string) => http.request<GiftCardView>('/customer/gift-cards/redeem', { method: 'POST', body: { code } }),
    usable: (service: string) => http.request<{ results: { id: UUID; title: string; balance: Money; codeEnd: string; expiresAt: ISODateTime | null }[] }>('/customer/gift-cards/usable', { query: { service } }),
  },
  safety: {
    get: () => http.request<SafetyState>('/customer/safety'),
    signOutOthers: () => http.request<{ signedOut: number; active: number }>('/customer/safety/sign-out-others', { method: 'POST' }),
  },
  reviews: {
    get: () => http.request<ReviewsState>('/customer/reviews'),
    submit: (input: ReviewInput) => http.request<ReviewsState>('/customer/reviews', { method: 'POST', body: input }),
    report: (kind: string, reviewId: string, reason: string, note = '') =>
      http.request<{ reported: boolean }>('/customer/reviews/report', { method: 'POST', body: { kind, reviewId, reason, note } }),
  },
  invoices: {
    list: (q: { service?: string; status?: string; q?: string; from?: string; to?: string } = {}) =>
      http.request<{ results: InvoiceCard[]; services: string[] }>('/customer/invoices', { query: { ...q } }),
    get: (id: string) => http.request<InvoiceDetail>(`/customer/invoices/${id}`),
    document: (id: string) => {
      if (!http.blob) throw new Error('Downloads are not supported by this client.');
      return http.blob(`/customer/invoices/${id}/document`);
    },
  },
  search: {
    global: (q: string, group = '') => http.request<GlobalSearchResult>('/search/global', { query: { q, group: group || undefined } }),
    suggest: (q: string) => http.request<SearchSuggestions>('/search/suggest', { query: { q } }),
    clearRecent: (id?: string) => http.request<void>(id ? `/customer/search/recent/${id}` : '/customer/search/recent', { method: 'DELETE' }),
  },
  wallet: {
    get: () => http.request<Wallet>('/customer/wallet'),
    transactions: (q: { filter?: WalletFilter; q?: string; page?: number } = {}) =>
      http.request<Page<WalletEntry>>('/customer/wallet/transactions', { query: { filter: q.filter || undefined, q: q.q, page: q.page } }),
    transaction: (id: string) => http.request<WalletEntryDetail>(`/customer/wallet/transactions/${id}`),
    startTopUp: (input: { amount: string; method: string; idempotencyKey: string }) =>
      http.request<WalletTopUp>('/customer/wallet/top-ups', { method: 'POST', body: input }),
    topUp: (id: string) => http.request<WalletTopUp>(`/customer/wallet/top-ups/${id}`),
    /** Test mode only: the sandbox provider's approve / decline step. The server signs and verifies the event. */
    sandbox: (id: string, outcome: 'succeeded' | 'failed') =>
      http.request<WalletTopUp>(`/customer/wallet/top-ups/${id}/sandbox`, { method: 'POST', body: { outcome } }),
    security: () => http.request<WalletSecurity>('/customer/wallet/security'),
  },
  payments: {
    list: (q: PaymentsQuery = {}) => http.request<Page<PaymentRow>>('/customer/payments', { query: { ...q } }),
    get: (id: string) => http.request<PaymentDetail>(`/customer/payments/${id}`),
    overview: () => http.request<PaymentsOverview>('/customer/payments/overview'),
    setDefault: (defaultMethod: string) => http.request<{ defaultMethod: string }>('/customer/payments/preferences', { method: 'PATCH', body: { defaultMethod } }),
    refunds: (page = 1) => http.request<Page<RefundRow>>('/customer/payments/refunds', { query: { page } }),
    intent: (reference: string) => http.request<PaymentIntent>(`/customer/payments/intents/${encodeURIComponent(reference)}`),
    /** Test mode only: the sandbox provider's approve / decline step (signed and verified on the server). */
    sandbox: (reference: string, outcome: 'succeeded' | 'failed') =>
      http.request<PaymentIntent>(`/customer/payments/intents/${encodeURIComponent(reference)}/sandbox`, { method: 'POST', body: { outcome } }),
  },
  rewards: {
    get: () => http.request<Rewards>('/customer/rewards'),
    history: (q: { kind?: string; page?: number } = {}) => http.request<Page<RewardEntry>>('/customer/rewards/history', { query: { kind: q.kind || undefined, page: q.page } }),
    entry: (id: string) => http.request<RewardEntry>(`/customer/rewards/history/${id}`),
    redeem: (itemId: string, idempotencyKey: string) =>
      http.request<Redemption>(`/customer/rewards/catalog/${itemId}/redeem`, { method: 'POST', body: { idempotencyKey } }),
  },
  offers: {
    hub: (q: { service?: string; kind?: string; q?: string; sort?: string } = {}) => http.request<OffersHub>('/offers/hub', { query: { ...q } }),
    get: (ref: string) => http.request<Offer>(`/offers/item/${encodeURIComponent(ref)}`),
    save: (ref: string) => http.request<{ saved: true }>(`/customer/offers/${encodeURIComponent(ref)}/save`, { method: 'POST' }),
    unsave: (ref: string) => http.request<void>(`/customer/offers/${encodeURIComponent(ref)}/save`, { method: 'DELETE' }),
    claim: (ref: string) => http.request<{ claimed: true; code: string }>(`/customer/offers/${encodeURIComponent(ref)}/claim`, { method: 'POST' }),
    claimed: (service?: string) => http.request<{ results: { offer: string; code: string; title: string; benefit: string }[] }>('/customer/offers/claimed', { query: { service } }),
    mine: () => http.request<MyOffers>('/customer/offers/mine'),
  },
  notifications: {
    list: (q: { group?: string; unread?: boolean; q?: string; page?: number } = {}) =>
      http.request<Page<InboxNotification>>('/customer/notifications', { query: { group: q.group || undefined, unread: q.unread ? 'true' : undefined, q: q.q, page: q.page } }),
    summary: () => http.request<NotificationSummary>('/customer/notifications/summary'),
    read: (id: string) => http.request<InboxNotification>(`/customer/notifications/${id}/read`, { method: 'POST' }),
    unread: (id: string) => http.request<InboxNotification>(`/customer/notifications/${id}/unread`, { method: 'POST' }),
    readAll: (group?: string) => http.request<{ updated: number }>('/customer/notifications/read-all', { method: 'POST', body: group ? { group } : {} }),
    prefs: () => http.request<NotificationPrefs>('/customer/notifications/preferences'),
    setPrefs: (muted: string[]) => http.request<NotificationPrefs>('/customer/notifications/preferences', { method: 'PATCH', body: { muted } }),
  },
  activity: (q: { category?: string; q?: string; status?: string; cursor?: string | null } = {}) =>
    http.request<ActivityPage>('/customer/activity', { query: { category: q.category || undefined, q: q.q || undefined, status: q.status || undefined, cursor: q.cursor || undefined } }),
  support: {
    home: () => http.request<HelpHome>('/support/help', { auth: false }),
    search: (q: string) => http.request<{ results: HelpArticleSummary[] }>('/support/articles', { query: { q }, auth: false }),
    article: (slug: string) => http.request<HelpArticle>(`/support/articles/${slug}`, { auth: false }),
    feedback: (slug: string, helpful: boolean) => http.request<{ helpful: boolean }>(`/support/articles/${slug}/feedback`, { method: 'POST', body: { helpful } }),
    list: (page = 1) => http.request<Page<SupportRequest>>('/customer/support/tickets', { query: { page } }),
    get: (id: string) => http.request<SupportRequest>(`/customer/support/tickets/${id}`),
    create: (input: SupportCreate) => http.request<SupportRequest>('/customer/support/tickets', { method: 'POST', body: input }),
    related: (category: string) => http.request<{ results: SupportRelated[]; issues: string[] }>('/customer/support/related', { query: { category } }),
    messages: (id: string) => http.request<{ results: SupportMessage[] }>(`/customer/support/tickets/${id}/messages`),
    send: (id: string, body: string, file?: File | null) => {
      const form = new FormData();
      if (body) form.append('body', body);
      if (file) form.append('attachment', file);
      return http.request<SupportMessage>(`/customer/support/tickets/${id}/messages`, { method: 'POST', body: form });
    },
    action: (id: string, action: 'close' | 'reopen') => http.request<SupportRequest>(`/customer/support/tickets/${id}/${action}`, { method: 'POST' }),
    attachment: (messageId: string) => {
      if (!http.blob) throw new Error('Downloads are not supported by this client.');
      return http.blob(`/customer/support/attachments/${messageId}`);
    },
  },
});
