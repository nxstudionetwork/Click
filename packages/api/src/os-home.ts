/** Click Business OS — Home / Command Center contract (/api/v1/os/home, alerts, announcements, help). */
import type { HttpClient, Query } from './http';

type UUID = string;
type ISO = string;

export interface OSWidgetMeta {
  key: string; title: string; size: 's' | 'm' | 'l'; category: 'action' | 'attention' | 'awareness' | 'insight' | 'decision';
  description: string; source: string; refreshSeconds: number; periods: boolean; unitAware: boolean; mandatory: boolean;
  period: string | null; pinned: boolean; visible?: boolean;
}
export interface OSHomeSummary {
  date: string; weekday: string; tasksOpen: number; tasksDueToday: number; tasksOverdue: number; approvalsWaiting: number;
  approvalsOverdue: number; alertsImportant: number; alertsCritical: number; deadlinesWeek: number;
}
export interface OSContextUnit { id: UUID; name: string; code: string; type: string; typeLabel: string; depth: number; parentId: UUID | null }
export interface OSHomeV2 {
  summary: OSHomeSummary;
  context: { orgWide: boolean; units: OSContextUnit[]; selected: UUID | null; switchable: boolean; unit: { id: UUID; name: string; typeLabel: string } | null };
  layout: OSWidgetMeta[];
  available: OSWidgetMeta[];
  views: { active: string | null; saved: { id: string; name: string; preset: false }[]; presets: { id: string; name: string; preset: true; widgets: string[] }[] };
  canExecutive: boolean;
  isManager: boolean;
  periods: { key: string; label: string }[];
  pulse: { available: { key: string; label: string }[]; selected: string[] };
  generatedAt: ISO;
}
export interface OSPeriod { key: string; label: string; start: ISO; end: ISO; previousStart: ISO; previousEnd: ISO; bucket: 'day' | 'month' }
export interface OSWidgetResult<T = any> { // eslint-disable-line @typescript-eslint/no-explicit-any
  key: string; title: string; data: T | null; error: { code: string; message: string } | null; generatedAt: ISO; source: string;
  refreshSeconds: number; live: boolean; cached?: boolean; period: OSPeriod | null; location: string | null;
}
export interface OSPulseMetric {
  key: string; label: string; format: 'money' | 'number' | 'percent'; value: string | number | null; previous: string | number | null;
  deltaPct: number | null; series: { t: string | null; v: string }[]; drill: string; source: string; note: string; description: string;
  pointInTime: boolean; goodWhen: 'up' | 'down'; error: string | null; locationApplied: boolean; platformWide: boolean;
}
export interface OSAlert {
  id: UUID; category: string; severity: 'critical' | 'high' | 'medium' | 'low'; title: string; detail: string; source: string; path: string;
  recommendedAction: string; status: 'open' | 'acknowledged' | 'resolved'; owner: { id: UUID; fullName: string } | null; firstSeenAt: ISO;
  lastSeenAt: ISO; dueOn: string | null; isRisk: boolean; personal: boolean; location: string | null;
}
export interface OSAnnouncement {
  id: UUID; title: string; body: string; category: string; categoryLabel: string; priority: 'normal' | 'important' | 'critical';
  startsAt: ISO; endsAt: ISO | null; requiresAck: boolean; acknowledged: boolean; acknowledgedAt: ISO | null; dismissed?: boolean; canDismiss: boolean;
  author: string | null; audience: Record<string, string[]>; acks?: number; isPublished?: boolean;
}

export const osHomeApi = (http: HttpClient) => ({
  get: (q: Query = {}) => http.request<OSHomeV2>('/os/home', { query: q }),
  widget: <T = any>(key: string, q: Query = {}, signal?: AbortSignal) => // eslint-disable-line @typescript-eslint/no-explicit-any
    http.request<OSWidgetResult<T>>(`/os/home/widgets/${encodeURIComponent(key)}`, { query: q, signal }),
  saveLayout: (layout: { key: string; size?: string; period?: string | null; pinned?: boolean }[]) =>
    http.request<{ saved: boolean; keptMandatory: string[] }>('/os/home/layout', { method: 'PATCH', body: { layout } }),
  resetLayout: () => http.request<{ reset: boolean }>('/os/home/layout/reset', { method: 'POST' }),
  saveView: (name: string) => http.request<{ id: string; name: string }>('/os/home/views', { method: 'POST', body: { name } }),
  activateView: (id: string) => http.request<{ active: string | null }>(`/os/home/views/${encodeURIComponent(id)}`, { method: 'POST' }),
  deleteView: (id: string) => http.request<void>(`/os/home/views/${encodeURIComponent(id)}`, { method: 'DELETE' }),
  setContext: (unitId: string | null) => http.request<{ selected: string | null }>('/os/home/context', { method: 'PATCH', body: { unitId } }),
  setPulse: (metrics: string[]) => http.request<{ selected: string[] }>('/os/home/pulse', { method: 'PATCH', body: { metrics } }),
  pinQuickActions: (pins: string[]) => http.request<{ pins: string[] }>('/os/home/quick-actions', { method: 'PATCH', body: { pins } }),
  quickActionUsed: (key: string) => http.request<void>(`/os/home/quick-actions/${encodeURIComponent(key)}/used`, { method: 'POST' }),
  alerts: (q: Query = {}) => http.request<{ results: OSAlert[]; categories: string[] }>('/os/alerts', { query: q }),
  alertAction: (id: string, action: 'acknowledge' | 'resolve' | 'reopen' | 'assign', ownerId?: string) =>
    http.request<OSAlert>(`/os/alerts/${encodeURIComponent(id)}/${action}`, { method: 'POST', body: ownerId ? { ownerId } : {} }),
  announcements: (manage = false) =>
    http.request<{ results: OSAnnouncement[]; canCreate?: boolean; categories?: { key: string; label: string }[] }>('/os/announcements', { query: { manage: manage ? 'true' : undefined } }),
  createAnnouncement: (input: { title: string; body: string; category: string; priority: string; requiresAck: boolean; startsAt?: string; endsAt?: string | null;
    audience?: Record<string, string[]> }) => http.request<OSAnnouncement>('/os/announcements', { method: 'POST', body: input }),
  updateAnnouncement: (id: string, input: Partial<{ title: string; body: string; endsAt: string | null; isPublished: boolean }>) =>
    http.request<OSAnnouncement>(`/os/announcements/${encodeURIComponent(id)}`, { method: 'PATCH', body: input }),
  announcementAction: (id: string, action: 'acknowledge' | 'dismiss') =>
    http.request<OSAnnouncement>(`/os/announcements/${encodeURIComponent(id)}/${action}`, { method: 'POST' }),
  notificationAction: (id: string, action: 'unread' | 'archive' | 'restore') =>
    http.request<{ id: string }>(`/os/notifications/${encodeURIComponent(id)}/${action}`, { method: 'POST' }),
  clearRead: () => http.request<{ cleared: number }>('/os/notifications/clear-read', { method: 'POST' }),
  reportProblem: (input: { summary: string; details?: string; page?: string }) =>
    http.request<{ reference: string; routed: boolean; supportEmail: string }>('/os/help/report', { method: 'POST', body: input }),
});
