/* eslint-disable @typescript-eslint/no-explicit-any */
import { useState } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Button, Icon, useToast } from '@click/ui';
import { apiMessage, people } from '../../lib/api';
import { fmtDate, fmtDateTime } from '../../lib/format';
import { useAccess } from '../../session/access';
import { DataTable, FormDialog, StatGrid } from '../../components/forms';
import { Alert, Card, Empty, LoadingRows, QueryError, Status, Tabs } from '../../components/ui';
import { LeaveSummary } from './core';
import { SectionTitle } from './common';

const K = ['os', 'people'];
const hm = (min: number | null) => (min == null ? '—' : `${Math.floor(min / 60)}h ${min % 60}m`);
const time = (iso: string | null) => (iso ? new Date(iso).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }) : '—');

// =================================================================================================================
// Attendance
// =================================================================================================================
export function Attendance() {
  const access = useAccess();
  const [params, setParams] = useSearchParams();
  const canTeam = access.can('people.attendance.view');
  const tab = (params.get('tab') ?? 'me') as 'me' | 'team' | 'exceptions';
  return (
    <>
      <SectionTitle title="Attendance" desc="Check in and out, see your month and request corrections. Corrections go to your manager for approval." />
      {canTeam && <Tabs value={tab} onChange={(t) => setParams({ tab: t })} items={[{ value: 'me', label: 'Mine' }, { value: 'team', label: 'Team today' }, { value: 'exceptions', label: 'Exceptions' }]} />}
      {tab === 'me' ? <MyAttendance /> : <TeamAttendance exceptions={tab === 'exceptions'} />}
    </>
  );
}

