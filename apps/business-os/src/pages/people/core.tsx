/* eslint-disable @typescript-eslint/no-explicit-any */
import { useEffect, useMemo, useState } from 'react';
import { Link, useNavigate, useParams, useSearchParams } from 'react-router-dom';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Button, Icon, useToast } from '@click/ui';
import { apiMessage, http, people } from '../../lib/api';
import { fmtDate, fmtDateTime, fmtMoney, humanize, relative } from '../../lib/format';
import { useAccess } from '../../session/access';
import { useOS } from '../../session/OSSession';
import { DataTable, FormDialog, StatGrid, type FieldSpec } from '../../components/forms';
import { Alert, Avatar, Card, Empty, LoadingRows, Pager, QueryError, Status, Tabs } from '../../components/ui';
import { Bars, DocumentsPanel, EmpStatus, SectionTitle, opts, useLookups, vopts } from './common';

// =================================================================================================================
// HR home
// =================================================================================================================
export function HRHome() {
  const q = useQuery({ queryKey: ['os', 'people', 'home'], queryFn: people.home });
  const nav = useNavigate();
  useEffect(() => { if (q.data?.mode === 'self') nav('/people/me', { replace: true }); }, [q.data, nav]);
  if (q.isPending) return <><SectionTitle title="People & HR" /><Card><LoadingRows rows={6} /></Card></>;
  if (q.error) return <QueryError error={q.error} />;
  const d = q.data;
  if (d.mode === 'self') return null;
  return (
    <>
      <SectionTitle title="People & HR" desc={`HR command center · scope: ${d.scope}`} />
      <div className="stack stack--lg">
        <StatGrid items={d.metrics.map((m: any) => ({ key: m.key, label: m.label, value: m.value ?? '—', to: m.path,
          tone: ['attendance_exceptions', 'expiring_docs'].includes(m.key) && Number(m.value) > 0 ? 'alert' : undefined }))} />
        <div className="grid grid--2">
          <Card title="Hiring pipeline" actions={<Link to="/people/recruitment" className="small">Recruitment</Link>}>
            <Bars rows={d.pipeline.map((p: any) => ({ label: p.label, value: p.count }))} />
          </Card>
          <Card title="Celebrations this week">
            {!d.celebrations.birthdays.length && !d.celebrations.anniversaries.length ? <p className="muted small">No birthdays or work anniversaries this week.</p> : (
              <ul className="list">
                {d.celebrations.birthdays.map((b: any) => <li key={`b${b.id}`} className="list-row"><span>🎂</span><span className="grow">{b.name}</span><span className="xs muted">{fmtDate(b.on)}</span></li>)}
                {d.celebrations.anniversaries.map((a: any) => <li key={`a${a.id}`} className="list-row"><span>🎉</span><span className="grow">{a.name} · {a.years} year{a.years > 1 ? 's' : ''}</span><span className="xs muted">{fmtDate(a.on)}</span></li>)}
              </ul>
            )}
            <p className="xs muted" style={{ marginTop: 8 }}>{d.celebrations.note}</p>
          </Card>
        </div>
        <p className="xs muted">Updated {relative(d.generatedAt)}. Workforce alerts appear on Home and in Alerts.</p>
      </div>
    </>
  );
}

