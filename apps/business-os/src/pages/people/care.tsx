/* eslint-disable @typescript-eslint/no-explicit-any */
import { useRef, useState } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Button, Icon, useToast } from '@click/ui';
import { apiMessage, people } from '../../lib/api';
import { fmtDate, fmtDateTime, humanize, relative } from '../../lib/format';
import { useAccess } from '../../session/access';
import { DataTable, FormDialog, StatGrid, type FieldSpec } from '../../components/forms';
import { Alert, Card, Dialog, Empty, LoadingRows, Pager, QueryError, Status, Tabs } from '../../components/ui';
import { OffboardingCard } from './core';
import { Bars, SectionTitle, opts, useLookups } from './common';

const K = ['os', 'people'];
const REQUEST_CATEGORIES = [['employment_letter', 'Employment letter'], ['document', 'Document request'], ['leave', 'Leave issue'], ['payroll', 'Payroll question'],
  ['attendance', 'Attendance issue'], ['benefits', 'Benefits question'], ['profile_correction', 'Profile correction'], ['transfer', 'Transfer request'], ['other', 'Other HR support']]
  .map(([value, label]) => ({ value: value!, label: label! }));

// =================================================================================================================
// HR requests (service desk)
// =================================================================================================================
export function Requests() {
  const access = useAccess();
  const qc = useQueryClient();
  const toast = useToast();
  const [params, setParams] = useSearchParams();
  const staff = access.can('people.request.manage');
  const view = (params.get('view') ?? 'mine') as 'mine' | 'assigned' | 'queue';
  const [page, setPage] = useState(1);
  const q = useQuery({ queryKey: [...K, 'requests', view, page], queryFn: () => people.list('requests', { view, page }) });
  const set = (k: string, v: string | null) => setParams((p) => { if (v) p.set(k, v); else p.delete(k); return p; });
  return (
    <>
      <SectionTitle title="HR requests" desc="Letters, documents, payroll and leave questions, profile corrections. Only you and HR can see your requests."
        actions={<Button onClick={() => set('new', '1')}><Icon name="plus" size={16} />New request</Button>} />
      <Tabs value={view} onChange={(v) => { setPage(1); set('view', v); }} items={[{ value: 'mine', label: 'My requests' }, { value: 'assigned', label: 'Assigned to me' },
        ...(staff ? [{ value: 'queue' as const, label: 'HR queue' }] : [])]} />
      <Card flush>
        {q.isPending ? <LoadingRows /> : q.error ? <QueryError error={q.error} /> : <>
          <DataTable rows={q.data.results} empty="No requests" onRow={(r: any) => set('open', r.id)} columns={[
            { key: 's', label: 'Request', render: (r: any) => <><strong>{r.subject}</strong><div className="xs muted mono">{r.code} · {humanize(r.category)}</div></> },
            ...(view !== 'mine' ? [{ key: 'e', label: 'Employee', render: (r: any) => r.employeeName }] : []),
            { key: 'a', label: 'Assignee', render: (r: any) => r.assigneeName ?? '—' }, { key: 'u', label: 'Updated', render: (r: any) => relative(r.updatedAt) },
            { key: 'st', label: 'Status', render: (r: any) => <Status value={r.status} label={humanize(r.status)} /> }]} />
          <Pager page={q.data.page} hasNext={q.data.hasNext} count={q.data.count} onPage={setPage} /></>}
      </Card>
      {params.get('open') && <RequestDialog id={params.get('open')!} onClose={() => set('open', null)} />}
      {params.get('new') === '1' && <FormDialog title="New HR request" onClose={() => set('new', null)} submitLabel="Send to HR"
        fields={[{ name: 'category', label: 'What do you need?', type: 'select', required: true, options: REQUEST_CATEGORIES },
          { name: 'subject', label: 'Subject', required: true }, { name: 'description', label: 'Details', type: 'textarea' }]}
        onSubmit={(v) => people.create('requests', v)} onDone={(r: any) => { toast(`Request ${r.code} sent`); void qc.invalidateQueries({ queryKey: [...K, 'requests'] }); }} />}
    </>
  );
}

