/**
 * Click Business OS contract (/api/v1/os/*). One typed client for the shell and every future OS module.
 * The server decides access; these types only describe what it returns.
 */
import type { HttpClient, Query } from './http';
import type { Paginated, Session } from './types';

type UUID = string;
type ISO = string;

// --- identity & context ----------------------------------------------------------------
export type OSAccessType = 'employee' | 'administrator' | 'partner' | 'other';
export type OSAccountKind = 'employee' | 'partner' | 'external';
export type OSAccountStatus = 'invited' | 'active' | 'suspended' | 'deactivated';

export interface OSUser { id: UUID; fullName: string; email: string | null; avatarUrl: string | null; kind: OSAccountKind | null }
export interface OSAuthenticated { status: 'authenticated'; access: string; user: OSUser; session: { id: UUID; expiresAt: ISO } }
export interface OSMfaRequired { status: 'mfa_required'; mfaToken: string; methods: ('totp' | 'recovery_code')[] }
export interface OSIdentifyResult { flowToken: string; accessType: OSAccessType; methods: string[]; sso: null | { provider: string; url: string } }

export interface OSUnitBrief { id: UUID; name: string; code: string; type: string; typeLabel: string }
export interface OSNavItem { key: string; label: string; icon: string; path: string; status: 'live' | 'foundation' | 'planned' }
export interface OSNavGroup { key: string; label: string; items: OSNavItem[] }
export interface OSQuickAction { key: string; label: string; icon: string; path: string }
export type OSScopeLevel = 'organization' | 'units' | 'department' | 'team' | 'partner' | 'own' | 'none';

export interface OSPreferences {
  notifications?: { muted: string[] };
  home?: { hidden: string[]; order: string[] };
  appearance?: { theme: 'light' | 'dark' | 'system'; density: 'comfortable' | 'compact' };
}

export interface OSContext {
  user: { id: UUID; fullName: string; email: string | null; phone: string; avatarUrl: string | null };
  account: {
    id: UUID; kind: OSAccountKind; status: OSAccountStatus; mfaEnabled: boolean; onboardingRequired: boolean; timezone: string;
    language: string; lastLoginAt: ISO | null; accessVersion: number; preferences: OSPreferences;
    partner: { id: UUID; name: string; code: string | null } | null;
  };
  employee: {
    id: UUID; employeeId: string; fullName: string; designation: string | null; status: string; employmentType: string;
    joinedOn: string | null; manager: { id: UUID; fullName: string } | null;
  } | null;
  organization: { id: UUID; name: string; code: string; currency: string; timezone: string };
  orgContext: { units: OSUnitBrief[]; location: OSUnitBrief | null; department: { id: UUID; name: string; code: string } | null; team: { id: UUID; name: string } | null };
  roles: { id: UUID; key: string; name: string }[];
  permissions: { code: string; scope: OSScopeLevel }[];
  mfaBlocked: string[];
  approvalAuthority: { type: string; label: string; maxAmount: string | null; currency: string }[];
  navigation: OSNavGroup[];
  quickActions: OSQuickAction[];
  contextOptions: { orgWide: boolean; units: { id: UUID; name: string; code: string; type: string; typeLabel: string; depth: number }[]; selected: UUID | null; switchable: boolean };
  isManager: boolean;
  directReports: number;
  session: { id: UUID; expiresAt: ISO; mfaVerified: boolean } | null;
  security: { sensitiveRequiresMfa: boolean; idleMinutes: number };
}

// --- home ---------------------------------------------------------------------------------
export interface OSMetric { key: string; label: string; value: string | number; previous?: string | number; format: 'money' | 'number'; alert?: boolean }
export interface OSWidget<T = Record<string, unknown>> {
  key: string; title: string; size: 's' | 'm' | 'l'; description: string;
  data: T | null; error: { code: string; message: string } | null;
}
export interface OSHome { widgets: OSWidget[]; available: { key: string; title: string; visible: boolean }[]; generatedAt: ISO }

// --- notifications ----------------------------------------------------------------------------
export interface OSNotification {
  id: UUID; type: string; typeLabel: string; module: string; title: string; body: string; path: string;
  priority: 'normal' | 'important' | 'critical'; read: boolean; createdAt: ISO; channels: string[];
}

