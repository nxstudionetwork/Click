import type { HttpClient } from './http';
import type { ISODateTime, Money, UUID } from './types';

/**
 * Click. Bookings (apps/experiences): temples, tourist spots, parks and experiences, plus the central list of every
 * booking across Click. Availability, prices and policies come from the server; information-only places are never
 * presented as bookable.
 */

export type BookingGroup = 'spiritual' | 'tourist' | 'parks' | 'experiences';
export interface AttractionCard {
  id: UUID; slug: string; name: string; kind: string; kindLabel: string; group: BookingGroup; groupLabel: string; city: string; region: string; area: string;
  tagline: string; deity: string; accent: string; imageUrl: string | null; rating: { average: string; count: number } | null; bookable: boolean; verified: boolean;
  instant: boolean; freeCancellation: boolean; fromPrice: Money | null; bookingTypes: string[]; nextAvailable: string | null; officialSource: string;
  durationMinutes: number | null; familyFriendly: boolean; kidsFriendly: boolean; setting: 'indoor' | 'outdoor' | 'both'; distanceKm: number | null;
  favoriteId: string | null; recentBookings: number;
}
export interface BookingsHome {
  groups: { code: BookingGroup; label: string; count: number; kinds: { code: string; label: string; count: number }[] }[];
  services: { code: string; title: string; subtitle: string; link: string; theme: string }[];
  cities: { name: string; region: string; count: number; bookable: number }[];
  sections: { code: string; title: string; subtitle: string; items: AttractionCard[] }[];
  counts: { total: number; bookable: number };
}
export interface BookingsSearchResult {
  count: number; results: AttractionCard[]; hasMore: boolean; elsewhere: { kind: string; title: string; link: string }[];
  filters: { sorts: string[]; near: boolean };
}
export interface SlotState { time: string | null; left: number; status: 'available' | 'sold_out' | 'expired'; label: string }
export interface Offering {
  id: UUID; kind: string; kindLabel: string; bookingModel: 'ticket' | 'slot'; name: string; description: string; includes: string[]; durationMinutes: number | null;
  days: number[]; slotTimes: string[]; maxPerBooking: number; minAge: number | null; pickupPoints: string[]; requirements: string; taxPercent: string; bookAheadDays: number;
  prices: { visitor: string; label: string; note: string; amount: Money; units: number }[];
  calendar: { date: string; status: 'available' | 'sold_out' | 'expired' | 'closed' | 'not_running' | 'too_far' | 'past'; left: number }[];
}
export interface AttractionDetail extends AttractionCard {
  description: string; highlights: string[]; facilities: string[]; accessibility: string[]; rules: string[]; dressCode: string; prohibited: string[]; ageNote: string;
  opening: { days?: number[]; open?: string; close?: string; note?: string } | null; address: string; latitude: number | null; longitude: number | null;
  faqs: { q: string; a: string }[]; officialUrl: string | null; provider: string | null; images: { url: string; caption: string; credit: string }[]; policy: string;
  offerings: Offering[]; reviews: { rating: number; comment: string; author: string; visited: string; offering: string; verified: boolean }[]; related: AttractionCard[];
}
export interface ExperienceReviewInput {
  offeringId: UUID; visitDate: string; slotTime?: string | null; tickets: Record<string, number>; pickupPoint?: string; coupon?: string;
}
export interface ExperienceReview {
  attraction: { id: UUID; slug: string; name: string; kind: string; kindLabel: string; city: string; address: string; accent: string };
  offering: { id: UUID; name: string; kind: string; kindLabel: string; bookingModel: string; requirements: string; durationMinutes: number | null };
  visitDate: string; slotTime: string | null; pickupPoint: string; lines: { visitor: string; label: string; qty: number; unit: Money; amount: Money; units: number }[];
  visitors: number; units: number; subtotal: Money; discount: Money; offer: string | null; tax: Money; total: Money; couponError: string; policy: string;
  refundable: boolean; freeCancelUntil: ISODateTime | null; points: number; instantConfirmation: boolean; holdMinutes: number; bookable: boolean; problem: string; dressCode: string;
}
export interface ExperienceBookingSummary {
  id: UUID; number: string; kind: 'experience'; status: 'pending_payment' | 'confirmed' | 'cancelled' | 'completed' | 'failed'; statusLabel: string;
  paymentStatus: string; paymentStatusLabel: string; title: string;
  attraction: { slug: string; name: string; kind: string; kindLabel: string; group: BookingGroup; city: string; accent: string };
  offering: { name: string; kind: string; kindLabel: string }; visitDate: string; slotTime: string | null; visitors: number; total: Money; createdAt: ISODateTime; isActive: boolean;
}
export interface ExperienceBookingDetail extends ExperienceBookingSummary {
  lines: ExperienceReview['lines']; lead: { name: string; phone: string; email: string }; visitorNames: string[]; pickupPoint: string; subtotal: Money; discount: Money;
  offerTitle: string; tax: Money; refunded: Money; entryCode: string | null; checkedInAt: ISODateTime | null; policy: string; address: string;
  latitude: number | null; longitude: number | null; provider: string | null; requirements: string; dressCode: string; rules: string[]; prohibited: string[];
  holdExpiresAt: ISODateTime | null; timeline: { to: string; label: string; note: string; at: ISODateTime }[];
  payment: { method: string; status: string; statusLabel: string; amount: Money; reference: string } | null;
  refund: { amount: Money; status: string; label: string } | null; cancellation: { allowed: boolean; fee: Money | null; refund: Money | null; note: string };
  canPay: boolean; canReview: boolean; review: { rating: number; comment: string } | null; cancelReason: string; tickets: { id: UUID; reference: string; status: string }[];
  entryNote: string; paymentError?: string;
}
export interface ExperienceBookInput extends ExperienceReviewInput {
  leadName: string; leadPhone: string; leadEmail?: string; visitorNames?: string[]; expectedTotal?: Money | null; idempotencyKey: string;
}
export interface Reservation {
  id: string; kind: 'temple' | 'attraction' | 'experience' | 'travel' | 'hotel' | 'show' | 'event' | 'service'; kindLabel: string; theme: string; reference: string;
  title: string; subtitle: string; when: ISODateTime | null; group: 'upcoming' | 'completed' | 'cancelled'; statusLabel: string; paymentLabel: string; amount: Money | null; link: string;
}

