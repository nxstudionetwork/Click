import type { HttpClient } from './http';
import type { ISODateTime, Money, UUID } from './types';

/** Click. Events (apps/eventhub on the backend): plan an event, find teams and venues, quotes, bookings. Attending events
 *  is Click. Showtime; `liveEvents` here are its live events, linked by `path`. Every fact comes from the server. */

export type EventProviderKind = 'team' | 'vendor' | 'venue';
export interface EventTypeInfo { slug: string; name: string; icon: string; accent: string; summary: string; group: string; suggestedServices: string[] }
export interface EventServiceInfo { slug: string; name: string; icon: string; group: string }
export interface GuestBand { code: string; label: string; min: number; max: number }
export interface EventAvailability { state: 'available' | 'booked' | 'unavailable' | 'too_soon'; label: string }
export interface EventProviderCard {
  id: UUID; name: string; kind: EventProviderKind; kindLabel: string; tagline: string; accent: string; logoUrl: string; coverUrl: string;
  verified: boolean; featured: boolean; rating: { average: string; count: number } | null; eventsCompleted: number; experienceYears: number | null;
  teamSize: number | null; area: string; city: string; serviceRadiusKm: number; distanceKm: number | null; services: EventServiceInfo[]; eventTypes: string[];
  priceFrom: { amount: Money; label: string } | null; response: string; availability: EventAvailability | null; capacityOk: boolean | null;
  venue: { spaceType: string; seated: number; floating: number; amenities: string[]; indoor: boolean; outdoor: boolean } | null;
  favoriteId?: string | null;
}
export interface EventPackageInfo {
  id: UUID; name: string; description: string; includes: string[]; basis: 'fixed' | 'per_guest'; price: Money; priceLabel: string;
  minGuests: number; maxGuests: number; durationHours: number; terms: string; services: EventServiceInfo[]; eventTypes: string[];
  addons: { id: UUID; name: string; price: Money; perGuest: boolean }[]; estimate: Money | null;
  provider?: { id: UUID; name: string; kind: EventProviderKind; verified: boolean; accent: string; logoUrl: string; distanceKm: number | null;
    rating: { average: string; count: number } | null };
  favoriteId?: string | null;
}
export interface LiveEvent {
  slug: string; title: string; tagline: string; category: string; imageUrl: string; startsAt: ISODateTime; shows: number; venue: string; area: string;
  distanceKm: number | null; priceFrom: Money | null; path: string; rating: { average: string; count: number } | null;
}
export interface EventsRegistry { eventTypes: EventTypeInfo[]; services: EventServiceInfo[]; guestBands: GuestBand[] }
export interface EventsHome extends EventsRegistry {
  hasLocation: boolean; liveEvents: LiveEvent[]; featured: EventProviderCard[]; teams: EventProviderCard[]; venues: EventProviderCard[];
  packages: EventPackageInfo[]; counts: { teams: number; venues: number; packages: number };
}
export interface EventProviderProfile extends EventProviderCard {
  about: string; languages: string[]; since: ISODateTime; faqs: { q: string; a: string }[]; minNoticeDays: number; maxEventsPerDay: number;
  guestsRange: [number | null, number | null]; unavailableDates: string[]; cancellation: { freeDays: number; feePercent: number };
  packages: EventPackageInfo[]; portfolio: { id: UUID; caption: string; eventType: string; src: string; thumb: string }[];
  reviews: { id: UUID; overall: number; comment: string; createdAt: ISODateTime; verifiedBooking: boolean; eventType: string; author: string }[];
  aspects: { quality?: number; communication?: number; value?: number };
  venue: (EventProviderCard['venue'] & { address: string; rules: string[]; parking: string; cateringPolicy: string; hours: string }) | null;
}
export interface EventsSearch {
  query: string; eventTypes: EventTypeInfo[]; services: EventServiceInfo[]; providers: EventProviderCard[]; packages: EventPackageInfo[]; liveEvents: LiveEvent[];
}
export interface EventQuote {
  id: UUID; version: number; items: { label: string; amount: Money; optional: boolean }[]; amount: Money; tax: Money; total: Money;
  durationHours: number | null; teamSize: number | null; terms: string; notes: string; validUntil: string | null; expired: boolean;
  status: 'pending' | 'accepted' | 'rejected' | 'changes' | 'superseded'; statusLabel: string; customerNote: string; createdAt: ISODateTime;
}
export interface EventEnquiry {
  id: UUID; status: 'requested' | 'quoted' | 'revision' | 'accepted' | 'rejected' | 'provider_declined' | 'withdrawn'; statusLabel: string; message: string;
  createdAt: ISODateTime; provider: { id: UUID; name: string; kind: EventProviderKind; accent: string; logoUrl: string; verified: boolean;
    rating: { average: string; count: number } | null };
  package: { id: UUID; name: string } | null; quotes: EventQuote[]; messages: { id: UUID; fromCustomer: boolean; body: string; at: ISODateTime }[];
  bookingId: UUID | null;
}
export interface EventPlanSummary {
  id: UUID; number: string; title: string; status: 'planning' | 'booked' | 'done' | 'cancelled'; statusLabel: string; eventType: EventTypeInfo;
  date: string | null; dateFlexible: boolean; dateNote: string; startTime: string | null; guests: number; address: Record<string, string>;
  createdAt: ISODateTime; quotesWaiting: number; bookings: number;
}
export interface EventBookingSummary {
  id: UUID; number: string; title: string; status: 'payment_pending' | 'confirmed' | 'preparing' | 'in_progress' | 'completed' | 'cancelled';
  statusLabel: string; paymentStatus: string; paymentStatusLabel: string; eventDate: string; startTime: string | null; guests: number; total: Money;
  createdAt: ISODateTime; isActive: boolean; planId: UUID; reviewed: boolean;
  provider: { id: UUID; name: string; kind: EventProviderKind; accent: string; logoUrl: string; verified: boolean };
}
export interface EventPlanDetail extends EventPlanSummary {
  budget: { min: Money | null; max: Money | null; flexible: boolean }; services: EventServiceInfo[]; requirements: string; needsVenue: boolean;
  attachments: { id: UUID; src: string; thumb: string }[];
  checklist: { id: UUID; label: string; done: boolean; auto: boolean; service: string | null; custom: boolean }[];
  progress: { done: number; total: number }; enquiries: EventEnquiry[]; bookingList: EventBookingSummary[];
}
export interface EventMatch extends EventProviderCard { covers: string[]; coverage: number; packages: EventPackageInfo[]; contacted: boolean }
export interface EventBookingDetail extends EventBookingSummary {
  address: Record<string, string>; lines: { label: string; amount: Money }[]; services: string[]; subtotal: Money; discount: Money; tax: Money;
  refunded: Money; package: string | null; quoteVersion: number | null; teamNote: string; cancelReason: string;
  plan: { id: UUID; number: string; eventType: string; requirements: string; attachments: { id: UUID; src: string; thumb: string }[] };
  milestones: { key: string; label: string; dueDate: string | null; doneAt: ISODateTime | null; note: string }[];
  timeline: { to: string; label: string; note: string; at: ISODateTime }[];
  payment: { method: string; status: string; amount: Money } | null; canPay: boolean; payBy: string;
  cancellation: { allowed: boolean; refund: Money | null; note: string }; canReview: boolean;
  review: { overall: number; quality: number; communication: number; value: number; comment: string } | null;
  tickets: { id: UUID; reference: string; status: string }[]; terms: string;
}
export interface EventEstimate {
  title: string; provider: { id: UUID; name: string; kind: EventProviderKind };
  plan: { id: UUID; number: string; eventType: string; date: string | null; startTime: string | null; address: Record<string, string> };
  guests: number; lines: { label: string; amount: Money }[]; services: string[]; subtotal: Money; discount: Money; tax: Money; total: Money;
  problem: string; bookable: boolean; payLaterAllowed: boolean; cancellation: string; terms: string;
}
export interface PlanInput {
  eventType: string; title?: string; date?: string | null; dateFlexible?: boolean; dateNote?: string; startTime?: string | null; addressId: UUID;
  guests: number; budgetMin?: Money | null; budgetMax?: Money | null; budgetFlexible?: boolean; services: string[]; requirements?: string; attachmentIds?: UUID[];
}
export interface EventBookInput {
  planId: UUID; quoteId?: UUID | null; packageId?: UUID | null; guests?: number | null; addonIds?: UUID[]; optionalItems?: string[];
  paymentMethod?: 'wallet' | 'pay_later'; expectedTotal?: Money | null; idempotencyKey?: string;
}

