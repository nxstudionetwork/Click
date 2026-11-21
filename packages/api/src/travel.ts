import type { HttpClient } from './http';
import type { ISODateTime, Money, UUID } from './types';

/** Click. Travel (apps/travel): bus, train and flight. Availability, fares, seats and policies all come from the server. */

export type TravelMode = 'bus' | 'train' | 'flight';
export interface TravelPlace {
  id: UUID; slug: string; kind: 'city' | 'airport' | 'station' | 'bus_stop'; kindLabel: string; name: string; code: string; city: string; citySlug: string;
  state: string; label: string;
}
export interface TravelAvailability { status: 'available' | 'rac' | 'waitlist' | 'not_available'; count: number; label: string }
export interface TravelClass {
  code: string; name: string; fareType: string; fare: Money; fees: Money; tax: Money; perPerson: Money; availability: TravelAvailability; bookable: boolean;
  refundable: boolean; meal: string; changeFee: Money | null; infantFare: Money | null;
}
export interface TravelStopPoint { stopId: UUID; placeId: UUID; name: string; code: string; kind: string; city: string; address: string; landmark: string; note: string; at: ISODateTime }
export interface TravelOption {
  id: string; mode: TravelMode; journeyId: UUID; fromStopId: UUID; toStopId: UUID;
  operator: { id: UUID; name: string; code: string; accent: string; logoUrl: string | null; rating: { average: string; count: number } | null };
  service: { number: string; name: string; vehicle: string; busType: string; busTypeLabel: string; ac: boolean; premium: boolean; amenities: string[];
    runningDays: number[]; baggage: { cabin?: string; checkIn?: string } | null };
  departsAt: ISODateTime; arrivesAt: ISODateTime; durationMinutes: number; daysLater: number; from: TravelStopPoint; to: TravelStopPoint; stops: number; via: string[];
  distanceKm: number; classes: TravelClass[]; lowest: Money | null; available: boolean; refundable: boolean; cancellation: 'free' | 'partial' | 'non_refundable';
  policy: string; status: 'scheduled' | 'delayed' | 'cancelled'; statusLabel: string; delayMinutes: number; notice: string; depBucket: string; arrBucket: string;
  seatsLeft?: number; boardingPoints?: TravelStopPoint[]; droppingPoints?: TravelStopPoint[]; highlights?: ('cheapest' | 'fastest' | 'best_value')[];
}
export interface TravelSearchQuery {
  mode: TravelMode; origin: string; destination: string; date: string; returnDate?: string | null; adults: number; children: number; infants: number; travelClass?: string;
}
export interface TravelSearchResult {
  query: { mode: TravelMode; origin: TravelPlace; destination: TravelPlace; date: string; returnDate: string | null; adults: number; children: number; infants: number; travelClass: string };
  count: number; total: number; results: TravelOption[]; hasMore: boolean;
  strip: { key: 'cheapest' | 'fastest' | 'best_value'; label: string; id: string; total: Money; durationMinutes: number; departsAt: ISODateTime; operator: string }[];
  facets: { operators: { id: UUID; name: string }[]; price: { min: Money | null; max: Money | null }; amenities: string[]; departure: { code: string; label: string }[];
    cancellation: string[]; boarding?: { id: UUID; name: string }[]; dropping?: { id: UUID; name: string }[]; trainTypes?: string[] };
  alternatives: { mode: TravelMode; count: number; lowest: Money | null }[]; savedRouteId: string | null; fareNote: string;
}
export interface TravelRoute { mode: TravelMode; from: TravelPlace; to: TravelPlace; km: number; services: number; fromPrice: Money | null; minutes: number | null }
export interface TravelHome {
  routes: Record<TravelMode, TravelRoute[]>; fromCity: TravelRoute[]; collections: { code: string; title: string; subtitle: string; routes: TravelRoute[] }[];
  offers: { id: UUID; title: string; mode: TravelMode | null; code: string | null; percent: number; maxDiscount: string | null; minFare: string | null; endsAt: ISODateTime }[];
  trainClasses: { code: string; name: string }[]; cabins: { code: string; name: string }[]; maxPassengers: Record<TravelMode, number>; priceNote: string;
}
export interface SeatInfo { class: string; kind: 'seater' | 'sleeper'; status: 'available' | 'sold' | 'blocked'; ladies: boolean; gents: boolean; fare: Money }
export interface TravelOptionDetail extends TravelOption {
  route: { name: string; code: string; city: string; arrive: ISODateTime | null; depart: ISODateTime | null; km: number; day: number; note: string; inSegment: boolean }[];
  bookableNow: boolean; seatMap?: { decks: { name: string; rows: (string | null)[][] }[]; seats: Record<string, SeatInfo>; max: number };
  policyRules: { hours: number; feePercent: number }[]; source: string; savedRouteId: string | null;
}
export interface TravelPassengerInput { name: string; age: number; gender: 'female' | 'male' | 'other'; berthPreference?: string }
export interface TravelReviewInput {
  journeyId: UUID; fromStopId: UUID; toStopId: UUID; classCode: string; passengers: TravelPassengerInput[]; infants?: number; seats?: string[]; coupon?: string;
}
export interface TravelReview {
  journey: { journeyId: UUID; mode: TravelMode; operator: string; number: string; name: string; vehicle: string; classCode: string; className: string; fareType: string;
    from: string; fromCity: string; to: string; toCity: string; departsAt: ISODateTime; arrivesAt: ISODateTime; durationMinutes: number;
    baggage: { cabin?: string; checkIn?: string } | null; status: string; notice: string };
  passengers: (TravelPassengerInput & { status: 'CNF' | 'RAC' | 'WL' | 'NA'; seat: string; berth: string; queue: number })[];
  infants: number; unitFare: Money; baseFare: Money; fees: Money; discount: Money; offer: string | null; tax: Money; total: Money; lines: { label: string; amount: Money }[];
  couponError: string; refundable: boolean; policy: string; changeFee: Money | null; points: number; holdMinutes: number; bookable: boolean; problem: string; statusNote: string;
}
export interface TravelBookingSummary {
  id: UUID; number: string; kind: 'travel'; mode: TravelMode; modeLabel: string; pnr: string; status: 'pending_payment' | 'confirmed' | 'cancelled' | 'completed' | 'failed';
  statusLabel: string; paymentStatus: string; paymentStatusLabel: string; operator: string; service: string; className: string;
  from: { name: string; city: string; code: string }; to: { name: string; city: string; code: string }; departsAt: ISODateTime; arrivesAt: ISODateTime;
  passengersCount: number; total: Money; createdAt: ISODateTime; isActive: boolean; journeyStatus: string; journeyStatusLabel: string; delayMinutes: number; notice: string;
}
export interface TravelPassenger {
  position: number; name: string; age: number; gender: string; genderLabel: string; seat: string; status: 'CNF' | 'RAC' | 'WL' | 'CAN'; statusLabel: string; queue: number;
  berthPreference: string; fare: Money;
}
export interface TravelBookingDetail extends TravelBookingSummary {
  tripRef: string; contact: { phone: string; email: string }; passengers: TravelPassenger[]; infants: number;
  fromFull: { label: string; address: string; landmark: string; note: string }; toFull: { label: string; address: string; landmark: string; note: string };
  durationMinutes: number; vehicle: string; baggage: { cabin?: string; checkIn?: string } | null; baseFare: Money; fees: Money; discount: Money; offerTitle: string;
  tax: Money; refunded: Money; refundable: boolean; policy: string; holdExpiresAt: ISODateTime | null;
  timeline: { to: string; label: string; note: string; at: ISODateTime }[];
  payment: { method: string; status: string; statusLabel: string; amount: Money; reference: string } | null;
  refund: { amount: Money; status: string; label: string; to: string } | null;
  cancellation: { allowed: boolean; fee: Money | null; refund: Money | null; feePercent: number | null; note: string; refundTo?: string };
  canPay: boolean; hasTicket: boolean; cancelReason: string; canRate: boolean; rating: { rating: number; comment: string } | null;
  tickets: { id: UUID; reference: string; status: string }[]; points: number; modification: string; paymentError?: string;
}
export interface TravelTicket {
  number: string; pnr: string; mode: TravelMode; modeLabel: string; operator: string; service: string; className: string; vehicle: string;
  from: TravelBookingSummary['from']; to: TravelBookingSummary['to']; fromFull: TravelBookingDetail['fromFull']; toFull: TravelBookingDetail['toFull'];
  departsAt: ISODateTime; arrivesAt: ISODateTime; durationMinutes: number; passengers: TravelPassenger[]; infants: number; baggage: TravelBookingDetail['baggage'];
  total: Money; status: string; statusLabel: string; journeyStatus: string; notice: string; issuedAt: ISODateTime | null; instructions: string[]; issuer: string;
  code: string | null; codeNote: string;
}
export interface TravelBookInput extends TravelReviewInput {
  contactPhone: string; contactEmail?: string; expectedTotal?: Money | null; idempotencyKey: string; tripRef?: string; saveTravellers?: boolean;
}
export interface SavedTraveller { id: UUID; name: string; age: number; gender: 'female' | 'male' | 'other'; berthPreference: string }
export interface RecentTravelSearch {
  id: UUID; mode: TravelMode; origin: TravelPlace; destination: TravelPlace; date: string; returnDate: string | null; adults: number; children: number; infants: number; travelClass: string;
}
export interface TravelPriceAlert {
  id: UUID; mode: TravelMode; origin: TravelPlace; destination: TravelPlace; date: string; lastFare: Money | null; lastCheckedAt: ISODateTime | null; isActive: boolean;
}
export interface TravelPreferences {
  busTypes: string[]; busDeparture: string; trainClass: string; berth: string; flightCabin: string; nonstop: boolean; airlines: string[];
  airlineOptions: { id: UUID; name: string }[];
}