function RequestDialog({ id, onClose }: { id: string; onClose: () => void }) {
  const qc = useQueryClient();
  const toast = useToast();
  const key = [...K, 'request', id];
  const q = useQuery({ queryKey: key, queryFn: () => people.get('requests', id) });
  const [body, setBody] = useState('');
  const [internal, setInternal] = useState(false);
  const [resolution, setResolution] = useState<string | null>(null);
  const inv = () => { void qc.invalidateQueries({ queryKey: key }); void qc.invalidateQueries({ queryKey: [...K, 'requests'] }); };
  const comment = useMutation({ mutationFn: () => people.action(`requests/${id}/comments`, { body, internal }), onSuccess: () => { setBody(''); inv(); }, onError: (e) => toast(apiMessage(e), 'error') });
  const update = useMutation({ mutationFn: (v: Record<string, unknown>) => people.update('requests', id, v), onSuccess: () => { toast('Updated'); inv(); }, onError: (e) => toast(apiMessage(e), 'error') });
  return (
    <Dialog title={q.data ? `${q.data.code} · ${q.data.subject}` : 'Request'} onClose={onClose} wide>
      {q.isPending ? <LoadingRows /> : q.error ? <QueryError error={q.error} /> : (
        <div className="stack">
          <div className="row row--wrap"><Status value={q.data.status} label={humanize(q.data.status)} /><span className="chip">{humanize(q.data.category)}</span>
            <span className="xs muted">{q.data.employeeName} · opened {fmtDateTime(q.data.createdAt)}</span></div>
          {q.data.description && <p className="small" style={{ whiteSpace: 'pre-wrap' }}>{q.data.description}</p>}
          {q.data.resolution && <Alert tone="success">{q.data.resolution}</Alert>}
          <ul className="timeline">{q.data.comments.map((c: any, i: number) => <li key={i}><strong className="small">{c.author ?? '—'}</strong>{c.internal && <span className="flag" style={{ marginLeft: 6 }}>internal</span>}
            <span className="xs muted"> · {relative(c.at)}</span><div className="small" style={{ whiteSpace: 'pre-wrap' }}>{c.body}</div></li>)}</ul>
          {q.data.status !== 'closed' && <div className="stack" style={{ gap: 6 }}>
            <textarea className="field__input" rows={2} aria-label="Reply" placeholder="Write a reply" value={body} onChange={(e) => setBody(e.target.value)} />
            <div className="row">{q.data.canManage && <label className="row small"><input type="checkbox" checked={internal} onChange={(e) => setInternal(e.target.checked)} />Internal note (HR only)</label>}
              <Button size="sm" style={{ marginLeft: 'auto' }} disabled={!body.trim()} loading={comment.isPending} onClick={() => comment.mutate()}>Send</Button></div></div>}
          {q.data.canManage && <Card title="HR actions">
            <div className="row row--wrap">
              {['in_progress', 'waiting', 'closed'].filter((s) => s !== q.data.status).map((s) => <Button key={s} size="sm" variant="outline" onClick={() => update.mutate({ status: s })}>{humanize(s)}</Button>)}
              <Button size="sm" onClick={() => setResolution(q.data.resolution || '')}>Resolve</Button>
            </div>
            {resolution !== null && <div className="stack" style={{ gap: 6, marginTop: 8 }}>
              <textarea className="field__input" rows={2} aria-label="Resolution" placeholder="Resolution shared with the employee" value={resolution} onChange={(e) => setResolution(e.target.value)} />
              <Button size="sm" disabled={!resolution.trim()} onClick={() => { update.mutate({ status: 'resolved', resolution }); setResolution(null); }}>Save resolution</Button></div>}
          </Card>}
        </div>
      )}
    </Dialog>
  );
}

