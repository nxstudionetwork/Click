/** Click. Showtime API shapes. Mirrors backend/apps/bookings/showtime.py and views.py. */
import type { ISODateTime, Money, UUID } from './types';

export interface ShowtimeTitle {
  id: UUID;
  slug: string;
  kind: 'movie' | 'event';
  status: 'now_showing' | 'coming_soon';
  title: string;
  tagline: string;
  posterUrl: string;
  backdropUrl: string;
  /** A licensed video file; empty when the title has no trailer. */
  trailerUrl: string;
  /** Attribution/licence for artwork and trailer (shown where they appear). */
  mediaCredit: string;
  languages: string[];
  genres: string[];
  certification: string;
  durationMinutes: number | null;
  releaseDate: string | null;
  /** Only once enough verified-attendance reviews exist; null otherwise. */
  rating: number | null;
  ratingCount: number;
  formats: string[];
  nextShowAt: ISODateTime | null;
  venueCount: number;
  bookable: boolean;
  /** Signed-in customers only: whether they follow this title. */
  interested: boolean | null;
}

export interface TonightTitle extends ShowtimeTitle { tonightCount: number; tonightFirst: ISODateTime; nearestKm: number | null }

export interface ShowtimeCinema {
  id: UUID;
  slug: string;
  name: string;
  kind: string;
  locality: string;
  city: string;
  address: string;
  /** Only when both your location and the cinema's are known. */
  distanceKm: number | null;
  facilities: string[];
  formats: string[];
  sound: string[];
  showsToday: number;
  nextShow: { title: string; slug: string; startsAt: ISODateTime } | null;
  latitude: number | null;
  longitude: number | null;
}

export interface ShowtimeSection {
  id: 'tonight' | 'now_showing' | 'coming_soon' | 'trending' | 'top_rated' | 'trailers' | 'live';
  kind: 'titles' | 'coming' | 'trailers' | 'tonight';
  title: string;
  subtitle: string | null;
  link: string | null;
  titles: (ShowtimeTitle & Partial<TonightTitle>)[];
}

export interface ShowtimeOffer { id: UUID; title: string; description: string; venue: string | null; titleSlug: string | null; paymentMethod: string; minSeats: number; endsAt: ISODateTime | null }

export interface ShowtimeHome {
  featured: (ShowtimeTitle & { headline: string; description: string }) | null;
  highlights: ShowtimeTitle[];
  sections: ShowtimeSection[];
  cinemas: ShowtimeCinema[];
  formats: { code: string; label: string; titleCount: number; venueCount: number }[];
  offers: ShowtimeOffer[];
  filters: { languages: string[]; genres: string[]; formats: string[] };
  locationUsed: boolean;
}

export interface ShowtimeSearchResult {
  query: string;
  /** Only what the search recognised and applied. */
  understood: { kind: string; label: string }[];
  count: number;
  titles: ShowtimeTitle[];
  cinemas: ShowtimeCinema[];
  people: { name: string; role: 'cast' | 'crew'; titleCount: number }[];
  applied: { language: string | null; genre: string | null; format: string | null; when: string | null; kind: string | null; status: string | null };
}

export interface ShowtimeSuggestions {
  query: string;
  suggestions: { text: string; kind: 'title' | 'title_language' | 'cinema' | 'person'; path: string }[];
  trending: string[];
  popular: { title: string; slug: string }[];
}

export interface ShowtimeTime {
  showId: UUID;
  startsAt: ISODateTime;
  screen: string;
  seatsLeft: number;
  status: 'available' | 'filling_fast' | 'sold_out';
  priceFrom: Money;
  priceTo: Money;
  currency: string;
  sound: string;
}

export interface ShowtimeVenueSchedule {
  venue: { id: UUID; slug: string; name: string; kind: string; locality: string; address: string; city: string; facilities: string[]; hasFood: boolean; latitude: number | null; longitude: number | null };
  distanceKm: number | null;
  groups: { format: string; language: string; times: ShowtimeTime[] }[];
}

export interface ShowtimeReview { id: UUID; rating: number; body: string; author: string; verified: boolean; createdAt: ISODateTime; edited: boolean }

export interface ShowtimeTitleDetail extends ShowtimeTitle {
  description: string;
  credits: { name: string; role: 'cast' | 'crew'; part: string }[];
  /** Local dates with showtimes (next two weeks); `date` is the one shown. */
  dates: string[];
  date: string | null;
  allFormats: string[];
  allLanguages: string[];
  schedule: ShowtimeVenueSchedule[];
  filters: { format: string | null; language: string | null };
  ratingSummary: { average: number | null; count: number; minimum: number; distribution: Record<string, number> };
  reviews: ShowtimeReview[];
  myReview: ShowtimeReview | null;
  canReview: boolean;
  interestCount: number | null;
  offers: ShowtimeOffer[];
  related: ShowtimeTitle[];
  locationUsed: boolean;
}

export type SeatState = 'available' | 'booked' | 'held' | 'mine' | 'unavailable';

export interface ShowtimeSeatMap {
  id: UUID;
  startsAt: ISODateTime;
  format: string;
  language: string;
  screen: string;
  sound: string;
  currency: string;
  event: ShowtimeTitle;
  venue: { id: UUID; slug: string; name: string; locality: string; address: string; city: string; facilities: string[]; latitude: number | null; longitude: number | null };
  tiers: { code: string; name: string; price: Money }[];
  /** Front (nearest the screen) to back. `gaps` = aisle after seat N. */
  rows: { row: string; tier: string; gaps: number[]; seats: { label: string; number: number; accessible: boolean; state: SeatState }[] }[];
  maxPerBooking: number;
  holdMinutes: number;
  myHold: { id: UUID; expiresAt: ISODateTime; seats: string[] } | null;
  cancellationHours: number;
}

export interface SeatHold { id: UUID; showId: UUID; expiresAt: ISODateTime; seats: { label: string; tier: string; price: Money }[] }

export interface ShowtimeQuote {
  hold: SeatHold;
  lines: { tickets: Money; convenienceFee: Money; concessions: Money; tax: Money; discount: Money; total: Money };
  offer: { id: UUID; title: string } | null;
  offerProblem: string | null;
  concessions: { id: UUID; name: string; quantity: number; lineTotal: Money }[];
  menu: { id: UUID; name: string; description: string; category: string; categoryLabel: string; price: Money; isVeg: boolean; imageUrl: string }[];
  offers: { id: UUID; title: string; description: string; paymentMethod: string; problem: string | null; saving: Money | null }[];
  currency: string;
}

export interface ShowtimeQuoteInput { holdId: string; concessions?: { id: string; quantity: number }[]; offerId?: string | null; paymentMethod?: 'pay_at_venue' | 'wallet' | null }
