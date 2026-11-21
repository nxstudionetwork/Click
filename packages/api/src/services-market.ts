import type { HttpClient } from './http';
import type { ISODateTime, Money, UUID } from './types';

/** Click. Services (apps/professionals on the backend). Everything shown as fact comes from the server. */

export type PricingModel = 'fixed' | 'starting' | 'hourly' | 'quote';
export type Availability = 'now' | 'today' | 'tomorrow' | 'later' | 'none';
export type ServiceBookingStatus = 'requested' | 'confirmed' | 'on_the_way' | 'arrived' | 'quote_pending' | 'in_progress' | 'completed' | 'paid'
  | 'cancelled' | 'unassigned';

export interface ServiceCategoryInfo {
  slug: string; name: string; profession: string; group: string; groupLabel: string; icon: string; accent: string; summary: string;
  professionals: number | null;
}
export interface ServiceJobInfo {
  id: UUID; slug: string; name: string; description: string; includes: string[]; excludes: string[]; pricing: PricingModel; pricingLabel: string;
  price: Money | null; priceLabel: string; minHours: number; inspectionFee: Money | null; durationMinutes: number; instant: boolean; schedulable: boolean;
  category?: { slug: string; name: string };
}
export interface ProCard {
  id: UUID; name: string; profession: string; photoUrl: string; categories: string[]; experienceYears: number | null;
  rating: { average: string; count: number } | null; jobsCompleted: number; verified: boolean; availability: Availability; availabilityLabel: string;
  distanceKm: number | null; etaMinutes: number | null; price: Money | null; pricing: PricingModel; priceLabel: string; languages: string[]; accent: string;
  favoriteId?: string | null; lastBooking?: { id: UUID; job: string } | null;
}
export interface ServiceOfferInfo {
  id: UUID; title: string; description: string; category: string | null; categoryName: string | null; firstBookingOnly: boolean;
  minAmount: Money | null; endsAt: ISODateTime | null;
}
export interface ServicesHome {
  hasLocation: boolean; categories: ServiceCategoryInfo[]; groups: { code: string; label: string; categories: ServiceCategoryInfo[] }[];
  popular: ProCard[]; availableNow: ProCard[]; trusted: ProCard[]; offers: ServiceOfferInfo[]; unsupportedCategories: string[];
}
export interface ServicesSearch { query: string; categories: ServiceCategoryInfo[]; jobs: ServiceJobInfo[]; professionals: ProCard[] }
export interface ServiceCategoryPage extends Omit<ServiceCategoryInfo, 'professionals'> {
  jobs: ServiceJobInfo[]; offers: ServiceOfferInfo[]; professionals: ProCard[]; hasLocation: boolean;
}
export interface ProProfile extends ProCard {
  about: string; skills: string[]; serviceArea: string; serviceRadiusKm: number; servesLocation: boolean | null; since: ISODateTime;
  certificates: { name: string; issuer: string }[]; portfolio: { id: UUID; caption: string; src: string; thumb: string }[];
  hours: { weekday: number; starts: string; ends: string }[];
  services: (ServiceCategoryInfo & { jobs: ServiceJobInfo[] })[];
  reviews: { id: UUID; overall: number; comment: string; job: string; createdAt: ISODateTime; author: string }[];
  aspects: { quality?: number; behaviour?: number; timeliness?: number }; rates: { responseRate?: number; completionRate?: number };
  favoriteId: string | null; partnerStatus: string;
}
export interface ServiceSlot { start: ISODateTime; end: ISODateTime; day: string; label: string }
export interface ServiceEstimateInput {
  jobId: UUID; providerId?: UUID | null; addressId?: UUID | null; mode: 'now' | 'scheduled'; scheduledStart?: string | null; hours?: number | null;
}
export interface ServiceEstimate {
  job: { id: UUID; name: string; category: string; categorySlug: string; pricing: PricingModel; pricingLabel: string; minHours: number; includes: string[]; excludes: string[]; durationMinutes: number };
  price: Money | null; priceLabel: string; hours: number | null; agreed: Money | null; offer: { title: string; discount: Money } | null; tax: Money | null;
  estimatedTotal: Money | null; inspectionFee: Money | null; additionalCharges: string[]; professionals: number; etaMinutes: number | null;
  slots: ServiceSlot[]; problem: string; bookable: boolean; cancellation: string;
}
export interface ServiceBookInput extends ServiceEstimateInput {
  addressId: UUID; description?: string; attachmentIds?: UUID[]; expectedAmount?: Money | null; idempotencyKey: string; rebookOf?: string | null;
}
export interface ServiceBookingSummary {
  id: UUID; number: string; status: ServiceBookingStatus; statusLabel: string; category: { slug: string; name: string; accent: string; icon: string };
  job: { id: UUID; name: string }; mode: 'now' | 'scheduled'; scheduledStart: ISODateTime | null; addressLabel: string; pricing: PricingModel;
  pricingLabel: string; agreedAmount: Money | null; total: Money | null; createdAt: ISODateTime; isActive: boolean; reviewed: boolean;
  /** Who the customer asked for, until they accept (then `provider` is set). */
  requestedProvider?: { id: UUID; name: string } | null;
  provider: { id: UUID; name: string; profession: string; photoUrl: string; rating: { average: string; count: number } | null; verified: boolean } | null;
}
export interface ServiceBookingDetail extends ServiceBookingSummary {
  address: Record<string, string>; description: string; unitPrice: Money | null; priceLabel: string; hours: number | null; billedHours: string | null;
  inspectionFee: Money | null; excludes: string[]; discount: Money; offerTitle: string; tax: Money; paymentMethod: string; etaMinutes: number | null;
  acceptedAt: ISODateTime | null; timeline: { to: ServiceBookingStatus; label: string; note: string; at: ISODateTime }[];
  quotes: { id: UUID; amount: Money; note: string; status: 'pending' | 'approved' | 'declined'; createdAt: ISODateTime }[];
  photos: { id: UUID; src: string; thumb: string }[]; payment: { method: string; status: string; amount: Money } | null;
  cancellation: { allowed: boolean; note: string }; canPay: boolean; awaitingCash: boolean; canReview: boolean;
  review: { overall: number; quality: number; behaviour: number; timeliness: number; comment: string } | null;
  tickets: { id: UUID; reference: string; status: string }[]; tracking: 'status_only';
}
export interface ServiceReviewInput { overall: number; quality: number; behaviour: number; timeliness: number; comment?: string }

