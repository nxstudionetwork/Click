/* eslint-disable @typescript-eslint/no-explicit-any */
import { useState } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Button, Icon, useToast } from '@click/ui';
import { apiMessage, http, people } from '../../lib/api';
import { fmtDate, fmtMoney, humanize, relative } from '../../lib/format';
import { useAccess } from '../../session/access';
import { useOS } from '../../session/OSSession';
import { DataTable, FormDialog } from '../../components/forms';
import { Alert, Card, Dialog, Empty, LoadingRows, QueryError, Status, Tabs } from '../../components/ui';
import { GoalRows } from './core';
import { Bars, SectionTitle, useLookups } from './common';

const K = ['os', 'people'];

// =================================================================================================================
// Performance: my reviews, goals, cycles
// =================================================================================================================
export function Performance() {
  const access = useAccess();
  const [params, setParams] = useSearchParams();
  const tab = (params.get('tab') ?? 'reviews') as 'reviews' | 'goals' | 'cycles';
  return (
    <>
      <SectionTitle title="Goals & reviews" desc="Reviews you need to write, goals that cascade from company to individual, and review cycles." />
      <Tabs value={tab} onChange={(t) => setParams({ tab: t })} items={[{ value: 'reviews', label: 'Reviews to write' }, { value: 'goals', label: 'Goals' },
        ...(access.can('people.performance.view') ? [{ value: 'cycles' as const, label: 'Review cycles' }] : [])]} />
      {tab === 'reviews' && <MyReviews />}
      {tab === 'goals' && <Goals />}
      {tab === 'cycles' && <Cycles />}
    </>
  );
}

function MyReviews() {
  const q = useQuery({ queryKey: [...K, 'reviews', 'mine'], queryFn: () => people.fetch('reviews/mine') });
  const [open, setOpen] = useState<any>(null);
  const qc = useQueryClient();
  const toast = useToast();
  if (q.isPending) return <Card><LoadingRows /></Card>;
  if (q.error) return <QueryError error={q.error} />;
  return (
    <Card flush>
      {!q.data.results.length ? <Empty title="No reviews to write" message="Reviews appear here when a review cycle is launched." /> : (
        <DataTable rows={q.data.results} onRow={(r: any) => r.status === 'pending' && setOpen(r)} columns={[
          { key: 'e', label: 'About', render: (r: any) => <>{r.kind === 'self' ? 'Yourself' : r.employee.name}<div className="xs muted">{r.kindLabel} · {r.cycle}</div></> },
          { key: 'd', label: 'Due', render: (r: any) => fmtDate(r.dueOn) }, { key: 'r', label: 'Rating', render: (r: any) => (r.rating ? `${r.rating} / 5` : '—') },
          { key: 's', label: 'Status', render: (r: any) => <Status value={r.status} /> },
          { key: 'a', label: '', render: (r: any) => r.status === 'pending' && <Button size="sm" variant="outline" onClick={(ev) => { ev.stopPropagation(); setOpen(r); }}>Write</Button> }]} />
      )}
      {open && <ReviewDialog r={open} onClose={() => setOpen(null)} onDone={(sub) => { toast(sub ? 'Review submitted' : 'Draft saved'); void qc.invalidateQueries({ queryKey: K }); }} />}
    </Card>
  );
}

function ReviewDialog({ r, onClose, onDone }: { r: any; onClose: () => void; onDone: (submitted: boolean) => void }) {
  const [v, setV] = useState({ rating: r.rating ? String(r.rating) : '', strengths: r.strengths, improvements: r.improvements, comments: r.comments });
  const save = useMutation({
    mutationFn: (submit: boolean) => people.update('reviews', r.id, { rating: v.rating ? Number(v.rating) : null, strengths: v.strengths, improvements: v.improvements, comments: v.comments, submit }),
    onSuccess: (_x, submit) => { onDone(submit); onClose(); },
  });
  const set = (k: string) => (e: { target: { value: string } }) => setV((s) => ({ ...s, [k]: e.target.value }));
  return (
    <Dialog title={`${r.kindLabel} · ${r.kind === 'self' ? 'You' : r.employee.name}`} onClose={onClose} wide footer={<>
      <Button variant="outline" onClick={() => save.mutate(false)} loading={save.isPending}>Save draft</Button>
      <Button onClick={() => save.mutate(true)} loading={save.isPending} disabled={r.kind !== 'peer' && !v.rating}>Submit</Button></>}>
      {save.error && <Alert tone="error">{apiMessage(save.error)}</Alert>}
      <p className="small muted">{r.cycle}. Base your review on observed work and goals. Once submitted it can’t be edited.</p>
      <div className="form-grid">
        {r.kind !== 'peer' && <label className="field form-grid__full"><span className="field__label">Overall rating</span>
          <select className="field__input" value={v.rating} onChange={set('rating')}><option value="">Choose…</option>
            {['Needs improvement', 'Partly meets', 'Meets expectations', 'Exceeds', 'Outstanding'].map((l, i) => <option key={l} value={i + 1}>{i + 1} · {l}</option>)}</select></label>}
        <label className="field form-grid__full"><span className="field__label">Strengths</span><textarea className="field__input" rows={3} value={v.strengths} onChange={set('strengths')} /></label>
        <label className="field form-grid__full"><span className="field__label">To develop</span><textarea className="field__input" rows={3} value={v.improvements} onChange={set('improvements')} /></label>
        <label className="field form-grid__full"><span className="field__label">Comments</span><textarea className="field__input" rows={3} value={v.comments} onChange={set('comments')} /></label>
      </div>
    </Dialog>
  );
}

