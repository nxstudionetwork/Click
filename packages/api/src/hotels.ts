import type { HttpClient } from './http';
import type { ISODateTime, Money, UUID } from './types';

/** Click. Hotels (apps/hotels on the backend). Prices, availability, ratings and policies all come from the server. */

export interface HotelAmenity { slug: string; name: string; icon: string }
export interface HotelRating { average: string; count: number; label: string }
export interface StayQuery { checkIn: string; checkOut: string; adults: number; children: number; rooms: number }
export interface HotelCard {
  id: UUID; name: string; type: string; typeLabel: string; starRating: number | null; tagline: string; area: string; destination: string; accent: string;
  imageUrl: string; photos: number; rating: HotelRating | null; distanceKm: number | null; distanceFrom: string; amenities: HotelAmenity[];
  room: string; roomsLeft: number | null; mealLabel: string; breakfast: boolean; freeCancellation: boolean; cancellation: string; payAtProperty: boolean;
  offer: string | null; price: { perNight: Money; total: Money; tax: Money; beforeDiscount: Money | null; nights: number; rooms: number };
  highlights: string[]; favoriteId?: string | null;
}
export interface HotelSearchResult {
  destination: { slug: string; name: string; region: string } | null; measuredFrom?: string; count: number; page: number; hasMore: boolean;
  results: HotelCard[]; landmarks?: { id: UUID; name: string; kind: string; kindLabel: string }[];
}
export interface HotelFilters {
  types: { value: string; label: string }[]; amenities: HotelAmenity[]; roomClasses: { value: string; label: string }[];
  sorts: { value: string; label: string }[]; guestRatings: { value: number; label: string }[];
}
export interface HotelsHome {
  destinations: { slug: string; name: string; region: string; tagline: string; tags: string[]; properties: number; fromPrice: Money | null }[];
  collections: { code: string; title: string; subtitle: string; properties: number; destinations: string[]; fromPrice: Money | null }[];
  filters: HotelFilters; offers: { id: UUID; title: string; kind: string; kindLabel: string; percent: number; property: string | null; minNights: number; conditions: string }[];
  priceNote: string;
}
export interface RateOption {
  rateId: UUID; rateName: string; mealPlan: string; mealLabel: string; refundable: boolean; freeCancelUntil: ISODateTime | null; cancelFeePercent: number;
  policy: string; payment: 'pay_now' | 'at_property' | 'either'; paymentLabel: string; perNight: Money | null; nightly: { date: string; price: Money }[];
  roomTotal: Money; discount: Money; offer: string | null; tax: Money; total: Money; roomsLeft: number; problem: string;
}
export interface RoomOption {
  id: UUID; name: string; roomClass: string; roomClassLabel: string; beds: string; maxAdults: number; maxChildren: number; maxOccupancy: number;
  sizeSqm: number | null; view: string; description: string; imageUrl: string; amenities: HotelAmenity[]; fits: boolean; rates: RateOption[];
}
export interface HotelReviewItem {
  id: UUID; overall: number; title: string; comment: string; traveller: string; stayed: string; nights: number; room: string; author: string;
  createdAt: ISODateTime; verifiedStay: boolean;
}
export interface HotelDetail {
  id: UUID; name: string; type: string; typeLabel: string; starRating: number | null; tagline: string; description: string; highlights: string[];
  destination: { slug: string; name: string }; area: string; address: string; latitude: number; longitude: number; accent: string;
  rating: HotelRating | null; aspects: Partial<Record<'cleanliness' | 'location' | 'comfort' | 'facilities' | 'staff' | 'value', number>>;
  amenities: HotelAmenity[]; checkInTime: string; checkOutTime: string; languages: string[]; policies: string[]; accessibility: string; parking: string;
  goodFor: string[]; paymentOptions: string[]; mealOptions: string[]; distances: { name: string; kind: string; kindLabel: string; km: number | null }[];
  distanceFromCentre: number | null; nearby: { name: string; km: number }[];
  images: { id: UUID; category: string; caption: string; src: string; thumb: string }[]; favoriteId: string | null;
  rooms: RoomOption[] | null; stay: StayQuery | null; offers: { title: string; percent: number; conditions: string }[]; reviews: HotelReviewItem[];
}
export interface HotelReview {
  property: { id: UUID; name: string; address: string; typeLabel: string; checkInTime: string; checkOutTime: string; policies: string[]; starRating: number | null };
  room: { id: UUID; name: string; beds: string; maxAdults: number; maxChildren: number };
  stay: { checkIn: string; checkOut: string; nights: number; rooms: number; adults: number; children: number };
  rateId: UUID; rateName: string; mealLabel: string; refundable: boolean; policy: string; payment: RateOption['payment']; paymentLabel: string;
  nightly: { date: string; price: Money }[]; roomTotal: Money; discount: Money; offer: string | null; tax: Money; total: Money; roomsLeft: number;
  bookable: boolean; problem: string; holdMinutes: number; taxNote: string;
}
export interface HotelBookingSummary {
  id: UUID; number: string; kind: 'hotel'; status: 'pending_payment' | 'confirmed' | 'cancelled' | 'completed' | 'failed'; statusLabel: string;
  paymentStatus: string; paymentStatusLabel: string;
  property: { id: UUID; name: string; area: string; destination: string; imageUrl: string; accent: string };
  roomName: string; checkIn: string; checkOut: string; nights: number; rooms: number; adults: number; children: number; total: Money; createdAt: ISODateTime;
  isActive: boolean; reviewed: boolean;
}
export interface HotelBookingDetail extends HotelBookingSummary {
  guest: { name: string; email: string; phone: string; others: string[] }; specialRequests: string; rateName: string; mealPlan: string; mealLabel: string;
  paymentMode: string; paymentModeLabel: string; policy: string; refundable: boolean; freeCancelUntil: ISODateTime | null;
  nightly: { date: string; price: Money }[]; roomTotal: Money; discount: Money; offerTitle: string; tax: Money; refunded: Money; address: string;
  latitude: number; longitude: number; checkInTime: string; checkOutTime: string; policies: string[]; holdExpiresAt: ISODateTime | null;
  timeline: { to: string; label: string; note: string; at: ISODateTime }[]; payment: { method: string; status: string; amount: Money; reference: string } | null;
  cancellation: { allowed: boolean; fee: Money | null; refund: Money | null; note: string }; canPay: boolean; canReview: boolean;
  review: { overall: number; comment: string } | null; cancelReason: string; tickets: { id: UUID; reference: string; status: string }[]; modification: string;
  paymentError?: string;
}
export interface HotelBookInput extends StayQuery {
  rateId: UUID; coupon?: string; guestName: string; guestEmail?: string; guestPhone: string; otherGuests?: string[]; specialRequests?: string;
  paymentMode?: 'pay_now' | 'at_property'; expectedTotal?: Money | null; idempotencyKey: string;
}
export interface SavedHotel {
  id: UUID; name: string; typeLabel: string; starRating: number | null; area: string; destination: string; imageUrl: string; accent: string;
  rating: HotelRating | null; fromPrice: Money | null; favoriteId: string;
}