function MyAttendance() {
  const qc = useQueryClient();
  const toast = useToast();
  const now = new Date();
  const [ym, setYm] = useState({ y: now.getFullYear(), m: now.getMonth() + 1 });
  const [mode, setMode] = useState('office');
  const [fix, setFix] = useState<string | null>(null);
  const q = useQuery({ queryKey: [...K, 'attendance', 'me', ym], queryFn: () => people.fetch('attendance/me', { year: ym.y, month: ym.m }) });
  const check = useMutation({ mutationFn: (a: 'in' | 'out') => people.action(`attendance/check-${a}`, a === 'in' ? { mode } : {}),
    onSuccess: (_r, a) => { toast(a === 'in' ? 'Checked in' : 'Checked out'); void qc.invalidateQueries({ queryKey: [...K, 'attendance'] }); void qc.invalidateQueries({ queryKey: [...K, 'me'] }); },
    onError: (e) => toast(apiMessage(e), 'error') });
  if (q.isPending) return <Card><LoadingRows /></Card>;
  if (q.error) return <QueryError error={q.error} />;
  const d = q.data;
  const t = d.today;
  const recs: any[] = d.records;
  const shift = (n: number) => setYm(({ y, m }) => { const x = new Date(y, m - 1 + n, 1); return { y: x.getFullYear(), m: x.getMonth() + 1 }; });
  return (
    <div className="stack stack--lg">
      <Card title="Today" actions={<span className="xs muted">{d.schedule}</span>}>
        <div className="row row--wrap" style={{ gap: 12 }}>
          <div className="grow">
            <div className="small">{t?.checkIn ? `In at ${time(t.checkIn)}` : 'Not checked in'}{t?.checkOut ? ` · out at ${time(t.checkOut)} · ${hm(t.workedMinutes)}` : ''}</div>
            {t?.late && <span className="flag flag--due_soon">late</span>}
          </div>
          {d.canCheckIn && !t?.checkIn && <>
            <select className="field__input" aria-label="Work mode" value={mode} onChange={(e) => setMode(e.target.value)}><option value="office">Office</option><option value="remote">Remote</option><option value="field">Field</option></select>
            <Button loading={check.isPending} onClick={() => check.mutate('in')}>Check in</Button></>}
          {d.canCheckIn && t?.checkIn && !t?.checkOut && <Button loading={check.isPending} onClick={() => check.mutate('out')}>Check out</Button>}
          <Button variant="outline" onClick={() => setFix(new Date().toISOString().slice(0, 10))}>Request correction</Button>
        </div>
      </Card>
      <StatGrid items={[{ key: 'p', label: 'Present', value: recs.filter((r) => r.status === 'present').length }, { key: 'l', label: 'Late', value: recs.filter((r) => r.late).length },
        { key: 'r', label: 'Remote', value: recs.filter((r) => r.mode === 'remote').length }, { key: 'h', label: 'Holidays', value: d.holidays.length },
        { key: 'mc', label: 'Missing check-out', value: recs.filter((r) => r.checkIn && !r.checkOut && r.date !== new Date().toISOString().slice(0, 10)).length }]} />
      <Card title={new Date(ym.y, ym.m - 1, 1).toLocaleDateString(undefined, { month: 'long', year: 'numeric' })} flush actions={<span className="row">
        <Button size="sm" variant="ghost" onClick={() => shift(-1)} aria-label="Previous month">‹</Button><Button size="sm" variant="ghost" onClick={() => shift(1)} aria-label="Next month">›</Button></span>}>
        <DataTable rows={recs.map((r) => ({ ...r, id: r.date }))} empty="No attendance this month" columns={[
          { key: 'd', label: 'Date', render: (r: any) => fmtDate(r.date) }, { key: 'i', label: 'In', render: (r: any) => time(r.checkIn) }, { key: 'o', label: 'Out', render: (r: any) => time(r.checkOut) },
          { key: 'w', label: 'Worked', render: (r: any) => hm(r.workedMinutes) },
          { key: 'f', label: 'Flags', render: (r: any) => <span className="row" style={{ gap: 4 }}>{r.late && <span className="flag flag--due_soon">late</span>}{r.early && <span className="flag">early</span>}<span className="xs muted">{r.mode} · {r.source}</span></span> },
          { key: 'a', label: '', render: (r: any) => <Button size="sm" variant="ghost" onClick={() => setFix(r.date)}>Correct</Button> }]} />
      </Card>
      {d.holidays.length > 0 && <Card title="Holidays this month"><ul className="list">{d.holidays.map((h: any) => <li key={h.date} className="list-row small"><span className="grow">{h.name}</span><span className="muted">{fmtDate(h.date)}</span></li>)}</ul></Card>}
      <Card title="Correction requests" flush><DataTable rows={d.corrections} empty="No correction requests" columns={[{ key: 'd', label: 'Date', render: (c: any) => fmtDate(c.date) },
        { key: 'r', label: 'Reason', render: (c: any) => <span className="small">{c.reason}</span> }, { key: 's', label: 'Status', render: (c: any) => <Status value={c.status} /> },
        { key: 'a', label: '', render: (c: any) => c.approvalId && <Link to={`/approvals/${c.approvalId}`} className="small">Approval</Link> }]} /></Card>
      {fix && <FormDialog title="Attendance correction" onClose={() => setFix(null)} submitLabel="Send for approval" initial={{ date: fix }}
        fields={[{ name: 'date', label: 'Date', type: 'date', required: true }, { name: 'check_in', label: 'Correct check-in', type: 'time', half: true },
          { name: 'check_out', label: 'Correct check-out', type: 'time', half: true }, { name: 'reason', label: 'Reason', type: 'textarea', required: true }]}
        onSubmit={(v) => people.action('attendance/corrections', v)} onDone={() => { toast('Sent to your manager'); void qc.invalidateQueries({ queryKey: [...K, 'attendance'] }); }} />}
    </div>
  );
}

