/* eslint-disable @typescript-eslint/no-explicit-any */
/** Procurement — suppliers, contracts, recurring purchases, exceptions, conflicts, policies, analytics, settings. */
import { useState } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import { Button, Icon } from '@click/ui';
import { procurement } from '../../lib/api';
import { fmtDate, fmtDateTime, humanize } from '../../lib/format';
import { DataTable, FormDialog } from '../../components/forms';
import { DownloadButton, Kpis, money, useAction } from '../../components/ModuleShell';
import { Alert, Card, Dialog, Pager, Status, Tabs } from '../../components/ui';
import { Load, PK, PT, today, tone, useP } from './index';

const TYPES = ['manufacturer', 'distributor', 'wholesaler', 'retailer', 'service_provider', 'consultant', 'technology', 'contractor', 'logistics', 'professional', 'local',
  'international', 'other'];

export function Suppliers() {
  const [params, setParams] = useSearchParams();
  const [tab, setTab] = useState<'directory' | 'performance'>('directory');
  const [f, setF] = useState({ q: '', status: '', preference: '', page: 1 });
  const q = useP('suppliers', { q: f.q || undefined, status: f.status || undefined, preference: f.preference || undefined, issues: params.get('issues') || undefined, page: f.page }, tab === 'directory');
  const perf = useP('suppliers/performance', {}, tab === 'performance');
  const open = params.get('open');
  const lk = useP('lookups', {}, params.get('new') === '1');
  const [dup, setDup] = useState<any[] | null>(null);
  return <>{PT('Suppliers', 'One supplier master: onboarding, verification, risk, performance and restrictions. Partners are not suppliers unless the relationship says so.',
    <><DownloadButton api={procurement} path="suppliers" filename="suppliers.csv" /><Button onClick={() => setParams({ new: '1' })}><Icon name="plus" size={16} />Register supplier</Button></>)}
    <Tabs value={tab} onChange={setTab} items={[{ value: 'directory', label: 'Directory' }, { value: 'performance', label: 'Performance scorecards' }]} />
    {tab === 'directory' ? <Card flush>
      <div className="toolbar"><div className="search-input"><Icon name="search" size={16} /><input value={f.q} onChange={(e) => setF({ ...f, q: e.target.value, page: 1 })} placeholder="Name or SUP- code" aria-label="Search suppliers" /></div>
        <select className="field__input" aria-label="Status" value={f.status} onChange={(e) => setF({ ...f, status: e.target.value, page: 1 })}><option value="">All statuses</option>
          {['registered', 'under_review', 'active', 'inactive', 'rejected'].map((s) => <option key={s} value={s}>{humanize(s)}</option>)}</select>
        <select className="field__input" aria-label="Preference" value={f.preference} onChange={(e) => setF({ ...f, preference: e.target.value, page: 1 })}><option value="">Any preference</option>
          {['preferred', 'approved', 'conditional', 'restricted', 'blocked'].map((s) => <option key={s} value={s}>{humanize(s)}</option>)}</select></div>
      <Load q={q}>{() => <><DataTable rows={q.data.results} onRow={(s: any) => setParams({ open: s.id })} empty="No suppliers" columns={[
        { key: 'n', label: 'Supplier', render: (s: any) => <><strong>{s.name}</strong><div className="xs muted mono">{s.code} · {s.typeLabel}{s.city ? ` · ${s.city}` : ''}</div></> },
        { key: 'c', label: 'Categories', render: (s: any) => <span className="xs">{s.categories.join(', ') || '—'}</span> },
        { key: 'st', label: 'Status', render: (s: any) => <Status value={tone(s.status)} label={s.statusLabel} /> },
        { key: 'p', label: 'Preference', render: (s: any) => <Status value={tone(s.preference)} label={humanize(s.preference)} /> },
        { key: 'r', label: 'Risk', render: (s: any) => <span className={`sev sev--${s.riskLevel === 'high' ? 'high' : s.riskLevel === 'medium' ? 'medium' : 'low'}`} title={s.riskLevel} /> },
        { key: 'b', label: 'Bank', render: (s: any) => <span className="xs mono">{s.bank}{s.bankVerified ? ' ✓' : ''}</span> }]} />
        <Pager page={q.data.page} hasNext={q.data.hasNext} count={q.data.count} onPage={(p) => setF({ ...f, page: p })} /></>}</Load></Card>
      : <Load q={perf}>{() => <Card flush><DataTable rows={perf.data.results} empty="No active suppliers" columns={[
        { key: 'n', label: 'Supplier', render: (s: any) => <Link to={`/procurement/suppliers?open=${s.id}`}>{s.name}</Link> }, { key: 'o', label: 'Overall', num: true, render: (s: any) => (s.overall ?? '—') },
        { key: 'd', label: 'On time', num: true, render: (s: any) => (s.onTimePct != null ? `${s.onTimePct}%` : '—') }, { key: 'q', label: 'Rejected', num: true, render: (s: any) => (s.rejectionPct != null ? `${s.rejectionPct}%` : '—') },
        { key: 'i', label: 'Invoice match', num: true, render: (s: any) => (s.invoiceMatchPct != null ? `${s.invoiceMatchPct}%` : '—') },
        { key: 'r', label: 'RFQ response', num: true, render: (s: any) => (s.responseRatePct != null ? `${s.responseRatePct}%` : '—') },
        { key: 'sp', label: 'Spend', num: true, render: (s: any) => money(s.spend) }]} /><p className="xs muted" style={{ padding: 12 }}>Scores come from measured data only; blank = not enough data yet.</p></Card>}</Load>}
    {open && <SupplierDrawer id={open} onClose={() => setParams({})} />}
    {params.get('new') === '1' && <FormDialog title="Register supplier" wide onClose={() => { setParams({}); setDup(null); }} submitLabel="Register"
      intro={<>{dup && <Alert tone="warning">Possible duplicates: {dup.map((x) => `${x.name} (${x.code}: ${x.why.join(', ')})`).join('; ')}. Tick the box below if this really is a different business.</Alert>}
        <p className="small muted">New suppliers start as registered/conditional. Verification and an approved onboarding make them active. Bank details are added through an approved change.</p></>}
      initial={{ supplier_type: 'other', relationship: 'procurement_supplier', payment_terms_days: 30 }}
      fields={[{ name: 'legal_name', label: 'Legal name', required: true }, { name: 'trading_name', label: 'Trading name', half: true },
        { name: 'supplier_type', label: 'Type', type: 'select', half: true, options: TYPES.map((t) => ({ value: t, label: humanize(t) })) },
        { name: 'tax_id', label: 'GSTIN', half: true }, { name: 'pan', label: 'PAN', half: true }, { name: 'registration_number', label: 'Registration (CIN/Udyam)', half: true },
        { name: 'payment_terms_days', label: 'Payment terms (days)', type: 'number', half: true }, { name: 'contact_name', label: 'Contact', half: true }, { name: 'email', label: 'Email', type: 'email', half: true },
        { name: 'phone', label: 'Phone', half: true }, { name: 'city', label: 'City', half: true }, { name: 'address', label: 'Address' },
        { name: 'relationship', label: 'Relationship with Click', type: 'select', options: [{ value: 'procurement_supplier', label: 'Sells to Click (supplier)' }, { value: 'both', label: 'Also a Click marketplace partner' }, { value: 'other', label: 'Other' }] },
        { name: 'category_ids', label: 'Categories', type: 'multiselect', options: (lk.data?.categories ?? []).filter((c: any) => !c.parent).map((c: any) => ({ value: c.id, label: c.name })) },
        { name: 'confirm_not_duplicate', label: 'I checked the possible duplicates — this is a different business', type: 'checkbox' }]}
      onSubmit={async (v) => { try { return await procurement.post('suppliers', v); } catch (e: any) { if (e.code === 'possible_duplicate') setDup(e.details?.duplicates ?? []); throw e; } }}
      onDone={(r: any) => setParams({ open: r.id })} />}</>;
}