export const experiencesApi = (http: HttpClient) => ({
  home: (params: { city?: string; lat?: number; lng?: number } = {}) =>
    http.request<BookingsHome>('/experiences/home', { query: { city: params.city, lat: params.lat?.toString(), lng: params.lng?.toString() } }),
  search: (params: Record<string, string | undefined>) => http.request<BookingsSearchResult>('/experiences/search', { query: params }),
  attraction: (slug: string) => http.request<AttractionDetail>(`/experiences/attractions/${slug}`),
  availability: (offeringId: string, date: string) =>
    http.request<{ date: string; state: string; reason: string; slots: SlotState[] }>(`/experiences/offerings/${offeringId}/availability`, { query: { date } }),
  review: (input: ExperienceReviewInput) => http.request<ExperienceReview>('/customer/experiences/review', { method: 'POST', body: input }),
  book: (input: ExperienceBookInput) => http.request<ExperienceBookingDetail>('/customer/experiences/bookings', { method: 'POST', body: input }),
  list: () => http.request<{ results: ExperienceBookingSummary[] }>('/customer/experiences/bookings'),
  booking: (id: string) => http.request<ExperienceBookingDetail>(`/customer/experiences/bookings/${id}`),
  act: (id: string, action: 'pay' | 'cancel' | 'review', body: object = {}) =>
    http.request<ExperienceBookingDetail>(`/customer/experiences/bookings/${id}/${action}`, { method: 'POST', body }),
  saved: () => http.request<{ results: AttractionCard[] }>('/customer/experiences/saved'),
  /** Every booking across Click. (Shows, Hotels, Travel, Events, Services, places and experiences), one list. */
  reservations: (group: 'upcoming' | 'completed' | 'cancelled' | 'all', kind?: string) =>
    http.request<{ results: Reservation[]; counts: Record<'upcoming' | 'completed' | 'cancelled' | 'all', number>; unavailable: string[] }>(
      '/customer/reservations', { query: { group, kind } }),
});
