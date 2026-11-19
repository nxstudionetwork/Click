/* eslint-disable @typescript-eslint/no-explicit-any */
import { useState } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Button, Icon, useToast } from '@click/ui';
import { api, apiMessage, people } from '../../lib/api';
import { fmtDate, fmtDateTime, fmtMoney, humanize } from '../../lib/format';
import { useAccess } from '../../session/access';
import { DataTable, FormDialog, StatGrid } from '../../components/forms';
import { Card, Dialog, Empty, LoadingRows, Pager, QueryError, Status, Tabs } from '../../components/ui';
import { DocumentsPanel, SectionTitle, opts, useLookups, vopts } from './common';

const K = ['os', 'people'];

// =================================================================================================================
// Positions & workforce planning
// =================================================================================================================
export function Positions() {
  const access = useAccess();
  const lk = useLookups();
  const qc = useQueryClient();
  const toast = useToast();
  const [tab, setTab] = useState<'positions' | 'workforce'>('positions');
  const [status, setStatus] = useState('');
  const [page, setPage] = useState(1);
  const [create, setCreate] = useState(false);
  const q = useQuery({ queryKey: [...K, 'positions', status, page], queryFn: () => people.list('positions', { status: status || undefined, page }), enabled: tab === 'positions' });
  const wf = useQuery({ queryKey: [...K, 'workforce'], queryFn: () => people.fetch('workforce'), enabled: tab === 'workforce' && access.can('people.workforce.view') });
  const submit = useMutation({ mutationFn: (id: string) => people.action(`positions/${id}/submit`), onSuccess: () => { toast('Sent for approval'); void qc.invalidateQueries({ queryKey: [...K, 'positions'] }); },
    onError: (e) => toast(apiMessage(e), 'error') });
  return (
    <>
      <SectionTitle title="Positions & workforce" desc="Approved roles, headcount and open positions. Hiring starts from an approved position."
        actions={access.can('people.position.create') && <Button onClick={() => setCreate(true)}><Icon name="plus" size={16} />New position</Button>} />
      {access.can('people.workforce.view') && <Tabs value={tab} onChange={setTab} items={[{ value: 'positions', label: 'Positions' }, { value: 'workforce', label: 'Headcount' }]} />}
      {tab === 'positions' && (
        <Card flush>
          <div className="toolbar"><select className="field__input" aria-label="Status" value={status} onChange={(e) => { setStatus(e.target.value); setPage(1); }}>
            <option value="">All statuses</option>{['draft', 'pending_approval', 'approved', 'open', 'filled', 'frozen', 'closed'].map((s) => <option key={s} value={s}>{humanize(s)}</option>)}</select></div>
          {q.isPending ? <LoadingRows /> : q.error ? <QueryError error={q.error} /> : (
            <>
              <DataTable rows={q.data.results} empty="No positions yet" columns={[
                { key: 'c', label: 'Position', render: (p: any) => <><strong>{p.title}</strong><div className="xs muted mono">{p.code}</div></> },
                { key: 'd', label: 'Department', render: (p: any) => <span className="small">{p.departmentName}{p.locationName ? <div className="xs muted">{p.locationName}</div> : null}</span> },
                { key: 'm', label: 'Reports to', render: (p: any) => p.reportingManagerName ?? '—' },
                { key: 'h', label: 'Filled', num: true, render: (p: any) => `${p.filled} / ${p.headcount}` },
                ...(q.data.results.some((p: any) => 'salaryMin' in p) ? [{ key: 's', label: 'Budget range', render: (p: any) => (p.salaryMin ? `${fmtMoney(p.salaryMin, p.currency)} – ${fmtMoney(p.salaryMax, p.currency)}` : '—') }] : []),
                { key: 'st', label: 'Status', render: (p: any) => <Status value={p.status} label={humanize(p.status)} /> },
                { key: 'a', label: '', render: (p: any) => p.status === 'draft' && access.can('people.position.create') ? <Button size="sm" variant="outline" onClick={() => submit.mutate(p.id)}>Submit for approval</Button>
                  : p.approval ? <Link to={`/approvals/${p.approval}`} className="small">Approval</Link> : null },
              ]} />
              <Pager page={q.data.page} hasNext={q.data.hasNext} count={q.data.count} onPage={setPage} />
            </>
          )}
        </Card>
      )}
      {tab === 'workforce' && (
        <Card title="Headcount by department" flush>
          {wf.isPending ? <LoadingRows /> : wf.error ? <QueryError error={wf.error} /> : <DataTable rows={wf.data.results} empty="No departments with headcount yet" columns={[
            { key: 'd', label: 'Department', render: (r: any) => r.department }, { key: 'c', label: 'Current', num: true, render: (r: any) => r.current },
            { key: 'a', label: 'Approved positions', num: true, render: (r: any) => r.approved }, { key: 'o', label: 'Open', num: true, render: (r: any) => r.open },
            { key: 'p', label: 'Planned', num: true, render: (r: any) => (r.planned != null ? `${r.planned} (${r.period})` : '—') }]} />}
        </Card>
      )}
      {create && <FormDialog title="New position" wide onClose={() => setCreate(false)} initial={{ worker_type: 'employee', employment_type: 'full_time', headcount: 1, currency: 'INR' }}
        intro={<p className="small muted">The position code (POS-…) is assigned automatically. Save it as a draft, then submit it for approval.</p>}
        fields={[{ name: 'title', label: 'Title', required: true }, { name: 'description', label: 'Description', type: 'textarea' },
          { name: 'department', label: 'Department', type: 'select', required: true, half: true, options: opts(lk.data?.departments) },
          { name: 'org_unit', label: 'Location', type: 'select', half: true, options: opts(lk.data?.locations) },
          { name: 'designation', label: 'Designation', type: 'select', half: true, options: opts(lk.data?.designations) },
          { name: 'job_level', label: 'Job level', type: 'select', half: true, options: opts(lk.data?.jobLevels) },
          { name: 'worker_type', label: 'Worker type', type: 'select', half: true, options: vopts(lk.data?.workerTypes) },
          { name: 'employment_type', label: 'Employment type', type: 'select', half: true, options: vopts(lk.data?.employmentTypes) },
          { name: 'headcount', label: 'Headcount', type: 'number', min: 1, half: true },
          ...(access.can('people.payroll.view') ? [{ name: 'salary_min', label: 'Budget min (annual)', type: 'number' as const, half: true }, { name: 'salary_max', label: 'Budget max (annual)', type: 'number' as const, half: true }] : [])]}
        onSubmit={(v) => people.create('positions', v)} onDone={() => { toast('Position saved as draft'); void qc.invalidateQueries({ queryKey: [...K, 'positions'] }); }} />}
    </>
  );
}