function SupplierDrawer({ id, onClose }: { id: string; onClose: () => void }) {
  const q = useP(`suppliers/${id}`);
  const act = useAction((b: any) => procurement.post(`suppliers/${id}/${b.action}`, b), [PK], 'Saved');
  const [dlg, setDlg] = useState('');
  const d = q.data;
  return <Dialog title={d ? `${d.name} · ${d.code}` : 'Supplier'} wide onClose={onClose}><Load q={q}>{() => <div className="stack">
    <div className="row row--wrap"><Status value={tone(d.status)} label={d.statusLabel} /><Status value={tone(d.preference)} label={humanize(d.preference)} />
      <span className={`sev sev--${d.riskLevel === 'high' ? 'high' : d.riskLevel === 'medium' ? 'medium' : 'low'}`} /> <span className="small">risk {d.riskLevel}</span>
      <span className="small muted">{d.typeLabel} · {humanize(d.relationship)}{d.partner ? ` · partner ${d.partner}` : ''}</span></div>
    {d.restrictionReason && <Alert tone="warning">{humanize(d.preference)}: {d.restrictionReason}</Alert>}
    {d.duplicates.length > 0 && <Alert tone="warning">Possible duplicates (review, never merged automatically): {d.duplicates.map((x: any) => `${x.name} — ${x.why.join(', ')}`).join('; ')}</Alert>}
    <div className="grid grid--2">
      <Card title="Profile"><dl className="kv"><dt>Legal name</dt><dd>{d.legalName}</dd><dt>GSTIN / PAN</dt><dd className="mono">{d.taxId || '—'} / {d.pan || '—'}</dd>
        <dt>Registration</dt><dd>{d.registrationNumber || '—'}</dd><dt>Contact</dt><dd>{d.contactName} {d.email} {d.phone}</dd><dt>Address</dt><dd>{d.address} {d.city}</dd>
        <dt>Bank</dt><dd className="mono">{d.bank}{d.bankVerified ? ' (verified)' : ''}</dd><dt>Payment terms</dt><dd>{d.paymentTermsDays} days</dd>
        <dt>Categories</dt><dd>{d.categories.join(', ') || '—'}</dd></dl></Card>
      <Card title={`Scorecard${d.scorecard.overall != null ? ` — ${d.scorecard.overall}/100` : ''}`}><dl className="kv">
        {Object.entries(d.scorecard.scores).map(([k, v]: any) => <div key={k} style={{ display: 'contents' }}><dt>{humanize(k)}</dt><dd>{v ?? '—'}</dd></div>)}
        <dt>Orders / spend</dt><dd>{d.scorecard.orders} · {money(d.scorecard.spend)}</dd><dt>Disputes</dt><dd>{d.scorecard.disputes}</dd></dl>
        <p className="xs muted">{d.scorecard.basis}</p></Card>
    </div>
    <Card title="Verification" flush><DataTable rows={d.checks.map((c: string) => ({ id: c, c, v: d.verification[c] }))} columns={[
      { key: 'c', label: 'Check', render: (r: any) => <>{humanize(r.c)}{d.requiredChecks.includes(r.c) && <span className="xs muted"> · required</span>}</> },
      { key: 's', label: 'Status', render: (r: any) => (r.v ? <Status value={r.v.status === 'verified' ? 'approved' : r.v.status === 'failed' ? 'rejected' : 'neutral'} label={humanize(r.v.status)} /> : <span className="xs muted">Not checked</span>) },
      { key: 'b', label: 'By', render: (r: any) => <span className="xs">{r.v ? `${r.v.by} · ${fmtDate(r.v.at)}` : ''}</span> },
      { key: 'a', label: '', render: (r: any) => <span className="row" style={{ gap: 4 }}><Button size="sm" variant="ghost" onClick={() => act.mutate({ action: 'verify', check: r.c, status: 'verified' })}>Verified</Button>
        <Button size="sm" variant="ghost" onClick={() => act.mutate({ action: 'verify', check: r.c, status: 'failed' })}>Failed</Button></span> }]} /></Card>
    {Object.keys(d.riskFactors).length > 0 && <Card title="Risk factors (flags for review)"><ul className="small">{Object.entries(d.riskFactors).map(([k, v]: any) => <li key={k}><strong>{humanize(k)}</strong> {v.level}: {v.note} <span className="xs muted">({v.by})</span></li>)}</ul></Card>}
    <div className="row row--wrap">
      {['registered', 'rejected', 'invited'].includes(d.status) && <Button onClick={() => act.mutate({ action: 'submit' })}>Submit onboarding for approval</Button>}
      <Button variant="outline" onClick={() => setDlg('preference')}>Preference / restriction</Button>
      <Button variant="outline" onClick={() => setDlg('risk')}>Record risk</Button>
      <Button variant="outline" onClick={() => setDlg('bank')}>Change bank details</Button>
      <Link to={`/procurement/requests`} className="btn btn--ghost" style={{ textDecoration: 'none' }}>Purchase history ({d.orders.length})</Link>
    </div>
    {d.bankChanges.length > 0 && <Card title="Bank detail changes" flush><DataTable rows={d.bankChanges} columns={[{ key: 'a', label: 'Account', render: (b: any) => <span className="mono">••••{b.last4} {b.ifsc}</span> },
      { key: 'r', label: 'Reason', render: (b: any) => <span className="small">{b.reason}</span> }, { key: 'b', label: 'Requested', render: (b: any) => <span className="xs">{b.by} · {fmtDateTime(b.at)}</span> },
      { key: 's', label: 'Status', render: (b: any) => <Status value={tone(b.status)} label={humanize(b.status)} /> }]} /></Card>}
    {d.history.length > 0 && <Card title="History"><ul className="timeline">{d.history.map((h: any, i: number) => <li key={i}>{humanize(h.field)} {h.from} → <strong>{h.to}</strong> {h.reason && `(${humanize(h.reason)})`} · {h.by} {fmtDate(h.at)}<div className="xs">{h.note}</div></li>)}</ul></Card>}
    {dlg === 'preference' && <FormDialog title="Supplier preference" onClose={() => setDlg('')} initial={{ preference: d.preference }}
      intro={<p className="small muted">Restricting or blocking is permission-controlled and audited. It never labels anyone fraudulent — use “fraud investigation” only for an open investigation.</p>}
      fields={[{ name: 'preference', label: 'Preference', type: 'select', options: ['preferred', 'approved', 'conditional', 'restricted', 'blocked'].map((x) => ({ value: x, label: humanize(x) })) },
        { name: 'reason_category', label: 'Reason', type: 'select', options: ['compliance', 'quality', 'contract', 'fraud_investigation', 'legal', 'performance', 'other_approved'].map((x) => ({ value: x, label: humanize(x) })) },
        { name: 'note', label: 'Note', type: 'textarea' }]} onSubmit={(v) => procurement.post(`suppliers/${id}/preference`, v)} onDone={() => void q.refetch()} />}
    {dlg === 'risk' && <FormDialog title="Record a risk factor" onClose={() => setDlg('')} initial={{ level: 'medium' }}
      fields={[{ name: 'factor', label: 'Factor', type: 'select', required: true, options: ['financial', 'compliance', 'delivery', 'quality', 'cybersecurity', 'concentration', 'single_source', 'geographic', 'contract', 'reputational'].map((x) => ({ value: x, label: humanize(x) })) },
        { name: 'level', label: 'Level', type: 'select', options: ['low', 'medium', 'high'].map((x) => ({ value: x, label: humanize(x) })) }, { name: 'note', label: 'Evidence', type: 'textarea' }]}
      onSubmit={(v) => procurement.post(`suppliers/${id}/risk`, v)} onDone={() => void q.refetch()} />}
    {dlg === 'bank' && <FormDialog title="Request a bank details change" onClose={() => setDlg('')} submitLabel="Send for approval"
      intro={<Alert tone="warning">A classic fraud route. Verify independently (call back on a number you already had, cancelled cheque). Someone else approves; Finance is alerted.</Alert>}
      fields={[{ name: 'account_number', label: 'Account number', required: true, half: true }, { name: 'ifsc', label: 'IFSC', required: true, half: true },
        { name: 'reason', label: 'Why it changed', required: true }, { name: 'evidence', label: 'How you verified it', required: true }]}
      onSubmit={(v) => procurement.post(`suppliers/${id}/bank-change`, v)} onDone={() => void q.refetch()} />}
  </div>}</Load></Dialog>;
}