// --- approvals & tasks ---------------------------------------------------------------------------
export type OSApprovalStatus = 'pending' | 'approved' | 'rejected' | 'cancelled' | 'changes_requested';
export interface OSPersonRef { id: UUID; fullName: string }
export interface OSApprovalBrief {
  id: UUID; reference: string; title: string; status: OSApprovalStatus; amount: string | null; currency: string;
  policy: { key: string; name: string; module: string }; requestedBy: OSPersonRef; orgUnit: string | null;
  currentSequence: number | null; dueAt: ISO | null; createdAt: ISO; decidedAt: ISO | null;
  priority?: string; flags?: string[]; amountUnit?: 'currency' | 'days' | 'count';
}
export interface OSApprovalDetail extends OSApprovalBrief {
  description: string; department: string | null;
  steps: { sequence: number; name: string; status: string; decidedBy: OSPersonRef | null; onBehalfOf: OSPersonRef | null; decidedAt: ISO | null; comment: string; dueAt: ISO | null }[];
  history: { kind: string; author: OSPersonRef | null; body: string; at: ISO }[];
  canDecide: boolean; decidingOnBehalfOf: OSPersonRef | null; canCancel: boolean; canResubmit?: boolean; canRequestChanges?: boolean;
}
export interface OSPolicyOption { key: string; name: string; description: string; module: string; currency: string; requiresAmount: boolean; levels: { name: string; minAmount: string }[] }
export interface OSDelegation { id: UUID; person: OSPersonRef; policy: string; startsAt: ISO; endsAt: ISO; reason: string }

export type OSTaskStatus = 'open' | 'in_progress' | 'done' | 'cancelled';
export type OSTaskPriority = 'low' | 'normal' | 'high' | 'urgent';
export interface OSTask {
  id: UUID; title: string; description: string; status: OSTaskStatus; priority: OSTaskPriority; dueAt: ISO | null; completedAt: ISO | null;
  assignee: OSPersonRef; createdBy: OSPersonRef; module: string; linkPath: string; createdAt: ISO; overdue: boolean; canEdit: boolean;
}

// --- search / calendar / modules / AI ----------------------------------------------------------
export interface OSSearchResult { id: string; title: string; subtitle: string; path: string }
export interface OSSearchGroup { type: string; label: string; results: OSSearchResult[] }
export interface OSCalendarItem { id: string; kind: 'task' | 'approval'; title: string; at: ISO; priority: string; path: string }
export interface OSModule {
  key: string; label: string; group: string; icon: string; description: string; status: 'live' | 'foundation' | 'planned'; path: string;
  submodules: string[]; includes: string[];
  resources: { key: string; label: string; sensitive: boolean; actions: { action: string; allowed: boolean; scope: OSScopeLevel }[] }[];
}
export interface OSAIAnswer {
  answer: string; available: boolean; denied?: boolean; tool?: string | null; provider?: string; note?: string;
  items?: { title: string; subtitle: string; path: string }[];
  proposedAction?: { type: 'create_task'; title: string; assignee: 'me' };
}

// --- security ---------------------------------------------------------------------------------
export interface OSSessionRow { id: UUID; deviceLabel: string; ip: string | null; createdAt: ISO; lastSeenAt: ISO; expiresAt: ISO; mfaVerified: boolean; current: boolean }
export interface OSActivity { id: UUID; action: string; category: string; outcome: string; ip: string | null; metadata: Record<string, unknown>; createdAt: ISO }

