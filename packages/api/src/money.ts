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
export interface PaymentsOverview {
  methods: { code: string; label: string; description: string; where: string; canDefault: boolean; default: boolean; detail: string }[];
  defaultMethod: string; onlineMethods: { available: boolean; note: string };
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
export type SupportCreate = { category: string; issueType?: string; subject: string; message: string; idempotencyKey?: string } & Partial<Record<SupportLink, string>>;

/** The related-item type (from the API) → the field a new request sends it in. */
export const SUPPORT_LINK_FIELD: Record<string, SupportLink> = {
  order: 'orderId', parcel: 'parcelId', service_booking: 'serviceBookingId', event_booking: 'eventBookingId', hotel_booking: 'hotelBookingId',
  travel_booking: 'travelBookingId', experience_booking: 'experienceBookingId', ride: 'rideId', show_booking: 'showBookingId', payment: 'paymentId',
  wallet_transaction: 'walletTransactionId',
};

type Page<T> = { results: T[]; hasNext: boolean; page: number; count?: number };

export const moneyApi = (http: HttpClient) => ({
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