// =================================================================================================================
// Directory
// =================================================================================================================
export function Directory() {
  const [params, setParams] = useSearchParams();
  const lk = useLookups();
  const ctx = useOS();
  const [page, setPage] = useState(1);
  const [text, setText] = useState(params.get('q') ?? '');
  const filters = Object.fromEntries(['department', 'location', 'designation', 'worker_type', 'status', 'team', 'joined', 'business_unit', 'sort'].map((k) => [k, params.get(k) ?? undefined]));
  if (params.get('manager') === 'me' && ctx.employee) filters.manager = ctx.employee.id;
  useEffect(() => { const t = setTimeout(() => setParams((p) => { if (text) p.set('q', text); else p.delete('q'); return p; }, { replace: true }), 250); return () => clearTimeout(t); }, [text, setParams]);
  const q = useQuery({ queryKey: ['os', 'people', 'employees', filters, params.get('q'), page], queryFn: () => people.employees({ ...filters, q: params.get('q') ?? undefined, page }) });
  const setF = (k: string, v: string) => { setPage(1); setParams((p) => { if (v) p.set(k, v); else p.delete(k); return p; }); };
  const navigate = useNavigate();
  const qc = useQueryClient();
  const toast = useToast();
  const exportCsv = async () => {
    try {
      const qs = new URLSearchParams(Object.entries({ ...filters, export: 'csv' }).filter(([, v]) => v) as [string, string][]);
      const blob = await http.blob!(`/os/people/employees?${qs}`);
      const a = document.createElement('a'); a.href = URL.createObjectURL(blob); a.download = 'click-employees.csv'; a.click();
    } catch (e) { toast(apiMessage(e), 'error'); }
  };
  const fields: FieldSpec[] = [
    { name: 'full_name', label: 'Full name', required: true }, { name: 'preferred_name', label: 'Preferred name', half: true },
    { name: 'work_email', label: 'Work email', type: 'email', half: true },
    { name: 'department_id', label: 'Department', type: 'select', options: opts(lk.data?.departments), required: true, half: true },
    { name: 'designation_id', label: 'Designation', type: 'select', options: opts(lk.data?.designations), half: true },
    { name: 'org_unit_id', label: 'Work location', type: 'select', options: (lk.data?.locations ?? []).map((l) => ({ value: l.id, label: `${'  '.repeat(l.depth)}${l.name}` })), half: true },
    { name: 'job_level_id', label: 'Job level', type: 'select', options: opts(lk.data?.jobLevels), half: true },
    { name: 'worker_type', label: 'Worker type', type: 'select', options: vopts(lk.data?.workerTypes), required: true, half: true },
    { name: 'employment_type', label: 'Employment type', type: 'select', options: vopts(lk.data?.employmentTypes), half: true },
    { name: 'work_mode', label: 'Work mode', type: 'select', options: vopts(lk.data?.workModes), half: true },
    { name: 'joined_on', label: 'Joining date', type: 'date', half: true },
    { name: 'start_onboarding', label: 'Start the onboarding checklist', type: 'checkbox' },
    { name: 'invite', label: 'Send a Business OS invitation (no access until an administrator assigns roles)', type: 'checkbox' },
  ];
  return (
    <>
      <SectionTitle title="Employee directory" desc={q.data?.fullRecord ? 'Employment records in your scope.' : 'The company directory: names, roles and how to reach people.'}
        actions={<>
          {q.data?.canExport && <Button variant="outline" onClick={() => void exportCsv()}><Icon name="download" size={16} />Export</Button>}
          {q.data?.canCreate && <Button onClick={() => setParams((p) => { p.set('new', '1'); return p; })}><Icon name="plus" size={16} />Add employee</Button>}
        </>} />
      <Card flush>
        <div className="toolbar">
          <div className="search-input"><Icon name="search" size={16} /><input value={text} onChange={(e) => setText(e.target.value)} placeholder="Name, ID or email" aria-label="Search employees" /></div>
          {([['department', 'Department', opts(lk.data?.departments)], ['location', 'Location', opts(lk.data?.locations)], ['designation', 'Designation', opts(lk.data?.designations)],
             ['worker_type', 'Worker type', vopts(lk.data?.workerTypes)]] as const).map(([k, l, o]) => (
            <select key={k} className="field__input" aria-label={l} value={params.get(k) ?? ''} onChange={(e) => setF(k, e.target.value)}>
              <option value="">{l}: all</option>{o.map((x) => <option key={x.value} value={x.value}>{x.label}</option>)}
            </select>
          ))}
          {q.data?.fullRecord && <select className="field__input" aria-label="Status" value={params.get('status') ?? ''} onChange={(e) => setF('status', e.target.value)}>
            <option value="">Working</option><option value="pre_onboarding">Pre-onboarding</option><option value="probation">Probation</option><option value="notice">Notice period</option>
            <option value="on_leave">On leave</option><option value="former">Former employees</option></select>}
          <select className="field__input" aria-label="Sort" value={params.get('sort') ?? 'name'} onChange={(e) => setF('sort', e.target.value)}>
            <option value="name">Sort: name</option><option value="-joined">Newest joiners</option><option value="joined">Longest tenure</option><option value="department">Department</option></select>
        </div>
        {q.isPending ? <LoadingRows /> : q.error ? <QueryError error={q.error} /> : (
          <>
            <DataTable rows={q.data.results} onRow={(e) => navigate(`/people/${e.id}`)} empty="No employees match" caption="Employees" columns={[
              { key: 'name', label: 'Name', render: (e) => <div className="row"><Avatar name={e.displayName} src={e.avatarUrl} size="sm" /><div><strong>{e.displayName}</strong><div className="xs muted mono">{e.employeeId}</div></div></div> },
              { key: 'role', label: 'Designation', render: (e) => e.designation?.name ?? '—' },
              { key: 'dept', label: 'Department / team', render: (e) => <span className="small">{e.department?.name ?? '—'}{e.team ? <div className="xs muted">{e.team.name}</div> : null}</span> },
              { key: 'loc', label: 'Location', render: (e) => <span className="small">{e.location?.name ?? '—'}{e.businessUnit ? <div className="xs muted">{e.businessUnit.name}</div> : null}</span> },
              { key: 'mgr', label: 'Manager', render: (e) => e.manager?.name ?? '—' },
              { key: 'type', label: 'Type', render: (e) => <span className="small">{humanize(e.workerType)}{e.employmentType ? ` · ${humanize(e.employmentType)}` : ''}</span> },
              ...(q.data.fullRecord ? [{ key: 'joined', label: 'Joined', render: (e: any) => fmtDate(e.joinedOn) }, { key: 'status', label: 'Status', render: (e: any) => <EmpStatus value={e.status} /> }] : []),
            ]} />
            <Pager page={q.data.page} hasNext={q.data.hasNext} count={q.data.count} onPage={setPage} />
          </>
        )}
      </Card>
      {params.get('new') === '1' && (
        <FormDialog title="Add employee" wide fields={fields} initial={{ worker_type: 'employee', employment_type: 'full_time', work_mode: 'office', start_onboarding: true }}
          intro={<p className="small muted">The employee number (EMP-…) is assigned automatically. Access is never granted from here — only an invitation.</p>}
          onSubmit={(v) => people.createEmployee(v)} onClose={() => setParams((p) => { p.delete('new'); return p; })}
          onDone={(e: any) => { toast(`${e.fullName} added (${e.employeeId})`); void qc.invalidateQueries({ queryKey: ['os', 'people'] }); navigate(`/people/${e.id}`); }} />
      )}
    </>
  );
}

// =================================================================================================================
// People 360
// =================================================================================================================
const TAB_LABEL: Record<string, string> = {
  overview: 'Overview', employment: 'Employment', contact: 'Contact', attendance: 'Attendance', leave: 'Leave', performance: 'Performance', learning: 'Learning',
  compensation: 'Compensation', documents: 'Documents', activity: 'Activity', lifecycle: 'Lifecycle', security: 'Security',
};