function TeamAttendance({ exceptions }: { exceptions: boolean }) {
  const [day, setDay] = useState(new Date().toISOString().slice(0, 10));
  const q = useQuery({ queryKey: [...K, 'attendance', 'team', day], queryFn: () => people.fetch('attendance/team', { date: day }) });
  return (
    <Card flush>
      <div className="toolbar"><label className="row small">Date <input type="date" className="field__input" value={day} onChange={(e) => setDay(e.target.value)} /></label>
        {q.data && <span className="small muted" style={{ marginLeft: 'auto' }}>{q.data.results.filter((r: any) => r.record?.checkIn).length} checked in · {q.data.results.filter((r: any) => r.onLeave).length} on leave · {q.data.exceptions.length} exceptions</span>}</div>
      {q.isPending ? <LoadingRows /> : q.error ? <QueryError error={q.error} /> : exceptions ? (
        <DataTable rows={q.data.exceptions.map((x: any, i: number) => ({ ...x, id: String(i) }))} empty="No exceptions" columns={[
          { key: 'e', label: 'Employee', render: (x: any) => <Link to={`/people/${x.employeeId}?tab=attendance`}>{x.employee}</Link> },
          { key: 'k', label: 'Exception', render: (x: any) => <span className="flag flag--due_soon">{x.label}</span> }]} />
      ) : (
        <DataTable rows={q.data.results.map((r: any) => ({ ...r, id: r.employee.id }))} empty="No one in your scope" columns={[
          { key: 'e', label: 'Employee', render: (r: any) => <Link to={`/people/${r.employee.id}?tab=attendance`}>{r.employee.name}</Link> },
          { key: 'i', label: 'In', render: (r: any) => time(r.record?.checkIn ?? null) }, { key: 'o', label: 'Out', render: (r: any) => time(r.record?.checkOut ?? null) },
          { key: 's', label: 'Status', render: (r: any) => (r.onLeave ? <Status value="on_leave" label="On leave" /> : r.record ? <span className="row" style={{ gap: 4 }}><Status value="active" label={r.record.mode} />{r.record.late && <span className="flag flag--due_soon">late</span>}</span> : <span className="xs muted">No record</span>) }]} />
      )}
    </Card>
  );
}

// =================================================================================================================
// Leave & holidays
// =================================================================================================================
export function Leave() {
  const access = useAccess();
  const [params, setParams] = useSearchParams();
  const canTeam = access.can('people.leave.view');
  const tab = (params.get('tab') ?? 'me') as 'me' | 'team' | 'holidays';
  return (
    <>
      <SectionTitle title="Leave & holidays" desc="Balances, requests and the holiday calendar. Requests go through your manager (and HR for longer leave)."
        actions={<Button onClick={() => setParams((p) => { p.set('new', '1'); return p; })}><Icon name="plus" size={16} />Request leave</Button>} />
      <Tabs value={tab} onChange={(t) => setParams({ tab: t })} items={[{ value: 'me', label: 'Mine' }, ...(canTeam ? [{ value: 'team' as const, label: 'Team calendar' }] : []), { value: 'holidays', label: 'Holidays' }]} />
      {tab === 'team' ? <TeamLeave /> : <MyLeave holidays={tab === 'holidays'} />}
      {params.get('new') === '1' && <LeaveDialog onClose={() => setParams((p) => { p.delete('new'); return p; })} />}
    </>
  );
}

function MyLeave({ holidays }: { holidays: boolean }) {
  const qc = useQueryClient();
  const toast = useToast();
  const q = useQuery({ queryKey: [...K, 'leave', 'me'], queryFn: () => people.fetch('leave/me') });
  const cancel = useMutation({ mutationFn: (id: string) => people.action(`leave/requests/${id}/cancel`), onSuccess: () => { toast('Leave cancelled'); void qc.invalidateQueries({ queryKey: [...K, 'leave'] }); },
    onError: (e) => toast(apiMessage(e), 'error') });
  if (q.isPending) return <Card><LoadingRows /></Card>;
  if (q.error) return <QueryError error={q.error} />;
  if (holidays) return (
    <Card flush><DataTable rows={q.data.holidays.map((h: any) => ({ ...h, id: h.date + h.name }))} empty="No holidays published" columns={[
      { key: 'd', label: 'Date', render: (h: any) => fmtDate(h.date) }, { key: 'n', label: 'Holiday', render: (h: any) => <>{h.name}{h.optional && <span className="xs muted"> · optional</span>}</> },
      { key: 'c', label: 'Calendar', render: (h: any) => <span className="small muted">{h.calendar}</span> }]} /></Card>
  );
  const withCancel = { ...q.data, requests: q.data.requests };
  return (
    <div className="stack stack--lg">
      <LeaveSummary d={withCancel} />
      {q.data.requests.some((r: any) => ['pending', 'approved'].includes(r.status) && r.startDate >= new Date().toISOString().slice(0, 10)) && (
        <Card title="Upcoming — cancel if plans change" flush><ul className="list">
          {q.data.requests.filter((r: any) => ['pending', 'approved'].includes(r.status) && r.startDate >= new Date().toISOString().slice(0, 10)).map((r: any) => (
            <li key={r.id} className="list-row"><span className="grow small">{r.leaveType.name} · {fmtDate(r.startDate)} – {fmtDate(r.endDate)} · {Number(r.days)} day(s)</span>
              <Status value={r.status} /><Button size="sm" variant="ghost" onClick={() => cancel.mutate(r.id)}>Cancel</Button></li>))}
        </ul></Card>)}
    </div>
  );
}