// ---------------------------------------------------------------------------------------------------------------------
export function Contracts() {
  const q = useP('contracts');
  const lk = useP('lookups');
  const [add, setAdd] = useState(false);
  const [decide, setDecide] = useState<any>(null);
  const act = useAction((b: any) => procurement.post(`contracts/${b.id}/${b.action}`, b), [PK], 'Saved');
  return <>{PT('Contracts & renewals', 'Supplier agreements, obligations and renewal decisions (90 / 60 / 30-day alerts). Documents live in the central store.',
    <Button onClick={() => setAdd(true)}><Icon name="plus" size={16} />New contract</Button>)}
    <Load q={q}>{() => <Card flush><DataTable rows={q.data.results} empty="No contracts" columns={[
      { key: 'n', label: 'Contract', render: (c: any) => <><strong>{c.title}</strong><div className="xs muted mono">{c.number} · {c.supplier} · {humanize(c.type)}</div></> },
      { key: 'v', label: 'Value', num: true, render: (c: any) => <>{money(c.value)}<div className="xs muted">ordered {money(c.ordersValue)}</div></> },
      { key: 'e', label: 'Ends', render: (c: any) => <span style={{ color: c.daysLeft <= 30 ? 'var(--c-danger)' : c.daysLeft <= 90 ? 'var(--c-warning)' : undefined }}>{fmtDate(c.end)} ({c.daysLeft} days)</span> },
      { key: 'o', label: 'Obligations', render: (c: any) => <span className="xs">{c.obligations.filter((o: any) => o.status === 'open').map((o: any) => `${o.title} ${fmtDate(o.due)}`).join(' · ') || '—'}</span> },
      { key: 'd', label: 'Renewal', render: (c: any) => (c.decision ? <span title={c.decisionNote}>{humanize(c.decision)}</span> : <Button size="sm" variant="outline" onClick={() => setDecide(c)}>Decide</Button>) },
      { key: 's', label: 'Status', render: (c: any) => <Status value={tone(c.status)} label={humanize(c.status)} /> },
      { key: 'x', label: '', render: (c: any) => c.obligations.some((o: any) => o.status === 'open') && <Button size="sm" variant="ghost" onClick={() => act.mutate({ id: c.id, action: 'obligation-done', obligationId: c.obligations.find((o: any) => o.status === 'open').id })}>Mark next done</Button> }]} /></Card>}</Load>
    {add && <FormDialog title="New contract" wide onClose={() => setAdd(false)} initial={{ contract_type: 'supply', notice_period_days: 30, start_date: today() }}
      fields={[{ name: 'supplier_id', label: 'Supplier', type: 'select', required: true, options: (lk.data?.suppliers ?? []).map((s: any) => ({ value: s.id, label: s.name })) },
        { name: 'title', label: 'Title', required: true }, { name: 'contract_type', label: 'Type', type: 'select', half: true, options: ['framework', 'service', 'supply', 'license', 'lease', 'maintenance', 'other'].map((x) => ({ value: x, label: humanize(x) })) },
        { name: 'value', label: 'Value', type: 'number', half: true }, { name: 'start_date', label: 'Start', type: 'date', required: true, half: true }, { name: 'end_date', label: 'End', type: 'date', required: true, half: true },
        { name: 'notice_period_days', label: 'Notice period (days)', type: 'number', half: true }, { name: 'insurance_expiry', label: 'Supplier insurance expires', type: 'date', half: true },
        { name: 'auto_renew', label: 'Renews automatically', type: 'checkbox' }, { name: 'scope', label: 'Scope & deliverables', type: 'textarea' }, { name: 'slas', label: 'SLAs', type: 'textarea' },
        { name: 'pricing_terms', label: 'Pricing', type: 'textarea' }, { name: 'penalties', label: 'Penalties', type: 'textarea' }]}
      onSubmit={(v) => procurement.post('contracts', v)} onDone={() => void q.refetch()} />}
    {decide && <FormDialog title={`Renewal decision · ${decide.title}`} onClose={() => setDecide(null)} initial={{ decision: 'renegotiate' }}
      intro={<p className="small muted">Review performance (supplier scorecard), spend ({money(decide.ordersValue)} ordered against {money(decide.value)}) and pricing first.</p>}
      fields={[{ name: 'decision', label: 'Decision', type: 'select', options: ['renew', 'renegotiate', 'resource', 'terminate'].map((x) => ({ value: x, label: x === 'resource' ? 'Re-source' : humanize(x) })) },
        { name: 'note', label: 'Review notes', type: 'textarea', required: true }]} onSubmit={(v) => procurement.post(`contracts/${decide.id}/decision`, v)} onDone={() => void q.refetch()} />}</>;
}