export function Profile() {
  const { id = '' } = useParams();
  const [params, setParams] = useSearchParams();
  const q = useQuery({ queryKey: ['os', 'people', 'employee', id], queryFn: () => people.employee(id) });
  const [dialog, setDialog] = useState<'none' | 'promote' | 'transfer' | 'exit' | 'feedback' | 'edit' | 'resign'>('none');
  if (q.isPending) return <><SectionTitle title="Employee" /><Card><LoadingRows rows={6} /></Card></>;
  if (q.error) return <><SectionTitle title="Employee" /><QueryError error={q.error} /></>;
  const e = q.data;
  const tab = params.get('tab') && e.tabs.includes(params.get('tab')!) ? params.get('tab')! : 'overview';
  return (
    <>
      <SectionTitle title={e.displayName} actions={<>
        {e.actions.feedback && <Button variant="outline" size="sm" onClick={() => setDialog('feedback')}><Icon name="star" size={15} />Recognise</Button>}
        {e.canEdit && <Button variant="outline" size="sm" onClick={() => setDialog('edit')}><Icon name="edit" size={15} />Edit</Button>}
        {e.actions.promote && <Button variant="outline" size="sm" onClick={() => setDialog('promote')}>Promote / transfer</Button>}
        {e.actions.offboard && <Button variant="danger" size="sm" onClick={() => setDialog('exit')}>Start exit</Button>}
        {e.actions.resign && !e.actions.offboard && <Button variant="ghost" size="sm" onClick={() => setDialog('resign')}>Resign</Button>}
      </>} />
      <Card>
        <div className="row row--wrap" style={{ gap: 16 }}>
          <Avatar name={e.displayName} src={e.avatarUrl} size="lg" />
          <div className="grow">
            <h2 style={{ fontSize: 'var(--fs-xl)' }}>{e.fullName}{e.preferredName && <span className="muted small"> · goes by {e.preferredName}</span>}</h2>
            <div className="muted small">{e.designation?.name ?? '—'} · {e.department?.name ?? '—'}{e.team ? ` · ${e.team.name}` : ''} · {e.location?.name ?? '—'}</div>
            <div className="row row--wrap" style={{ marginTop: 6 }}><span className="chip mono">{e.employeeId}</span><EmpStatus value={e.status} />
              <span className="chip">{humanize(e.workerType)}</span>{e.tenureDays != null && <span className="chip">{Math.floor(e.tenureDays / 365)}y {Math.floor((e.tenureDays % 365) / 30)}m tenure</span>}</div>
          </div>
          <dl className="kv" style={{ gridTemplateColumns: '90px minmax(0, 1fr)' }}>
            <dt>Email</dt><dd>{e.workEmail ? <a href={`mailto:${e.workEmail}`}>{e.workEmail}</a> : '—'}</dd>
            <dt>Phone</dt><dd>{e.workPhone || '—'}</dd>
            <dt>Manager</dt><dd>{e.manager ? <Link to={`/people/${e.manager.id}`}>{e.manager.name}</Link> : '—'}</dd>
          </dl>
        </div>
      </Card>
      <div style={{ height: 16 }} />
      <Tabs value={tab} onChange={(t) => setParams({ tab: t })} items={e.tabs.map((t) => ({ value: t, label: TAB_LABEL[t] ?? t }))} />
      {tab === 'overview' && <Overview e={e} />}
      {tab === 'documents' && <DocumentsPanel resourceType="people.employee" resourceId={e.id} />}
      {!['overview', 'documents'].includes(tab) && <ProfileTab id={e.id} tab={tab} isSelf={e.isSelf} />}
      {dialog === 'edit' && <EditEmployee e={e} onClose={() => setDialog('none')} />}
      {dialog === 'feedback' && <FeedbackDialog employeeId={e.id} onClose={() => setDialog('none')} />}
      {dialog === 'promote' && <ChangeDialog e={e} onClose={() => setDialog('none')} />}
      {(dialog === 'exit' || dialog === 'resign') && <ExitDialog e={e} self={dialog === 'resign'} onClose={() => setDialog('none')} />}
    </>
  );
}

function Overview({ e }: { e: any }) {
  return (
    <div className="grid grid--2">
      <Card title="About">
        <dl className="kv">
          <dt>Designation</dt><dd>{e.designation?.name ?? '—'}</dd><dt>Department</dt><dd>{e.department?.name ?? '—'}</dd><dt>Team</dt><dd>{e.team?.name ?? '—'}</dd>
          <dt>Location</dt><dd>{e.location?.name ?? '—'}{e.businessUnit ? ` · ${e.businessUnit.name}` : ''}</dd><dt>Work mode</dt><dd>{humanize(e.workMode)}</dd>
          {e.fullRecord && <><dt>Joined</dt><dd>{fmtDate(e.joinedOn)}</dd><dt>Employment</dt><dd>{humanize(e.employmentType ?? '')}</dd>
            <dt>Probation</dt><dd>{e.probationEndOn ? `until ${fmtDate(e.probationEndOn)}` : e.confirmedOn ? `confirmed ${fmtDate(e.confirmedOn)}` : '—'}</dd></>}
          {e.secondaryManagers.length > 0 && <><dt>Dotted-line</dt><dd>{e.secondaryManagers.map((m: any) => m.name).join(', ')}</dd></>}
        </dl>
      </Card>
      <Card title={`Direct reports (${e.directReports.length})`} flush>
        {!e.directReports.length ? <p className="muted small" style={{ padding: 16 }}>No direct reports.</p> : (
          <ul className="list">{e.directReports.map((r: any) => <li key={r.id}><Link to={`/people/${r.id}`} className="list-row"><span className="list-row__main">{r.name}<span className="list-row__sub" style={{ display: 'block' }}>{r.designation}</span></span></Link></li>)}</ul>
        )}
      </Card>
    </div>
  );
}