// =================================================================================================================
// Recruitment: openings + pipeline
// =================================================================================================================
export function Recruitment() {
  const access = useAccess();
  const [params, setParams] = useSearchParams();
  const open = params.get('opening');
  const qc = useQueryClient();
  const toast = useToast();
  const [create, setCreate] = useState(false);
  const q = useQuery({ queryKey: [...K, 'openings'], queryFn: () => people.list('openings', { page_size: 100 }) });
  const positions = useQuery({ queryKey: [...K, 'positions', 'approved'], queryFn: () => people.list('positions', { page_size: 100 }), enabled: create });
  if (open) return <Pipeline id={open} onBack={() => setParams({})} />;
  return (
    <>
      <SectionTitle title="Recruitment" desc="Open roles and hiring pipelines."
        actions={access.can('people.recruitment.create') && <Button onClick={() => setCreate(true)}><Icon name="plus" size={16} />New opening</Button>} />
      <Card flush>
        {q.isPending ? <LoadingRows /> : q.error ? <QueryError error={q.error} /> : (
          <DataTable rows={q.data.results} empty="No openings" emptyMessage="Openings are created from an approved position." onRow={(o: any) => setParams({ opening: o.id })} columns={[
            { key: 't', label: 'Opening', render: (o: any) => <><strong>{o.title}</strong><div className="xs muted mono">{o.code} · {o.positionCode}</div></> },
            { key: 'd', label: 'Department', render: (o: any) => <span className="small">{o.departmentName}{o.locationName ? <div className="xs muted">{o.locationName}</div> : null}</span> },
            { key: 'r', label: 'Recruiter / hiring manager', render: (o: any) => <span className="small">{o.recruiterName ?? '—'}<div className="xs muted">{o.hiringManagerName ?? '—'}</div></span> },
            { key: 'n', label: 'Candidates', num: true, render: (o: any) => Object.entries(o.counts ?? {}).filter(([k]) => !['rejected', 'withdrawn'].includes(k)).reduce((a, [, v]) => a + Number(v), 0) },
            { key: 's', label: 'Status', render: (o: any) => <Status value={o.status} /> }]} />
        )}
      </Card>
      {create && <FormDialog title="New opening" onClose={() => setCreate(false)} initial={{ openings: 1, internal: true, external: true }}
        fields={[{ name: 'position', label: 'Approved position', type: 'select', required: true,
          options: (positions.data?.results ?? []).filter((p: any) => ['approved', 'open'].includes(p.status)).map((p: any) => ({ value: p.id, label: `${p.code} · ${p.title}` })) },
          { name: 'title', label: 'Opening title', required: true }, { name: 'description', label: 'Job description', type: 'textarea' },
          { name: 'openings', label: 'Number of hires', type: 'number', min: 1, half: true },
          { name: 'internal', label: 'Show to employees as an internal job', type: 'checkbox' }, { name: 'external', label: 'Recruit externally', type: 'checkbox' }]}
        onSubmit={(v) => people.create('openings', { ...v, status: 'open' })} onDone={() => { toast('Opening created'); void qc.invalidateQueries({ queryKey: [...K, 'openings'] }); }} />}
    </>
  );
}