export const eventHubApi = (http: HttpClient) => ({
  registry: () => http.request<EventsRegistry>('/eventhub/registry'),
  home: (address?: string | null) => http.request<EventsHome>('/eventhub/home', { query: { address: address ?? undefined } }),
  search: (q: string, address?: string | null) => http.request<EventsSearch>('/eventhub/search', { query: { q, address: address ?? undefined } }),
  live: (address?: string | null, q?: string) => http.request<{ results: LiveEvent[] }>('/eventhub/live', { query: { address: address ?? undefined, q } }),
  providers: (params: Record<string, string | undefined>) =>
    http.request<{ count: number; page: number; hasMore: boolean; results: EventProviderCard[] }>('/eventhub/providers', { query: params }),
  provider: (id: string, params: Record<string, string | undefined> = {}) => http.request<EventProviderProfile>(`/eventhub/providers/${id}`, { query: params }),
  upload: (file: File) => {
    const form = new FormData();
    form.append('file', file);
    return http.request<{ id: UUID; src: string; thumb: string }>('/customer/eventhub/attachments', { method: 'POST', body: form });
  },
  removeUpload: (id: string) => http.request<void>(`/customer/eventhub/attachments/${id}`, { method: 'DELETE' }),
  plans: () => http.request<{ results: EventPlanSummary[] }>('/customer/eventhub/plans'),
  createPlan: (input: PlanInput) => http.request<EventPlanDetail>('/customer/eventhub/plans', { method: 'POST', body: input }),
  plan: (id: string) => http.request<EventPlanDetail>(`/customer/eventhub/plans/${id}`),
  cancelPlan: (id: string) => http.request<EventPlanDetail>(`/customer/eventhub/plans/${id}`, { method: 'DELETE' }),
  matches: (id: string, kind?: string) => http.request<{ results: EventMatch[] }>(`/customer/eventhub/plans/${id}/matches`, { query: { kind } }),
  enquire: (id: string, providerIds: string[], message = '', packageId?: string | null) =>
    http.request<EventPlanDetail>(`/customer/eventhub/plans/${id}/enquiries`, { method: 'POST', body: { providerIds, message, packageId: packageId ?? null } }),
  addTask: (id: string, label: string) => http.request<EventPlanDetail>(`/customer/eventhub/plans/${id}/checklist`, { method: 'POST', body: { label } }),
  toggleTask: (id: string, item: string, done: boolean) =>
    http.request<EventPlanDetail>(`/customer/eventhub/plans/${id}/checklist/${item}`, { method: 'PATCH', body: { done } }),
  removeTask: (id: string, item: string) => http.request<EventPlanDetail>(`/customer/eventhub/plans/${id}/checklist/${item}`, { method: 'DELETE' }),
  enquiry: (id: string, action: 'reject' | 'changes' | 'message' | 'withdraw', note = '') =>
    http.request<EventEnquiry>(`/customer/eventhub/enquiries/${id}/${action}`, { method: 'POST', body: { note } }),
  estimate: (input: EventBookInput) => http.request<EventEstimate>('/customer/eventhub/estimate', { method: 'POST', body: input }),
  book: (input: EventBookInput) => http.request<EventBookingDetail>('/customer/eventhub/bookings', { method: 'POST', body: input }),
  bookings: (when?: 'active' | 'past') => http.request<{ results: EventBookingSummary[] }>('/customer/eventhub/bookings', { query: { when } }),
  booking: (id: string) => http.request<EventBookingDetail>(`/customer/eventhub/bookings/${id}`),
  act: (id: string, action: 'pay' | 'cancel' | 'review', body: object = {}) =>
    http.request<EventBookingDetail>(`/customer/eventhub/bookings/${id}/${action}`, { method: 'POST', body }),
  favorites: (address?: string | null) =>
    http.request<{ providers: EventProviderCard[]; packages: EventPackageInfo[] }>('/customer/eventhub/favorites', { query: { address: address ?? undefined } }),
});
