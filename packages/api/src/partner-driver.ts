import type { HttpClient } from './http';
import type { Money, UUID } from './types';

/**
 * Click Partner — Driver mode (/partner/driver/* on the backend, apps/rides/driver.py) and verification documents
 * (/partner/documents, every partner type). The server resolves the driver from the signed-in partner.
 */

export type DocumentState = 'missing' | 'pending' | 'verified' | 'expiring' | 'expired' | 'rejected';
export interface PartnerDocumentStatus {
  key: string; label: string; required: boolean; expires: boolean; help: string; state: DocumentState; stateLabel: string;
  number: string; expiresOn: string | null; reviewNote: string; canSubmit: boolean;
}
export interface PartnerDocuments { documents: PartnerDocumentStatus[]; blockedReason: string }

export interface DriverPublicIdentity {
  name: string; rating: number | null; ratingCount: number; vehicleType: string; vehicleModel: string; vehicleColor: string; plate: string;
}

export interface DriverProfile {
  partnerCode: string; name: string; status: string; statusLabel: string; isVerified: boolean; category: string; joined: string;
  vehicle: { type: string; typeLabel: string; model: string; color: string; number: string; rideTypes: string[] };
  availabilityPreference: string;
  capabilities: { key: string; label: string }[];
  documents: PartnerDocumentStatus[];
  blockedReason: string;
  public: DriverPublicIdentity;
  stats: {
    completedTrips: number; distanceKm: number; acceptanceRate: number | null; completionRate: number | null;
    cancelledByYou: number; missedRequests: number;
  };
  recentFeedback: { stars: number; comment: string; compliment: string; at: string }[];
}

export interface DriverPeriod {
  key: 'today' | 'yesterday' | 'week' | 'month'; label: string; total: Money; trips: number; distanceKm: number;
  cashCollected: Money; paidViaClick: Money; onlineSeconds: number; onlineLabel: string; perTrip: Money | null;
}
export interface DriverEarnings {
  periods: DriverPeriod[]; last7Days: { date: string; total: Money; trips: number }[]; currency: string; note: string;
}

export interface DriverTrip {
  id: UUID; number: string; status: string; statusLabel: string; rideType: string; pickup: string; drop: string; distanceKm: number;
  fare: Money; payment: string; at: string; cancelReason: string;
  ratingReceived: { stars: number; comment: string } | null; riderRated: number | null; canRateRider: boolean;
}
export interface DriverTrips { results: DriverTrip[]; page: number; total: number; hasMore: boolean }

export interface SafetyResult { id: UUID; kind: 'sos' | 'report'; emergencyNumber: string; message: string }

export const driverApi = (http: HttpClient) => ({
  profile: () => http.request<DriverProfile>('/partner/driver/profile'),
  earnings: () => http.request<DriverEarnings>('/partner/driver/earnings'),
  trips: (q: { status?: string; page?: number }) => http.request<DriverTrips>('/partner/driver/trips', { query: q }),
  rateRider: (id: UUID, stars: number, note = '') =>
    http.request<{ stars: number }>(`/partner/driver/trips/${id}/rate-rider`, { method: 'POST', body: { stars, note } }),
  safety: (id: UUID, kind: 'sos' | 'report', note = '') =>
    http.request<SafetyResult>(`/partner/driver/trips/${id}/safety`, { method: 'POST', body: { kind, note } }),
  documents: () => http.request<PartnerDocuments>('/partner/documents'),
  submitDocument: (body: { key: string; number: string; expiresOn?: string }) =>
    http.request<PartnerDocuments>('/partner/documents', { method: 'POST', body }),
});