function ProfileTab({ id, tab, isSelf }: { id: string; tab: string; isSelf: boolean }) {
  const q = useQuery({ queryKey: ['os', 'people', 'tab', id, tab], queryFn: () => people.tab(id, tab) });
  if (q.isPending) return <Card><LoadingRows /></Card>;
  if (q.error) return <QueryError error={q.error} />;
  const d = q.data;
  switch (tab) {
    case 'employment': return (
      <Card title="Employment"><dl className="kv">
        <dt>Employee ID</dt><dd className="mono">{d.record.employeeId}</dd><dt>Worker type</dt><dd>{humanize(d.record.workerType)}</dd>
        <dt>Employment type</dt><dd>{humanize(d.record.employmentType)}</dd><dt>Job level</dt><dd>{d.record.jobLevel?.name ?? '—'}</dd>
        <dt>Position</dt><dd>{d.position ? `${d.position.code} · ${d.position.title}` : '—'}</dd><dt>Schedule</dt><dd>{d.schedule ? `${d.schedule.name}` : 'Standard'}</dd>
        <dt>Joined</dt><dd>{fmtDate(d.record.joinedOn)}</dd><dt>Probation ends</dt><dd>{fmtDate(d.record.probationEndOn)}</dd>
        <dt>Confirmed</dt><dd>{fmtDate(d.record.confirmedOn)}</dd><dt>Contract ends</dt><dd>{fmtDate(d.record.contractEndOn)}</dd>
        {d.record.exitDate && <><dt>Exit</dt><dd>{fmtDate(d.record.exitDate)} · {humanize(d.record.exitReason)}</dd></>}
      </dl></Card>);
    case 'contact': return <ContactTab id={id} d={d} />;
    case 'attendance': return (
      <div className="stack stack--lg">
        <StatGrid items={[{ key: 'p', label: 'Present this month', value: d.summary.present }, { key: 'l', label: 'Late arrivals', value: d.summary.late, tone: d.summary.late ? 'alert' : undefined },
          { key: 'e', label: 'Early departures', value: d.summary.early }, { key: 'r', label: 'Remote days', value: d.summary.remote },
          { key: 'm', label: 'Missing check-outs', value: d.summary.missingCheckout, tone: d.summary.missingCheckout ? 'alert' : undefined }]} />
        <Card title="Recent records" flush><DataTable rows={d.records} empty="No attendance recorded" columns={[
          { key: 'date', label: 'Date', render: (r: any) => fmtDate(r.date) }, { key: 'in', label: 'In', render: (r: any) => (r.checkIn ? fmtDateTime(r.checkIn) : '—') },
          { key: 'out', label: 'Out', render: (r: any) => (r.checkOut ? fmtDateTime(r.checkOut) : '—') },
          { key: 'h', label: 'Worked', render: (r: any) => (r.workedMinutes != null ? `${Math.floor(r.workedMinutes / 60)}h ${r.workedMinutes % 60}m` : '—') },
          { key: 'f', label: 'Flags', render: (r: any) => <span className="row" style={{ gap: 4 }}>{r.late && <span className="flag flag--due_soon">late</span>}{r.early && <span className="flag">early</span>}<span className="xs muted">{r.mode}</span></span> }]} /></Card>
      </div>);
    case 'leave': return <LeaveSummary d={d} />;
    case 'performance': return (
      <div className="stack stack--lg">
        <Card title="Goals" flush><GoalRows goals={d.goals} /></Card>
        <Card title="Reviews" flush>{!d.reviews.length ? <p className="muted small" style={{ padding: 16 }}>No submitted reviews yet.</p> : (
          <ul className="list">{d.reviews.map((r: any) => <li key={r.id} className="list-row" style={{ alignItems: 'flex-start' }}>
            <div className="list-row__main"><strong>{r.cycle} · {r.kind}</strong> <span className="xs muted">by {r.reviewer}</span>
              {r.strengths && <p className="small">Strengths: {r.strengths}</p>}{r.improvements && <p className="small">To develop: {r.improvements}</p>}{r.comments && <p className="small">{r.comments}</p>}</div>
            {r.rating && <span className="chip">{r.rating} / 5</span>}</li>)}</ul>)}</Card>
        <Card title="Feedback & recognition" flush>{!d.feedback.length ? <p className="muted small" style={{ padding: 16 }}>No feedback yet.</p> : (
          <ul className="list">{d.feedback.map((f: any) => <li key={f.id} className="list-row"><span className="grow small">{f.kind === 'recognition' ? '🏅 ' : ''}{f.body}<div className="xs muted">{f.author} · {relative(f.at)} · {humanize(f.visibility)}</div></span></li>)}</ul>)}</Card>
      </div>);
    case 'learning': return <LearningTab id={id} d={d} isSelf={isSelf} />;
    case 'compensation': return (
      <div className="stack stack--lg">
        <Alert tone="warning">Restricted information. Viewing is recorded in the audit trail.</Alert>
        <Card title="Compensation history" flush><DataTable rows={d.history} empty="No compensation records" columns={[
          { key: 'd', label: 'Effective', render: (c: any) => fmtDate(c.effectiveDate) }, { key: 'b', label: 'Base (annual)', num: true, render: (c: any) => fmtMoney(c.baseAnnual, c.currency) },
          { key: 'v', label: 'Variable target', num: true, render: (c: any) => fmtMoney(c.variableTarget, c.currency) }, { key: 'r', label: 'Reason', render: (c: any) => c.reason },
          { key: 'n', label: 'Note', render: (c: any) => <span className="small muted">{c.note || '—'}</span> }]} /></Card>
        <Card title="Benefits" flush><DataTable rows={d.benefits} empty="No benefits" columns={[{ key: 'p', label: 'Plan', render: (b: any) => b.plan }, { key: 'k', label: 'Type', render: (b: any) => humanize(b.kind) },
          { key: 'e', label: 'Since', render: (b: any) => fmtDate(b.enrolledOn) }]} /></Card>
        {d.canManage && <SalaryRevision id={id} />}
      </div>);
    case 'activity': return (
      <Card title="Employment history" flush>{!d.events.length ? <p className="muted small" style={{ padding: 16 }}>No history yet.</p> : (
        <ul className="timeline" style={{ padding: 16 }}>{d.events.map((x: any) => <li key={x.id}><strong>{x.kind}</strong> · {fmtDate(x.effectiveDate)} <span className="xs muted">by {x.by}</span>
          {x.reason && <div className="small">{x.reason}</div>}{Object.keys(x.after).length > 0 && <div className="xs muted">{Object.entries(x.after).map(([k, v]) => `${humanize(k)}: ${v}`).join(' · ')}</div>}</li>)}</ul>)}</Card>);
    case 'lifecycle': return (
      <div className="stack stack--lg">
        {d.plans.map((p: any) => <Card key={p.id} title={`${humanize(p.kind)} · ${p.done}/${p.total} done`} flush>
          <div className="progress" style={{ margin: '0 16px' }}><span style={{ width: `${p.pct}%` }} /></div>
          <ul className="list">{p.tasks.map((t: any) => <li key={t.id} className="list-row"><Status value={t.status} /><span className="grow small">{t.title}</span><span className="xs muted">{t.assignee} · {fmtDate(t.dueAt)}</span></li>)}</ul></Card>)}
        <Card title="Promotions, transfers & revisions" flush><DataTable rows={d.changes} empty="None" columns={[{ key: 'k', label: 'Change', render: (c: any) => c.kind },
          { key: 's', label: 'Status', render: (c: any) => <Status value={c.status} /> }, { key: 'e', label: 'Effective', render: (c: any) => fmtDate(c.effectiveDate) },
          { key: 'a', label: '', render: (c: any) => c.approvalId && <Link to={`/approvals/${c.approvalId}`}>Approval</Link> }]} /></Card>
        {d.offboarding.map((o: any) => <OffboardingCard key={o.id} o={o} />)}
      </div>);
    case 'security': return (
      <Card title="Account & access">{d.account ? <dl className="kv"><dt>Status</dt><dd><Status value={d.account.status} /></dd><dt>Two-step</dt><dd>{d.account.mfaEnabled ? 'On' : 'Off'}</dd>
        <dt>Last sign-in</dt><dd>{fmtDateTime(d.account.lastLoginAt)}</dd><dt>Roles</dt><dd>{d.account.roles.join(', ') || 'None'}</dd>
        <dt>Manage</dt><dd><Link to={d.path}>Open in Users</Link></dd></dl> : <p className="muted small">{d.message}</p>}</Card>);
    default: return null;
  }
}