function Pipeline({ id, onBack }: { id: string; onBack: () => void }) {
  const qc = useQueryClient();
  const toast = useToast();
  const access = useAccess();
  const key = [...K, 'pipeline', id];
  const q = useQuery({ queryKey: key, queryFn: () => people.fetch(`openings/${id}/pipeline`) });
  const [dlg, setDlg] = useState<{ kind: 'add' | 'reject' | 'interview' | 'offer'; app?: any } | null>(null);
  const cands = useQuery({ queryKey: [...K, 'candidates', 'all'], queryFn: () => people.list('candidates', { page_size: 100 }), enabled: dlg?.kind === 'add' });
  const lk = useLookups();
  const users = useQuery({ queryKey: ['os', 'people-picker'], queryFn: () => api.people.picker(''), enabled: dlg?.kind === 'interview' });
  const inv = () => void qc.invalidateQueries({ queryKey: key });
  const move = useMutation({ mutationFn: ({ app, stage, reason }: { app: string; stage: string; reason?: string }) => people.action(`applications/${app}/move`, { stage, reason }),
    onSuccess: inv, onError: (e) => toast(apiMessage(e), 'error') });
  if (q.isPending) return <><SectionTitle title="Pipeline" /><Card><LoadingRows /></Card></>;
  if (q.error) return <QueryError error={q.error} />;
  const d = q.data;
  const stages = d.columns.map((c: any) => c.stage).filter((s: string) => !['accepted', 'onboarding'].includes(s));
  return (
    <>
      <SectionTitle title={d.opening.title} desc={`${d.opening.code} · ${d.opening.departmentName}`} actions={<>
        <Button variant="ghost" onClick={onBack}>All openings</Button>
        {d.canManage && <Button onClick={() => setDlg({ kind: 'add' })}><Icon name="plus" size={16} />Add candidate</Button>}</>} />
      <div className="kanban" role="list" aria-label="Hiring pipeline">
        {d.columns.filter((c: any) => c.items.length || !['rejected', 'withdrawn'].includes(c.stage)).map((c: any) => (
          <section key={c.stage} className="kanban__col" role="listitem" aria-label={c.label}>
            <div className="kanban__head"><span>{c.label}</span><span>{c.items.length}</span></div>
            {c.items.map((a: any) => (
              <article key={a.id} className="kanban__card">
                <Link to={`/people/candidates?open=${a.candidate.id}`}><strong>{a.candidate.fullName}</strong></Link>
                <span className="xs muted">{a.candidate.currentTitle || '—'}{a.candidate.experienceYears ? ` · ${Number(a.candidate.experienceYears)}y` : ''}</span>
                <span className="xs muted">{a.daysInStage != null ? `${a.daysInStage}d in stage` : ''}{a.interviews.length ? ` · ${a.interviews.length} interview(s)` : ''}</span>
                {a.rejectionReason && <span className="xs" style={{ color: 'var(--c-danger)' }}>{a.rejectionReason}</span>}
                {d.canManage && !['rejected', 'withdrawn', 'accepted', 'onboarding'].includes(a.stage) && (
                  <div className="row row--wrap" style={{ gap: 4 }}>
                    <select className="field__input" style={{ padding: '2px 6px', fontSize: 'var(--fs-xs)' }} aria-label={`Move ${a.candidate.fullName}`} value=""
                      onChange={(e) => { const st = e.target.value; if (st === 'rejected') setDlg({ kind: 'reject', app: a }); else if (st) move.mutate({ app: a.id, stage: st }); }}>
                      <option value="">Move to…</option>{stages.filter((s: string) => s !== a.stage).map((s: string) => <option key={s} value={s}>{humanize(s)}</option>)}
                    </select>
                    <Button size="sm" variant="ghost" onClick={() => setDlg({ kind: 'interview', app: a })}>Interview</Button>
                    {access.can('people.offer.create') && ['selected', 'offer'].includes(a.stage) && <Button size="sm" variant="ghost" onClick={() => setDlg({ kind: 'offer', app: a })}>Offer</Button>}
                  </div>
                )}
              </article>
            ))}
          </section>
        ))}
      </div>
      {access.can('people.offer.view') && <div style={{ marginTop: 16 }}><Offers /></div>}
      {dlg?.kind === 'add' && <FormDialog title="Add candidate to this opening" onClose={() => setDlg(null)}
        intro={<p className="small muted">Not listed? Create the candidate first under Candidates.</p>}
        fields={[{ name: 'candidate_id', label: 'Candidate', type: 'select', required: true, options: (cands.data?.results ?? []).map((c: any) => ({ value: c.id, label: `${c.fullName} · ${c.code}` })) }]}
        onSubmit={(v) => people.action('applications', { ...v, openingId: id })} onDone={() => { toast('Added'); inv(); }} />}
      {dlg?.kind === 'reject' && <FormDialog title={`Reject ${dlg.app.candidate.fullName}`} onClose={() => setDlg(null)} submitLabel="Reject"
        fields={[{ name: 'reason', label: 'Reason (kept for reporting, not shared with the candidate)', required: true, type: 'select',
          options: ['Skills mismatch', 'Experience mismatch', 'Compensation mismatch', 'Failed interview', 'Position filled', 'Candidate unresponsive', 'Other'].map((r) => ({ value: r, label: r })) }]}
        onSubmit={(v) => people.action(`applications/${dlg.app.id}/move`, { stage: 'rejected', reason: v.reason })} onDone={inv} />}
      {dlg?.kind === 'interview' && <FormDialog title={`Schedule interview · ${dlg.app.candidate.fullName}`} onClose={() => setDlg(null)} initial={{ kind: 'video', duration_minutes: 45 }}
        fields={[{ name: 'round_name', label: 'Round', required: true, placeholder: 'e.g. Technical round 1' },
          { name: 'kind', label: 'Type', type: 'select', half: true, options: ['phone', 'video', 'onsite', 'technical', 'hr', 'panel'].map((k) => ({ value: k, label: humanize(k) })) },
          { name: 'duration_minutes', label: 'Minutes', type: 'number', half: true },
          { name: 'scheduled_at', label: 'When', type: 'datetime-local', required: true, half: true }, { name: 'location', label: 'Location or link', half: true },
          { name: 'panel_ids', label: 'Interviewers', type: 'multiselect', options: (users.data?.results ?? []).map((u) => ({ value: u.id, label: u.designation ? `${u.fullName} · ${u.designation}` : u.fullName })) }]}
        onSubmit={(v) => people.action('interviews', { ...v, applicationId: dlg.app.id, scheduledAt: v.scheduledAt ? new Date(String(v.scheduledAt)).toISOString() : null })}
        onDone={() => { toast('Interview scheduled; the panel was notified'); inv(); }} />}
      {dlg?.kind === 'offer' && <FormDialog title={`Offer · ${dlg.app.candidate.fullName}`} onClose={() => setDlg(null)} submitLabel="Create & submit for approval" wide
        intro={<p className="small muted">Offers go through approval before release. Pay is visible only to people who can view offers.</p>}
        fields={[{ name: 'designation_id', label: 'Designation', type: 'select', half: true, options: opts(lk.data?.designations) },
          { name: 'joining_date', label: 'Joining date', type: 'date', required: true, half: true },
          { name: 'base_annual', label: 'Annual base', type: 'number', required: true, half: true }, { name: 'variable_annual', label: 'Annual variable', type: 'number', half: true },
          { name: 'joining_bonus', label: 'Joining bonus', type: 'number', half: true }, { name: 'expires_on', label: 'Offer expires', type: 'date', half: true },
          { name: 'benefits', label: 'Benefits summary', type: 'textarea' }]}
        onSubmit={(v) => people.action('offers', { ...v, applicationId: dlg.app.id, submit: true })} onDone={() => { toast('Offer sent for approval'); inv(); void qc.invalidateQueries({ queryKey: [...K, 'offers'] }); }} />}
    </>
  );
}