function Goals() {
  const access = useAccess();
  const os = useOS();
  const qc = useQueryClient();
  const toast = useToast();
  const [level, setLevel] = useState('');
  const [mine, setMine] = useState(true);
  const [dlg, setDlg] = useState<'none' | 'new'>('none');
  const [edit, setEdit] = useState<any>(null);
  const q = useQuery({ queryKey: [...K, 'goals', level, mine], queryFn: () => people.fetch('goals', { level: level || undefined, employee: mine && os.employee ? os.employee.id : undefined }) });
  const manage = access.can('people.performance.manage');
  const cycles = useQuery({ queryKey: [...K, 'cycles'], queryFn: () => people.list('review-cycles'), enabled: dlg === 'new' });
  return (
    <Card flush actions={<Button size="sm" onClick={() => setDlg('new')}><Icon name="plus" size={15} />New goal</Button>} title="Goals">
      <div className="toolbar">
        <select className="field__input" aria-label="Level" value={level} onChange={(e) => { setLevel(e.target.value); if (e.target.value && e.target.value !== 'employee') setMine(false); }}>
          <option value="">All levels</option>{['company', 'business_unit', 'department', 'team', 'employee'].map((l) => <option key={l} value={l}>{humanize(l)}</option>)}</select>
        {os.employee && <label className="row small"><input type="checkbox" checked={mine} onChange={(e) => setMine(e.target.checked)} />Only mine</label>}
      </div>
      {q.isPending ? <LoadingRows /> : q.error ? <QueryError error={q.error} /> : (
        <ul className="list">{q.data.results.length ? q.data.results.map((g: any) => (
          <li key={g.id}><button className="list-row" style={{ width: '100%', textAlign: 'left', background: 'none', border: 0 }} onClick={() => setEdit(g)}>
            <span className="grow"><GoalRows goals={[g]} /></span>{g.employeeName && <span className="xs muted">{g.employeeName}</span>}</button></li>))
          : <li><Empty title="No goals yet" /></li>}</ul>
      )}
      {dlg === 'new' && <FormDialog title="New goal" wide onClose={() => setDlg('none')} initial={{ level: 'employee', kind: 'okr', weight: 0 }}
        fields={[{ name: 'title', label: 'Goal', required: true }, { name: 'description', label: 'Description', type: 'textarea' },
          { name: 'level', label: 'Level', type: 'select', required: true, half: true, options: (manage ? ['company', 'business_unit', 'department', 'team', 'employee'] : ['employee']).map((l) => ({ value: l, label: humanize(l) })) },
          { name: 'parent', label: 'Supports (parent goal)', type: 'select', half: true, options: (q.data?.results ?? []).filter((g: any) => g.level !== 'employee').map((g: any) => ({ value: g.id, label: g.title })) },
          { name: 'cycle', label: 'Cycle', type: 'select', half: true, options: (cycles.data?.results ?? []).map((c: any) => ({ value: c.id, label: c.name })) },
          { name: 'metric', label: 'Measure', half: true, placeholder: 'e.g. Orders per day' }, { name: 'target', label: 'Target', type: 'number', half: true },
          { name: 'current', label: 'Current', type: 'number', half: true }, { name: 'due_on', label: 'Due', type: 'date', half: true }]}
        onSubmit={(v) => people.create('goals', v)} onDone={() => { toast('Goal created'); void qc.invalidateQueries({ queryKey: [...K, 'goals'] }); }} />}
      {edit && <FormDialog title={`Update · ${edit.title}`} onClose={() => setEdit(null)} initial={{ current: edit.current, status: edit.status }}
        fields={[{ name: 'current', label: `Current ${edit.metric ? `(${edit.metric})` : 'value'}`, type: 'number', half: true },
          { name: 'status', label: 'Status', type: 'select', half: true, options: ['on_track', 'at_risk', 'off_track', 'done', 'dropped'].map((s) => ({ value: s, label: humanize(s) })) }]}
        onSubmit={(v) => people.update('goals', edit.id, v)} onDone={() => { toast('Goal updated'); void qc.invalidateQueries({ queryKey: [...K, 'goals'] }); }} />}
    </Card>
  );
}