function ContactTab({ id, d }: { id: string; d: any }) {
  const toast = useToast();
  const qc = useQueryClient();
  const [edit, setEdit] = useState(false);
  const p = d.private;
  return (
    <Card title="Contact & personal details" actions={d.canEdit && <Button size="sm" variant="outline" onClick={() => setEdit(true)}>Edit</Button>}>
      <dl className="kv">
        <dt>Work email</dt><dd>{d.workEmail || '—'}</dd><dt>Work phone</dt><dd>{d.workPhone || '—'}</dd><dt>Personal email</dt><dd>{p.personalEmail || '—'}</dd>
        <dt>Personal phone</dt><dd>{p.personalPhone || '—'}</dd><dt>Address</dt><dd style={{ whiteSpace: 'pre-wrap' }}>{p.address || '—'}</dd>
        <dt>Emergency contact</dt><dd>{p.emergencyContactName ? `${p.emergencyContactName} (${p.emergencyContactRelation}) · ${p.emergencyContactPhone}` : '—'}</dd>
        <dt>Date of birth</dt><dd>{fmtDate(p.dateOfBirth)}{p.shareBirthday ? ' · shared with colleagues' : ''}</dd>
      </dl>
      <p className="xs muted" style={{ marginTop: 8 }}>Personal details are visible only to the employee and authorised HR, and viewing is audited.</p>
      {edit && <FormDialog title="Edit contact details" onClose={() => setEdit(false)} initial={{
        personal_email: p.personalEmail, personal_phone: p.personalPhone, address: p.address, emergency_contact_name: p.emergencyContactName,
        emergency_contact_relation: p.emergencyContactRelation, emergency_contact_phone: p.emergencyContactPhone, date_of_birth: p.dateOfBirth, share_birthday: p.shareBirthday }}
        fields={[{ name: 'personal_email', label: 'Personal email', type: 'email', half: true }, { name: 'personal_phone', label: 'Personal phone', half: true },
          { name: 'address', label: 'Address', type: 'textarea' }, { name: 'emergency_contact_name', label: 'Emergency contact', half: true },
          { name: 'emergency_contact_relation', label: 'Relation', half: true }, { name: 'emergency_contact_phone', label: 'Emergency phone', half: true },
          { name: 'date_of_birth', label: 'Date of birth', type: 'date', half: true }, { name: 'share_birthday', label: 'Show my birthday (day and month) to colleagues', type: 'checkbox' }]}
        onSubmit={(v) => people.updateContact(id, v)} onDone={() => { toast('Saved'); void qc.invalidateQueries({ queryKey: ['os', 'people', 'tab', id] }); }} />}
    </Card>
  );
}

export function LeaveSummary({ d }: { d: any }) {
  return (
    <div className="stack stack--lg">
      <div className="stat-grid">{d.balances.map((b: any) => (
        <div key={b.typeId} className="stat" style={{ borderLeft: `3px solid ${b.color}` }}><span className="stat__label">{b.type}{!b.paid && ' (unpaid)'}</span>
          <strong className="stat__value">{Number(b.available)}</strong><span className="stat__hint">available · {Number(b.used)} used · {Number(b.pending)} pending of {Number(b.entitled)}</span></div>))}</div>
      <Card title="Leave requests" flush><DataTable rows={d.requests} empty="No leave requests" columns={[
        { key: 't', label: 'Type', render: (r: any) => r.leaveType.name }, { key: 'd', label: 'Dates', render: (r: any) => `${fmtDate(r.startDate)}${r.endDate !== r.startDate ? ` – ${fmtDate(r.endDate)}` : ''}${r.halfDay ? ` (${r.halfDay} half)` : ''}` },
        { key: 'n', label: 'Days', num: true, render: (r: any) => Number(r.days) }, { key: 's', label: 'Status', render: (r: any) => <Status value={r.status} /> },
        { key: 'a', label: '', render: (r: any) => r.approvalId && <Link to={`/approvals/${r.approvalId}`} className="small">Approval</Link> }]} /></Card>
    </div>
  );
}

export function GoalRows({ goals }: { goals: any[] }) {
  if (!goals.length) return <p className="muted small" style={{ padding: 16 }}>No goals yet.</p>;
  return (
    <ul className="list">{goals.map((g) => (
      <li key={g.id} className="list-row">
        <div className="list-row__main"><span className="list-row__title" style={{ display: 'block' }}>{g.title}</span>
          <span className="list-row__sub" style={{ display: 'block' }}>{humanize(g.level)}{g.metric ? ` · ${g.metric}: ${g.current ?? '—'} / ${g.target ?? '—'}` : ''}{g.dueOn ? ` · due ${fmtDate(g.dueOn)}` : ''}</span>
          {g.progress != null && <div className="progress" style={{ marginTop: 4, maxWidth: 260 }}><span style={{ width: `${g.progress}%` }} /></div>}</div>
        <Status value={g.status} tone={g.status === 'on_track' || g.status === 'done' ? 'success' : g.status === 'at_risk' ? 'warning' : g.status === 'off_track' ? 'danger' : 'neutral'} label={humanize(g.status)} />
      </li>))}</ul>
  );
}

function LearningTab({ id, d, isSelf }: { id: string; d: any; isSelf: boolean }) {
  const qc = useQueryClient();
  const toast = useToast();
  const skills = useQuery({ queryKey: ['os', 'people', 'skills'], queryFn: () => people.list('skills', { page_size: 100 }) });
  const [dlg, setDlg] = useState<'none' | 'skill' | 'cert'>('none');
  const inv = () => void qc.invalidateQueries({ queryKey: ['os', 'people', 'tab', id] });
  return (
    <div className="stack stack--lg">
      <Card title="Training" flush><DataTable rows={d.enrollments} empty="No training assigned" columns={[{ key: 'c', label: 'Course', render: (x: any) => <>{x.course}{x.mandatory && <span className="flag flag--due_soon" style={{ marginLeft: 6 }}>mandatory</span>}</> },
        { key: 's', label: 'Status', render: (x: any) => <Status value={x.status} /> }, { key: 'd', label: 'Due', render: (x: any) => fmtDate(x.dueOn) }]} /></Card>
      <Card title="Skills" flush actions={<Button size="sm" variant="outline" onClick={() => setDlg('skill')}>Rate a skill</Button>}>
        {!d.skills.length ? <p className="muted small" style={{ padding: 16 }}>No skills recorded.</p> : (
          <ul className="list">{d.skills.map((s: any) => <li key={s.id} className="list-row"><span className="grow">{s.skill} <span className="xs muted">{s.category}</span></span>
            <span className="progress" style={{ width: 120 }}><span style={{ width: `${s.proficiency * 20}%`, background: 'var(--c-brand)' }} /></span>
            <span className="xs">{['', 'Basic', 'Working', 'Proficient', 'Advanced', 'Expert'][s.proficiency]}</span><span className="xs muted">{s.source}</span></li>)}</ul>)}
      </Card>
      <Card title="Certifications" flush actions={<Button size="sm" variant="outline" onClick={() => setDlg('cert')}>Add</Button>}>
        <DataTable rows={d.certifications} empty="No certifications" columns={[{ key: 'n', label: 'Certification', render: (c: any) => <>{c.name}<div className="xs muted">{c.provider}</div></> },
          { key: 'e', label: 'Expires', render: (c: any) => fmtDate(c.expiresOn) }, { key: 'v', label: 'Verification', render: (c: any) => <Status value={c.verification === 'verified' ? 'active' : 'pending'} label={c.verification} /> }]} />
      </Card>
      {dlg === 'skill' && <FormDialog title="Rate a skill" onClose={() => setDlg('none')}
        intro={<p className="small muted">{isSelf ? 'Your own ratings are labelled self-assessed.' : 'Your rating is recorded as a manager/HR assessment.'}</p>}
        fields={[{ name: 'skill_id', label: 'Skill', type: 'select', required: true, options: (skills.data?.results ?? []).map((s: any) => ({ value: s.id, label: s.name })) },
          { name: 'proficiency', label: 'Level', type: 'select', required: true, options: ['Basic', 'Working', 'Proficient', 'Advanced', 'Expert'].map((l, i) => ({ value: String(i + 1), label: `${i + 1} · ${l}` })) },
          { name: 'evidence', label: 'Evidence (optional)' }]}
        onSubmit={(v) => people.setSkill(id, { skillId: String(v.skillId), proficiency: Number(v.proficiency), evidence: v.evidence ? String(v.evidence) : undefined })}
        onDone={() => { toast('Skill saved'); inv(); }} />}
      {dlg === 'cert' && <FormDialog title="Add certification" onClose={() => setDlg('none')}
        fields={[{ name: 'name', label: 'Certification', required: true }, { name: 'provider', label: 'Provider', half: true }, { name: 'credential_id', label: 'Credential ID', half: true },
          { name: 'issued_on', label: 'Issued', type: 'date', half: true }, { name: 'expires_on', label: 'Expires', type: 'date', half: true }]}
        onSubmit={(v) => people.addCertification(id, v)} onDone={() => { toast('Certification added'); inv(); }} />}
    </div>
  );
}