function Offers() {
  const qc = useQueryClient();
  const toast = useToast();
  const access = useAccess();
  const q = useQuery({ queryKey: [...K, 'offers'], queryFn: () => people.fetch('offers') });
  const [accept, setAccept] = useState<any>(null);
  const act = useMutation({ mutationFn: ({ id, a, body }: { id: string; a: string; body?: Record<string, unknown> }) => people.action(`offers/${id}/${a}`, body),
    onSuccess: () => { toast('Updated'); void qc.invalidateQueries({ queryKey: K }); }, onError: (e) => toast(apiMessage(e), 'error') });
  const can = access.can('people.offer.create');
  return (
    <Card title="Offers" flush>
      {q.isPending ? <LoadingRows /> : q.error ? <QueryError error={q.error} /> : <DataTable rows={q.data.results} empty="No offers" columns={[
        { key: 'c', label: 'Candidate', render: (o: any) => <><strong>{o.candidate}</strong><div className="xs muted mono">{o.code} · {o.opening}</div></> },
        { key: 'p', label: 'Pay', render: (o: any) => (o.baseAnnual ? fmtMoney(o.baseAnnual, o.currency) : <span className="xs muted">Restricted</span>) },
        { key: 'j', label: 'Joining', render: (o: any) => fmtDate(o.joiningDate) }, { key: 's', label: 'Status', render: (o: any) => <Status value={o.status} /> },
        { key: 'a', label: '', render: (o: any) => (
          <span className="row" style={{ gap: 4 }}>
            {o.approvalId && <Link to={`/approvals/${o.approvalId}`} className="small">Approval</Link>}
            {can && o.status === 'draft' && <Button size="sm" variant="ghost" onClick={() => act.mutate({ id: o.id, a: 'submit' })}>Submit</Button>}
            {can && o.status === 'approved' && <Button size="sm" variant="ghost" onClick={() => act.mutate({ id: o.id, a: 'release' })}>Release</Button>}
            {can && o.status === 'released' && <><Button size="sm" variant="ghost" onClick={() => setAccept(o)}>Accepted</Button>
              <Button size="sm" variant="ghost" onClick={() => act.mutate({ id: o.id, a: 'respond', body: { response: 'declined' } })}>Declined</Button></>}
          </span>) }]} />}
      {accept && <FormDialog title={`${accept.candidate} accepted`} onClose={() => setAccept(null)} submitLabel="Create employee record" initial={{ invite: true }}
        intro={<p className="small muted">Creates the employee record (EMP-…) in pre-onboarding and starts the onboarding checklist. Business OS access still needs roles from an administrator.</p>}
        fields={[{ name: 'work_email', label: 'Work email', type: 'email' }, { name: 'invite', label: 'Send a Business OS invitation', type: 'checkbox' }]}
        onSubmit={(v) => people.action(`offers/${accept.id}/respond`, { ...v, response: 'accepted' })}
        onDone={() => { toast('Employee record created'); void qc.invalidateQueries({ queryKey: K }); }} />}
    </Card>
  );
}