function LeaveDialog({ onClose }: { onClose: () => void }) {
  const qc = useQueryClient();
  const toast = useToast();
  const types = useQuery({ queryKey: [...K, 'leave', 'types'], queryFn: () => people.fetch('leave/types') });
  return (
    <FormDialog title="Request leave" onClose={onClose} submitLabel="Send for approval"
      intro={<Alert tone="info">Weekends and holidays on your calendar aren’t counted. The approval shows the exact working days.</Alert>}
      fields={[{ name: 'leave_type_id', label: 'Leave type', type: 'select', required: true, options: (types.data?.results ?? []).map((x: any) => ({ value: x.id, label: `${x.name}${x.paid ? '' : ' (unpaid)'}` })) },
        { name: 'start_date', label: 'From', type: 'date', required: true, half: true }, { name: 'end_date', label: 'To', type: 'date', half: true },
        { name: 'half_day', label: 'Half day (single-day leave)', type: 'select', half: true, options: [{ value: 'first', label: 'First half' }, { value: 'second', label: 'Second half' }] },
        { name: 'reason', label: 'Reason', type: 'textarea' }]}
      onSubmit={(x) => people.action('leave/requests', x)}
      onDone={() => { toast('Leave request sent'); void qc.invalidateQueries({ queryKey: [...K, 'leave'] }); void qc.invalidateQueries({ queryKey: [...K, 'me'] }); }} />
  );
}

function TeamLeave() {
  const q = useQuery({ queryKey: [...K, 'leave', 'team'], queryFn: () => people.fetch('leave/team') });
  if (q.isPending) return <Card><LoadingRows /></Card>;
  if (q.error) return <QueryError error={q.error} />;
  return (
    <div className="stack stack--lg">
      <StatGrid items={[{ key: 'a', label: 'Away today', value: q.data.awayToday }, { key: 'p', label: 'Pending requests', value: q.data.results.filter((r: any) => r.status === 'pending').length, to: '/approvals' }]} />
      <Card title={`${fmtDate(q.data.from)} – ${fmtDate(q.data.to)}`} flush>
        {!q.data.results.length ? <Empty title="No leave in this period" /> : <DataTable rows={q.data.results} columns={[
          { key: 'e', label: 'Employee', render: (r: any) => <Link to={`/people/${r.employee.id}?tab=leave`}>{r.employee.name}</Link> },
          { key: 't', label: 'Type', render: (r: any) => <span className="row" style={{ gap: 6 }}><span className="dot" style={{ background: r.leaveType.color }} />{r.leaveType.name}</span> },
          { key: 'd', label: 'Dates', render: (r: any) => `${fmtDate(r.startDate)} – ${fmtDate(r.endDate)}` }, { key: 'n', label: 'Days', num: true, render: (r: any) => Number(r.days) },
          { key: 's', label: 'Status', render: (r: any) => <Status value={r.status} /> },
          { key: 'a', label: '', render: (r: any) => r.approvalId && r.status === 'pending' && <Link to={`/approvals/${r.approvalId}`} className="small">Review</Link> }]} />}
      </Card>
      <p className="xs muted">Leave reasons and medical details are visible only to the approvers and HR — the calendar shows dates and type only. Updated {fmtDateTime(new Date().toISOString())}.</p>
    </div>
  );
}