// =================================================================================================================
// Employee relations cases (restricted; every view is audited)
// =================================================================================================================
export function Cases() {
  const access = useAccess();
  const qc = useQueryClient();
  const toast = useToast();
  const [status, setStatus] = useState('');
  const [page, setPage] = useState(1);
  const [open, setOpen] = useState<string | null>(null);
  const [create, setCreate] = useState(false);
  const q = useQuery({ queryKey: [...K, 'cases', status, page], queryFn: () => people.list('cases', { status: status || undefined, page }) });
  const emps = useQuery({ queryKey: [...K, 'employees', 'case'], queryFn: () => people.employees({ page_size: 100 }), enabled: create });
  return (
    <>
      <SectionTitle title="Employee relations" desc="Restricted. Concerns, grievances, investigations and corrective actions. Cases are never deleted, and every view is audited."
        actions={access.can('people.case.manage') && <Button onClick={() => setCreate(true)}><Icon name="plus" size={16} />Open case</Button>} />
      <Card flush>
        <div className="toolbar"><select className="field__input" aria-label="Status" value={status} onChange={(e) => { setStatus(e.target.value); setPage(1); }}>
          <option value="">All</option>{['open', 'investigating', 'action', 'closed'].map((s) => <option key={s} value={s}>{humanize(s)}</option>)}</select></div>
        {q.isPending ? <LoadingRows /> : q.error ? <QueryError error={q.error} /> : <>
          <DataTable rows={q.data.results} empty="No cases" onRow={(c: any) => setOpen(c.id)} columns={[
            { key: 'c', label: 'Case', render: (c: any) => <><strong>{c.summary}</strong><div className="xs muted mono">{c.code} · {humanize(c.kind)}</div></> },
            { key: 'e', label: 'Employee', render: (c: any) => c.employeeName }, { key: 'v', label: 'Severity', render: (c: any) => <span className={`sev sev--${c.severity}`} title={c.severity} /> },
            { key: 'a', label: 'Assigned', render: (c: any) => c.assignedToName ?? '—' }, { key: 's', label: 'Status', render: (c: any) => <Status value={c.status} /> }]} />
          <Pager page={q.data.page} hasNext={q.data.hasNext} count={q.data.count} onPage={setPage} /></>}
      </Card>
      {open && <CaseDialog id={open} onClose={() => setOpen(null)} />}
      {create && <FormDialog title="Open case" onClose={() => setCreate(false)} initial={{ kind: 'concern', severity: 'medium' }}
        fields={[{ name: 'employee', label: 'Employee concerned', type: 'select', required: true, options: (emps.data?.results ?? []).map((e) => ({ value: e.id, label: `${e.displayName} · ${e.employeeId}` })) },
          { name: 'kind', label: 'Type', type: 'select', half: true, options: ['concern', 'complaint', 'grievance', 'investigation', 'disciplinary', 'corrective_action'].map((k) => ({ value: k, label: humanize(k) })) },
          { name: 'severity', label: 'Severity', type: 'select', half: true, options: ['low', 'medium', 'high', 'critical'].map((k) => ({ value: k, label: humanize(k) })) },
          { name: 'summary', label: 'Summary (no unnecessary personal detail)', required: true }]}
        onSubmit={(v) => people.create('cases', v)} onDone={() => { toast('Case opened'); void qc.invalidateQueries({ queryKey: [...K, 'cases'] }); }} />}
    </>
  );
}