const stay = (s: StayQuery) => ({ check_in: s.checkIn, check_out: s.checkOut, adults: String(s.adults), children: String(s.children), rooms: String(s.rooms) });

export const hotelsApi = (http: HttpClient) => ({
  home: () => http.request<HotelsHome>('/hotels/home'),
  destinations: (q: string) => http.request<{ results: { kind: 'destination' | 'landmark' | 'property'; value: string; label: string; detail: string }[] }>(
    '/hotels/destinations', { query: { q } }),
  search: (params: Record<string, string | undefined>) => http.request<HotelSearchResult>('/hotels/search', { query: params }),
  property: (id: string, s?: StayQuery | null) => http.request<HotelDetail>(`/hotels/properties/${id}`, { query: s ? stay(s) : {} }),
  reviews: (id: string, sort: string, page = 1) =>
    http.request<{ count: number; aspects: HotelDetail['aspects']; results: HotelReviewItem[]; hasMore: boolean }>(`/hotels/properties/${id}/reviews`, { query: { sort, page: String(page) } }),
  compare: (ids: string[], s: StayQuery) =>
    http.request<{ results: { id: UUID; name: string; typeLabel: string; starRating: number | null; area: string; imageUrl: string; rating: { average: string; count: number } | null;
      amenities: string[]; checkInTime: string; cheapest: { room: string; meal: string; total: Money; policy: string; payment: string } | null }[] }>(
      '/hotels/compare', { query: { ids: ids.join(','), ...stay(s) } }),
  review: (input: { rateId: string; coupon?: string } & StayQuery) => http.request<HotelReview>('/customer/hotels/review', { method: 'POST', body: input }),
  book: (input: HotelBookInput) => http.request<HotelBookingDetail>('/customer/hotels/bookings', { method: 'POST', body: input }),
  bookings: (when?: 'upcoming' | 'past') => http.request<{ results: HotelBookingSummary[] }>('/customer/hotels/bookings', { query: { when } }),
  booking: (id: string) => http.request<HotelBookingDetail>(`/customer/hotels/bookings/${id}`),
  act: (id: string, action: 'pay' | 'cancel' | 'review', body: object = {}) =>
    http.request<HotelBookingDetail>(`/customer/hotels/bookings/${id}/${action}`, { method: 'POST', body }),
  saved: () => http.request<{ results: SavedHotel[] }>('/customer/hotels/saved'),
});