function Cycles() {
  const access = useAccess();
  const qc = useQueryClient();
  const toast = useToast();
  const [create, setCreate] = useState(false);
  const q = useQuery({ queryKey: [...K, 'cycles'], queryFn: () => people.list('review-cycles') });
  const launch = useMutation({ mutationFn: (id: string) => people.action(`review-cycles/${id}/launch`),
    onSuccess: (r: any) => { toast(`${r.reviewsCreated} reviews opened`); void qc.invalidateQueries({ queryKey: K }); }, onError: (e) => toast(apiMessage(e), 'error') });
  const manage = access.can('people.performance.manage');
  return (
    <Card flush title="Review cycles" actions={manage && <Button size="sm" onClick={() => setCreate(true)}><Icon name="plus" size={15} />New cycle</Button>}>
      {q.isPending ? <LoadingRows /> : q.error ? <QueryError error={q.error} /> : <DataTable rows={q.data.results} empty="No review cycles" columns={[
        { key: 'n', label: 'Cycle', render: (c: any) => <><strong>{c.name}</strong><div className="xs muted">{humanize(c.frequency)}</div></> },
        { key: 'p', label: 'Period', render: (c: any) => `${fmtDate(c.startsOn)} – ${fmtDate(c.endsOn)}` },
        { key: 'd', label: 'Self / manager due', render: (c: any) => <span className="small">{fmtDate(c.selfReviewDue)} · {fmtDate(c.managerReviewDue)}</span> },
        { key: 's', label: 'Status', render: (c: any) => <Status value={c.status} /> },
        { key: 'a', label: '', render: (c: any) => manage && c.status === 'draft' && <Button size="sm" variant="outline" loading={launch.isPending} onClick={() => launch.mutate(c.id)}>Launch</Button> }]} />}
      {create && <FormDialog title="New review cycle" onClose={() => setCreate(false)} initial={{ frequency: 'half_yearly' }}
        fields={[{ name: 'name', label: 'Name', required: true, placeholder: 'e.g. H1 2027' },
          { name: 'frequency', label: 'Frequency', type: 'select', half: true, options: ['quarterly', 'half_yearly', 'annual', 'probation'].map((f) => ({ value: f, label: humanize(f) })) },
          { name: 'starts_on', label: 'Period starts', type: 'date', required: true, half: true }, { name: 'ends_on', label: 'Period ends', type: 'date', required: true, half: true },
          { name: 'self_review_due', label: 'Self reviews due', type: 'date', half: true }, { name: 'manager_review_due', label: 'Manager reviews due', type: 'date', half: true },
          { name: 'peer_feedback', label: 'Include peer feedback', type: 'checkbox' }]}
        onSubmit={(v) => people.create('review-cycles', v)} onDone={() => { toast('Cycle created — launch it when ready'); void qc.invalidateQueries({ queryKey: [...K, 'cycles'] }); }} />}
    </Card>
  );
}