export function Recurring() {
  const q = useP('recurring');
  const lk = useP('lookups');
  const [add, setAdd] = useState(false);
  const run = useAction(() => procurement.post('recurring', { run: true }), [PK], 'Due recurring requests created');
  return <>{PT('Recurring purchases', 'Rent, cloud, subscriptions and maintenance: a draft purchase request is prepared a week before each purchase.',
    <><Button variant="outline" onClick={() => run.mutate(undefined)}>Prepare due requests</Button><Button onClick={() => setAdd(true)}><Icon name="plus" size={16} />New</Button></>)}
    <Load q={q}>{() => <Card flush><DataTable rows={q.data.results} empty="No recurring purchases" columns={[{ key: 'n', label: 'Purchase', render: (r: any) => <><strong>{r.title}</strong><div className="xs muted mono">{r.number} · {r.supplier}{r.contract ? ` · ${r.contract}` : ''}</div></> },
      { key: 'f', label: 'Frequency', render: (r: any) => humanize(r.frequency) }, { key: 'a', label: 'Expected', num: true, render: (r: any) => money(r.amount) },
      { key: 'd', label: 'Next', render: (r: any) => fmtDate(r.next) }, { key: 'l', label: 'Last request', render: (r: any) => r.lastRequest ?? '—' }, { key: 'o', label: 'Owner', render: (r: any) => r.owner }]} /></Card>}</Load>
    {add && <FormDialog title="New recurring purchase" onClose={() => setAdd(false)} initial={{ frequency: 'monthly' }}
      fields={[{ name: 'title', label: 'What', required: true }, { name: 'supplier_id', label: 'Supplier', type: 'select', required: true, options: (lk.data?.suppliers ?? []).map((s: any) => ({ value: s.id, label: s.name })) },
        { name: 'category_id', label: 'Category', type: 'select', required: true, options: (lk.data?.categories ?? []).map((c: any) => ({ value: c.id, label: c.name })) },
        { name: 'frequency', label: 'Frequency', type: 'select', half: true, options: ['monthly', 'quarterly', 'yearly'].map((x) => ({ value: x, label: humanize(x) })) },
        { name: 'expected_amount', label: 'Expected amount', type: 'number', required: true, half: true }, { name: 'next_date', label: 'Next purchase', type: 'date', required: true }]}
      onSubmit={(v) => procurement.post('recurring', v)} onDone={() => void q.refetch()} />}</>;
}