function CaseDialog({ id, onClose }: { id: string; onClose: () => void }) {
  const qc = useQueryClient();
  const access = useAccess();
  const key = [...K, 'case', id];
  const q = useQuery({ queryKey: key, queryFn: () => people.get('cases', id) });
  const [note, setNote] = useState('');
  const inv = () => { void qc.invalidateQueries({ queryKey: key }); void qc.invalidateQueries({ queryKey: [...K, 'cases'] }); };
  const add = useMutation({ mutationFn: () => people.action(`cases/${id}/notes`, { body: note }), onSuccess: () => { setNote(''); inv(); } });
  const upd = useMutation({ mutationFn: (v: Record<string, unknown>) => people.update('cases', id, v), onSuccess: inv });
  const manage = access.can('people.case.manage');
  return (
    <Dialog title={q.data ? `${q.data.code} · ${humanize(q.data.kind)}` : 'Case'} onClose={onClose} wide>
      {q.isPending ? <LoadingRows /> : q.error ? <QueryError error={q.error} /> : (
        <div className="stack">
          <Alert tone="warning">Confidential. This view was recorded in the audit trail.</Alert>
          <dl className="kv"><dt>Employee</dt><dd>{q.data.employeeName}</dd><dt>Summary</dt><dd>{q.data.summary}</dd><dt>Severity</dt><dd>{humanize(q.data.severity)}</dd>
            <dt>Status</dt><dd><Status value={q.data.status} /></dd><dt>Opened</dt><dd>{fmtDateTime(q.data.createdAt)}</dd>{q.data.outcome && <><dt>Outcome</dt><dd>{q.data.outcome}</dd></>}</dl>
          <ul className="timeline">{q.data.notes.map((n: any, i: number) => <li key={i}><strong className="small">{n.author}</strong><span className="xs muted"> · {fmtDateTime(n.at)}</span><div className="small" style={{ whiteSpace: 'pre-wrap' }}>{n.body}</div></li>)}</ul>
          {manage && q.data.status !== 'closed' && <>
            <textarea className="field__input" rows={2} aria-label="Case note" placeholder="Add a case note" value={note} onChange={(e) => setNote(e.target.value)} />
            <div className="row row--wrap"><Button size="sm" disabled={!note.trim()} onClick={() => add.mutate()}>Add note</Button>
              {['investigating', 'action'].filter((s) => s !== q.data.status).map((s) => <Button key={s} size="sm" variant="outline" onClick={() => upd.mutate({ status: s })}>{humanize(s)}</Button>)}
              <Button size="sm" variant="outline" onClick={() => { const outcome = window.prompt('Outcome'); if (outcome) upd.mutate({ status: 'closed', outcome }); }}>Close case</Button></div></>}
        </div>
      )}
    </Dialog>
  );
}

// =================================================================================================================
// Lifecycle: promotions, transfers, revisions and exits
// =================================================================================================================
export function Lifecycle() {
  const access = useAccess();
  const [tab, setTab] = useState<'changes' | 'exits'>(access.can('people.lifecycle.view') ? 'changes' : 'exits');
  const changes = useQuery({ queryKey: [...K, 'changes'], queryFn: () => people.fetch('changes'), enabled: tab === 'changes' });
  const exits = useQuery({ queryKey: [...K, 'offboarding'], queryFn: () => people.list('offboarding', { page_size: 50 }), enabled: tab === 'exits' });
  return (
    <>
      <SectionTitle title="Promotions, transfers & exits" desc="Every change goes through approval and applies on its effective date. Start one from the employee’s profile." />
      <Tabs value={tab} onChange={setTab} items={[...(access.can('people.lifecycle.view') ? [{ value: 'changes' as const, label: 'Changes' }] : []),
        ...(access.can('people.offboarding.view') ? [{ value: 'exits' as const, label: 'Exits' }] : [])]} />
      {tab === 'changes' && (changes.isPending ? <Card><LoadingRows /></Card> : changes.error ? <QueryError error={changes.error} /> : (
        <Card flush><DataTable rows={changes.data.results} empty="No changes" columns={[
          { key: 'e', label: 'Employee', render: (c: any) => <Link to={`/people/${c.employee.id}?tab=lifecycle`}>{c.employee.name}</Link> },
          { key: 'k', label: 'Change', render: (c: any) => <>{c.kindLabel}<div className="xs muted">{Object.keys(c.proposed).map((k) => humanize(k.replace(/_id$/, ''))).join(', ')}{c.compensation && Object.keys(c.compensation).length ? ' · pay' : ''}</div></> },
          { key: 'd', label: 'Effective', render: (c: any) => fmtDate(c.effectiveDate) }, { key: 'r', label: 'Requested by', render: (c: any) => c.requestedBy ?? '—' },
          { key: 's', label: 'Status', render: (c: any) => <Status value={c.status} label={humanize(c.status)} /> },
          { key: 'a', label: '', render: (c: any) => c.approvalId && <Link to={`/approvals/${c.approvalId}`} className="small">Approval</Link> }]} /></Card>))}
      {tab === 'exits' && (exits.isPending ? <Card><LoadingRows /></Card> : exits.error ? <QueryError error={exits.error} /> : !exits.data.results.length ? <Card><Empty title="No exits" /></Card> : (
        <div className="stack">{exits.data.results.map((o: any) => <OffboardingCard key={o.id} o={o} />)}</div>))}
    </>
  );
}