// =================================================================================================================
// Learning & skills
// =================================================================================================================
export function Learning() {
  const access = useAccess();
  const os = useOS();
  const qc = useQueryClient();
  const toast = useToast();
  const [tab, setTab] = useState<'mine' | 'catalog' | 'skills' | 'certs'>('mine');
  const me = useQuery({ queryKey: [...K, 'tab', os.employee?.id, 'learning'], queryFn: () => people.tab(os.employee!.id, 'learning'), enabled: tab === 'mine' && !!os.employee });
  const courses = useQuery({ queryKey: [...K, 'courses'], queryFn: () => people.list('courses', { page_size: 100 }), enabled: tab === 'catalog' });
  const skills = useQuery({ queryKey: [...K, 'skills'], queryFn: () => people.list('skills', { page_size: 100 }), enabled: tab === 'skills' });
  const certs = useQuery({ queryKey: [...K, 'certifications'], queryFn: () => people.fetch('certifications'), enabled: tab === 'certs' });
  const [dlg, setDlg] = useState<'none' | 'course' | 'assign' | 'skill'>('none');
  const [assign, setAssign] = useState<any>(null);
  const emps = useQuery({ queryKey: [...K, 'employees', 'assign'], queryFn: () => people.employees({ page_size: 100 }), enabled: !!assign });
  const inv = () => void qc.invalidateQueries({ queryKey: K });
  const enroll = useMutation({ mutationFn: (courseId: string) => people.action('enrollments', { courseId }), onSuccess: () => { toast('Enrolled'); inv(); }, onError: (e) => toast(apiMessage(e), 'error') });
  const setStatus = useMutation({ mutationFn: ({ id, status }: { id: string; status: string }) => people.update('enrollments', id, { status }), onSuccess: inv });
  const verify = useMutation({ mutationFn: ({ id, ok }: { id: string; ok: boolean }) => people.action(`certifications/${id}/verify`, { verified: ok }), onSuccess: inv,
    onError: (e) => toast(apiMessage(e), 'error') });
  const manage = access.can('people.learning.manage');
  return (
    <>
      <SectionTitle title="Learning & skills" desc="Your training, the course catalogue, the company skills library and certifications."
        actions={manage && <><Button variant="outline" onClick={() => setDlg('skill')}>New skill</Button><Button onClick={() => setDlg('course')}><Icon name="plus" size={16} />New course</Button></>} />
      <Tabs value={tab} onChange={setTab} items={[{ value: 'mine', label: 'My training' }, { value: 'catalog', label: 'Catalogue' }, { value: 'skills', label: 'Skills library' }, { value: 'certs', label: 'Certifications' }]} />
      {tab === 'mine' && (!os.employee ? <Empty title="No employee record" /> : me.isPending ? <Card><LoadingRows /></Card> : me.error ? <QueryError error={me.error} /> : (
        <Card flush><DataTable rows={me.data.enrollments} empty="No training assigned" columns={[
          { key: 'c', label: 'Course', render: (x: any) => <>{x.course}{x.mandatory && <span className="flag flag--due_soon" style={{ marginLeft: 6 }}>mandatory</span>}</> },
          { key: 'd', label: 'Due', render: (x: any) => fmtDate(x.dueOn) }, { key: 's', label: 'Status', render: (x: any) => <Status value={x.status} /> },
          { key: 'a', label: '', render: (x: any) => x.status !== 'completed' && <span className="row" style={{ gap: 4 }}>
            {x.status === 'assigned' && <Button size="sm" variant="ghost" onClick={() => setStatus.mutate({ id: x.id, status: 'in_progress' })}>Start</Button>}
            <Button size="sm" variant="ghost" onClick={() => setStatus.mutate({ id: x.id, status: 'completed' })}>Mark complete</Button></span> }]} /></Card>))}
      {tab === 'catalog' && (courses.isPending ? <Card><LoadingRows /></Card> : courses.error ? <QueryError error={courses.error} /> : (
        <Card flush><DataTable rows={courses.data.results} empty="No courses yet" columns={[
          { key: 't', label: 'Course', render: (c: any) => <><strong>{c.title}</strong>{c.mandatory && <span className="flag flag--due_soon" style={{ marginLeft: 6 }}>mandatory</span>}<div className="xs muted">{c.provider} · {humanize(c.kind)}{c.durationHours ? ` · ${c.durationHours}h` : ''}</div></> },
          { key: 'e', label: 'Enrolled', num: true, render: (c: any) => c.enrolled },
          { key: 'a', label: '', render: (c: any) => <span className="row" style={{ gap: 4 }}>
            {c.url && <a href={c.url} target="_blank" rel="noopener noreferrer" className="small">Open</a>}
            {os.employee && <Button size="sm" variant="ghost" onClick={() => enroll.mutate(c.id)}>Enrol me</Button>}
            {access.can('people.learning.assign') && <Button size="sm" variant="ghost" onClick={() => setAssign(c)}>Assign</Button>}</span> }]} /></Card>))}
      {tab === 'skills' && (skills.isPending ? <Card><LoadingRows /></Card> : skills.error ? <QueryError error={skills.error} /> : (
        <Card flush><DataTable rows={skills.data.results} empty="No skills defined" columns={[{ key: 'n', label: 'Skill', render: (s: any) => s.name },
          { key: 'c', label: 'Category', render: (s: any) => humanize(s.category) }, { key: 'h', label: 'People', num: true, render: (s: any) => s.holders }]} /></Card>))}
      {tab === 'certs' && (certs.isPending ? <Card><LoadingRows /></Card> : certs.error ? <QueryError error={certs.error} /> : (
        <Card flush><DataTable rows={certs.data.results} empty="No certifications" columns={[
          { key: 'n', label: 'Certification', render: (c: any) => <>{c.name}<div className="xs muted">{c.provider}</div></> },
          { key: 'e', label: 'Employee', render: (c: any) => <Link to={`/people/${c.employeeId}?tab=learning`}>{c.employee}</Link> },
          { key: 'x', label: 'Expires', render: (c: any) => fmtDate(c.expiresOn) }, { key: 'v', label: 'Verification', render: (c: any) => <Status value={c.verification === 'verified' ? 'active' : 'pending'} label={c.verification} /> },
          { key: 'a', label: '', render: (c: any) => !c.mine && c.verification === 'pending' && access.can('people.learning.verify') && <span className="row" style={{ gap: 4 }}>
            <Button size="sm" variant="ghost" onClick={() => verify.mutate({ id: c.id, ok: true })}>Verify</Button><Button size="sm" variant="ghost" onClick={() => verify.mutate({ id: c.id, ok: false })}>Reject</Button></span> }]} /></Card>))}
      {dlg === 'course' && <FormDialog title="New course" onClose={() => setDlg('none')} initial={{ kind: 'internal', is_active: true }}
        fields={[{ name: 'title', label: 'Title', required: true }, { name: 'provider', label: 'Provider', half: true },
          { name: 'kind', label: 'Type', type: 'select', half: true, options: ['internal', 'external', 'workshop', 'certification'].map((k) => ({ value: k, label: humanize(k) })) },
          { name: 'duration_hours', label: 'Hours', type: 'number', half: true }, { name: 'url', label: 'Link', half: true }, { name: 'description', label: 'Description', type: 'textarea' },
          { name: 'mandatory', label: 'Mandatory (compliance)', type: 'checkbox' }, { name: 'is_active', label: 'Active', type: 'checkbox' }]}
        onSubmit={(v) => people.create('courses', v)} onDone={() => { toast('Course added'); inv(); }} />}
      {dlg === 'skill' && <FormDialog title="New skill" onClose={() => setDlg('none')} initial={{ category: 'technical' }}
        fields={[{ name: 'name', label: 'Skill', required: true }, { name: 'category', label: 'Category', type: 'select', options: ['technical', 'soft', 'domain', 'language'].map((k) => ({ value: k, label: humanize(k) })) }]}
        onSubmit={(v) => people.create('skills', v)} onDone={() => { toast('Skill added'); inv(); }} />}
      {assign && <FormDialog title={`Assign · ${assign.title}`} onClose={() => setAssign(null)} submitLabel="Assign"
        fields={[{ name: 'employee_ids', label: 'People', type: 'multiselect', options: (emps.data?.results ?? []).map((e) => ({ value: e.id, label: e.displayName })) },
          { name: 'due_on', label: 'Due', type: 'date' }]}
        onSubmit={(v) => people.action('enrollments', { ...v, courseId: assign.id })} onDone={(r: any) => { toast(`${r.enrolled} assigned`); inv(); }} />}
    </>
  );
}