// ---------------------------------------------------------------------------------------------------------------------
export function Exceptions() {
  const [params, setParams] = useSearchParams();
  const [status, setStatus] = useState('open');
  const q = useP('exceptions', { kind: params.get('kind') || undefined, status });
  const detect = useAction(() => procurement.post('exceptions'), [PK], 'Checks run');
  const [dlg, setDlg] = useState<any>(null);
  return <>{PT('Exceptions & risk', 'Policy deviations and detected patterns (split purchases, duplicate suppliers, bank changes, maverick spend, concentration). Flags are for review — never accusations.',
    <Button variant="outline" loading={detect.isPending} onClick={() => detect.mutate(undefined)}>Run checks now</Button>)}
    <Card flush><div className="toolbar">
      <select className="field__input" aria-label="Kind" value={params.get('kind') ?? ''} onChange={(e) => setParams(e.target.value ? { kind: e.target.value } : {})}><option value="">All kinds</option>
        {(q.data?.kinds ?? []).map((k: any) => <option key={k.value} value={k.value}>{k.label}</option>)}</select>
      <select className="field__input" aria-label="Status" value={status} onChange={(e) => setStatus(e.target.value)}>
        {['open', 'approved', 'resolved', 'rejected', 'all'].map((s) => <option key={s} value={s}>{humanize(s)}</option>)}</select></div>
      <Load q={q}>{() => <DataTable rows={q.data.results} empty="Nothing flagged" columns={[{ key: 'k', label: 'Exception', render: (x: any) => <><strong>{x.kindLabel}</strong>{x.detected && <span className="flag" style={{ marginLeft: 6 }}>detected</span>}<div className="xs muted mono">{x.number} · {x.label}</div></> },
        { key: 'd', label: 'Detail', render: (x: any) => <span className="small">{x.description}{x.reason && <div className="xs muted">Reason: {x.reason}</div>}{x.resolution && <div className="xs">Resolution: {x.resolution}</div>}</span> },
        { key: 'a', label: 'Amount', num: true, render: (x: any) => (Number(x.amount) ? money(x.amount) : '') }, { key: 's', label: 'Status', render: (x: any) => <Status value={tone(x.status)} label={humanize(x.status)} /> },
        { key: 'x', label: '', render: (x: any) => x.status === 'open' && <span className="row" style={{ gap: 4 }}><Button size="sm" variant="ghost" onClick={() => setDlg({ x, action: 'submit' })}>Request approval</Button>
          <Button size="sm" variant="ghost" onClick={() => setDlg({ x, action: 'resolve' })}>Resolve</Button></span> }]} />}</Load></Card>
    {dlg?.action === 'submit' && <FormDialog title={`Approve exception ${dlg.x.number}`} onClose={() => setDlg(null)} submitLabel="Send for approval"
      fields={[{ name: 'reason', label: 'Justification', type: 'textarea', required: true }]} onSubmit={(v) => procurement.post(`exceptions/${dlg.x.id}/submit`, v)} onDone={() => void q.refetch()} />}
    {dlg?.action === 'resolve' && <FormDialog title={`Resolve ${dlg.x.number}`} onClose={() => setDlg(null)} initial={{ status: 'resolved' }}
      fields={[{ name: 'status', label: 'Outcome', type: 'select', options: [{ value: 'resolved', label: 'Resolved / explained' }, { value: 'rejected', label: 'Not acceptable (escalated)' }] },
        { name: 'resolution', label: 'What was found and done', type: 'textarea', required: true }]} onSubmit={(v) => procurement.post(`exceptions/${dlg.x.id}/resolve`, v)} onDone={() => void q.refetch()} />}</>;
}