export const servicesApi = (http: HttpClient) => ({
  home: (q: { address?: string | null }) => http.request<ServicesHome>('/services/home', { query: { address: q.address ?? undefined } }),
  search: (q: string, address?: string | null) => http.request<ServicesSearch>('/services/search', { query: { q, address: address ?? undefined } }),
  category: (slug: string, params: Record<string, string | undefined>) =>
    http.request<ServiceCategoryPage>(`/services/categories/${encodeURIComponent(slug)}`, { query: params }),
  provider: (id: string, address?: string | null) => http.request<ProProfile>(`/services/providers/${id}`, { query: { address: address ?? undefined } }),
  slots: (id: string, jobId: string) => http.request<{ availableNow: boolean; slots: ServiceSlot[] }>(`/services/providers/${id}/slots`, { query: { job: jobId } }),
  upload: (file: File) => {
    const form = new FormData();
    form.append('file', file);
    return http.request<{ id: UUID; src: string; thumb: string }>('/customer/services/attachments', { method: 'POST', body: form });
  },
  removeUpload: (id: string) => http.request<void>(`/customer/services/attachments/${id}`, { method: 'DELETE' }),
  estimate: (input: ServiceEstimateInput) => http.request<ServiceEstimate>('/customer/services/estimate', { method: 'POST', body: input }),
  book: (input: ServiceBookInput) => http.request<ServiceBookingDetail>('/customer/services/bookings', { method: 'POST', body: input }),
  bookings: (when?: 'upcoming' | 'active' | 'completed' | 'cancelled') =>
    http.request<{ results: ServiceBookingSummary[] }>('/customer/services/bookings', { query: { when } }),
  booking: (id: string) => http.request<ServiceBookingDetail>(`/customer/services/bookings/${id}`),
  act: (id: string, action: 'cancel' | 'quote' | 'pay' | 'review', body: object) =>
    http.request<ServiceBookingDetail>(`/customer/services/bookings/${id}/${action}`, { method: 'POST', body }),
  rebook: (id: string) => http.request<{ category: string; jobId: UUID; providerId: UUID | null; addressId: UUID | null; hours: number | null;
    description: string; rebookOf: UUID }>(`/customer/services/bookings/${id}/rebook`),
  need: (input: { text: string; addressId?: string | null; preferredTime?: string; attachmentIds?: string[] }) =>
    http.request<{ id: UUID; status: string }>('/customer/services/needs', { method: 'POST', body: input }),
  favorites: (address?: string | null) => http.request<{ results: ProCard[] }>('/customer/services/favorites', { query: { address: address ?? undefined } }),
});