// =================================================================================================================
// Compensation, payroll inputs and benefits (restricted)
// =================================================================================================================
export function Compensation() {
  const access = useAccess();
  const [params, setParams] = useSearchParams();
  const tab = (params.get('tab') ?? (access.can('people.payroll.view') ? 'pay' : 'benefits')) as 'pay' | 'payroll' | 'benefits';
  return (
    <>
      <SectionTitle title="Compensation & benefits" desc="Restricted. Every view and export is recorded in the audit trail." />
      <Tabs value={tab} onChange={(t) => setParams({ tab: t })} items={[
        ...(access.can('people.payroll.view') ? [{ value: 'pay' as const, label: 'Current pay' }] : []),
        ...(access.can('people.payroll.export') ? [{ value: 'payroll' as const, label: 'Payroll inputs' }] : []),
        ...(access.can('people.benefit.view') ? [{ value: 'benefits' as const, label: 'Benefit plans' }] : [])]} />
      {tab === 'pay' && <CurrentPay />}
      {tab === 'payroll' && <PayrollInputs />}
      {tab === 'benefits' && <Benefits />}
    </>
  );
}

function CurrentPay() {
  const q = useQuery({ queryKey: [...K, 'compensation'], queryFn: () => people.fetch('compensation') });
  if (q.isPending) return <Card><LoadingRows /></Card>;
  if (q.error) return <QueryError error={q.error} />;
  return (
    <div className="stack stack--lg">
      <Alert tone="warning">Confidential pay data. Don’t copy it outside Business OS.</Alert>
      <Card flush><DataTable rows={q.data.results.map((r: any) => ({ ...r, id: r.employee.id }))} empty="No compensation records in your scope" columns={[
        { key: 'e', label: 'Employee', render: (r: any) => <Link to={`/people/${r.employee.id}?tab=compensation`}>{r.employee.name}</Link> },
        { key: 'd', label: 'Role', render: (r: any) => <span className="small">{r.designation ?? '—'}<div className="xs muted">{r.department ?? '—'}</div></span> },
        { key: 'b', label: 'Annual base', num: true, render: (r: any) => fmtMoney(r.baseAnnual, r.currency) },
        { key: 'v', label: 'Variable target', num: true, render: (r: any) => fmtMoney(r.variableTarget, r.currency) },
        { key: 'f', label: 'Effective', render: (r: any) => fmtDate(r.effectiveDate) }]} /></Card>
      {q.data.missing.length > 0 && <Card title="No pay record yet"><p className="small">{q.data.missing.join(', ')}</p></Card>}
      <p className="xs muted">Payroll provider: {q.data.payrollProvider ?? 'not connected (Settings → Integrations)'}.</p>
    </div>
  );
}