export function Conflicts() {
  const q = useP('conflicts');
  const lk = useP('lookups');
  const [add, setAdd] = useState(false);
  const [rev, setRev] = useState<any>(null);
  return <>{PT('Conflict of interest', 'Declare relationships with suppliers before evaluating or approving. Declared conflicts block you from scoring that supplier.',
    <Button onClick={() => setAdd(true)}><Icon name="plus" size={16} />Declare a conflict</Button>)}
    <Load q={q}>{() => <Card flush><DataTable rows={q.data.results} empty="No declarations" columns={[{ key: 'p', label: 'Declared by', render: (c: any) => <>{c.declarant}<div className="xs muted">{fmtDate(c.at)}</div></> },
      { key: 's', label: 'Supplier', render: (c: any) => c.supplier }, { key: 'k', label: 'Kind', render: (c: any) => c.kindLabel }, { key: 'd', label: 'Description', render: (c: any) => <span className="small">{c.description}</span> },
      { key: 'st', label: 'Status', render: (c: any) => <>{humanize(c.status)}{c.decision && <div className="xs muted">{c.decision} ({c.reviewedBy})</div>}</> },
      { key: 'a', label: '', render: (c: any) => q.data.canReview && c.status === 'open' && <Button size="sm" variant="ghost" onClick={() => setRev(c)}>Review</Button> }]} /></Card>}</Load>
    {add && <FormDialog title="Declare a conflict of interest" onClose={() => setAdd(false)}
      fields={[{ name: 'supplier_id', label: 'Supplier (if registered)', type: 'select', options: (lk.data?.suppliers ?? []).map((s: any) => ({ value: s.id, label: s.name })) },
        { name: 'supplier_name', label: '…or the business name' }, { name: 'kind', label: 'Kind', type: 'select', required: true,
          options: [['supplier_relationship', 'Supplier relationship'], ['personal', 'Family / personal relationship'], ['financial_interest', 'Financial interest'], ['previous_employment', 'Previous employment'], ['other', 'Other']].map(([v, l]) => ({ value: v!, label: l! })) },
        { name: 'description', label: 'Describe it', type: 'textarea', required: true }]} onSubmit={(v) => procurement.post('conflicts', v)} onDone={() => void q.refetch()} />}
    {rev && <FormDialog title="Review declaration" onClose={() => setRev(null)} initial={{ status: 'reviewed' }}
      fields={[{ name: 'status', label: 'Outcome', type: 'select', options: [{ value: 'reviewed', label: 'Reviewed — keep excluded' }, { value: 'mitigated', label: 'Mitigated — may take part' }] },
        { name: 'decision', label: 'Decision', type: 'textarea', required: true }]} onSubmit={(v) => procurement.patch(`conflicts/${rev.id}`, v)} onDone={() => void q.refetch()} />}</>;
}

export function Policies() {
  const q = useP('policies');
  return <>{PT('Procurement policies & ethics', 'How Click buys. These rules are enforced by the system, not only written down.')}
    <Load q={q}>{() => <div className="stack stack--lg">
      <Card title="Purchasing rules"><ul className="small" style={{ margin: 0, paddingLeft: 18 }}>{q.data.rules.map((r: string) => <li key={r}>{r}</li>)}</ul></Card>
      <div className="grid grid--3">
        <Card title="Code of conduct"><p className="small" style={{ whiteSpace: 'pre-wrap' }}>{q.data.codeOfConduct}</p></Card>
        <Card title="Gifts & hospitality"><p className="small" style={{ whiteSpace: 'pre-wrap' }}>{q.data.giftPolicy}</p></Card>
        <Card title="Anti-bribery"><p className="small" style={{ whiteSpace: 'pre-wrap' }}>{q.data.antiBriberyPolicy}</p></Card>
      </div>
      <p className="xs muted">Policies are configured by procurement administrators and should be reviewed against Click's legal and compliance requirements.</p>
    </div>}</Load></>;
}

