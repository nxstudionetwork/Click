import type { ISODateTime, Money, UUID } from './types';

/** Contracts for Click. Parcel (apps/parcels on the backend). Prices and times always come from the server. */

export type ParcelMode = 'send' | 'receive' | 'store_pickup';
export type ParcelServiceCode = 'express' | 'same_day' | 'standard' | 'scheduled';
export type ParcelStatus = 'scheduled' | 'searching' | 'assigned' | 'at_pickup' | 'picked_up' | 'in_transit' | 'arriving' | 'delivered'
  | 'cancelled' | 'failed' | 'no_partner';

export interface ParcelOptions {
  coverage: { checked: boolean; available: boolean; area: string | null };
  services: { code: ParcelServiceCode; name: string; description: string; allowStops: boolean; maxStops: number; cashAllowed: boolean;
    cancellationFee: Money; maxDistanceKm: string; hours: string; vehicles: string[] }[];
  vehicles: ParcelVehicleInfo[];
  categories: { code: string; label: string; icon: string; requiresValue: boolean; allowed: boolean; note: string }[];
  sizes: { code: 'small' | 'medium' | 'large' | 'custom'; label: string; hint: string; maxKg: number | null; dims: [number, number, number] | null }[];
  rules: { kind: 'rule' | 'prohibited'; text: string; service: string | null }[];
}
export interface ParcelVehicleInfo { code: string; name: string; description: string; icon: string; capacity: { maxKg: string; maxCm: [number, number, number] } }

export interface ParcelPlaceInput {
  label: string; address?: string; lat: number; lng: number; name?: string; phone?: string; altPhone?: string; instructions?: string;
}
export interface ParcelPackageInput {
  category?: string; size?: string; weightKg?: string | null; lengthCm?: number | null; widthCm?: number | null; heightCm?: number | null;
  declaredValue?: string | null; notes?: string;
}
export interface ParcelQuoteInput {
  mode: ParcelMode; pickup?: ParcelPlaceInput | null; drop?: ParcelPlaceInput | null; stops?: ParcelPlaceInput[];
  package?: ParcelPackageInput; service?: string; scheduledFor?: string | null; storeId?: string | null;
}
export interface ParcelFare { base: Money; distance: Money; service: Money; stops: Money; tax: Money; discount: Money; total: Money }
export interface ParcelQuote {
  distanceKm: string; stops: number; estimateBasis: 'straight_line' | string; packageProblem: string | null; service: ParcelServiceCode | null;
  services: { code: ParcelServiceCode; name: string; description: string; available: boolean; reason: string; label?: string;
    slots?: { start: ISODateTime; label: string }[]; needsTime?: boolean }[];
  vehicles: (ParcelVehicleInfo & { available: boolean; reason: string; fare?: ParcelFare; tripMinutes?: number; window?: string;
    pickupEtaMinutes?: number | null })[];
  paymentMethods: ('wallet' | 'cash')[];
  cancellationFee: Money | null;
}
export interface ParcelBookInput extends ParcelQuoteInput {
  pickup: ParcelPlaceInput; drop: ParcelPlaceInput; service: string; vehicle: string; paymentMethod: 'wallet' | 'cash'; expectedTotal: Money;
  idempotencyKey: string; contentsConfirmed: boolean; saveRecipient?: boolean; storeReference?: string; repeatOf?: string | null;
}

export interface ParcelPlace { label: string; address: string; lat: number; lng: number }
export interface ParcelSummary {
  id: UUID; number: string; mode: ParcelMode; modeLabel: string; status: ParcelStatus; statusLabel: string;
  service: { code: ParcelServiceCode; name: string }; vehicle: { code: string; name: string; icon: string };
  pickup: ParcelPlace; drop: ParcelPlace; total: Money; currency: string; createdAt: ISODateTime;
  scheduledFor: ISODateTime | null; deliverBy: ISODateTime | null; deliveredAt: ISODateTime | null; isActive: boolean;
}
export interface ParcelDetail extends Omit<ParcelSummary, 'pickup' | 'drop'> {
  pickup: ParcelPlace & { name: string; phoneMasked: string; instructions: string; store: { id: UUID; name: string } | null; storeReference: string };
  drop: ParcelPlace & { name: string; phoneMasked: string; instructions: string };
  stops: (ParcelPlace & { position: number; name: string; completedAt: ISODateTime | null })[];
  package: { category: string; categoryCode: string; size: string; sizeLabel: string; weightKg: string; dims: [number, number, number] | null;
    declaredValue: Money | null; notes: string };
  fare: ParcelFare & { cancellationFee: Money };
  distanceKm: string; durationMinutes: number; estimateBasis: string;
  payment: { method: 'wallet' | 'cash'; status: string | null; refunded: boolean };
  pins: { pickup: string | null; delivery: string | null };
  partner: { name: string; vehicle: string; vehicleNumber: string; position: { lat: number; lng: number; reportedAt: ISODateTime; live: boolean } | null } | null;
  timeline: { status: ParcelStatus; label: string; at: ISODateTime | null }[];
  events: { to: ParcelStatus; note: string; at: ISODateTime }[];
  proofs: { kind: 'pickup' | 'stop' | 'delivery'; kindLabel: string; method: string; at: ISODateTime; located: boolean }[];
  cancellation: { allowed: boolean; fee: Money | null; note: string };
  failureReason: string; cancelReason: string; supportRequired: boolean;
  tickets: { id: UUID; reference: string; status: string }[];
}
export interface SharedParcel {
  number: string; status: ParcelStatus; statusLabel: string; service: string; from: string; to: string; deliverBy: ISODateTime | null;
  timeline: ParcelDetail['timeline']; deliveredAt: ISODateTime | null;
}
export interface SavedRecipient {
  id: UUID; name: string; phone: string; altPhone: string; label: string; address: string; lat: string | null; lng: string | null;
  instructions: string; timesUsed: number; lastUsedAt: ISODateTime | null;
}
export interface ParcelDraft extends ParcelQuoteInput { repeatOf?: string; vehicle?: string; pickup: ParcelPlaceInput; drop: ParcelPlaceInput }