// =================================================================================================================
// Candidates
// =================================================================================================================
export function Candidates() {
  const access = useAccess();
  const qc = useQueryClient();
  const toast = useToast();
  const [params, setParams] = useSearchParams();
  const [text, setText] = useState('');
  const [page, setPage] = useState(1);
  const [create, setCreate] = useState(false);
  const q = useQuery({ queryKey: [...K, 'candidates', text, page], queryFn: () => people.list('candidates', { q: text || undefined, page }) });
  const openId = params.get('open');
  return (
    <>
      <SectionTitle title="Candidates" desc="Candidate records and the talent pool. Kept only with consent."
        actions={access.can('people.recruitment.create') && <Button onClick={() => setCreate(true)}><Icon name="plus" size={16} />New candidate</Button>} />
      <Card flush>
        <div className="toolbar"><div className="search-input"><Icon name="search" size={16} /><input value={text} onChange={(e) => { setText(e.target.value); setPage(1); }} placeholder="Name, email, code or title" aria-label="Search candidates" /></div></div>
        {q.isPending ? <LoadingRows /> : q.error ? <QueryError error={q.error} /> : (
          <>
            <DataTable rows={q.data.results} empty="No candidates" onRow={(c: any) => setParams({ open: c.id })} columns={[
              { key: 'n', label: 'Candidate', render: (c: any) => <><strong>{c.fullName}</strong><div className="xs muted mono">{c.code}</div></> },
              { key: 't', label: 'Current role', render: (c: any) => <span className="small">{c.currentTitle || '—'}<div className="xs muted">{c.currentCompany}</div></span> },
              { key: 'e', label: 'Experience', render: (c: any) => (c.experienceYears ? `${Number(c.experienceYears)} yrs` : '—') },
              { key: 's', label: 'Source', render: (c: any) => humanize(c.source || '—') },
              { key: 'a', label: 'Applications', render: (c: any) => <span className="small">{c.applications.map((a: any) => `${a.opening} (${humanize(a.stage)})`).join(', ') || '—'}</span> }]} />
            <Pager page={q.data.page} hasNext={q.data.hasNext} count={q.data.count} onPage={setPage} />
          </>
        )}
      </Card>
      {openId && <CandidateDrawer id={openId} onClose={() => setParams({})} />}
      {create && <FormDialog title="New candidate" wide onClose={() => setCreate(false)} initial={{ source: 'referral' }}
        intro={<p className="small muted">Record consent before storing a candidate’s details. A candidate code (CAN-…) is assigned automatically.</p>}
        fields={[{ name: 'full_name', label: 'Full name', required: true }, { name: 'email', label: 'Email', type: 'email', half: true }, { name: 'phone', label: 'Phone', half: true },
          { name: 'current_company', label: 'Current company', half: true }, { name: 'current_title', label: 'Current title', half: true },
          { name: 'experience_years', label: 'Experience (years)', type: 'number', half: true }, { name: 'notice_days', label: 'Notice period (days)', type: 'number', half: true },
          { name: 'location', label: 'Location', half: true },
          { name: 'source', label: 'Source', type: 'select', half: true, options: ['referral', 'careers_site', 'job_board', 'agency', 'linkedin', 'campus', 'internal', 'other'].map((s) => ({ value: s, label: humanize(s) })) },
          { name: 'consent_on', label: 'Consent recorded on', type: 'date', required: true, half: true }, { name: 'talent_pool', label: 'Keep in the talent pool', type: 'checkbox' },
          { name: 'notes', label: 'Notes', type: 'textarea' }]}
        onSubmit={(v) => people.create('candidates', v)} onDone={() => { toast('Candidate added'); void qc.invalidateQueries({ queryKey: [...K, 'candidates'] }); }} />}
    </>
  );
}