function PayrollInputs() {
  const toast = useToast();
  const now = new Date();
  const [month, setMonth] = useState(`${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}`);
  const [y, mo] = month.split('-').map(Number);
  const q = useQuery({ queryKey: [...K, 'payroll', month], queryFn: () => people.fetch('payroll/inputs', { year: y, month: mo }) });
  const csv = async () => {
    try {
      const blob = await http.blob!(`/os/people/payroll/inputs?year=${y}&month=${mo}&export=csv`);
      const a = document.createElement('a'); a.href = URL.createObjectURL(blob); a.download = `payroll-inputs-${month}.csv`; a.click();
    } catch (e) { toast(apiMessage(e), 'error'); }
  };
  return (
    <Card flush title="Payroll inputs" actions={<span className="row"><input type="month" className="field__input" aria-label="Month" value={month} onChange={(e) => setMonth(e.target.value)} />
      <Button size="sm" variant="outline" onClick={() => void csv()}><Icon name="download" size={15} />CSV</Button></span>}>
      {q.isPending ? <LoadingRows /> : q.error ? <QueryError error={q.error} /> : <>
        <p className="xs muted" style={{ padding: '0 16px' }}>{q.data.note}</p>
        <DataTable rows={q.data.results.map((r: any) => ({ ...r, id: r.employeeId }))} empty="No employees in scope" columns={[
          { key: 'e', label: 'Employee', render: (r: any) => <>{r.name}<div className="xs muted mono">{r.employeeId}</div></> },
          { key: 'w', label: 'Working days', num: true, render: (r: any) => r.workingDays }, { key: 'p', label: 'Present', num: true, render: (r: any) => r.presentDays },
          { key: 'l', label: 'Paid leave', num: true, render: (r: any) => r.paidLeaveDays }, { key: 'u', label: 'Unpaid leave', num: true, render: (r: any) => r.unpaidLeaveDays },
          { key: 'b', label: 'Annual base', num: true, render: (r: any) => (r.baseAnnual ? fmtMoney(r.baseAnnual, r.currency) : '—') },
          { key: 's', label: 'Status', render: (r: any) => <span className="small">{humanize(r.status)}{r.exitDate ? ` · exits ${fmtDate(r.exitDate)}` : ''}</span> }]} /></>}
    </Card>
  );
}

function Benefits() {
  const access = useAccess();
  const qc = useQueryClient();
  const toast = useToast();
  const lk = useLookups();
  const q = useQuery({ queryKey: [...K, 'benefits'], queryFn: () => people.list('benefits') });
  const [create, setCreate] = useState(false);
  const [enroll, setEnroll] = useState<any>(null);
  const emps = useQuery({ queryKey: [...K, 'employees', 'benefit'], queryFn: () => people.employees({ page_size: 100 }), enabled: !!enroll });
  const manage = access.can('people.benefit.manage');
  return (
    <Card flush title="Benefit plans" actions={manage && <Button size="sm" onClick={() => setCreate(true)}><Icon name="plus" size={15} />New plan</Button>}>
      {q.isPending ? <LoadingRows /> : q.error ? <QueryError error={q.error} /> : <DataTable rows={q.data.results} empty="No benefit plans" columns={[
        { key: 'n', label: 'Plan', render: (b: any) => <><strong>{b.name}</strong><div className="xs muted">{b.description}</div></> }, { key: 'k', label: 'Type', render: (b: any) => humanize(b.kind) },
        { key: 'w', label: 'Eligible', render: (b: any) => <span className="small">{b.workerTypes.length ? b.workerTypes.map(humanize).join(', ') : 'All worker types'}</span> },
        { key: 'e', label: 'Enrolled', num: true, render: (b: any) => b.enrolled },
        { key: 'a', label: '', render: (b: any) => manage && b.isActive && <Button size="sm" variant="ghost" onClick={() => setEnroll(b)}>Enrol</Button> }]} />}
      {create && <FormDialog title="New benefit plan" onClose={() => setCreate(false)} initial={{ kind: 'insurance', is_active: true }}
        fields={[{ name: 'name', label: 'Plan', required: true }, { name: 'kind', label: 'Type', type: 'select', half: true, options: ['insurance', 'allowance', 'retirement', 'wellness', 'program', 'other'].map((k) => ({ value: k, label: humanize(k) })) },
          { name: 'worker_types', label: 'Only for', type: 'multiselect', options: lk.data?.workerTypes ?? [] }, { name: 'description', label: 'Description', type: 'textarea' }, { name: 'is_active', label: 'Active', type: 'checkbox' }]}
        onSubmit={(v) => people.create('benefits', { ...v, workerTypes: v.workerTypes ?? [] })} onDone={() => { toast('Plan added'); void qc.invalidateQueries({ queryKey: [...K, 'benefits'] }); }} />}
      {enroll && <FormDialog title={`Enrol in ${enroll.name}`} onClose={() => setEnroll(null)}
        fields={[{ name: 'employee_id', label: 'Employee', type: 'select', required: true, options: (emps.data?.results ?? []).map((e) => ({ value: e.id, label: e.displayName })) }, { name: 'details', label: 'Details' }]}
        onSubmit={(v) => people.action(`benefits/${enroll.id}/enroll`, v)} onDone={() => { toast('Enrolled'); void qc.invalidateQueries({ queryKey: [...K, 'benefits'] }); }} />}
    </Card>
  );
}