// =================================================================================================================
// HR analytics (aggregates only; small groups suppressed)
// =================================================================================================================
export function Analytics() {
  const q = useQuery({ queryKey: [...K, 'analytics'], queryFn: people.analytics });
  if (q.isPending) return <><SectionTitle title="HR analytics" /><Card><LoadingRows rows={6} /></Card></>;
  if (q.error) return <QueryError error={q.error} />;
  const d = q.data;
  return (
    <>
      <SectionTitle title="HR analytics" desc={`Aggregates for your ${d.scope} scope as of ${fmtDate(d.asOf)}. Groups smaller than ${d.minGroup} are hidden to protect individuals.`} />
      <div className="stack stack--lg">
        <StatGrid items={[{ key: 'h', label: 'Headcount', value: d.headcount.total }, { key: 'a', label: 'Attrition · 12 months', value: `${d.attritionTwelveMonthsPct ?? d.attrition12mPct ?? 0}%` },
          { key: 't', label: 'Time to hire', value: d.recruitment.timeToHireDays != null ? `${d.recruitment.timeToHireDays} days` : '—' },
          { key: 'l', label: 'Late check-ins · 30d', value: d.attendance30d?.records ? `${Math.round((d.attendance30d.late / d.attendance30d.records) * 100)}%` : '—' },
          { key: 'c', label: 'Training completed', value: d.training.assigned ? `${Math.round((d.training.completed / d.training.assigned) * 100)}%` : '—', hint: `${d.training.mandatoryOverdue} mandatory overdue`,
            tone: d.training.mandatoryOverdue ? 'alert' : undefined }]} />
        {d.insights.length > 0 && <Card title="What stands out">
          <ul className="list">{d.insights.map((x: any, i: number) => <li key={i} className="list-row" style={{ alignItems: 'flex-start' }}><span className="chip">{x.kind}</span>
            <div className="list-row__main"><strong className="small">{x.title}</strong><div className="small">{x.what}</div><div className="xs muted">Suggestion: {x.suggestion}</div></div></li>)}</ul>
          <p className="xs muted">Observations from your data — not predictions about individuals.</p></Card>}
        <div className="grid grid--2">
          <Card title="By department"><Bars rows={d.headcount.byDepartment} /></Card>
          <Card title="By location"><Bars rows={d.headcount.byLocation} /></Card>
          <Card title="Joiners vs leavers"><div className="bars">{d.movement.map((m: any) => <div key={m.month} className="bars__row"><span>{m.month}</span>
            <span className="small">+{m.joined} / −{m.left}</span><span /></div>)}</div></Card>
          <Card title="Tenure"><Bars rows={d.tenure} /></Card>
          <Card title="Hiring funnel"><Bars rows={d.recruitment.funnel.map((f: any) => ({ label: humanize(f.stage), value: f.value }))} /></Card>
          <Card title="Performance distribution"><Bars rows={d.performanceDistribution} /></Card>
          <Card title="Leave taken · 12 months"><Bars rows={d.leave12m} /></Card>
          <Card title="Skills"><Bars rows={d.skills} /></Card>
        </div>
      </div>
    </>
  );
}

// =================================================================================================================
// HR settings (generic CRUD over configuration) + bulk import
// =================================================================================================================
type SettingDef = { key: string; label: string; path: string; fields: FieldSpec[]; columns: { key: string; label: string; render: (r: any) => React.ReactNode }[]; initial?: Record<string, unknown> };

