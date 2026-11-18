import type { HttpClient } from './http';
import type { Money, UUID } from './types';

/**
 * Click. Buzz for partners (/partner/buzz/* on the backend, apps/buzz/partner.py) and Buzz engagement
 * (/buzz/posts/<id>/*, Customer App and Partner App). Every post links to one of the partner's own live Click
 * listings and is reviewed by Click before customers see it.
 */

export type BuzzPostStatus = 'draft' | 'in_review' | 'live' | 'scheduled' | 'expired' | 'paused' | 'rejected' | 'removed' | 'archived';
export type BuzzPostAction = 'edit' | 'submit' | 'withdraw' | 'pause' | 'resume' | 'archive' | 'restore' | 'delete';
export type BuzzPostKind = 'update' | 'new_item' | 'offer' | 'announcement' | 'event' | 'seasonal' | 'behind_scenes' | 'tip' | 'achievement';
export type BuzzAudience = 'public' | 'partners';

export interface BuzzMediaFile { id: UUID; kind: 'image' | 'video'; url: string; thumb: string; width: number | null; height: number | null; bytes: number }

export interface BuzzListing { type: string; id: string; title: string; link: string; ctas: string[]; handle: string }

export interface PartnerBuzzPost {
  id: UUID; kind: BuzzPostKind; kindLabel: string; headline: string; caption: string; audience: BuzzAudience;
  targetType: string; targetId: string; targetTitle: string; cta: string; ctaLabel: string; link: string;
  product: { id: UUID; name: string; price: Money; available: boolean } | null;
  offer: { id: UUID; title: string } | null;
  media: BuzzMediaFile[];
  status: BuzzPostStatus; statusLabel: string; reviewNote: string;
  publishAt: string | null; expiresAt: string | null; submittedAt: string | null; createdAt: string;
  stats: { views: number; ctaClicks: number; likes: number; saves: number; ctr: number | null; openReports: number };
  actions: BuzzPostAction[];
}

export interface PartnerBuzzOverview {
  posts: PartnerBuzzPost[];
  counts: { status: BuzzPostStatus; count: number }[];
  totals: { views7d: number; clicks7d: number; likes: number; saves: number };
  canPublish: boolean;
  listings: BuzzListing[];
  ctaLabels: { value: string; label: string }[];
  kinds: { value: BuzzPostKind; label: string }[];
  products: { id: UUID; storeId: UUID; name: string; price: Money; available: boolean }[];
  offers: { id: UUID; storeId: UUID; title: string; endsAt: string | null }[];
  limits: { media: number; videoMb: number; imageMb: number; maxDays: number };
}

export interface BuzzPostInput {
  headline?: string; caption?: string; kind?: BuzzPostKind; audience?: BuzzAudience;
  targetType?: string; targetId?: string; cta?: string; productId?: UUID | null; offerId?: UUID | null;
  publishAt?: string | null; expiresAt?: string | null; mediaIds?: UUID[]; submit?: boolean;
}

export interface CommunityBuzzPost {
  id: UUID; kindLabel: string; headline: string; caption: string; media: BuzzMediaFile[]; ctaLabel: string; link: string;
  audience: BuzzAudience; product: PartnerBuzzPost['product']; offer: PartnerBuzzPost['offer']; publishAt: string | null;
  partner: string; category: string; likes: number; liked: boolean; saved: boolean;
}

export type BuzzReportReason = 'misleading' | 'spam' | 'offensive' | 'illegal' | 'other';

export const partnerBuzzApi = (http: HttpClient) => ({
  overview: (status = '') => http.request<PartnerBuzzOverview>('/partner/buzz', { query: { status } }),
  create: (body: BuzzPostInput) => http.request<PartnerBuzzPost>('/partner/buzz', { method: 'POST', body }),
  update: (id: UUID, body: BuzzPostInput) => http.request<PartnerBuzzPost>(`/partner/buzz/${id}`, { method: 'PATCH', body }),
  remove: (id: UUID) => http.request<void>(`/partner/buzz/${id}`, { method: 'DELETE' }),
  act: (id: UUID, action: Exclude<BuzzPostAction, 'edit' | 'delete'>) =>
    http.request<PartnerBuzzPost>(`/partner/buzz/${id}/${action}`, { method: 'POST' }),
  upload: (file: File) => {
    const body = new FormData();
    body.append('file', file);
    return http.request<BuzzMediaFile>('/partner/buzz/media', { method: 'POST', body });
  },
  discardMedia: (id: UUID) => http.request<void>(`/partner/buzz/media/${id}`, { method: 'DELETE' }),
  community: () => http.request<{ results: CommunityBuzzPost[] }>('/partner/buzz/community'),
});

/** Engagement on partner posts, shared by the Customer App and the Partner App. */
export const buzzEngageApi = (http: HttpClient) => ({
  like: (id: UUID) => http.request<{ on: boolean; count: number }>(`/buzz/posts/${id}/like`, { method: 'POST' }),
  save: (id: UUID) => http.request<{ on: boolean; count: number }>(`/buzz/posts/${id}/save`, { method: 'POST' }),
  event: (id: UUID, kind: 'view' | 'click') =>
    http.request<{ counted: boolean }>(`/buzz/posts/${id}/event`, { method: 'POST', body: { kind } }),
  report: (id: UUID, reason: BuzzReportReason, note = '') =>
    http.request<{ ok: boolean }>(`/buzz/posts/${id}/report`, { method: 'POST', body: { reason, note } }),
});