function CandidateDrawer({ id, onClose }: { id: string; onClose: () => void }) {
  const q = useQuery({ queryKey: [...K, 'candidate', id], queryFn: () => people.get('candidates', id) });
  return (
    <Dialog title={q.data?.fullName ?? 'Candidate'} onClose={onClose} wide>
      {q.isPending ? <LoadingRows /> : q.error ? <QueryError error={q.error} /> : (
        <div className="stack">
          <dl className="kv">
            <dt>Code</dt><dd className="mono">{q.data.code}</dd><dt>Email</dt><dd>{q.data.email || '—'}</dd><dt>Phone</dt><dd>{q.data.phone || '—'}</dd>
            <dt>Current</dt><dd>{q.data.currentTitle || '—'}{q.data.currentCompany ? ` at ${q.data.currentCompany}` : ''}</dd>
            <dt>Experience</dt><dd>{q.data.experienceYears ? `${Number(q.data.experienceYears)} years` : '—'}</dd><dt>Notice</dt><dd>{q.data.noticeDays != null ? `${q.data.noticeDays} days` : '—'}</dd>
            {'expectedCompensation' in q.data && <><dt>Expected pay</dt><dd>{q.data.expectedCompensation ? fmtMoney(q.data.expectedCompensation) : '—'}</dd></>}
            <dt>Skills</dt><dd>{q.data.skills.join(', ') || '—'}</dd><dt>Consent</dt><dd>{fmtDate(q.data.consentOn)}</dd>
          </dl>
          {q.data.notes && <p className="small" style={{ whiteSpace: 'pre-wrap' }}>{q.data.notes}</p>}
          <DocumentsPanel resourceType="people.candidate" resourceId={id} title="Résumé & documents" />
        </div>
      )}
    </Dialog>
  );
}

