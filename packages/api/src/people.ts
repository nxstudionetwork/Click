/** Click Business OS — People & HR contract (/api/v1/os/people/*). The server decides what each caller sees. */
import type { HttpClient, Query } from './http';
import type { Paginated } from './types';

type UUID = string;
type ISO = string;
type Any = any; // eslint-disable-line @typescript-eslint/no-explicit-any
export interface PRef { id: UUID; name: string }

export interface PEmployee {
  id: UUID; employeeId: string; fullName: string; preferredName: string; displayName: string; workEmail: string; workPhone: string;
  designation: PRef | null; department: PRef | null; team: PRef | null; location: PRef | null; businessUnit: PRef | null; manager: PRef | null;
  status: string; workerType: string; workMode: string; avatarUrl: string | null;
  // full record only
  employmentType?: string; jobLevel?: PRef | null; joinedOn?: string | null; probationEndOn?: string | null; confirmedOn?: string | null;
  contractEndOn?: string | null; exitDate?: string | null; exitReason?: string; hasAccount?: boolean; tenureDays?: number | null; createdAt?: ISO;
}
export interface PEmployeeDetail extends PEmployee {
  tabs: string[]; isSelf: boolean; fullRecord: boolean; canEdit: boolean; canEditSelf: boolean;
  actions: { promote: boolean; offboard: boolean; feedback: boolean; resign: boolean; uploadDocument: boolean };
  secondaryManagers: PRef[]; directReports: { id: UUID; name: string; designation: string | null }[];
}
export interface PNavSection { key: string; label: string; items: { key: string; label: string; path: string }[] }
export interface PMetric { key: string; label: string; value: number | string | null; path?: string; format?: string }
export interface PLookups {
  departments: { id: UUID; name: string; code: string }[]; teams: { id: UUID; name: string; departmentId: UUID }[];
  locations: { id: UUID; name: string; type: string; depth: number }[]; designations: PRef[]; jobLevels: PRef[]; schedules: PRef[];
  workerTypes: { value: string; label: string }[]; employmentTypes: { value: string; label: string }[]; workModes: { value: string; label: string }[];
  statuses: { value: string; label: string }[];
}
export interface PLeaveBalance { type: string; typeId: UUID; color: string; paid: boolean; entitled: string; used: string; pending: string; available: string }
export interface PLeaveRequest {
  id: UUID; employee: PRef; leaveType: { id: UUID; name: string; color: string; paid: boolean }; startDate: string; endDate: string; halfDay: string;
  days: string; reason: string; status: string; approvalId: UUID | null; createdAt: ISO;
}
export interface PAttendance { date: string; checkIn: ISO | null; checkOut: ISO | null; status: string; mode: string; late: boolean; early: boolean;
  workedMinutes: number | null; source: string; note?: string }
export interface PGoal { id: UUID; level: string; parent: UUID | null; cycle: UUID | null; employee: UUID | null; employeeName: string | null; title: string;
  description: string; kind: string; metric: string; target: string | null; current: string | null; weight: number; dueOn: string | null; status: string;
  progress: number | null; children: number }
export interface PReview { id: UUID; cycle: string; employee: PRef; kind: string; kindLabel: string; status: string; dueOn: string | null; rating: number | null;
  strengths: string; improvements: string; comments: string; submittedAt: ISO | null; mine: boolean }
export interface PPosition { id: UUID; code: string; title: string; description: string; department: UUID; departmentName: string; team: UUID | null;
  orgUnit: UUID | null; locationName: string | null; jobLevel: UUID | null; designation: UUID | null; workerType: string; employmentType: string;
  reportingManager: UUID | null; reportingManagerName: string | null; headcount: number; filled: number; salaryMin?: string | null; salaryMax?: string | null;
  currency: string; status: string; approval: UUID | null; createdAt: ISO }
export interface POpening { id: UUID; code: string; position: UUID; positionCode: string; title: string; description: string; status: string; openings: number;
  recruiter: UUID | null; recruiterName: string | null; hiringManager: UUID | null; hiringManagerName: string | null; internal: boolean; external: boolean;
  openedOn: string | null; departmentName: string; locationName: string | null; counts: Record<string, number> }
export interface PApplication { id: UUID; candidate: { id: UUID; code: string; fullName: string; currentTitle: string; experienceYears: string | null; source: string; skills: string[] };
  opening: UUID; stage: string; stageChangedAt: ISO; daysInStage: number | null; rejectionReason: string;
  interviews: { id: UUID; round: string; at: ISO; status: string; feedback: number }[]; offers: { id: UUID; code: string; status: string }[] }
export interface PCandidate { id: UUID; code: string; fullName: string; email: string; phone: string; currentCompany: string; currentTitle: string;
  experienceYears: string | null; skills: string[]; education: string; location: string; source: string; expectedCompensation?: string | null;
  noticeDays: number | null; talentPool: boolean; consentOn: string | null; notes: string; applications: { id: UUID; opening: string; openingId: UUID; stage: string }[] }
export interface PInterview { id: UUID; round: string; kind: string; at: ISO; duration: number; location: string; status: string; criteria: string[]; opening: string;
  candidate: { name: string; currentTitle: string; experienceYears: string | null; skills: string[] };
  myFeedback: { rating: number | null; recommendation: string; notes: string; scores: Record<string, number> } | null }