function useSettingDefs(): SettingDef[] {
  const lk = useLookups();
  const days = [['0', 'Mon'], ['1', 'Tue'], ['2', 'Wed'], ['3', 'Thu'], ['4', 'Fri'], ['5', 'Sat'], ['6', 'Sun']].map(([value, label]) => ({ value: value!, label: label! }));
  return [
    { key: 'levels', label: 'Job levels', path: 'settings/job-levels', fields: [{ name: 'code', label: 'Code', required: true, half: true }, { name: 'name', label: 'Name', required: true, half: true }, { name: 'rank', label: 'Rank', type: 'number', half: true }],
      columns: [{ key: 'c', label: 'Code', render: (r) => r.code }, { key: 'n', label: 'Name', render: (r) => r.name }, { key: 'r', label: 'Rank', render: (r) => r.rank }] },
    { key: 'designations', label: 'Designations', path: 'settings/designations', initial: { is_active: true },
      fields: [{ name: 'code', label: 'Code', required: true, half: true }, { name: 'name', label: 'Name', required: true, half: true }, { name: 'grade', label: 'Grade', half: true }, { name: 'is_active', label: 'Active', type: 'checkbox' }],
      columns: [{ key: 'c', label: 'Code', render: (r) => r.code }, { key: 'n', label: 'Name', render: (r) => r.name }, { key: 'g', label: 'Grade', render: (r) => r.grade || '—' }, { key: 'a', label: 'Active', render: (r) => (r.isActive ? 'Yes' : 'No') }] },
    { key: 'schedules', label: 'Work schedules', path: 'settings/schedules', initial: { kind: 'standard', start_time: '09:30', end_time: '18:30', grace_minutes: 15, working_days: ['0', '1', '2', '3', '4'] },
      fields: [{ name: 'name', label: 'Name', required: true }, { name: 'kind', label: 'Type', type: 'select', half: true, options: ['standard', 'shift', 'flexible', 'remote', 'hybrid'].map((k) => ({ value: k, label: humanize(k) })) },
        { name: 'grace_minutes', label: 'Late grace (min)', type: 'number', half: true }, { name: 'start_time', label: 'Starts', type: 'time', half: true }, { name: 'end_time', label: 'Ends', type: 'time', half: true },
        { name: 'working_days', label: 'Working days', type: 'multiselect', options: days }, { name: 'org_unit', label: 'Location (optional)', type: 'select', half: true, options: opts(lk.data?.locations) },
        { name: 'department', label: 'Department (optional)', type: 'select', half: true, options: opts(lk.data?.departments) }, { name: 'is_default', label: 'Default schedule', type: 'checkbox' }],
      columns: [{ key: 'n', label: 'Schedule', render: (r) => <>{r.name}{r.isDefault && <span className="chip" style={{ marginLeft: 6 }}>default</span>}</> }, { key: 'k', label: 'Type', render: (r) => humanize(r.kind) },
        { key: 't', label: 'Hours', render: (r) => `${String(r.startTime).slice(0, 5)}–${String(r.endTime).slice(0, 5)}` }, { key: 'd', label: 'Days', render: (r) => (r.workingDays ?? []).map((x: number) => days[x]?.label).join(' ') }] },
    { key: 'leave', label: 'Leave types', path: 'settings/leave-types', initial: { paid: true, allow_half_day: true, is_active: true, annual_quota: 12, color: '#2563eb' },
      fields: [{ name: 'code', label: 'Code', required: true, half: true }, { name: 'name', label: 'Name', required: true, half: true },
        { name: 'annual_quota', label: 'Days per year', type: 'number', half: true }, { name: 'carry_forward_max', label: 'Max carry-forward', type: 'number', half: true },
        { name: 'requires_document_after_days', label: 'Document needed after (days)', type: 'number', half: true }, { name: 'color', label: 'Colour', half: true },
        { name: 'paid', label: 'Paid leave', type: 'checkbox' }, { name: 'allow_half_day', label: 'Allow half days', type: 'checkbox' }, { name: 'is_active', label: 'Active', type: 'checkbox' }],
      columns: [{ key: 'n', label: 'Leave type', render: (r) => <><span className="dot" style={{ background: r.color }} /> {r.name} <span className="xs muted mono">{r.code}</span></> },
        { key: 'q', label: 'Per year', render: (r) => Number(r.annualQuota) }, { key: 'p', label: 'Paid', render: (r) => (r.paid ? 'Yes' : 'No') }, { key: 'a', label: 'Active', render: (r) => (r.isActive ? 'Yes' : 'No') }] },
    { key: 'calendars', label: 'Holiday calendars', path: 'settings/holiday-calendars',
      fields: [{ name: 'name', label: 'Name', required: true }, { name: 'org_unit', label: 'Location (blank = everyone)', type: 'select', options: opts(lk.data?.locations) }],
      columns: [{ key: 'n', label: 'Calendar', render: (r) => r.name }, { key: 'o', label: 'Applies to', render: (r) => r.orgUnitName ?? 'Everyone' }, { key: 'h', label: 'Holidays', render: (r) => (r.holidays ?? []).length }] },
    { key: 'checklists', label: 'Onboarding & exit checklists', path: 'settings/checklists', initial: { kind: 'onboarding' },
      fields: [{ name: 'name', label: 'Name', required: true }, { name: 'kind', label: 'Type', type: 'select', half: true, options: [{ value: 'onboarding', label: 'Onboarding' }, { value: 'offboarding', label: 'Offboarding' }] },
        { name: 'department', label: 'Department (optional)', type: 'select', half: true, options: opts(lk.data?.departments) }, { name: 'is_default', label: 'Default for this type', type: 'checkbox' },
        { name: 'steps_text', label: 'Steps — one per line as “Title | assignee (hr, it, manager, employee, finance) | days from start”', type: 'textarea', required: true }],
      columns: [{ key: 'n', label: 'Checklist', render: (r) => <>{r.name}{r.isDefault && <span className="chip" style={{ marginLeft: 6 }}>default</span>}</> }, { key: 'k', label: 'Type', render: (r) => humanize(r.kind) },
        { key: 's', label: 'Steps', render: (r) => (r.steps ?? []).length }] },
  ];
}

