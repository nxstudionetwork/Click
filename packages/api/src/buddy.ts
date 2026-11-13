import type { HttpClient } from './http';
import type { BuddyAction, BuddyCard, ISODateTime, UUID } from './types';

/** Buddy conversations and the secure action layer (apps/ai on the backend). Actions are validated and
 *  permission-checked on the server; confirmation-tier actions return a summary and wait for confirm(). */

export interface BuddyConversation { id: UUID; title: string; archived: boolean; mode: 'man' | 'go'; topic: string; updatedAt: ISODateTime; preview?: string }
export interface BuddyMessage {
  id: UUID; role: 'user' | 'assistant'; content: string; cards: BuddyCard[]; actions: BuddyAction[];
  attachment: { kind?: string; id?: string; label?: string }; viaVoice: boolean; createdAt: ISODateTime;
}
export interface BuddyActionRun {
  id: UUID; action: string; tier: 'safe' | 'confirm' | 'high'; status: 'done' | 'awaiting_confirmation' | 'confirmed' | 'cancelled' | 'failed' | 'expired';
  summary: string; result: { message?: string; navigate?: string; undo?: { action: string; args: Record<string, unknown> }; next?: { label: string; path: string }; code?: string };
  error: string; expiresAt: ISODateTime | null;
}
export type BuddyAttachment = { kind: 'order' | 'service_booking' | 'event_booking' | 'hotel_booking' | 'parcel' | 'address'; id: string };
export type BuddyEventKind = 'opened' | 'mode_man' | 'mode_go' | 'action_requested' | 'action_completed' | 'action_failed' | 'navigated'
  | 'voice_started' | 'voice_success' | 'voice_failed' | 'mic_denied';

export const buddyApi = (http: HttpClient) => ({
  conversations: (archived = false, page = 1) =>
    http.request<{ results: BuddyConversation[]; hasMore: boolean }>('/customer/assistant/conversations', { query: { archived: archived ? 'true' : undefined, page: String(page) } }),
  start: (mode: 'man' | 'go' = 'man') => http.request<BuddyConversation>('/customer/assistant/conversations', { method: 'POST', body: { mode } }),
  conversation: (id: string) => http.request<BuddyConversation & { messages: BuddyMessage[] }>(`/customer/assistant/conversations/${id}`),
  edit: (id: string, body: { title?: string; archived?: boolean }) =>
    http.request<BuddyConversation>(`/customer/assistant/conversations/${id}`, { method: 'PATCH', body }),
  remove: (id: string) => http.request<void>(`/customer/assistant/conversations/${id}`, { method: 'DELETE' }),
  say: (id: string, content: string, opts: { viaVoice?: boolean; attachment?: BuddyAttachment | null; language?: string; signal?: AbortSignal } = {}) =>
    http.request<{ message: BuddyMessage; conversation: BuddyConversation; understoodAs: string | null; mode: string }>(
      `/customer/assistant/conversations/${id}/messages`,
      { method: 'POST', body: { content, viaVoice: !!opts.viaVoice, attachment: opts.attachment ?? undefined, language: opts.language ?? 'en' }, signal: opts.signal }),
  act: (action: string, args: Record<string, unknown>, conversationId?: string | null) =>
    http.request<BuddyActionRun>('/customer/assistant/actions', { method: 'POST', body: { action, args, conversationId: conversationId ?? null } }),
  decide: (runId: string, decision: 'confirm' | 'cancel') => http.request<BuddyActionRun>(`/customer/assistant/actions/${runId}/${decision}`, { method: 'POST', body: {} }),
  track: (kind: BuddyEventKind, detail = '', latencyMs?: number) =>
    http.request<void>('/customer/assistant/events', { method: 'POST', body: { kind, detail, latencyMs: latencyMs ?? null } }).catch(() => undefined),
});