export interface POffer { id: UUID; code: string; candidate: string; opening: string; joiningDate: string; status: string; expiresOn: string | null;
  approvalId: UUID | null; designation: string | null; benefits: string; baseAnnual?: string; variableAnnual?: string; joiningBonus?: string; currency?: string }
export interface PHRRequest { id: UUID; code: string; employee: UUID; employeeName: string; category: string; subject: string; description: string; status: string;
  assignee: UUID | null; assigneeName: string | null; resolution: string; resolvedAt: ISO | null; createdAt: ISO; updatedAt: ISO }
export interface PDocument { id: UUID; title: string; category: string; sensitivity: string; expiresOn: string | null; expiring: boolean; expired: boolean;
  verification: string; status: string; version: number; fileName: string | null; size: number | null; uploadedBy: string | null; createdAt: ISO; canVerify: boolean }

const e = encodeURIComponent;
const P = '/os/people';

export const peopleApi = (http: HttpClient) => ({
  nav: () => http.request<{ sections: PNavSection[]; hasEmployeeRecord: boolean; isManager: boolean }>(`${P}/nav`),
  home: () => http.request<Any>(`${P}/home`),
  lookups: () => http.request<PLookups>(`${P}/lookups`),
  me: () => http.request<Any>(`${P}/me`),
  orgChart: (q: Query = {}) => http.request<{ nodes: { id: UUID; name: string; employeeId: string; designation: string | null; department: string | null;
    location: string | null; managerId: UUID | null; reports: number }[]; departments: PRef[] }>(`${P}/org-chart`, { query: q }),
  analytics: () => http.request<Any>(`${P}/analytics`),
  employees: (q: Query = {}) => http.request<Paginated<PEmployee> & { fullRecord: boolean; canCreate: boolean; canExport: boolean }>(`${P}/employees`, { query: q }),
  createEmployee: (input: Record<string, unknown>) => http.request<PEmployee>(`${P}/employees`, { method: 'POST', body: input }),
  employee: (id: string) => http.request<PEmployeeDetail>(`${P}/employees/${e(id)}`),
  updateEmployee: (id: string, input: Record<string, unknown>) => http.request<PEmployee>(`${P}/employees/${e(id)}`, { method: 'PATCH', body: input }),
  tab: (id: string, tab: string) => http.request<Any>(`${P}/employees/${e(id)}/${e(tab)}`),
  updateContact: (id: string, input: Record<string, unknown>) => http.request<Any>(`${P}/employees/${e(id)}/contact`, { method: 'PATCH', body: input }),
  setSkill: (id: string, input: { skillId: string; proficiency: number; evidence?: string }) => http.request<Any>(`${P}/employees/${e(id)}/skills`, { method: 'PATCH', body: input }),
  addCertification: (id: string, input: Record<string, unknown>) => http.request<{ id: UUID }>(`${P}/employees/${e(id)}/certifications`, { method: 'POST', body: input }),
  salaryRevision: (id: string, input: Record<string, unknown>) => http.request<Any>(`${P}/employees/${e(id)}/salary-revision`, { method: 'POST', body: input }),
  importEmployees: (file: File, mode: 'preview' | 'commit', allowUpdates = false) => {
    const f = new FormData();
    f.append('file', file);
    f.append('mode', mode);
    f.append('allow_updates', String(allowUpdates));
    return http.request<Any>(`${P}/employees/import`, { method: 'POST', body: f });
  },
  // generic list/create/update/delete for scoped resources
  list: <T = Any>(resource: string, q: Query = {}) => http.request<Paginated<T>>(`${P}/${resource}`, { query: q }),
  get: <T = Any>(resource: string, id: string) => http.request<T>(`${P}/${resource}/${e(id)}`),
  create: <T = Any>(resource: string, input: Record<string, unknown>) => http.request<T>(`${P}/${resource}`, { method: 'POST', body: input }),
  update: <T = Any>(resource: string, id: string, input: Record<string, unknown>) => http.request<T>(`${P}/${resource}/${e(id)}`, { method: 'PATCH', body: input }),
  remove: (resource: string, id: string) => http.request<void>(`${P}/${resource}/${e(id)}`, { method: 'DELETE' }),
  action: <T = Any>(path: string, input: Record<string, unknown> = {}) => http.request<T>(`${P}/${path}`, { method: 'POST', body: input }),
  fetch: <T = Any>(path: string, q: Query = {}) => http.request<T>(`${P}/${path}`, { query: q }),
  documents: (resourceType: string, resourceId: string) =>
    http.request<{ results: PDocument[]; canUpload: boolean }>('/os/documents', { query: { resource_type: resourceType, resource_id: resourceId } }),
  uploadDocument: (input: { resourceType: string; resourceId: string; title: string; category: string; sensitivity: string; expiresOn?: string; file: File }) => {
    const f = new FormData();
    f.append('resource_type', input.resourceType);
    f.append('resource_id', input.resourceId);
    f.append('title', input.title);
    f.append('category', input.category);
    f.append('sensitivity', input.sensitivity);
    if (input.expiresOn) f.append('expires_on', input.expiresOn);
    f.append('file', input.file);
    return http.request<PDocument>('/os/documents', { method: 'POST', body: f });
  },
  documentAction: (id: string, action: 'verify' | 'reject' | 'archive' | 'restore') => http.request<PDocument>(`/os/documents/${e(id)}/${action}`, { method: 'POST' }),
  downloadDocument: (id: string) => http.blob!(`/os/documents/${e(id)}/download`),
});
export type PeopleApi = ReturnType<typeof peopleApi>;