function SalaryRevision({ id }: { id: string }) {
  const [open, setOpen] = useState(false);
  const toast = useToast();
  return (
    <>
      <div><Button variant="outline" onClick={() => setOpen(true)}>Propose salary revision</Button></div>
      {open && <FormDialog title="Salary revision" onClose={() => setOpen(false)} submitLabel="Submit for approval"
        intro={<p className="small muted">Goes to payroll approval. It takes effect only once approved, on the effective date.</p>}
        fields={[{ name: 'base_annual', label: 'New annual base', type: 'number', required: true, half: true }, { name: 'variable_target', label: 'Variable target', type: 'number', half: true },
          { name: 'effective_date', label: 'Effective date', type: 'date', required: true, half: true }, { name: 'reason', label: 'Reason', type: 'textarea' }]}
        onSubmit={(v) => people.salaryRevision(id, v)} onDone={() => toast('Sent for approval')} />}
    </>
  );
}

function EditEmployee({ e, onClose }: { e: any; onClose: () => void }) {
  const lk = useLookups();
  const qc = useQueryClient();
  const toast = useToast();
  return (
    <FormDialog title={`Edit ${e.displayName}`} wide onClose={onClose}
      intro={<p className="small muted">Changes to department, team, location, manager or designation trigger an access review by an administrator.</p>}
      initial={{ preferred_name: e.preferredName, work_email: e.workEmail, work_phone: e.workPhone, department_id: e.department?.id, team_id: e.team?.id, org_unit_id: e.location?.id,
        designation_id: e.designation?.id, manager_id: e.manager?.id, worker_type: e.workerType, employment_type: e.employmentType, work_mode: e.workMode,
        probation_end_on: e.probationEndOn, confirmed_on: e.confirmedOn, contract_end_on: e.contractEndOn, status: e.status }}
      fields={[{ name: 'preferred_name', label: 'Preferred name', half: true }, { name: 'work_phone', label: 'Work phone', half: true }, { name: 'work_email', label: 'Work email', type: 'email' },
        { name: 'department_id', label: 'Department', type: 'select', options: opts(lk.data?.departments), half: true },
        { name: 'team_id', label: 'Team', type: 'select', options: (lk.data?.teams ?? []).map((t) => ({ value: t.id, label: t.name })), half: true },
        { name: 'org_unit_id', label: 'Location', type: 'select', options: opts(lk.data?.locations), half: true },
        { name: 'designation_id', label: 'Designation', type: 'select', options: opts(lk.data?.designations), half: true },
        { name: 'worker_type', label: 'Worker type', type: 'select', options: vopts(lk.data?.workerTypes), half: true },
        { name: 'work_mode', label: 'Work mode', type: 'select', options: vopts(lk.data?.workModes), half: true },
        { name: 'status', label: 'Status', type: 'select', half: true, options: ['pre_onboarding', 'active', 'probation', 'confirmed', 'on_leave', 'suspended'].map((v) => ({ value: v, label: humanize(v) })),
          hint: 'Exits go through the exit workflow.' },
        { name: 'probation_end_on', label: 'Probation ends', type: 'date', half: true }, { name: 'confirmed_on', label: 'Confirmed on', type: 'date', half: true },
        { name: 'contract_end_on', label: 'Contract ends', type: 'date', half: true }]}
      onSubmit={(v) => people.updateEmployee(e.id, v)} onDone={() => { toast('Saved'); void qc.invalidateQueries({ queryKey: ['os', 'people'] }); }} />
  );
}

export function FeedbackDialog({ employeeId, onClose }: { employeeId: string; onClose: () => void }) {
  const toast = useToast();
  return (
    <FormDialog title="Give feedback or recognition" onClose={onClose} initial={{ kind: 'recognition', visibility: 'public' }}
      fields={[{ name: 'kind', label: 'Type', type: 'select', required: true, half: true, options: [{ value: 'recognition', label: 'Recognition' }, { value: 'feedback', label: 'Feedback' }] },
        { name: 'visibility', label: 'Who can see it', type: 'select', required: true, half: true, options: [{ value: 'public', label: 'Everyone' }, { value: 'private', label: 'Them and their manager' }] },
        { name: 'badge', label: 'Badge', type: 'select', options: ['team_player', 'above_and_beyond', 'customer_hero', 'innovator', 'mentor'].map((b) => ({ value: b, label: humanize(b) })) },
        { name: 'body', label: 'Message', type: 'textarea', required: true }]}
      onSubmit={(v) => people.create('feedback', { ...v, employeeId })} onDone={() => toast('Sent')} />
  );
}