// ---------------------------------------------------------------------------------------------------------------------
export function Analytics() {
  const [r, setR] = useState({ from: today().slice(0, 4) + '-01-01', to: today() });
  const q = useP('analytics', r);
  const [dim, setDim] = useState('bySupplier');
  return <>{PT('Spend & procurement analytics', 'Where the money goes, what is managed, what was saved and where procurement slows down.',
    <span className="row"><input type="date" className="field__input" aria-label="From" value={r.from} onChange={(e) => setR({ ...r, from: e.target.value })} />
      <input type="date" className="field__input" aria-label="To" value={r.to} onChange={(e) => setR({ ...r, to: e.target.value })} /></span>)}
    <Load q={q}>{() => { const d = q.data; const rows = d[dim] ?? []; const max = Math.max(1, ...rows.map((x: any) => Number(x.amount)));
      return <div className="stack stack--lg">
        <Kpis items={[{ label: 'Committed (approved POs)', value: money(d.committedSpend) }, { label: 'Actual (approved bills)', value: money(d.actualSpend) },
          { label: 'Managed spend', value: money(d.managedSpend) }, { label: 'Unmanaged (no PO)', value: money(d.unmanagedSpend), tone: Number(d.unmanagedSpend) > 0 ? 'alert' : undefined },
          { label: 'Contracted spend', value: money(d.contractedSpend) }, { label: 'Savings', value: money(d.savings), tone: 'good' }, { label: 'Orders', value: d.orders },
          { label: 'Average order', value: money(d.averageOrderValue) }, { label: 'Suppliers used', value: d.supplierCount }]} />
        <Card title="KPIs"><Kpis items={Object.entries(d.kpis).map(([k, v]: any) => ({ label: humanize(k.replace(/Pct$/, '')).replace(/ pct$/i, ''), value: v != null ? `${v}%` : '—' }))} /></Card>
        <Card title="Spend breakdown" actions={<span className="row"><select className="field__input" aria-label="Dimension" value={dim} onChange={(e) => setDim(e.target.value)}>
          {[['bySupplier', 'Supplier'], ['byCategory', 'Category'], ['byDepartment', 'Department'], ['byLocation', 'Location'], ['byMonth', 'Month'], ['capexOpex', 'CAPEX / OPEX']].map(([v, l]) => <option key={v} value={v}>{l}</option>)}</select>
          <DownloadButton api={procurement} path="analytics" query={{ ...r, by: dim.replace(/[A-Z]/g, (c) => `_${c.toLowerCase()}`) }} filename={`spend-${dim}.csv`} /></span>}>
          <div className="bars">{rows.map((x: any) => <div key={x.label ?? x.month} className="bars__row"><span className="ellipsis">{x.label ?? x.month}</span>
            <span className="bars__track"><span style={{ width: `${(Number(x.amount) / max) * 100}%` }} /></span><strong className="num">{money(x.amount)}</strong></div>)}</div></Card>
        <div className="grid grid--2">
          <Card title="Supplier concentration" flush><DataTable rows={d.concentration.map((c: any) => ({ ...c, id: c.category }))} empty="No spend" columns={[{ key: 'c', label: 'Category', render: (c: any) => c.category },
            { key: 't', label: 'Spend', num: true, render: (c: any) => money(c.total) }, { key: 's', label: 'Top supplier', render: (c: any) => (c.top[0] ? `${c.top[0].supplier} ${c.top[0].sharePct}%` : '—') },
            { key: 'n', label: 'Suppliers', num: true, render: (c: any) => c.suppliers }]} /></Card>
          <Card title="Cycle time (average days)"><dl className="kv">{Object.entries(d.cycleTimeDays).map(([k, v]: any) => <div key={k} style={{ display: 'contents' }}><dt>{humanize(k).replace(/ to /g, ' → ')}</dt><dd>{v ?? '—'}</dd></div>)}</dl></Card>
        </div>
        <Card title="Savings (counted once, at award)" flush><DataTable rows={d.savingsDetail.map((s: any) => ({ ...s, id: s.award }))} empty="No awards in this period" columns={[{ key: 'a', label: 'Award', render: (s: any) => `${s.award} · ${s.supplier}` },
          { key: 'b', label: 'Benchmark', num: true, render: (s: any) => money(s.benchmark) }, { key: 'i', label: 'Initial quote', num: true, render: (s: any) => money(s.initial) },
          { key: 'f', label: 'Final', num: true, render: (s: any) => money(s.final) }, { key: 's', label: 'Savings', num: true, render: (s: any) => money(s.savings) }, { key: 'm', label: 'Method', render: (s: any) => s.method }]} /></Card>
        <p className="xs muted">{d.note}</p>
      </div>; }}</Load></>;
}