const q = (s: TravelSearchQuery) => ({
  mode: s.mode, origin: s.origin, destination: s.destination, date: s.date, return_date: s.returnDate || undefined, adults: String(s.adults),
  children: String(s.children), infants: String(s.infants), travel_class: s.travelClass || undefined,
});

export const travelApi = (http: HttpClient) => ({
  home: (city?: string) => http.request<TravelHome>('/travel/home', { query: { city } }),
  places: (qs: string, mode?: TravelMode) => http.request<{ results: TravelPlace[] }>('/travel/places', { query: { q: qs, mode } }),
  search: (s: TravelSearchQuery, extra: Record<string, string | undefined> = {}) =>
    http.request<TravelSearchResult>('/travel/search', { query: { ...q(s), ...extra } }),
  dates: (s: TravelSearchQuery) => http.request<{ results: { date: string; lowest: Money | null }[] }>('/travel/dates', { query: q(s) }),
  option: (journey: string, from: string, to: string, seats = 1) =>
    http.request<TravelOptionDetail>(`/travel/options/${journey}/${from}/${to}`, { query: { seats: String(seats) } }),
  review: (input: TravelReviewInput) => http.request<TravelReview>('/customer/travel/review', { method: 'POST', body: input }),
  book: (input: TravelBookInput) => http.request<TravelBookingDetail>('/customer/travel/bookings', { method: 'POST', body: input }),
  bookings: (when?: 'upcoming' | 'past' | 'cancelled') => http.request<{ results: TravelBookingSummary[] }>('/customer/travel/bookings', { query: { when } }),
  booking: (id: string) => http.request<TravelBookingDetail>(`/customer/travel/bookings/${id}`),
  ticket: (id: string) => http.request<TravelTicket>(`/customer/travel/bookings/${id}/ticket`),
  act: (id: string, action: 'pay' | 'cancel' | 'rate', body: object = {}) =>
    http.request<TravelBookingDetail>(`/customer/travel/bookings/${id}/${action}`, { method: 'POST', body }),
  next: () => http.request<{ booking: TravelBookingSummary | null }>('/customer/travel/next'),
  recent: () => http.request<{ results: RecentTravelSearch[] }>('/customer/travel/recent'),
  clearRecent: () => http.request<void>('/customer/travel/recent', { method: 'DELETE' }),
  routes: () => http.request<{ results: { favoriteId: string; origin: TravelPlace; destination: TravelPlace }[] }>('/customer/travel/routes'),
  saveRoute: (origin: string, destination: string) =>
    http.request<{ favoriteId: string }>('/customer/travel/routes', { method: 'POST', body: { origin, destination } }),
  travellers: () => http.request<{ results: SavedTraveller[] }>('/customer/travel/travellers'),
  addTraveller: (t: Omit<SavedTraveller, 'id'>) => http.request<SavedTraveller>('/customer/travel/travellers', { method: 'POST', body: t }),
  updateTraveller: (id: string, t: Partial<Omit<SavedTraveller, 'id'>>) => http.request<SavedTraveller>(`/customer/travel/travellers/${id}`, { method: 'PATCH', body: t }),
  removeTraveller: (id: string) => http.request<void>(`/customer/travel/travellers/${id}`, { method: 'DELETE' }),
  alerts: () => http.request<{ results: TravelPriceAlert[] }>('/customer/travel/alerts'),
  addAlert: (a: { origin: string; destination: string; mode: TravelMode; date: string }) =>
    http.request<TravelPriceAlert>('/customer/travel/alerts', { method: 'POST', body: a }),
  removeAlert: (id: string) => http.request<void>(`/customer/travel/alerts/${id}`, { method: 'DELETE' }),
  preferences: () => http.request<TravelPreferences>('/customer/travel/preferences'),
  savePreferences: (p: Partial<TravelPreferences>) => http.request<TravelPreferences>('/customer/travel/preferences', { method: 'PATCH', body: p }),
});