function ChangeDialog({ e, onClose }: { e: any; onClose: () => void }) {
  const lk = useLookups();
  const toast = useToast();
  const qc = useQueryClient();
  const access = useAccess();
  return (
    <FormDialog title={`Promotion or transfer · ${e.displayName}`} wide onClose={onClose} submitLabel="Submit for approval" initial={{ kind: 'promotion' }}
      intro={<p className="small muted">Goes through HR approval. Approved changes apply on the effective date and trigger an access review.</p>}
      fields={[{ name: 'kind', label: 'Change', type: 'select', required: true, options: [{ value: 'promotion', label: 'Promotion' }, { value: 'transfer', label: 'Transfer' }] },
        { name: 'designation_id', label: 'New designation', type: 'select', options: opts(lk.data?.designations), half: true },
        { name: 'job_level_id', label: 'New job level', type: 'select', options: opts(lk.data?.jobLevels), half: true },
        { name: 'department_id', label: 'New department', type: 'select', options: opts(lk.data?.departments), half: true },
        { name: 'org_unit_id', label: 'New location', type: 'select', options: opts(lk.data?.locations), half: true },
        { name: 'effective_date', label: 'Effective date', type: 'date', required: true, half: true },
        ...(access.can('people.payroll.manage') ? [{ name: 'base_annual', label: 'New annual base (optional, restricted)', type: 'number' as const, half: true }] : []),
        { name: 'reason', label: 'Reason', type: 'textarea' }]}
      onSubmit={(v) => {
        const { baseAnnual, kind, effectiveDate, reason, ...rest } = v as Record<string, unknown>;
        const proposed = Object.fromEntries(Object.entries(rest).filter(([, x]) => x).map(([k, x]) => [k.replace(/[A-Z]/g, (c) => `_${c.toLowerCase()}`), x]));
        return people.create('changes', { employeeId: e.id, kind, effectiveDate, reason, ...proposed, compensation: baseAnnual ? { baseAnnual } : {} });
      }}
      onDone={() => { toast('Sent for approval'); void qc.invalidateQueries({ queryKey: ['os', 'people'] }); }} />
  );
}

function ExitDialog({ e, self, onClose }: { e: any; self: boolean; onClose: () => void }) {
  const toast = useToast();
  const qc = useQueryClient();
  return (
    <FormDialog title={self ? 'Resign' : `Start exit · ${e.displayName}`} onClose={onClose} submitLabel="Submit" initial={{ kind: 'resignation', notice_start: new Date().toISOString().slice(0, 10) }}
      intro={<p className="small muted">HR approves the exit, then the offboarding checklist starts. Business OS access is revoked when the exit completes.</p>}
      fields={[...(self ? [] : [{ name: 'kind', label: 'Type', type: 'select' as const, required: true, options: [{ value: 'resignation', label: 'Resignation' }, { value: 'termination', label: 'Termination' },
          { value: 'retirement', label: 'Retirement' }, { value: 'contract_end', label: 'End of contract' }] }]),
        { name: 'notice_start', label: 'Notice starts', type: 'date', required: true, half: true }, { name: 'last_working_day', label: 'Last working day', type: 'date', required: true, half: true },
        { name: 'reason', label: 'Reason', type: 'textarea' }]}
      onSubmit={(v) => people.create('offboarding', { ...v, employeeId: self ? undefined : e.id, kind: self ? 'resignation' : v.kind })}
      onDone={() => { toast('Submitted for HR approval'); void qc.invalidateQueries({ queryKey: ['os', 'people'] }); }} />
  );
}

export function OffboardingCard({ o }: { o: any }) {
  const qc = useQueryClient();
  const toast = useToast();
  const [exit, setExit] = useState(false);
  const act = useMutation({ mutationFn: (a: string) => people.action(`offboarding/${o.id}/${a}`), onSuccess: () => { toast('Done'); void qc.invalidateQueries({ queryKey: ['os', 'people'] }); },
    onError: (e) => toast(apiMessage(e), 'error') });
  const restricted = 'exitFeedback' in o;
  return (
    <Card title={`Exit · ${humanize(o.kind)} · ${o.employeeName}`} actions={<Status value={o.status} />}>
      <dl className="kv"><dt>Notice</dt><dd>{fmtDate(o.noticeStart)} → last day {fmtDate(o.lastWorkingDay)}</dd><dt>Reason</dt><dd>{o.reason || '—'}</dd>
        <dt>Access</dt><dd>{o.accessRevokedAt ? `Revoked ${fmtDateTime(o.accessRevokedAt)}` : 'Active'}</dd></dl>
      {o.checklist && <><div className="progress" style={{ margin: '10px 0' }}><span style={{ width: `${o.checklist.pct}%` }} /></div><span className="xs muted">{o.checklist.done}/{o.checklist.total} checklist steps done</span></>}
      {restricted && o.status === 'in_progress' && (
        <div className="row row--wrap" style={{ marginTop: 12 }}>
          <Button size="sm" variant="outline" onClick={() => setExit(true)}>Exit interview</Button>
          {!o.accessRevokedAt && <Button size="sm" variant="outline" onClick={() => act.mutate('revoke-access')}>Revoke access now</Button>}
          <Button size="sm" onClick={() => act.mutate('complete')} loading={act.isPending}>Complete exit</Button>
        </div>
      )}
      {exit && <FormDialog title="Exit interview (restricted)" onClose={() => setExit(false)} initial={{ exit_reason: o.exitReason, exit_feedback: o.exitFeedback, exit_suggestions: o.exitSuggestions,
        manager_feedback: o.managerFeedback, rehire_eligible: o.rehireEligible }}
        fields={[{ name: 'exit_reason', label: 'Main reason for leaving', type: 'select', options: ['career', 'compensation', 'manager', 'relocation', 'personal', 'workload', 'other'].map((x) => ({ value: x, label: humanize(x) })) },
          { name: 'exit_feedback', label: 'Feedback', type: 'textarea' }, { name: 'exit_suggestions', label: 'Suggestions', type: 'textarea' },
          { name: 'manager_feedback', label: 'Manager feedback', type: 'textarea' }, { name: 'rehire_eligible', label: 'Eligible for rehire', type: 'checkbox' }]}
        onSubmit={(v) => people.update('offboarding', o.id, v)} onDone={() => { toast('Saved'); void qc.invalidateQueries({ queryKey: ['os', 'people'] }); }} />}
    </Card>
  );
}