export function Settings() {
  const q = useP('settings');
  const [edit, setEdit] = useState(false);
  const [add, setAdd] = useState(false);
  return <>{PT('Procurement settings', 'Purchasing policy values, category tree (with Finance account and budget mapping) and request templates.',
    <><Button variant="outline" onClick={() => setAdd(true)}>New category</Button><Button onClick={() => setEdit(true)}>Edit policy</Button></>)}
    <Load q={q}>{() => <div className="stack stack--lg">
      <Card title="Policy"><dl className="kv">{Object.entries(q.data.policy).filter(([k]) => !['codeOfConduct', 'giftPolicy', 'antiBriberyPolicy'].includes(k)).map(([k, v]: any) =>
        <div key={k} style={{ display: 'contents' }}><dt>{humanize(k.replace(/([A-Z])/g, '_$1').toLowerCase())}</dt><dd>{typeof v === 'boolean' ? (v ? 'Yes' : 'No') : String(v)}</dd></div>)}</dl></Card>
      <Card title="Categories" flush><DataTable rows={q.data.categories} columns={[{ key: 'c', label: 'Category', render: (c: any) => <span style={{ paddingLeft: c.parent ? 16 : 0 }}>{c.name} <span className="xs muted mono">{c.code}</span></span> },
        { key: 'e', label: 'Type', render: (c: any) => c.expenditure.toUpperCase() }, { key: 'a', label: 'Finance account', render: (c: any) => <span className="mono xs">{c.account}</span> },
        { key: 'b', label: 'Budget category', render: (c: any) => c.budgetCategory || '—' }, { key: 'm', label: 'Match', render: (c: any) => humanize(c.match) },
        { key: 'f', label: '', render: (c: any) => <span className="xs">{c.inventory ? 'inventory ' : ''}{c.service ? 'service' : ''}</span> }]} /></Card>
      <Card title="Request templates" flush><DataTable rows={q.data.templates.map((t: any) => ({ ...t, id: t.key }))} columns={[{ key: 'n', label: 'Template', render: (t: any) => t.name },
        { key: 'c', label: 'Category', render: (t: any) => t.category }, { key: 't', label: 'Type', render: (t: any) => humanize(t.type) }]} /></Card>
    </div>}</Load>
    {edit && q.data && <FormDialog title="Procurement policy" wide onClose={() => setEdit(false)} initial={Object.fromEntries(Object.entries(q.data.policy).map(([k, v]) => [k.replace(/([A-Z])/g, '_$1').toLowerCase(), v]))}
      fields={[{ name: 'rfq_required_above', label: 'Competitive quotes required above', type: 'number', half: true }, { name: 'min_quotes', label: 'Minimum quotes', type: 'number', half: true },
        { name: 'emergency_max_amount', label: 'Emergency purchase limit', type: 'number', half: true }, { name: 'capex_threshold', label: 'CAPEX threshold', type: 'number', half: true },
        { name: 'match_tolerance_pct', label: 'Match tolerance %', type: 'number', half: true }, { name: 'match_tolerance_amount', label: 'Match tolerance amount', type: 'number', half: true },
        { name: 'split_window_days', label: 'Split-purchase window (days)', type: 'number', half: true }, { name: 'concentration_threshold_pct', label: 'Concentration flag %', type: 'number', half: true },
        { name: 'receiver_not_buyer', label: 'Buyer may not receive their own order', type: 'checkbox' }, { name: 'requester_not_buyer', label: 'Requester may not raise the PO', type: 'checkbox' },
        { name: 'block_unapproved_suppliers', label: 'Block POs to suppliers that are not active and approved', type: 'checkbox' },
        { name: 'code_of_conduct', label: 'Code of conduct', type: 'textarea' }, { name: 'gift_policy', label: 'Gift policy', type: 'textarea' }, { name: 'anti_bribery_policy', label: 'Anti-bribery policy', type: 'textarea' }]}
      onSubmit={(v) => procurement.patch('settings', v)} onDone={() => void q.refetch()} />}
    {add && <FormDialog title="New category" onClose={() => setAdd(false)} initial={{ expenditure: 'opex', match_mode: 'three_way', finance_account_key: 'general_expense' }}
      fields={[{ name: 'code', label: 'Code', required: true, half: true }, { name: 'name', label: 'Name', required: true, half: true },
        { name: 'parent_id', label: 'Under', type: 'select', options: (q.data?.categories ?? []).filter((c: any) => !c.parent).map((c: any) => ({ value: c.id, label: c.name })) },
        { name: 'expenditure', label: 'Expenditure', type: 'select', half: true, options: [{ value: 'opex', label: 'OPEX' }, { value: 'capex', label: 'CAPEX' }] },
        { name: 'match_mode', label: 'Invoice matching', type: 'select', half: true, options: [{ value: 'three_way', label: 'Three-way' }, { value: 'two_way', label: 'Two-way (services)' }, { value: 'none', label: 'None' }] },
        { name: 'finance_account_key', label: 'Finance account key', half: true }, { name: 'budget_category', label: 'Budget category', half: true },
        { name: 'is_service', label: 'Services', type: 'checkbox' }, { name: 'is_inventory', label: 'Click-owned inventory', type: 'checkbox' }]}
      onSubmit={(v) => procurement.post('settings', v)} onDone={() => void q.refetch()} />}</>;
}