// =================================================================================================================
// My interviews (panel members see only what they need to assess)
// =================================================================================================================
export function Interviews() {
  const q = useQuery({ queryKey: [...K, 'interviews'], queryFn: () => people.fetch('interviews') });
  const [fb, setFb] = useState<any>(null);
  const qc = useQueryClient();
  const toast = useToast();
  return (
    <>
      <SectionTitle title="My interviews" desc="Interviews you’re on the panel for. You see the candidate’s profile for assessment only — no pay or private details." />
      <Card flush>
        {q.isPending ? <LoadingRows /> : q.error ? <QueryError error={q.error} /> : !q.data.results.length ? <Empty title="No interviews assigned to you" /> : (
          <ul className="list">{q.data.results.map((i: any) => (
            <li key={i.id} className="list-row" style={{ alignItems: 'flex-start' }}>
              <div className="list-row__main"><strong>{i.candidate.name}</strong> <span className="xs muted">· {i.opening}</span>
                <div className="small">{i.round} · {humanize(i.kind)} · {fmtDateTime(i.at)} · {i.duration} min{i.location ? ` · ${i.location}` : ''}</div>
                <div className="xs muted">{i.candidate.currentTitle}{i.candidate.experienceYears ? ` · ${Number(i.candidate.experienceYears)}y` : ''}{i.candidate.skills.length ? ` · ${i.candidate.skills.join(', ')}` : ''}</div>
                {i.myFeedback && <div className="xs">Your feedback: {humanize(i.myFeedback.recommendation)}{i.myFeedback.rating ? ` · ${i.myFeedback.rating}/5` : ''}</div>}</div>
              <Status value={i.status} />
              {i.status !== 'cancelled' && <Button size="sm" variant={i.myFeedback ? 'ghost' : 'outline'} onClick={() => setFb(i)}>{i.myFeedback ? 'Edit feedback' : 'Give feedback'}</Button>}
            </li>))}</ul>
        )}
      </Card>
      {fb && <FormDialog title={`Feedback · ${fb.candidate.name}`} onClose={() => setFb(null)} initial={{ recommendation: fb.myFeedback?.recommendation, rating: fb.myFeedback?.rating ? String(fb.myFeedback.rating) : '', notes: fb.myFeedback?.notes }}
        intro={fb.criteria.length > 0 && <p className="small muted">Assess against: {fb.criteria.join(', ')}</p>}
        fields={[{ name: 'recommendation', label: 'Recommendation', type: 'select', required: true, half: true,
          options: [{ value: 'strong_yes', label: 'Strong yes' }, { value: 'yes', label: 'Yes' }, { value: 'no', label: 'No' }, { value: 'strong_no', label: 'Strong no' }] },
          { name: 'rating', label: 'Overall (1–5)', type: 'select', half: true, options: [1, 2, 3, 4, 5].map((n) => ({ value: String(n), label: String(n) })) },
          { name: 'notes', label: 'Notes (evidence, not opinions about personal traits)', type: 'textarea' }]}
        onSubmit={(v) => people.action(`interviews/${fb.id}/feedback`, v)} onDone={() => { toast('Feedback saved'); void qc.invalidateQueries({ queryKey: [...K, 'interviews'] }); }} />}
    </>
  );
}