// =================================================================================================================
// Engagement: surveys and recognition
// =================================================================================================================
export function Engagement() {
  const access = useAccess();
  const [params, setParams] = useSearchParams();
  const tab = (params.get('tab') ?? 'surveys') as 'surveys' | 'recognition' | 'manage';
  return (
    <>
      <SectionTitle title="Surveys & engagement" desc="Answer pulse surveys and celebrate colleagues. Anonymous survey results only appear for groups large enough to protect individuals." />
      <Tabs value={tab} onChange={(t) => setParams({ tab: t })} items={[{ value: 'surveys', label: 'Open surveys' }, { value: 'recognition', label: 'Recognition wall' },
        ...(access.can('people.engagement.manage') ? [{ value: 'manage' as const, label: 'Manage surveys' }] : [])]} />
      {tab === 'surveys' && <OpenSurveys />}
      {tab === 'recognition' && <RecognitionWall />}
      {tab === 'manage' && <ManageSurveys />}
    </>
  );
}

function OpenSurveys() {
  const q = useQuery({ queryKey: [...K, 'surveys', 'open'], queryFn: () => people.fetch('surveys/open') });
  const [answer, setAnswer] = useState<any>(null);
  if (q.isPending) return <Card><LoadingRows /></Card>;
  if (q.error) return <QueryError error={q.error} />;
  if (!q.data.results.length) return <Card><Empty title="No open surveys" /></Card>;
  return (
    <div className="stack">
      {q.data.results.map((s: any) => (
        <Card key={s.id} title={s.title} actions={s.answered ? <Status value="active" label="Answered" /> : <Button size="sm" onClick={() => setAnswer(s)}>Answer</Button>}>
          <p className="small">{s.description}</p><p className="xs muted">{s.anonymous ? 'Anonymous — your name isn’t stored with your answers.' : 'Not anonymous.'}{s.closesOn ? ` Closes ${fmtDate(s.closesOn)}.` : ''}</p>
        </Card>))}
      {answer && <SurveyDialog s={answer} onClose={() => setAnswer(null)} />}
    </div>
  );
}

function SurveyDialog({ s, onClose }: { s: any; onClose: () => void }) {
  const qc = useQueryClient();
  const toast = useToast();
  const [a, setA] = useState<Record<string, string>>({});
  const send = useMutation({ mutationFn: () => people.action(`surveys/${s.id}/respond`, { answers: a }),
    onSuccess: () => { toast('Thanks for answering'); void qc.invalidateQueries({ queryKey: [...K, 'surveys'] }); onClose(); } });
  return (
    <Dialog title={s.title} onClose={onClose} wide footer={<><Button variant="outline" onClick={onClose}>Cancel</Button><Button loading={send.isPending} onClick={() => send.mutate()}>Submit</Button></>}>
      {send.error && <Alert tone="error">{apiMessage(send.error)}</Alert>}
      <div className="stack">{s.questions.map((qn: any) => (
        <fieldset key={qn.id} className="field" style={{ border: 0, padding: 0 }}><legend className="field__label">{qn.text}</legend>
          {qn.type === 'scale' ? <div className="row">{[1, 2, 3, 4, 5].map((n) => <label key={n} className={`pill ${a[qn.id] === String(n) ? 'pill--on' : ''}`}>
            <input type="radio" className="sr-only" name={qn.id} checked={a[qn.id] === String(n)} onChange={() => setA((x) => ({ ...x, [qn.id]: String(n) }))} />{n}</label>)}</div>
            : qn.type === 'choice' ? <select className="field__input" value={a[qn.id] ?? ''} onChange={(e) => setA((x) => ({ ...x, [qn.id]: e.target.value }))}><option value="">Choose…</option>
              {(qn.options ?? []).map((o: string) => <option key={o} value={o}>{o}</option>)}</select>
            : <textarea className="field__input" rows={3} value={a[qn.id] ?? ''} onChange={(e) => setA((x) => ({ ...x, [qn.id]: e.target.value }))} />}
        </fieldset>))}</div>
    </Dialog>
  );
}

function RecognitionWall() {
  const q = useQuery({ queryKey: [...K, 'feedback', 'wall'], queryFn: () => people.fetch('feedback', { wall: 'true' }) });
  if (q.isPending) return <Card><LoadingRows /></Card>;
  if (q.error) return <QueryError error={q.error} />;
  return (
    <Card flush>{!q.data.results.length ? <Empty title="No recognition yet" message="Open a colleague’s profile and choose Recognise." /> : (
      <ul className="list">{q.data.results.map((f: any) => (
        <li key={f.id} className="list-row" style={{ alignItems: 'flex-start' }}><span aria-hidden="true">🏅</span>
          <div className="list-row__main"><strong><Link to={`/people/${f.toId}`}>{f.to}</Link></strong>{f.badge && <span className="chip" style={{ marginLeft: 6 }}>{humanize(f.badge)}</span>}
            <p className="small" style={{ margin: '4px 0' }}>{f.body}</p><span className="xs muted">from {f.from ?? '—'} · {relative(f.at)}</span></div></li>))}</ul>)}</Card>
  );
}