const parseSteps = (text: string) => text.split('\n').map((l) => l.trim()).filter(Boolean).map((l) => {
  const [title, assignee, days] = l.split('|').map((x) => x.trim());
  return { title, owner: assignee || "hr", offset_days: Number(days) || 0 };
});

export function HRSettings() {
  const access = useAccess();
  const defs = useSettingDefs();
  const [tab, setTab] = useState(defs[0]!.key);
  const def = defs.find((d) => d.key === tab)!;
  const qc = useQueryClient();
  const toast = useToast();
  const [edit, setEdit] = useState<any>(null);
  const [holiday, setHoliday] = useState<any>(null);
  const q = useQuery({ queryKey: [...K, 'settings', def.path], queryFn: () => people.list(def.path, { page_size: 100 }), enabled: tab !== 'import' });
  const can = access.can('people.settings.configure');
  const inv = () => { void qc.invalidateQueries({ queryKey: [...K, 'settings'] }); void qc.invalidateQueries({ queryKey: [...K, 'lookups'] }); };
  const prep = (v: Record<string, unknown>) => {
    const out = { ...v };
    if (tab === 'schedules' && Array.isArray(out.workingDays)) out.workingDays = (out.workingDays as string[]).map(Number);
    if (tab === 'checklists') { out.steps = parseSteps(String(out.stepsText ?? '')); delete out.stepsText; }
    return out;
  };
  return (
    <>
      <SectionTitle title="HR settings" desc="Levels, designations, schedules, leave policies, holiday calendars, checklists and bulk import. Changes are audited." />
      <Tabs value={tab} onChange={setTab} items={[...defs.map((d) => ({ value: d.key, label: d.label })), ...(access.can('people.employee.create') ? [{ value: 'import', label: 'Import employees' }] : [])]} />
      {tab === 'import' ? <ImportEmployees /> : (
        <Card flush title={def.label} actions={can && <Button size="sm" onClick={() => setEdit({})}><Icon name="plus" size={15} />Add</Button>}>
          {q.isPending ? <LoadingRows /> : q.error ? <QueryError error={q.error} /> : <DataTable rows={q.data.results} onRow={can ? (r: any) => setEdit(r) : undefined} columns={[...def.columns,
            ...(tab === 'calendars' && can ? [{ key: 'h2', label: '', render: (r: any) => <Button size="sm" variant="ghost" onClick={(e) => { e.stopPropagation(); setHoliday(r); }}>Add holiday</Button> }] : [])]} />}
        </Card>
      )}
      {edit && <FormDialog title={`${edit.id ? 'Edit' : 'Add'} · ${def.label}`} wide onClose={() => setEdit(null)} fields={def.fields}
        initial={edit.id ? Object.fromEntries(def.fields.map((f) => {
          const camelKey = f.name.replace(/_([a-z])/g, (_, c: string) => c.toUpperCase());
          if (f.name === 'steps_text') return [f.name, (edit.steps ?? []).map((s: any) => `${s.title} | ${s.owner ?? "hr"} | ${s.offsetDays ?? 0}`).join('\n')];
          if (f.name === 'working_days') return [f.name, (edit.workingDays ?? []).map(String)];
          return [f.name, edit[camelKey]];
        })) : def.initial}
        onSubmit={(v) => (edit.id ? people.update(def.path, edit.id, prep(v)) : people.create(def.path, prep(v)))} onDone={() => { toast('Saved'); inv(); }} />}
      {holiday && <FormDialog title={`Add holiday · ${holiday.name}`} onClose={() => setHoliday(null)}
        fields={[{ name: 'date', label: 'Date', type: 'date', required: true, half: true }, { name: 'name', label: 'Holiday', required: true, half: true }, { name: 'optional', label: 'Optional holiday', type: 'checkbox' }]}
        onSubmit={(v) => people.action('holidays', { ...v, calendar: holiday.id })} onDone={() => { toast('Holiday added'); inv(); }} />}
    </>
  );
}