// --- administration ------------------------------------------------------------------------------
export interface OSAccountRow {
  id: UUID; userId: UUID; fullName: string; email: string | null; kind: OSAccountKind; status: OSAccountStatus;
  employee: { id: UUID; employeeId: string; designation: string | null; department: { name: string } | null; orgUnit: OSUnitBrief | null } | null;
  roles: { id: UUID; name: string }[]; mfaEnabled: boolean; isLocked: boolean; lastLoginAt: ISO | null; createdAt: ISO; avatarUrl: string | null;
}
export interface OSAssignment {
  id: UUID; role: { id: UUID; name: string; key: string }; orgUnit: OSUnitBrief | null; department: { id: UUID; name: string } | null;
  team: { id: UUID; name: string } | null; validFrom: ISO | null; validUntil: ISO | null; grantedBy: string | null; note: string; createdAt: ISO;
}
export interface OSAccountDetail extends OSAccountRow {
  assignments: OSAssignment[]; sessions: number; lockedUntil: ISO | null; invitedAt: ISO | null; partner: { id: UUID; name: string } | null;
  isSelf: boolean; canManage: boolean; canAssign: boolean; recentActivity?: { action: string; outcome: string; at: ISO; ip: string | null }[];
}
export interface OSRoleRow {
  id: UUID; key: string; name: string; description: string; audience: string; isSystem: boolean; requiresMfa: boolean;
  parent: { id: UUID; name: string } | null; priority: number; permissionCount: number; holderCount: number; isActive: boolean;
}
export interface OSGrant { code: string; scope: string; sensitive?: boolean }
export interface OSRoleDetail extends OSRoleRow {
  homeWidgets: string[]; grants: OSGrant[]; inherited: (OSGrant & { from: string })[];
  approvalLimits: { approvalType: string; maxAmount: string | null; currency: string }[];
  holders: { userId: UUID; fullName: string; orgUnit: string | null; department: string | null }[];
  canEdit: boolean; canDelete: boolean;
}
export interface OSPermissionCatalog {
  groups: { key: string; label: string }[];
  modules: { key: string; label: string; group: string; status: string;
    resources: { key: string; label: string; sensitive: boolean; actions: { action: string; code: string; youHold: OSScopeLevel }[] }[] }[];
  scopes: { key: string; label: string }[];
  approvalTypes: { key: string; label: string }[];
  audiences: { key: string; label: string }[];
  widgets: { key: string; title: string; permission: string | null }[];
}
export interface OSRoleInput {
  name: string; key?: string; description?: string; audience?: string; parentId?: string | null; requiresMfa?: boolean; priority?: number;
  homeWidgets?: string[]; grants?: { code: string; scope: string }[]; approvalLimits?: { approvalType: string; maxAmount: string | null; currency?: string }[];
}
export interface OSOrgUnit { id: UUID; parentId: UUID | null; name: string; code: string; type: string; typeLabel: string; depth: number; city: string; isActive: boolean; employees: number }
export interface OSDepartment { id: UUID; name: string; code: string; parentId: UUID | null; orgUnitId: UUID | null; head: string | null; isActive: boolean; teams: { id: UUID; name: string; code: string; lead: string | null }[] }
export interface OSOrgTree {
  organization: { id: UUID; name: string; code: string }; units: OSOrgUnit[]; departments: OSDepartment[];
  unitTypes: { key: string; label: string }[]; canManage: boolean;
}
export interface OSAuditEvent {
  id: UUID; at: ISO; actor: string; actorKind: string; action: string; category: string; module: string; resourceType: string; resourceId: string;
  resourceLabel: string; oldValue: Record<string, unknown> | null; newValue: Record<string, unknown> | null; outcome: string; ip: string | null;
  sensitive: boolean; metadata: Record<string, unknown>;
}
export interface OSPolicy {
  id: UUID; key: string; name: string; description: string; module: string; approvalType: string; submitPermission: string; currency: string;
  requiresAmount: boolean; isActive: boolean; openRequests: number;
  levels: { sequence: number; name: string; approverPermission: string; minAmount: string; enforceLimit: boolean; escalateAfterHours: number | null }[];
}
export interface OSHealthCheck { key: string; label: string; status: 'ok' | 'warning' | 'error' | 'not_configured'; detail: string }
export interface OSEmployee {
  id: UUID; fullName: string; employeeId: string; designation: string | null; department: string | null; team: string | null; location: string | null;
  workEmail: string; manager: OSPersonRef | null; status: string; fullRecord: boolean; employmentType?: string; joinedOn?: string | null; hasAccount?: boolean;
}

const enc = encodeURIComponent;