// =================================================================================================================
// Onboarding
// =================================================================================================================
export function Onboarding() {
  const [kind, setKind] = useState<'onboarding' | 'offboarding'>('onboarding');
  const q = useQuery({ queryKey: [...K, 'onboarding', kind], queryFn: () => people.fetch('onboarding', { kind }) });
  return (
    <>
      <SectionTitle title="Onboarding" desc="Checklists for new joiners and leavers. Tasks are assigned to IT, HR, managers and the employee." />
      <Tabs value={kind} onChange={setKind} items={[{ value: 'onboarding', label: 'Joiners' }, { value: 'offboarding', label: 'Leavers' }]} />
      {q.isPending ? <Card><LoadingRows /></Card> : q.error ? <QueryError error={q.error} /> : !q.data.results.length ? <Card><Empty title={`No ${kind} in progress`} /></Card> : (
        <>
          <StatGrid items={[{ key: 'n', label: 'In progress', value: q.data.results.length },
            { key: 'o', label: 'Steps still open', value: q.data.results.reduce((a: number, p: any) => a + p.total - p.done, 0) }]} />
          <div style={{ height: 12 }} />
          <Card flush><DataTable rows={q.data.results} columns={[
            { key: 'e', label: 'Employee', render: (p: any) => <Link to={`/people/${p.employee.id}?tab=lifecycle`}>{p.employee.name}</Link> },
            { key: 't', label: 'Checklist', render: (p: any) => p.template ?? '—' }, { key: 'j', label: 'Joining', render: (p: any) => fmtDate(p.joinedOn) },
            { key: 'p', label: 'Progress', render: (p: any) => <span className="row" style={{ gap: 8 }}><span className="progress" style={{ width: 120 }}><span style={{ width: `${p.pct}%` }} /></span><span className="xs">{p.done}/{p.total}</span></span> },
            { key: 'o', label: 'Open steps', render: (p: any) => <span className="xs muted">{p.tasks.filter((t: any) => t.status !== 'done').slice(0, 3).map((t: any) => `${t.title} (${t.assignee})`).join(' · ') || 'All done'}</span> }]} /></Card>
        </>
      )}
    </>
  );
}