function ImportEmployees() {
  const file = useRef<HTMLInputElement>(null);
  const toast = useToast();
  const qc = useQueryClient();
  const [allow, setAllow] = useState(false);
  const [preview, setPreview] = useState<any>(null);
  const run = useMutation({ mutationFn: (mode: 'preview' | 'commit') => people.importEmployees(file.current!.files![0]!, mode, allow),
    onSuccess: (r, mode) => { if (mode === 'commit') { toast(`Imported: ${r.creates} new, ${r.updates} updated`); setPreview(null); void qc.invalidateQueries({ queryKey: K }); } else setPreview(r); } });
  return (
    <Card title="Import employees from CSV">
      <div className="stack">
        <p className="small">Columns: <code>employee_id, full_name, work_email, department_code, designation_code, location_code, manager_employee_id, worker_type, employment_type, joined_on</code>.
          Leave employee_id blank to assign a new EMP- number. Preview first — nothing is written until you confirm, and rows outside your scope are rejected.</p>
        <input ref={file} type="file" accept=".csv,text/csv" className="field__input" aria-label="CSV file" onChange={() => setPreview(null)} />
        <label className="row small"><input type="checkbox" checked={allow} onChange={(e) => setAllow(e.target.checked)} />Update existing employees when the employee ID matches</label>
        {run.error && <Alert tone="error">{apiMessage(run.error)}</Alert>}
        <div className="row"><Button variant="outline" loading={run.isPending} onClick={() => file.current?.files?.[0] && run.mutate('preview')}>Preview</Button>
          {preview && !preview.errors && <Button loading={run.isPending} onClick={() => run.mutate('commit')}>Import {preview.total} rows</Button>}</div>
        {preview && <>
          <p className="small">{preview.total} rows · {preview.creates} new · {preview.updates} updates · <strong style={{ color: preview.errors ? 'var(--c-danger)' : undefined }}>{preview.errors} with errors</strong></p>
          <DataTable rows={preview.rows.map((r: any) => ({ ...r, id: String(r.row) }))} columns={[{ key: 'r', label: 'Row', render: (r: any) => r.row },
            { key: 'i', label: 'Employee ID', render: (r: any) => <span className="mono">{r.employeeId || 'new'}</span> }, { key: 'n', label: 'Name', render: (r: any) => r.fullName },
            { key: 'a', label: 'Action', render: (r: any) => <Status value={r.action === 'error' ? 'rejected' : 'active'} label={r.action} /> },
            { key: 'e', label: 'Problems', render: (r: any) => <span className="xs" style={{ color: 'var(--c-danger)' }}>{r.errors.join('; ')}</span> }]} /></>}
      </div>
    </Card>
  );
}