/** Everything Business OS calls. Sign-in endpoints are unauthenticated; the rest need an OS session. */
export const osApi = (http: HttpClient) => ({
  auth: {
    identify: (identifier: string, accessType: OSAccessType) =>
      http.request<OSIdentifyResult>('/os/auth/identify', { method: 'POST', body: { identifier, accessType }, auth: false }),
    password: (flowToken: string, password: string) =>
      http.request<OSAuthenticated | OSMfaRequired>('/os/auth/password', { method: 'POST', body: { flowToken, password }, auth: false }),
    mfa: (mfaToken: string, code: string) => http.request<OSAuthenticated>('/os/auth/mfa', { method: 'POST', body: { mfaToken, code }, auth: false }),
    refresh: () => http.request<Session>('/os/auth/refresh', { method: 'POST', auth: false }),
    logout: () => http.request<void>('/os/auth/logout', { method: 'POST', auth: false }),
    logoutAll: () => http.request<{ sessionsEnded: number }>('/os/auth/logout-all', { method: 'POST' }),
    invite: (token: string) => http.request<{ fullName: string; email: string; organization: string; kind: string }>('/os/auth/invite', { query: { token }, auth: false }),
    acceptInvite: (token: string, password: string) => http.request<OSAuthenticated>('/os/auth/invite', { method: 'POST', body: { token, password }, auth: false }),
    /** DEVELOPMENT ONLY: 404 unless the backend runs with DEBUG. */
    devPersonas: () => http.request<{ results: { userId: UUID; fullName: string; email: string; persona: string; kind: string }[] }>('/os/auth/dev-personas', { auth: false }),
    devLogin: (userId: string) => http.request<OSAuthenticated>('/os/auth/dev-personas', { method: 'POST', body: { userId }, auth: false }),
  },
  me: {
    context: () => http.request<OSContext>('/os/me/context'),
    updateProfile: (input: { fullName?: string; timezone?: string; language?: string }) => http.request<OSContext>('/os/me/profile', { method: 'PATCH', body: input }),
    updatePreferences: (input: OSPreferences) => http.request<OSContext>('/os/me/preferences', { method: 'PATCH', body: input }),
    uploadAvatar: (file: Blob) => {
      const form = new FormData();
      form.append('image', file, 'avatar');
      return http.request<OSContext>('/os/me/avatar', { method: 'POST', body: form });
    },
    removeAvatar: () => http.request<OSContext>('/os/me/avatar', { method: 'DELETE' }),
    onboarding: (input: { fullName: string; timezone: string; language: string; notifications: { muted: string[] }; correctionNote?: string }) =>
      http.request<OSContext>('/os/me/onboarding', { method: 'POST', body: input }),
    changePassword: (currentPassword: string, newPassword: string) =>
      http.request<{ otherSessionsEnded: number }>('/os/me/password', { method: 'POST', body: { currentPassword, newPassword } }),
    mfaSetup: () => http.request<{ secret: string; otpauthUri: string }>('/os/me/mfa/setup', { method: 'POST' }),
    mfaConfirm: (code: string) => http.request<{ recoveryCodes: string[] }>('/os/me/mfa/confirm', { method: 'POST', body: { code } }),
    mfaDisable: (password: string, code: string) => http.request<void>('/os/me/mfa/disable', { method: 'POST', body: { password, code } }),
    recoveryCodes: (password: string) => http.request<{ recoveryCodes: string[] }>('/os/me/mfa/recovery-codes', { method: 'POST', body: { password } }),
    sessions: () => http.request<{ results: OSSessionRow[] }>('/os/me/sessions'),
    revokeSession: (id: string) => http.request<void>(`/os/me/sessions/${enc(id)}`, { method: 'DELETE' }),
    activity: () => http.request<{ results: OSActivity[] }>('/os/me/activity'),
  },
  home: () => http.request<OSHome>('/os/home'),
  widget: (key: string) => http.request<OSWidget>(`/os/home/widgets/${enc(key)}`),
  notifications: {
    list: (q: Query = {}) => http.request<Paginated<OSNotification> & { unread: number; types: { value: string; label: string; essential: boolean }[] }>('/os/notifications', { query: q }),
    summary: () => http.request<{ unread: number; critical: number }>('/os/notifications/summary'),
    read: (id: string) => http.request<{ updated: number }>(`/os/notifications/${enc(id)}/read`, { method: 'POST' }),
    readAll: () => http.request<{ updated: number }>('/os/notifications/read-all', { method: 'POST' }),
  },
  search: (q: string, type?: string, signal?: AbortSignal) =>
    http.request<{ query: string; groups: OSSearchGroup[]; types: { type: string; label: string }[] }>('/os/search', { query: { q, type }, signal }),
  calendar: (q: { year?: number; month?: number } = {}) => http.request<{ results: OSCalendarItem[]; sources: string[] }>('/os/calendar', { query: q }),
  modules: () => http.request<{ results: OSModule[] }>('/os/modules'),
  module: (key: string) => http.request<OSModule>(`/os/modules/${enc(key)}`),
  ai: {
    status: () => http.request<{ available: boolean; provider: string | null; tools: { key: string; label: string }[] }>('/os/ai'),
    ask: (question: string) => http.request<OSAIAnswer>('/os/ai', { method: 'POST', body: { question } }),
  },
  people: {
    picker: (q: string) => http.request<{ results: { id: UUID; fullName: string; designation: string | null }[] }>('/os/people/picker', { query: { q } }),
  },
  approvals: {
    list: (box: 'inbox' | 'mine' | 'decided' | 'all', status?: string) =>
      http.request<{ results: OSApprovalBrief[]; box: string; counts: { inbox: number; minePending: number } }>('/os/approvals', { query: { box, status } }),
    get: (id: string) => http.request<OSApprovalDetail>(`/os/approvals/${enc(id)}`),
    act: (id: string, action: 'approve' | 'reject' | 'cancel' | 'comment' | 'request_changes', comment = '') =>
      http.request<OSApprovalDetail>(`/os/approvals/${enc(id)}/${action}`, { method: 'POST', body: { comment } }),
    resubmit: (id: string, input: { comment?: string; title?: string; description?: string; amount?: string }) =>
      http.request<OSApprovalDetail>(`/os/approvals/${enc(id)}/resubmit`, { method: 'POST', body: input }),
    submit: (input: { policyKey: string; title: string; amount?: string; description?: string }) =>
      http.request<OSApprovalBrief>('/os/approvals', { method: 'POST', body: input }),
    policies: () => http.request<{ results: OSPolicyOption[] }>('/os/approvals/policies'),
    delegations: () => http.request<{ given: OSDelegation[]; received: OSDelegation[] }>('/os/approvals/delegations'),
    delegate: (input: { delegateId: string; endsAt: string; startsAt?: string; policyKey?: string; reason?: string }) =>
      http.request<{ id: UUID }>('/os/approvals/delegations', { method: 'POST', body: input }),
    revokeDelegation: (id: string) => http.request<void>(`/os/approvals/delegations/${enc(id)}`, { method: 'DELETE' }),
  },
  tasks: {
    list: (view: 'assigned' | 'created' | 'overdue' | 'upcoming' | 'done', page = 1) => http.request<Paginated<OSTask>>('/os/tasks', { query: { view, page } }),
    create: (input: { title: string; description?: string; assigneeId?: string; dueAt?: string | null; priority?: OSTaskPriority }) =>
      http.request<OSTask>('/os/tasks', { method: 'POST', body: input }),
    update: (id: string, input: Partial<{ title: string; description: string; status: OSTaskStatus; priority: OSTaskPriority; dueAt: string | null }>) =>
      http.request<OSTask>(`/os/tasks/${enc(id)}`, { method: 'PATCH', body: input }),
  },
  org: {
    tree: () => http.request<OSOrgTree>('/os/org/tree'),
    createUnit: (input: { name: string; code: string; unitType: string; parentId?: string | null; city?: string }) =>
      http.request<OSOrgUnit>('/os/org/units', { method: 'POST', body: input }),
    updateUnit: (id: string, input: Partial<{ name: string; code: string; unitType: string; parentId: string | null; city: string; isActive: boolean }>) =>
      http.request<OSOrgUnit>(`/os/org/units/${enc(id)}`, { method: 'PATCH', body: input }),
    createDepartment: (input: { name: string; code: string; parentId?: string | null; orgUnitId?: string | null }) =>
      http.request<OSDepartment>('/os/org/departments', { method: 'POST', body: input }),
    createTeam: (input: { departmentId: string; name: string; code: string }) => http.request<{ id: UUID }>('/os/org/teams', { method: 'POST', body: input }),
  },
  admin: {
    users: (q: Query = {}) => http.request<Paginated<OSAccountRow> & { counts: Record<string, number> }>('/os/admin/users', { query: q }),
    user: (id: string) => http.request<OSAccountDetail>(`/os/admin/users/${enc(id)}`),
    invite: (input: { email: string; fullName: string; kind: OSAccountKind; employeeId?: string; partnerId?: string; externalOrgName?: string }) =>
      http.request<OSAccountRow & { inviteUrl: string; inviteExpiresDays: number }>('/os/admin/users', { method: 'POST', body: input }),
    userStatus: (id: string, action: 'suspend' | 'reactivate' | 'unlock' | 'sign_out_everywhere' | 'resend_invite') =>
      http.request<OSAccountRow & { inviteUrl?: string; sessionsEnded?: number }>(`/os/admin/users/${enc(id)}/status`, { method: 'POST', body: { action } }),
    assignRole: (id: string, input: { roleId: string; orgUnitId?: string; departmentId?: string; teamId?: string; validUntil?: string; note?: string }) =>
      http.request<OSAssignment>(`/os/admin/users/${enc(id)}/roles`, { method: 'POST', body: input }),
    removeRole: (id: string, assignmentId: string) => http.request<void>(`/os/admin/users/${enc(id)}/roles/${enc(assignmentId)}`, { method: 'DELETE' }),
    roles: () => http.request<{ results: OSRoleRow[] }>('/os/admin/roles'),
    role: (id: string) => http.request<OSRoleDetail>(`/os/admin/roles/${enc(id)}`),
    createRole: (input: OSRoleInput) => http.request<OSRoleDetail>('/os/admin/roles', { method: 'POST', body: input }),
    updateRole: (id: string, input: Partial<OSRoleInput>) => http.request<OSRoleDetail>(`/os/admin/roles/${enc(id)}`, { method: 'PATCH', body: input }),
    duplicateRole: (id: string) => http.request<OSRoleDetail>(`/os/admin/roles/${enc(id)}/duplicate`, { method: 'POST' }),
    deleteRole: (id: string) => http.request<void>(`/os/admin/roles/${enc(id)}`, { method: 'DELETE' }),
    permissions: () => http.request<OSPermissionCatalog>('/os/admin/permissions'),
    serviceAccounts: () => http.request<{ results: { id: UUID; name: string; description: string; keyPrefix: string; usable: boolean; lastUsedAt: ISO | null; expiresAt: ISO | null; revokedAt: ISO | null; createdAt: ISO }[] }>('/os/admin/service-accounts'),
    createServiceAccount: (input: { name: string; description?: string; expiresAt?: string }) =>
      http.request<{ id: UUID; name: string; key: string; note: string }>('/os/admin/service-accounts', { method: 'POST', body: input }),
    revokeServiceAccount: (id: string) => http.request<void>(`/os/admin/service-accounts/${enc(id)}`, { method: 'DELETE' }),
    policies: () => http.request<{ results: OSPolicy[]; approvalTypes: Record<string, string> }>('/os/admin/workflows'),
    updatePolicy: (id: string, input: Partial<Omit<OSPolicy, 'id' | 'openRequests'>>) => http.request<OSPolicy>(`/os/admin/workflows/${enc(id)}`, { method: 'PATCH', body: input }),
  },
  audit: (q: Query = {}) =>
    http.request<Paginated<OSAuditEvent> & { categories: { key: string; label: string }[]; canExport: boolean }>('/os/audit', { query: q }),
  system: {
    health: () => http.request<{ checks: OSHealthCheck[]; activeSessions: number; checkedAt: ISO; sessionPolicy: { idleMinutes: number; maxHours: number; maxFailedLogins: number; lockoutMinutes: number } }>('/os/system/health'),
    integrations: () => http.request<{ results: { key: string; label: string; area: string; status: 'connected' | 'not_configured'; provider: string | null }[]; note: string }>('/os/system/integrations'),
  },
});

export type OSApi = ReturnType<typeof osApi>;