// =================================================================================================================
// Org chart
// =================================================================================================================
export function OrgChart() {
  const [dept, setDept] = useState('');
  const q = useQuery({ queryKey: ['os', 'people', 'orgchart', dept], queryFn: () => people.orgChart({ department: dept || undefined }) });
  const tree = useMemo(() => {
    const nodes = q.data?.nodes ?? [];
    const kids: Record<string, any[]> = {};
    nodes.forEach((n) => { (kids[n.managerId ?? 'root'] ??= []).push(n); });
    return { roots: kids.root ?? [], kids };
  }, [q.data]);
  const [closed, setClosed] = useState<Set<string>>(new Set());
  const render = (n: any): React.ReactNode => (
    <li key={n.id}>
      <div className="row" style={{ gap: 4 }}>
        {tree.kids[n.id] && <button className="icon-btn" style={{ width: 24, height: 24 }} aria-label={closed.has(n.id) ? 'Expand' : 'Collapse'} aria-expanded={!closed.has(n.id)}
          onClick={() => setClosed((c) => { const x = new Set(c); if (x.has(n.id)) x.delete(n.id); else x.add(n.id); return x; })}>
          <Icon name="chevron" size={14} className={closed.has(n.id) ? '' : ''} /></button>}
        <Link to={`/people/${n.id}`} className="org-node"><Avatar name={n.name} size="sm" /><span className="grow"><strong className="small">{n.name}</strong>
          <span className="xs muted" style={{ display: 'block' }}>{n.designation ?? '—'} · {n.department ?? '—'}</span></span>{n.reports > 0 && <span className="chip">{n.reports}</span>}</Link>
      </div>
      {tree.kids[n.id] && !closed.has(n.id) && <ul>{tree.kids[n.id]!.map(render)}</ul>}
    </li>
  );
  return (
    <>
      <SectionTitle title="Org chart" desc="Reporting lines. Clicking someone opens the profile you’re allowed to see." actions={
        <select className="field__input" aria-label="Department" value={dept} onChange={(e) => setDept(e.target.value)}><option value="">All departments</option>
          {q.data?.departments.map((d) => <option key={d.id} value={d.id}>{d.name}</option>)}</select>} />
      <Card>{q.isPending ? <LoadingRows /> : q.error ? <QueryError error={q.error} /> : !tree.roots.length ? <Empty title="No one to show" /> : <div className="orgchart"><ul>{tree.roots.map(render)}</ul></div>}</Card>
    </>
  );
}

// =================================================================================================================
// My HR (self-service)
// =================================================================================================================
export function MyHR() {
  const q = useQuery({ queryKey: ['os', 'people', 'me'], queryFn: people.me });
  const [params, setParams] = useSearchParams();
  const tab = params.get('tab') ?? 'overview';
  if (q.isPending) return <><SectionTitle title="My HR" /><Card><LoadingRows /></Card></>;
  if (q.error) return <QueryError error={q.error} />;
  const d = q.data;
  if (!d.employee) return <><SectionTitle title="My HR" /><Empty title="No employee record" message={d.message} /></>;
  return (
    <>
      <SectionTitle title="My HR" desc="Your profile, time off, attendance, goals, training, documents and HR requests." actions={<Link to={`/people/${d.employee.id}`} className="btn btn--outline" style={{ textDecoration: 'none' }}>My full profile</Link>} />
      <Tabs value={tab} onChange={(t) => setParams({ tab: t })} items={[{ value: 'overview', label: 'Overview' }, { value: 'documents', label: 'My documents' }, { value: 'jobs', label: 'Internal jobs' }]} />
      {tab === 'documents' && <DocumentsPanel resourceType="people.employee" resourceId={d.employee.id} title="My documents" />}
      {tab === 'jobs' && (
        <Card title="Internal opportunities" flush><DataTable rows={d.internalJobs} empty="No internal openings right now" columns={[{ key: 't', label: 'Role', render: (j: any) => <>{j.title}<div className="xs muted mono">{j.code}</div></> },
          { key: 'd', label: 'Department', render: (j: any) => j.department }, { key: 'l', label: 'Location', render: (j: any) => j.location ?? '—' }]} />
          <p className="xs muted" style={{ padding: 12 }}>Interested? Raise an HR request (category “Transfer request”) mentioning the job code.</p></Card>
      )}
      {tab === 'overview' && (
        <div className="stack stack--lg">
          <div className="grid grid--3">
            <Card title="Today" actions={<Link to="/people/attendance" className="small">Attendance</Link>}>
              <p className="small">{d.today.checkIn ? `Checked in ${fmtDateTime(d.today.checkIn)}` : 'Not checked in yet'}{d.today.checkOut ? ` · out ${fmtDateTime(d.today.checkOut)}` : ''}</p>
              {d.today.late && <span className="flag flag--due_soon">late</span>}
            </Card>
            <Card title="Time off" actions={<Link to="/people/leave?new=1" className="small">Request leave</Link>}>
              {d.leave.balances.slice(0, 3).map((b: any) => <div key={b.typeId} className="row row--between small"><span>{b.type}</span><strong>{Number(b.available)} days</strong></div>)}
            </Card>
            <Card title="Reviews to write"><p className="small">{d.reviewsToWrite ? `${d.reviewsToWrite} waiting` : 'Nothing to write'} · <Link to="/people/performance">Performance</Link></p></Card>
          </div>
          <div className="grid grid--2">
            <Card title="My goals" flush actions={<Link to="/people/performance" className="small">All goals</Link>}><GoalRows goals={d.goals} /></Card>
            <Card title="Training" flush actions={<Link to="/people/learning" className="small">Learning</Link>}>
              <DataTable rows={d.training} empty="No training assigned" columns={[{ key: 'c', label: 'Course', render: (x: any) => x.course }, { key: 'd', label: 'Due', render: (x: any) => fmtDate(x.dueOn) },
                { key: 's', label: 'Status', render: (x: any) => <Status value={x.status} /> }]} /></Card>
            <Card title="HR requests" flush actions={<Link to="/people/requests?new=1" className="small">New request</Link>}>
              <DataTable rows={d.requests} empty="No requests" columns={[{ key: 's', label: 'Subject', render: (r: any) => <Link to={`/people/requests?open=${r.id}`}>{r.subject}</Link> },
                { key: 'st', label: 'Status', render: (r: any) => <Status value={r.status} /> }]} /></Card>
            <Card title="Benefits" flush><DataTable rows={d.benefits} empty="No benefits enrolled" columns={[{ key: 'p', label: 'Plan', render: (b: any) => b.plan }, { key: 'k', label: 'Type', render: (b: any) => humanize(b.kind) }]} /></Card>
          </div>
          <Card title="Need something else?"><div className="quick">
            <Link to="/approvals/new?policy=finance.expense" className="quick__btn">Submit an expense</Link><Link to="/people/attendance" className="quick__btn">Correct attendance</Link>
            <Link to="/people/requests?new=1" className="quick__btn">Request a letter or document</Link><Link to="/settings/preferences" className="quick__btn">Update preferences</Link></div></Card>
        </div>
      )}
    </>
  );
}