function ManageSurveys() {
  const qc = useQueryClient();
  const toast = useToast();
  const q = useQuery({ queryKey: [...K, 'surveys', 'all'], queryFn: () => people.list('surveys') });
  const [create, setCreate] = useState(false);
  const [results, setResults] = useState<any>(null);
  const r = useQuery({ queryKey: [...K, 'surveys', 'results', results?.id], queryFn: () => people.fetch(`surveys/${results.id}/results`), enabled: !!results });
  const setStatus = useMutation({ mutationFn: ({ id, status }: { id: string; status: string }) => people.update('surveys', id, { status }),
    onSuccess: () => void qc.invalidateQueries({ queryKey: [...K, 'surveys'] }) });
  return (
    <Card flush title="Surveys" actions={<Button size="sm" onClick={() => setCreate(true)}><Icon name="plus" size={15} />New pulse survey</Button>}>
      {q.isPending ? <LoadingRows /> : q.error ? <QueryError error={q.error} /> : <DataTable rows={q.data.results} empty="No surveys" columns={[
        { key: 't', label: 'Survey', render: (s: any) => <><strong>{s.title}</strong><div className="xs muted">{s.questions.length} questions · {s.anonymous ? `anonymous, min group ${s.minGroup}` : 'named'}</div></> },
        { key: 'd', label: 'Open', render: (s: any) => `${fmtDate(s.opensOn)} – ${fmtDate(s.closesOn)}` }, { key: 'r', label: 'Responses', num: true, render: (s: any) => s.responses },
        { key: 's', label: 'Status', render: (s: any) => <Status value={s.status} /> },
        { key: 'a', label: '', render: (s: any) => <span className="row" style={{ gap: 4 }}>
          {s.status === 'draft' && <Button size="sm" variant="ghost" onClick={() => setStatus.mutate({ id: s.id, status: 'open' })}>Open</Button>}
          {s.status === 'open' && <Button size="sm" variant="ghost" onClick={() => setStatus.mutate({ id: s.id, status: 'closed' })}>Close</Button>}
          <Button size="sm" variant="ghost" onClick={() => setResults(s)}>Results</Button></span> }]} />}
      {create && <FormDialog title="New pulse survey" onClose={() => setCreate(false)} initial={{ anonymous: true, min_group: 5 }}
        intro={<p className="small muted">Uses a standard 3-question pulse (1–5 scales and a comment). Results are hidden until the minimum group size answers.</p>}
        fields={[{ name: 'title', label: 'Title', required: true }, { name: 'description', label: 'Description', type: 'textarea' },
          { name: 'opens_on', label: 'Opens', type: 'date', required: true, half: true }, { name: 'closes_on', label: 'Closes', type: 'date', half: true },
          { name: 'min_group', label: 'Minimum group size', type: 'number', min: 3, half: true }, { name: 'anonymous', label: 'Anonymous', type: 'checkbox' }]}
        onSubmit={(v) => people.create('surveys', { ...v, status: 'draft', questions: [
          { id: 'q1', type: 'scale', text: 'I would recommend Click as a place to work.' }, { id: 'q2', type: 'scale', text: 'I have what I need to do my job well.' },
          { id: 'q3', type: 'text', text: 'What one thing should we change?' }] })}
        onDone={() => { toast('Survey created as a draft'); void qc.invalidateQueries({ queryKey: [...K, 'surveys'] }); }} />}
      {results && <Dialog title={`Results · ${results.title}`} onClose={() => setResults(null)} wide>
        {r.isPending ? <LoadingRows /> : r.error ? <QueryError error={r.error} /> : r.data.suppressed ? <Alert tone="info">{r.data.message} ({r.data.responses} so far)</Alert> : (
          <div className="stack">
            <p className="small">{r.data.responses} responses</p>
            {r.data.questions.map((qn: any) => <div key={qn.id}><strong className="small">{qn.text}</strong>
              {qn.type === 'scale' && <p className="small">Average {qn.average ?? '—'} / 5 ({qn.answers} answers)</p>}
              {qn.type === 'choice' && <Bars rows={Object.entries(qn.counts).map(([k, v]) => ({ label: k, value: Number(v) }))} />}
              {qn.type === 'text' && <ul className="small">{qn.answers.slice(0, 30).map((a: string, i: number) => <li key={i}>{a}</li>)}</ul>}</div>)}
            <div><strong className="small">By department</strong><Bars rows={r.data.byDepartment} /></div>
          </div>)}
      </Dialog>}
    </Card>
  );
}


