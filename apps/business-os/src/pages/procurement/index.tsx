/* eslint-disable @typescript-eslint/no-explicit-any */
/** Module 5 — Procurement workspace: home, requests, sourcing, purchase orders, receiving. */
import { useState } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { Button, Icon } from '@click/ui';
import { procurement } from '../../lib/api';
import { fmtDate, fmtDateTime, humanize } from '../../lib/format';
import { DataTable, FormDialog } from '../../components/forms';
import { DownloadButton, Kpis, ModuleShell, ModuleTitle, money, useAction } from '../../components/ModuleShell';
import { Alert, Card, Dialog, Empty, LoadingRows, Pager, QueryError, Status, Tabs } from '../../components/ui';

export const PK = ['os', 'procurement'];
export const PT = (title: string, desc?: React.ReactNode, actions?: React.ReactNode) => <ModuleTitle module="Procurement" root="/procurement" title={title} desc={desc} actions={actions} />;
export function useP<T = any>(path: string, query: Record<string, any> = {}, enabled = true) {
  return useQuery<T>({ queryKey: [...PK, path, query], queryFn: () => procurement.get<T>(path, query), enabled });
}
export function Load({ q, children }: { q: any; children: () => React.ReactNode }) {
  if (q.isPending) return <Card><LoadingRows /></Card>;
  if (q.error) return <QueryError error={q.error} />;
  return <>{children()}</>;
}
export const tone = (s: string) => (['approved', 'active', 'completed', 'received', 'invoiced', 'accepted', 'awarded', 'resolved', 'matched', 'confirmed', 'preferred', 'done'].includes(s) ? 'approved'
  : ['rejected', 'cancelled', 'blocked', 'exception', 'restricted', 'missed'].includes(s) ? 'rejected' : 'pending');
export const today = () => new Date().toISOString().slice(0, 10);

export function ProcurementLayout() { return <ModuleShell api={procurement} label="Procurement" root="/procurement" icon="bag" />; }

// ---------------------------------------------------------------------------------------------------------------------
export function ProcurementHome() {
  const q = useP('home');
  return <>{PT('Procurement', 'What needs buying, what is waiting for approval, what is being sourced, what is late — and where the money goes.',
    <Link to="/procurement/requests?new=1" className="btn btn--primary" style={{ textDecoration: 'none' }}>New purchase request</Link>)}
    <Load q={q}>{() => q.data.mode === 'self' ? <Card title="My purchase requests" flush><RequestRows rows={q.data.requests} /></Card> : (
      <div className="stack stack--lg">
        <Card title="Procurement pulse"><Kpis items={q.data.pulse.map((p: any) => ({ label: p.label, value: p.value === null ? '—' : p.money ? money(p.value) : p.value, to: p.path,
          tone: p.tone === 'alert' && Number(p.value) > 0 ? 'alert' : undefined }))} /></Card>
        <div className="grid grid--2">
          <Card title="Alerts & flags" flush>{!q.data.alerts.length ? <p className="muted small" style={{ padding: 16 }}>Nothing needs attention.</p> : (
            <ul className="list">{q.data.alerts.map((a: any, i: number) => <li key={i}><Link to={a.path} className="list-row"><span className={`sev sev--${a.severity}`} />
              <span className="grow small">{a.title}</span><span className="chip">{a.count}</span></Link></li>)}</ul>)}
            <p className="xs muted" style={{ padding: '0 16px 12px' }}>Flags are patterns for review, not findings about anyone.</p></Card>
          <Card title="My procurement work"><Kpis items={[
            { label: 'My open requests', value: q.data.myWork.myRequests, to: '/procurement/requests' }, { label: 'Approvals waiting on me', value: q.data.myWork.approvals, to: '/approvals' },
            { label: 'My RFQs / RFPs', value: q.data.myWork.myEvents, to: '/procurement/sourcing' }, { label: 'Quotes to review', value: q.data.myWork.quotesToReview, to: '/procurement/sourcing' },
            { label: 'My POs needing action', value: q.data.myWork.posToAct, to: '/procurement/orders' }, { label: 'Receipts pending', value: q.data.myWork.receiptsPending ?? '—', to: '/procurement/receiving' },
            { label: 'Services to confirm', value: q.data.myWork.servicesToConfirm, to: '/procurement/receiving' }, { label: 'My contracts', value: q.data.myWork.contractsMine, to: '/procurement/contracts' },
            { label: 'Emergency reviews due', value: q.data.myWork.postReviews ?? '—', to: '/procurement/requests?emergency=1' }]} /></Card>
        </div>
      </div>)}</Load></>;
}

function RequestRows({ rows, onRow }: { rows: any[]; onRow?: (r: any) => void }) {
  return <DataTable rows={rows} onRow={onRow} empty="No purchase requests" columns={[
    { key: 'n', label: 'Request', render: (p: any) => <><strong>{p.title}</strong><div className="xs muted mono">{p.number} · {p.category} · {p.typeLabel}</div></> },
    { key: 'r', label: 'Requester', render: (p: any) => <span className="small">{p.requester}{p.department ? <div className="xs muted">{p.department}</div> : null}</span> },
    { key: 't', label: 'Estimate', num: true, render: (p: any) => money(p.total) }, { key: 'd', label: 'Needed by', render: (p: any) => fmtDate(p.requiredBy) },
    { key: 'f', label: '', render: (p: any) => <span className="row" style={{ gap: 4 }}>{p.emergency && <span className="flag flag--overdue">emergency</span>}
      {p.singleSource && <span className="flag">single source</span>}{p.postReview === 'pending' && <span className="flag flag--due_soon">review due</span>}</span> },
    { key: 's', label: 'Status', render: (p: any) => <Status value={tone(p.status)} label={p.statusLabel} /> }]} />;
}

// ---------------------------------------------------------------------------------------------------------------------
export function Requests() {
  const [params, setParams] = useSearchParams();
  const [f, setF] = useState({ view: 'mine', status: '', page: 1 });
  const q = useP('requests', { view: f.view, status: f.status || undefined, page: f.page, emergency: params.get('emergency') || undefined });
  const open = params.get('open');
  return <>{PT('Purchase requests', 'Every purchase starts here: a need, a budget check and an approval — then sourcing.',
    <><DownloadButton api={procurement} path="requests" query={{ view: f.view }} filename="purchase-requests.csv" /><Button onClick={() => setParams({ new: '1' })}><Icon name="plus" size={16} />New request</Button></>)}
    {q.data?.canViewAll && <Tabs value={f.view} onChange={(v) => setF({ ...f, view: v, page: 1 })} items={[{ value: 'mine', label: 'My requests' }, { value: 'all', label: 'All I can see' }]} />}
    <Card flush><div className="toolbar"><select className="field__input" aria-label="Status" value={f.status} onChange={(e) => setF({ ...f, status: e.target.value, page: 1 })}>
      <option value="">All</option>{['draft', 'submitted', 'approved', 'sourcing', 'ordered', 'rejected', 'cancelled'].map((s) => <option key={s} value={s}>{humanize(s)}</option>)}</select></div>
      <Load q={q}>{() => <><RequestRows rows={q.data.results} onRow={(p) => setParams({ open: p.id })} /><Pager page={q.data.page} hasNext={q.data.hasNext} count={q.data.count} onPage={(p) => setF({ ...f, page: p })} /></>}</Load></Card>
    {open && <RequestDrawer id={open} onClose={() => setParams({})} />}
    {params.get('new') === '1' && <NewRequest onClose={() => setParams({})} onDone={(id) => setParams({ open: id })} />}</>;
}

function NewRequest({ onClose, onDone }: { onClose: () => void; onDone: (id: string) => void }) {
  const lk = useP('lookups');
  const [form, setForm] = useState<any>({ requestType: 'standard', priority: 'normal' });
  const [lines, setLines] = useState<any[]>([{ quantity: 1 }]);
  const [err, setErr] = useState<string | null>(null);
  const create = useAction((b: any) => procurement.post('requests', b), [PK], 'Request saved');
  const set = (k: string, v: any) => setForm({ ...form, [k]: v });
  const applyTemplate = (key: string) => {
    const t = lk.data?.templates.find((x: any) => x.key === key);
    const c = lk.data?.categories.find((x: any) => x.code === t?.category);
    if (t) setForm({ ...form, template: key, requestType: t.type, expenditure: t.expenditure, categoryId: c?.id, justificationHint: t.hint, sourcingNote: t.sourcing, documents: t.documents });
  };
  const total = lines.reduce((a, l) => a + Number(l.quantity || 0) * Number(l.estimatedUnitCost || 0), 0);
  const save = (submit: boolean) => create.mutate({ ...form, lines, submit }, { onSuccess: (r: any) => { onClose(); onDone(r.id); }, onError: (e: any) => setErr(e.message) });
  return <Dialog title="New purchase request" wide onClose={onClose} footer={<><Button variant="outline" onClick={onClose}>Cancel</Button>
    <Button variant="outline" loading={create.isPending} onClick={() => save(false)}>Save draft</Button><Button loading={create.isPending} onClick={() => save(true)}>Submit</Button></>}>
    {err && <Alert tone="error">{err}</Alert>}
    <div className="pill-list" style={{ marginBottom: 12 }}>{(lk.data?.templates ?? []).map((t: any) => <button key={t.key} className={`pill ${form.template === t.key ? 'pill--on' : ''}`} onClick={() => applyTemplate(t.key)}>{t.name}</button>)}</div>
    {form.sourcingNote && <Alert tone="info">{form.sourcingNote}{form.documents ? ` Attach: ${form.documents}.` : ''}</Alert>}
    <div className="form-grid">
      <label className="field form-grid__full"><span className="field__label">What do you need?</span><input className="field__input" value={form.title ?? ''} onChange={(e) => set('title', e.target.value)} /></label>
      <label className="field"><span className="field__label">Category</span><select className="field__input" value={form.categoryId ?? ''} onChange={(e) => set('categoryId', e.target.value)}>
        <option value="">Choose…</option>{(lk.data?.categories ?? []).map((c: any) => <option key={c.id} value={c.id}>{c.parent ? '  ' : ''}{c.name} ({c.expenditure.toUpperCase()})</option>)}</select></label>
      <label className="field"><span className="field__label">Type</span><select className="field__input" value={form.requestType} onChange={(e) => set('requestType', e.target.value)}>
        {['standard', 'urgent', 'emergency', 'recurring', 'project', 'capex', 'opex', 'service', 'software', 'hardware', 'inventory', 'contract', 'subscription'].map((t) => <option key={t} value={t}>{humanize(t)}</option>)}</select></label>
      <label className="field"><span className="field__label">Needed by</span><input type="date" className="field__input" value={form.requiredBy ?? ''} onChange={(e) => set('requiredBy', e.target.value)} /></label>
      <label className="field"><span className="field__label">Priority</span><select className="field__input" value={form.priority} onChange={(e) => set('priority', e.target.value)}>
        {['low', 'normal', 'high', 'critical'].map((p) => <option key={p} value={p}>{humanize(p)}</option>)}</select></label>
      <label className="field"><span className="field__label">Preferred supplier (optional)</span><select className="field__input" value={form.preferredSupplierId ?? ''} onChange={(e) => set('preferredSupplierId', e.target.value)}>
        <option value="">—</option>{(lk.data?.suppliers ?? []).map((s: any) => <option key={s.id} value={s.id}>{s.name}{s.preference === 'preferred' ? ' ★' : ''}</option>)}</select></label>
      <label className="field"><span className="field__label">Cost center</span><select className="field__input" value={form.costCenterId ?? ''} onChange={(e) => set('costCenterId', e.target.value)}>
        <option value="">—</option>{(lk.data?.costCenters ?? []).map((c: any) => <option key={c.id} value={c.id}>{c.code} {c.name}</option>)}</select></label>
      <label className="field"><span className="field__label">Project</span><input className="field__input" value={form.project ?? ''} onChange={(e) => set('project', e.target.value)} /></label>
      <label className="field form-grid__full"><span className="field__label">Business justification</span><textarea className="field__input" rows={2} placeholder={form.justificationHint}
        value={form.justification ?? ''} onChange={(e) => set('justification', e.target.value)} /></label>
      {form.requestType === 'emergency' && <label className="field form-grid__full"><span className="field__label">What is the emergency? (reviewed after purchase)</span>
        <textarea className="field__input" rows={2} value={form.emergencyReason ?? ''} onChange={(e) => set('emergencyReason', e.target.value)} /></label>}
      <label className="row small form-grid__full"><input type="checkbox" checked={!!form.singleSource} onChange={(e) => set('singleSource', e.target.checked)} />Only one supplier can provide this (single source)</label>
      {form.singleSource && <><label className="field"><span className="field__label">Reason</span><select className="field__input" value={form.singleSourceReason ?? ''} onChange={(e) => set('singleSourceReason', e.target.value)}>
        <option value="">Choose…</option>{['proprietary', 'compatibility', 'emergency', 'only_supplier', 'existing_contract', 'other'].map((x) => <option key={x} value={x}>{humanize(x)}</option>)}</select></label>
        <label className="field"><span className="field__label">Justification</span><textarea className="field__input" rows={2} value={form.singleSourceJustification ?? ''} onChange={(e) => set('singleSourceJustification', e.target.value)} /></label></>}
    </div>
    <div className="stack" style={{ gap: 6, marginTop: 8 }}>
      {lines.map((l, i) => <div key={i} className="row row--wrap" style={{ gap: 6 }}>
        <input className="field__input" placeholder="Item / service" aria-label="Item" value={l.description ?? ''} onChange={(e) => setLines(lines.map((x, j) => (j === i ? { ...x, description: e.target.value } : x)))} style={{ minWidth: 220 }} />
        <input className="field__input" type="number" placeholder="Qty" aria-label="Quantity" style={{ width: 80 }} value={l.quantity ?? ''} onChange={(e) => setLines(lines.map((x, j) => (j === i ? { ...x, quantity: e.target.value } : x)))} />
        <input className="field__input" type="number" placeholder="Est. unit cost" aria-label="Estimated unit cost" style={{ width: 130 }} value={l.estimatedUnitCost ?? ''} onChange={(e) => setLines(lines.map((x, j) => (j === i ? { ...x, estimatedUnitCost: e.target.value } : x)))} />
        <input className="field__input" placeholder="Specification" aria-label="Specification" value={l.specification ?? ''} onChange={(e) => setLines(lines.map((x, j) => (j === i ? { ...x, specification: e.target.value } : x)))} />
        <button className="icon-btn" aria-label="Remove" onClick={() => setLines(lines.filter((_, j) => j !== i))}><Icon name="close" size={14} /></button></div>)}
      <div className="row"><Button size="sm" variant="ghost" onClick={() => setLines([...lines, { quantity: 1 }])}><Icon name="plus" size={14} />Add item</Button>
        <span className="small" style={{ marginLeft: 'auto' }}>Estimated total <strong>{money(total)}</strong>{lk.data && total >= Number(lk.data.policy.rfqRequiredAbove) ? ' — competitive quotes required' : ''}</span></div>
    </div>
  </Dialog>;
}

function RequestDrawer({ id, onClose }: { id: string; onClose: () => void }) {
  const q = useP(`requests/${id}`);
  const act = useAction((b: any) => procurement.post(`requests/${id}/${b.action}`, b), [PK], 'Done');
  const [dlg, setDlg] = useState<'' | 'override' | 'cancel' | 'review' | 'po'>('');
  const lk = useP('lookups', {}, dlg === 'po');
  const d = q.data;
  return <Dialog title={d ? `${d.number} · ${d.title}` : 'Request'} wide onClose={onClose}><Load q={q}>{() => <div className="stack">
    <div className="row row--wrap"><Status value={tone(d.status)} label={d.statusLabel} /><span className="chip">{d.typeLabel}</span><span className="chip">{d.expenditure.toUpperCase()}</span>
      {d.emergency && <span className="flag flag--overdue">emergency</span>}<span className="small muted">{d.requester} · {d.category} · needed {fmtDate(d.requiredBy)}</span></div>
    <p className="small" style={{ whiteSpace: 'pre-wrap' }}>{d.justification}</p>
    {d.emergencyReason && <Alert tone="warning">Emergency: {d.emergencyReason}{d.postReview === 'done' ? ` — reviewed: ${d.postReviewNote}` : ' — post-purchase review pending'}</Alert>}
    {d.singleSource && <Alert tone="info">Single source ({humanize(d.singleSourceReason)}): {d.singleSourceJustification}</Alert>}
    <Card title="Budget check">{d.budget?.budget !== undefined ? <dl className="kv"><dt>Budget</dt><dd>{money(d.budget.budget)}</dd><dt>Already committed / spent</dt>
      <dd>{money(Number(d.budget.committed ?? 0) + Number(d.budget.actual ?? 0))}</dd><dt>Available</dt><dd>{money(d.budget.available)}</dd><dt>This request</dt><dd>{money(d.total)}</dd>
      <dt>After this request</dt><dd style={{ color: Number(d.budget.after) < 0 ? 'var(--c-danger)' : undefined }}>{money(d.budget.after)}</dd></dl>
      : <p className="small">{d.budget?.message ?? '—'}</p>}</Card>
    <DataTable rows={d.lines} columns={[{ key: 'd', label: 'Item', render: (l: any) => <>{l.description}<div className="xs muted">{l.specification}</div></> },
      { key: 'q', label: 'Qty', num: true, render: (l: any) => `${Number(l.quantity)} ${l.uom}` }, { key: 'u', label: 'Unit', num: true, render: (l: any) => money(l.unitCost) },
      { key: 't', label: 'Total', num: true, render: (l: any) => money(l.total) }]} />
    <Card title="Traceability: need → request → approval → sourcing → PO → receipt → invoice → payment">
      <ul className="timeline">
        <li>Requested by {d.requester} · {fmtDateTime(d.createdAt)}</li>
        {d.trace.approval && <li>Approval {d.trace.approval.reference}: {humanize(d.trace.approval.status)} · <Link to={`/approvals/${d.trace.approval.id}`}>open</Link></li>}
        {d.trace.sourcing.map((e: any) => <li key={e.id}><Link to={`/procurement/sourcing?open=${e.id}`}>{e.number}</Link> {e.title} — {e.statusLabel} ({e.responses}/{e.invited} responses)</li>)}
        {d.trace.awards.map((a: any) => <li key={a.number}>Award {a.number} to {a.supplier} — {money(a.amount)} ({a.status}): {a.reason}</li>)}
        {d.trace.orders.map((o: any) => <li key={o.id}><Link to={`/procurement/orders?open=${o.id}`}>{o.number}</Link> {o.supplier} — {money(o.total)} · {o.statusLabel}</li>)}
        {d.trace.receipts.map((r: any) => <li key={r.number}>Receipt {r.number} on {fmtDate(r.date)} — {r.status}</li>)}
        {d.trace.invoices.map((i: any) => <li key={i.number + i.supplierInvoice}>Invoice {i.supplierInvoice} ({i.number}) — {money(i.total)} · match {humanize(i.match)} · {humanize(i.status)}</li>)}
        {d.trace.payments.map((p: any) => <li key={p.number}>Payment {p.number} — {money(p.amount)} · {p.status}</li>)}
      </ul></Card>
    <div className="row row--wrap">
      {d.canSubmit && <><Button onClick={() => act.mutate({ action: 'submit' }, { onError: () => setDlg('override') })}>Submit for approval</Button></>}
      {d.canSource && <Link to={`/procurement/sourcing?new=1&request=${d.id}`} className="btn btn--outline" style={{ textDecoration: 'none' }}>Start RFQ / RFP</Link>}
      {d.canOrder && <Button variant="outline" onClick={() => setDlg('po')}>Direct purchase order</Button>}
      {d.postReview === 'pending' && <Button variant="outline" onClick={() => setDlg('review')}>Post-purchase review</Button>}
      {!['ordered', 'closed', 'cancelled', 'rejected'].includes(d.status) && <Button variant="ghost" onClick={() => setDlg('cancel')}>Cancel request</Button>}
    </div>
    {dlg === 'override' && <FormDialog title="Budget is insufficient" onClose={() => setDlg('')} submitLabel="Submit with override request"
      intro={<Alert tone="warning">The available budget doesn't cover this request. Approvers will see your reason, and a budget exception is recorded.</Alert>}
      fields={[{ name: 'budget_override_reason', label: 'Why should it proceed?', type: 'textarea', required: true }]} onSubmit={(v) => procurement.post(`requests/${id}/submit`, v)} onDone={() => void q.refetch()} />}
    {dlg === 'cancel' && <FormDialog title="Cancel request" onClose={() => setDlg('')} fields={[{ name: 'reason', label: 'Reason', required: true }]} onSubmit={(v) => procurement.post(`requests/${id}/cancel`, v)} onDone={() => void q.refetch()} />}
    {dlg === 'review' && <FormDialog title="Post-purchase review" onClose={() => setDlg('')} fields={[{ name: 'note', label: 'Was the emergency genuine and the price reasonable?', type: 'textarea', required: true }]}
      onSubmit={(v) => procurement.post(`requests/${id}/post-review`, v)} onDone={() => void q.refetch()} />}
    {dlg === 'po' && <FormDialog title="Direct purchase order" onClose={() => setDlg('')} submitLabel="Create draft PO"
      intro={<p className="small muted">For small purchases, single-source, emergency or contract purchases. Above {money(lk.data?.policy?.rfqRequiredAbove)} without these, give a reason (recorded as an exception).</p>}
      fields={[{ name: 'supplier_id', label: 'Supplier', type: 'select', required: true, options: (lk.data?.suppliers ?? []).map((s: any) => ({ value: s.id, label: `${s.name} (${s.status})` })) },
        { name: 'tax_rule_id', label: 'Tax', type: 'select', half: true, options: (lk.data?.taxRules ?? []).map((t: any) => ({ value: t.id, label: t.code })) },
        { name: 'delivery_location', label: 'Deliver to', half: true }, { name: 'exception_reason', label: 'Exception reason (if no quotes)', type: 'textarea' }]}
      onSubmit={(v) => procurement.post('orders', { ...v, purchaseRequestId: id })} onDone={(r: any) => { window.location.assign(`/procurement/orders?open=${r.id}`); }} />}
  </div>}</Load></Dialog>;
}

// ---------------------------------------------------------------------------------------------------------------------
export function Sourcing() {
  const [params, setParams] = useSearchParams();
  const [f, setF] = useState({ kind: '', page: 1 });
  const q = useP('sourcing', { kind: f.kind || undefined, page: f.page });
  const open = params.get('open');
  const lk = useP('lookups', {}, params.get('new') === '1');
  return <>{PT('RFQ / RFP / RFI', 'Competitive sourcing: invite suppliers, collect quotes, compare on weighted criteria and total cost, negotiate, award.',
    <Button onClick={() => setParams({ new: '1' })}><Icon name="plus" size={16} />New sourcing event</Button>)}
    <Tabs value={f.kind} onChange={(k) => setF({ kind: k, page: 1 })} items={[{ value: '', label: 'All' }, { value: 'rfq', label: 'RFQs' }, { value: 'rfp', label: 'RFPs' }, { value: 'rfi', label: 'RFIs' }]} />
    <Load q={q}>{() => <Card flush><DataTable rows={q.data.results} onRow={(e: any) => setParams({ open: e.id })} empty="No sourcing events" columns={[
      { key: 'n', label: 'Event', render: (e: any) => <><strong>{e.title}</strong><div className="xs muted mono">{e.number}{e.request ? ` · ${e.request}` : ''} · {e.category}</div></> },
      { key: 'r', label: 'Responses', num: true, render: (e: any) => `${e.responses}/${e.invited}` }, { key: 'd', label: 'Deadline', render: (e: any) => fmtDateTime(e.deadline) },
      { key: 'o', label: 'Owner', render: (e: any) => e.owner }, { key: 's', label: 'Status', render: (e: any) => <Status value={tone(e.status)} label={e.statusLabel} /> }]} />
      <Pager page={q.data.page} hasNext={q.data.hasNext} count={q.data.count} onPage={(p) => setF({ ...f, page: p })} /></Card>}</Load>
    {open && <EventDrawer id={open} onClose={() => setParams({})} />}
    {params.get('new') === '1' && <FormDialog title="New sourcing event" wide onClose={() => setParams({})} submitLabel="Create" initial={{ kind: 'rfq', purchase_request_id: params.get('request') ?? '' }}
      intro={<p className="small muted">From an approved request, items and need carry over. Suppliers never see each other's prices.</p>}
      fields={[{ name: 'kind', label: 'Type', type: 'select', half: true, options: [{ value: 'rfq', label: 'RFQ — quotation' }, { value: 'rfp', label: 'RFP — proposal' }, { value: 'rfi', label: 'RFI — information' }] },
        { name: 'purchase_request_id', label: 'Purchase request ID (optional)', half: true },
        { name: 'category_id', label: 'Category (if no request)', type: 'select', options: (lk.data?.categories ?? []).map((c: any) => ({ value: c.id, label: c.name })) },
        { name: 'title', label: 'Title' }, { name: 'description', label: 'Scope / need', type: 'textarea' }, { name: 'requirements', label: 'Requirements & specifications', type: 'textarea' },
        { name: 'response_deadline', label: 'Response deadline', type: 'datetime-local', half: true }, { name: 'delivery_location', label: 'Delivery location', half: true },
        { name: 'supplier_ids', label: 'Invite suppliers', type: 'multiselect', options: (lk.data?.suppliers ?? []).filter((s: any) => s.status === 'active').map((s: any) => ({ value: s.id, label: s.name })) }]}
      onSubmit={(v) => procurement.post('sourcing', { ...v, responseDeadline: v.responseDeadline ? new Date(String(v.responseDeadline)).toISOString() : null })}
      onDone={(r: any) => setParams({ open: r.id })} />}</>;
}

function EventDrawer({ id, onClose }: { id: string; onClose: () => void }) {
  const q = useP(`sourcing/${id}`);
  const lk = useP('lookups');
  const act = useAction((b: any) => procurement.post(`sourcing/${id}/${b.action}`, b), [PK], 'Done');
  const [dlg, setDlg] = useState<any>(null);
  const d = q.data;
  return <Dialog title={d ? `${d.number} · ${d.title}` : 'Sourcing event'} wide onClose={onClose}><Load q={q}>{() => <div className="stack">
    <div className="row row--wrap"><Status value={tone(d.status)} label={d.statusLabel} /><span className="small muted">{d.category} · deadline {fmtDateTime(d.deadline)} · owner {d.owner}</span>
      <span style={{ marginLeft: 'auto' }} className="row">{d.status === 'draft' && <Button onClick={() => act.mutate({ action: 'publish' })}>Publish</Button>}
        {['published', 'responses'].includes(d.status) && <><Button variant="outline" onClick={() => setDlg({ kind: 'quote' })}>Record quote</Button>
          <Button variant="ghost" onClick={() => act.mutate({ action: 'remind' })}>Remind</Button><Button variant="ghost" onClick={() => act.mutate({ action: 'close' })}>Close submissions</Button></>}
        {!['awarded', 'cancelled', 'closed'].includes(d.status) && <Button variant="ghost" onClick={() => setDlg({ kind: 'invite' })}>Invite</Button>}</span></div>
    {d.description && <p className="small" style={{ whiteSpace: 'pre-wrap' }}>{d.description}</p>}
    <Card title="Suppliers" flush><DataTable rows={d.invites.map((i: any) => ({ ...i, id: i.supplierId }))} empty="No suppliers invited" columns={[{ key: 's', label: 'Supplier', render: (i: any) => i.supplier },
      { key: 'st', label: 'Status', render: (i: any) => humanize(i.status) }, { key: 'r', label: 'Responded', render: (i: any) => fmtDateTime(i.respondedAt) }]} /></Card>
    {d.comparison && d.comparison.rows.length > 0 && <Card title={`Comparison (weighted, by ${d.comparison.basis})`} flush>
      <div className="table-wrap"><table className="table"><thead><tr><th>Criterion</th>{d.comparison.rows.map((r: any) => <th key={r.quotationId}>#{r.rank} {r.supplier}{r.revision > 1 ? ` (rev ${r.revision})` : ''}</th>)}</tr></thead>
        <tbody>
          <tr><td>Total</td>{d.comparison.rows.map((r: any) => <td key={r.quotationId} className="num">{money(r.total)}</td>)}</tr>
          {d.comparison.rows.some((r: any) => r.tco && Object.keys(r.tco).length) && <tr><td>Total cost of ownership</td>{d.comparison.rows.map((r: any) => <td key={r.quotationId} className="num">{money(r.tcoTotal)}</td>)}</tr>}
          <tr><td>Delivery</td>{d.comparison.rows.map((r: any) => <td key={r.quotationId}>{r.deliveryDays ? `${r.deliveryDays} days` : '—'}</td>)}</tr>
          <tr><td>Warranty</td>{d.comparison.rows.map((r: any) => <td key={r.quotationId}>{r.warrantyMonths ? `${r.warrantyMonths} months` : '—'}</td>)}</tr>
          <tr><td>Payment terms</td>{d.comparison.rows.map((r: any) => <td key={r.quotationId}>{r.paymentTermsDays} days</td>)}</tr>
          {d.criteria.map((c: any) => <tr key={c.key}><td>{c.label} <span className="xs muted">{c.weight}%{c.auto ? ' · auto' : ''}</span></td>
            {d.comparison.rows.map((r: any) => <td key={r.quotationId}>{r.scores[c.key] ?? <span className="xs muted">not scored</span>}</td>)}</tr>)}
          <tr><td><strong>Weighted score</strong></td>{d.comparison.rows.map((r: any) => <td key={r.quotationId}><strong>{r.weighted}</strong>{!r.complete && <div className="xs muted">incomplete</div>}</td>)}</tr>
          <tr><td /> {d.comparison.rows.map((r: any) => <td key={r.quotationId}><span className="row row--wrap" style={{ gap: 4 }}>
            {!d.myConflicts.includes(r.supplierId) ? <Button size="sm" variant="ghost" onClick={() => setDlg({ kind: 'score', row: r })}>Score</Button> : <span className="xs muted">conflict declared</span>}
            <Button size="sm" variant="ghost" onClick={() => setDlg({ kind: 'negotiate', row: r })}>Negotiate</Button>
            {d.kind !== 'rfi' && d.status !== 'awarded' && <Button size="sm" onClick={() => setDlg({ kind: 'award', row: r })}>Award</Button>}</span></td>)}</tr>
        </tbody></table></div></Card>}
    {d.negotiations.length > 0 && <Card title="Negotiation history (originals are kept)"><ul className="timeline">{d.negotiations.map((n: any, i: number) => <li key={i}>{n.quote}: {money(n.from)} → <strong>{money(n.to)}</strong> · {n.by} {fmtDateTime(n.at)}<div className="small">{n.note}</div></li>)}</ul></Card>}
    {d.awards.length > 0 && <Card title="Awards" flush><DataTable rows={d.awards.map((a: any) => ({ ...a, id: a.number }))} columns={[{ key: 'n', label: 'Award', render: (a: any) => <>{a.number} · {a.supplier}<div className="xs muted">{a.reason}</div></> },
      { key: 'a', label: 'Amount', num: true, render: (a: any) => money(a.amount) }, { key: 's', label: 'Savings', num: true, render: (a: any) => `${money(a.savings)} ${a.method ? `(${humanize(a.method)})` : ''}` },
      { key: 'st', label: 'Status', render: (a: any) => <>{humanize(a.status)} {a.approvalId && <Link to={`/approvals/${a.approvalId}`} className="small">approval</Link>}</> }]} /></Card>}
    {dlg?.kind === 'invite' && <FormDialog title="Invite suppliers" onClose={() => setDlg(null)} submitLabel="Invite"
      fields={[{ name: 'supplier_ids', label: 'Suppliers', type: 'multiselect', options: (lk.data?.suppliers ?? []).map((s: any) => ({ value: s.id, label: s.name })) }]}
      onSubmit={(v) => procurement.post(`sourcing/${id}/invite`, v)} onDone={() => void q.refetch()} />}
    {dlg?.kind === 'quote' && <FormDialog title="Record a quotation" wide onClose={() => setDlg(null)} submitLabel="Save quote" initial={{ quote_date: today(), payment_terms_days: 30 }}
      intro={<p className="small muted">Line prices in the order of the event's items: {d.lines.map((l: any) => `${l.description} ×${Number(l.quantity)}`).join(' · ')}</p>}
      fields={[{ name: 'supplier_id', label: 'Supplier', type: 'select', required: true, options: d.invites.filter((i: any) => i.status !== 'responded').map((i: any) => ({ value: i.supplierId, label: i.supplier })) },
        { name: 'quote_reference', label: 'Supplier quote ref', half: true }, { name: 'valid_until', label: 'Valid until', type: 'date', half: true },
        ...d.lines.map((l: any, i: number) => ({ name: `price${i}`, label: `Unit price — ${l.description}`, type: 'number' as const, required: true, half: true })),
        { name: 'tax_rate', label: 'Tax %', type: 'number', half: true }, { name: 'shipping', label: 'Shipping', type: 'number', half: true },
        { name: 'delivery_days', label: 'Delivery (days)', type: 'number', half: true }, { name: 'warranty_months', label: 'Warranty (months)', type: 'number', half: true },
        { name: 'payment_terms_days', label: 'Payment terms (days)', type: 'number', half: true }, { name: 'maintenance', label: 'TCO: annual maintenance/support', type: 'number', half: true },
        { name: 'installation', label: 'TCO: installation & training', type: 'number', half: true }, { name: 'notes', label: 'Notes', type: 'textarea' }]}
      onSubmit={(v: any) => procurement.post(`sourcing/${id}/quote`, { supplierId: v.supplierId, quoteReference: v.quoteReference, validUntil: v.validUntil, shipping: v.shipping, deliveryDays: v.deliveryDays,
        warrantyMonths: v.warrantyMonths, paymentTermsDays: v.paymentTermsDays, notes: v.notes, tco: Object.fromEntries(Object.entries({ maintenance: v.maintenance, installation: v.installation }).filter(([, x]) => x)),
        lines: d.lines.map((_: any, i: number) => ({ unitPrice: v[`price${i}`], taxRate: v.taxRate || 0 })) })} onDone={() => void q.refetch()} />}
    {dlg?.kind === 'score' && <FormDialog title={`Score ${dlg.row.supplier}`} onClose={() => setDlg(null)} submitLabel="Save scores"
      intro={<p className="small muted">0–100 per criterion; price, delivery and warranty are scored automatically from the quotes.</p>}
      fields={[...d.criteria.filter((c: any) => !c.auto).map((c: any) => ({ name: c.key, label: `${c.label} (${c.weight}%)`, type: 'number' as const, half: true, min: 0, max: 100 })),
        { name: 'note', label: 'Evidence / notes', type: 'textarea' }]}
      onSubmit={(v: any) => { const { note, ...scores } = v; return procurement.post(`quotations/${dlg.row.quotationId}/score`, { scores: Object.fromEntries(Object.entries(scores).filter(([, x]) => x !== null && x !== '')), note }); }}
      onDone={() => void q.refetch()} />}
    {dlg?.kind === 'negotiate' && <FormDialog title={`Negotiate with ${dlg.row.supplier}`} onClose={() => setDlg(null)} submitLabel="Record revised quote"
      intro={<p className="small muted">Creates revision {dlg.row.revision + 1}; the current quote is kept unchanged in the history.</p>}
      fields={[{ name: 'unit_price', label: 'Negotiated unit price (all lines, optional)', type: 'number', half: true }, { name: 'discount', label: 'Overall discount', type: 'number', half: true },
        { name: 'delivery_days', label: 'Delivery (days)', type: 'number', half: true }, { name: 'payment_terms_days', label: 'Payment terms (days)', type: 'number', half: true },
        { name: 'participants', label: 'Participants' }, { name: 'note', label: 'What was agreed', type: 'textarea', required: true }]}
      onSubmit={(v: any) => { const quote = d.quotes.find((x: any) => x.id === dlg.row.quotationId);
        return procurement.post(`quotations/${dlg.row.quotationId}/negotiate`, { note: v.note, participants: v.participants, changes: { discount: v.discount ?? undefined, deliveryDays: v.deliveryDays ?? undefined,
          paymentTermsDays: v.paymentTermsDays ?? undefined, lines: v.unitPrice ? (quote?.lines ?? []).map((l: any) => ({ lineId: l.id, unitPrice: v.unitPrice })) : [] } }); }}
      onDone={() => void q.refetch()} />}
    {dlg?.kind === 'award' && <FormDialog title={`Award to ${dlg.row.supplier}`} onClose={() => setDlg(null)} submitLabel="Send award for approval"
      intro={<p className="small muted">Ranked #{dlg.row.rank} with {dlg.row.weighted}. Once approved, a draft purchase order is created from this quote.</p>}
      fields={[{ name: 'reason', label: 'Why this supplier? (recorded)', type: 'textarea', required: true }, { name: 'exception_reason', label: 'If fewer quotes than policy requires: why', type: 'textarea' }]}
      onSubmit={(v) => procurement.post(`sourcing/${id}/award`, { ...v, quotationId: dlg.row.quotationId })} onDone={() => void q.refetch()} />}
  </div>}</Load></Dialog>;
}

// ---------------------------------------------------------------------------------------------------------------------
export function Orders() {
  const [params, setParams] = useSearchParams();
  const [f, setF] = useState({ status: '', q: '', page: 1 });
  const overdue = params.get('overdue') === '1';
  const q = useP('orders', { status: f.status || undefined, q: f.q || undefined, page: f.page, overdue: overdue ? '1' : undefined });
  const open = params.get('open');
  return <>{PT('Purchase orders', 'Approved orders are never edited silently: changes are amendments, approved, creating a new version.',
    <DownloadButton api={procurement} path="orders" filename="purchase-orders.csv" />)}
    <Card flush><div className="toolbar"><div className="search-input"><Icon name="search" size={16} /><input value={f.q} onChange={(e) => setF({ ...f, q: e.target.value, page: 1 })} placeholder="PO number or supplier" aria-label="Search" /></div>
      <select className="field__input" aria-label="Status" value={f.status} onChange={(e) => setF({ ...f, status: e.target.value, page: 1 })}><option value="">All</option>
        {['draft', 'pending_approval', 'approved', 'sent', 'confirmed', 'partially_received', 'received', 'partially_invoiced', 'invoiced', 'completed', 'cancelled', 'closed'].map((s) => <option key={s} value={s}>{humanize(s)}</option>)}</select>
      {overdue && <span className="chip">Overdue only <button className="icon-btn" aria-label="Clear" onClick={() => setParams({})}><Icon name="close" size={12} /></button></span>}</div>
      <Load q={q}>{() => <><DataTable rows={q.data.results} onRow={(p: any) => setParams({ open: p.id })} empty="No purchase orders" columns={[
        { key: 'n', label: 'PO', render: (p: any) => <><span className="mono">{p.number}</span>{p.version > 1 && <span className="xs muted"> v{p.version}</span>}<div className="xs muted">{p.category}{p.request ? ` · ${p.request}` : ''}</div></> },
        { key: 's', label: 'Supplier', render: (p: any) => p.supplier }, { key: 't', label: 'Total', num: true, render: (p: any) => money(p.total) },
        { key: 'd', label: 'Expected', render: (p: any) => <span style={{ color: p.overdue ? 'var(--c-danger)' : undefined }}>{fmtDate(p.expectedDelivery)}</span> },
        { key: 'b', label: 'Buyer', render: (p: any) => <span className="xs">{p.buyer}</span> }, { key: 'st', label: 'Status', render: (p: any) => <Status value={tone(p.status)} label={p.statusLabel} /> }]} />
        <Pager page={q.data.page} hasNext={q.data.hasNext} count={q.data.count} onPage={(p) => setF({ ...f, page: p })} /></>}</Load></Card>
    {open && <OrderDrawer id={open} onClose={() => setParams({})} />}</>;
}

function OrderDrawer({ id, onClose }: { id: string; onClose: () => void }) {
  const q = useP(`orders/${id}`);
  const act = useAction((b: any) => procurement.post(`orders/${id}/${b.action}`, b), [PK], 'Done');
  const [dlg, setDlg] = useState('');
  const d = q.data;
  return <Dialog title={d ? `${d.number} v${d.version} · ${d.supplier}` : 'Purchase order'} wide onClose={onClose}><Load q={q}>{() => <div className="stack">
    <div className="row row--wrap"><Status value={tone(d.status)} label={d.statusLabel} />{d.emergency && <span className="flag flag--overdue">emergency</span>}
      <span className="small muted">{d.category} · match: {humanize(d.matchMode)} · expected {fmtDate(d.expectedDelivery)}{d.confirmedDelivery ? ` (confirmed ${fmtDate(d.confirmedDelivery)})` : ''}
        {d.request ? ` · ${d.request}` : ''}{d.event ? ` · ${d.event}` : ''}{d.contract ? ` · contract ${d.contract}` : ''}</span></div>
    {d.confirmation && <Alert tone={d.confirmation === 'accepted' ? 'success' : 'warning'}>Supplier: {humanize(d.confirmation)}{d.confirmationNote ? ` — ${d.confirmationNote}` : ''}</Alert>}
    {d.commitment && <p className="xs muted">Budget commitment {money(d.commitment.amount)} · consumed {money(d.commitment.consumed)} · open {money(d.commitment.open)}</p>}
    <DataTable rows={d.lines} columns={[{ key: 'l', label: 'Line', render: (l: any) => <>{l.lineNo}. {l.description}<div className="xs muted">{l.service ? 'service' : `${Number(l.quantity)} ${l.uom}`}{l.capex ? ' · capex → asset' : ''}{l.inventory ? ' · inventory' : ''}</div></> },
      { key: 'p', label: 'Price', num: true, render: (l: any) => money(l.unitPrice) }, { key: 't', label: 'Amount', num: true, render: (l: any) => money(l.lineTotal) },
      { key: 'r', label: 'Received / accepted', render: (l: any) => (l.service ? `${money(l.serviceAccepted)} accepted` : `${Number(l.received)} / ${Number(l.accepted)}`) },
      { key: 'i', label: 'Invoiced', num: true, render: (l: any) => Number(l.invoiced) }]} />
    <p className="small" style={{ textAlign: 'right' }}>Subtotal {money(d.subtotal)} · Tax {money(d.tax)} · Shipping {money(d.shipping)} · <strong>Total {money(d.total)}</strong></p>
    {(d.carrier || d.trackingNumber) && <p className="small">Shipment: {d.carrier} {d.trackingNumber} {d.deliveryStatus && `· ${d.deliveryStatus}`}</p>}
    {d.invoices.length > 0 && <Card title="Supplier invoices (Finance)" flush><DataTable rows={d.invoices} columns={[{ key: 'n', label: 'Invoice', render: (i: any) => <>{i.supplierInvoice}<div className="xs muted">{i.number}</div></> },
      { key: 't', label: 'Total', num: true, render: (i: any) => money(i.total) }, { key: 'm', label: 'Match', render: (i: any) => <><Status value={tone(i.match)} label={humanize(i.match)} />{i.issues.length > 0 && <div className="xs" style={{ color: 'var(--c-danger)' }}>{i.issues.join(' · ')}</div>}</> },
      { key: 's', label: 'Status', render: (i: any) => humanize(i.status) }]} /></Card>}
    {d.receipts.length > 0 && <p className="small">Receipts: {d.receipts.map((r: any) => `${r.number} (${fmtDate(r.date)}, ${r.status}${r.inventory === 'pending' ? ', inventory update pending' : ''})`).join(' · ')}</p>}
    {d.versions.length > 0 && <p className="xs muted">Versions: {d.versions.map((v: any) => `v${v.version} ${v.reason} (${v.by ?? '—'}, ${fmtDate(v.at)})`).join(' · ')}</p>}
    {d.amendments.length > 0 && <p className="xs muted">Amendments: {d.amendments.map((a: any) => `${a.reason} → ${money(a.newTotal)} (${humanize(a.status)})`).join(' · ')}</p>}
    <div className="row row--wrap">
      {d.can.submit && <Button onClick={() => act.mutate({ action: 'submit' })}>Submit for approval</Button>}
      {d.status === 'approved' && <Button onClick={() => act.mutate({ action: 'send' })}>Mark sent to supplier</Button>}
      {['sent', 'approved'].includes(d.status) && <Button variant="outline" onClick={() => setDlg('confirm')}>Supplier response</Button>}
      {d.can.receive && <Button variant="outline" onClick={() => setDlg('receive')}>Receive goods</Button>}
      {d.can.receive && d.lines.some((l: any) => l.service) && <Button variant="outline" onClick={() => setDlg('service')}>Confirm service delivery</Button>}
      {d.can.invoice && !['draft', 'pending_approval', 'cancelled'].includes(d.status) && <Button variant="outline" onClick={() => setDlg('invoice')}>Record supplier invoice</Button>}
      {d.can.amend && <Button variant="ghost" onClick={() => setDlg('amend')}>Amend</Button>}
      {!['draft', 'pending_approval', 'cancelled', 'closed'].includes(d.status) && <Button variant="ghost" onClick={() => setDlg('delivery')}>Delivery tracking</Button>}
      {!['cancelled', 'completed', 'closed'].includes(d.status) && <Button variant="ghost" onClick={() => setDlg('cancel')}>Cancel / close</Button>}
    </div>
    {dlg === 'confirm' && <FormDialog title="Supplier confirmation" onClose={() => setDlg('')} initial={{ result: 'accepted' }}
      fields={[{ name: 'result', label: 'Supplier response', type: 'select', options: ['accepted', 'accepted_with_changes', 'partially_accepted', 'rejected'].map((x) => ({ value: x, label: humanize(x) })) },
        { name: 'confirmed_delivery', label: 'Confirmed delivery date', type: 'date', half: true }, { name: 'note', label: 'Changes / notes', type: 'textarea' }]}
      onSubmit={(v) => procurement.post(`orders/${id}/confirm`, v)} onDone={() => void q.refetch()} />}
    {dlg === 'receive' && <FormDialog title="Goods receipt" wide onClose={() => setDlg('')} submitLabel="Record receipt" initial={{ received_on: today() }}
      intro={<p className="small muted">The buyer who raised this order can't receive it. Partial deliveries leave the rest open.</p>}
      fields={[...d.lines.filter((l: any) => !l.service).flatMap((l: any, i: number) => [{ name: `rec${i}`, label: `Received — ${l.description} (open ${Number(l.remaining)})`, type: 'number' as const, half: true },
        { name: `rej${i}`, label: 'Rejected / damaged', type: 'number' as const, half: true }]),
        { name: 'received_on', label: 'Received on', type: 'date', half: true }, { name: 'delivery_note', label: 'Delivery note no.', half: true }, { name: 'condition', label: 'Condition' },
        { name: 'inspect', label: 'Hold for quality inspection', type: 'checkbox' }]}
      onSubmit={(v: any) => procurement.post(`orders/${id}/receive`, { receivedOn: v.receivedOn, deliveryNote: v.deliveryNote, condition: v.condition, inspect: v.inspect,
        lines: d.lines.filter((l: any) => !l.service).map((l: any, i: number) => ({ lineId: l.id, receivedQty: v[`rec${i}`] || 0, rejectedQty: v[`rej${i}`] || 0 })).filter((x: any) => Number(x.receivedQty) > 0) })}
      onDone={() => void q.refetch()} />}
    {dlg === 'service' && <FormDialog title="Service delivery" onClose={() => setDlg('')} submitLabel="Submit for acceptance"
      intro={<p className="small muted">The requester (or a quality inspector) accepts it — not the buyer or the person submitting.</p>}
      fields={[{ name: 'line_id', label: 'Service line', type: 'select', required: true, options: d.lines.filter((l: any) => l.service).map((l: any) => ({ value: l.id, label: l.description })) },
        { name: 'amount', label: 'Value delivered', type: 'number', required: true, half: true }, { name: 'completion_pct', label: 'Completion %', type: 'number', half: true },
        { name: 'period_from', label: 'From', type: 'date', half: true }, { name: 'period_to', label: 'To', type: 'date', half: true }, { name: 'deliverables', label: 'Deliverables completed', type: 'textarea', required: true }]}
      onSubmit={(v) => procurement.post(`orders/${id}/service-receipt`, v)} onDone={() => void q.refetch()} />}
    {dlg === 'invoice' && <FormDialog title="Record supplier invoice" onClose={() => setDlg('')} submitLabel="Create bill in Finance"
      intro={<p className="small muted">Creates a draft vendor bill in Finance for accepted, uninvoiced quantities and checks the {humanize(d.matchMode)} match.</p>}
      fields={[{ name: 'supplier_invoice_number', label: "Supplier's invoice number", required: true, half: true }, { name: 'issue_date', label: 'Invoice date', type: 'date', half: true }]}
      onSubmit={(v) => procurement.post(`orders/${id}/invoice`, v)} onDone={() => void q.refetch()} />}
    {dlg === 'amend' && <FormDialog title={`Amend ${d.number} (v${d.version})`} wide onClose={() => setDlg('')} submitLabel="Send amendment for approval"
      fields={[...d.lines.flatMap((l: any, i: number) => [{ name: `q${i}`, label: `Qty — ${l.description}`, type: 'number' as const, half: true }, { name: `p${i}`, label: 'Unit price', type: 'number' as const, half: true }]),
        { name: 'expected_delivery', label: 'New expected delivery', type: 'date', half: true }, { name: 'reason', label: 'Reason', type: 'textarea', required: true }]}
      initial={Object.fromEntries(d.lines.flatMap((l: any, i: number) => [[`q${i}`, Number(l.quantity)], [`p${i}`, l.unitPrice]]))}
      onSubmit={(v: any) => procurement.post(`orders/${id}/amend`, { reason: v.reason, changes: { expectedDelivery: v.expectedDelivery || undefined,
        lines: d.lines.map((l: any, i: number) => ({ lineId: l.id, quantity: v[`q${i}`], unitPrice: v[`p${i}`] })) } })} onDone={() => void q.refetch()} />}
    {dlg === 'delivery' && <FormDialog title="Delivery tracking" onClose={() => setDlg('')} initial={{ carrier: d.carrier, tracking_number: d.trackingNumber, delivery_status: d.deliveryStatus }}
      fields={[{ name: 'carrier', label: 'Carrier', half: true }, { name: 'tracking_number', label: 'Tracking number', half: true }, { name: 'delivery_status', label: 'Status', half: true },
        { name: 'confirmed_delivery', label: 'Confirmed delivery', type: 'date', half: true }]} onSubmit={(v) => procurement.post(`orders/${id}/delivery`, v)} onDone={() => void q.refetch()} />}
    {dlg === 'cancel' && <FormDialog title="Cancel or close the order" onClose={() => setDlg('')} initial={{ action: d.lines.some((l: any) => Number(l.received) > 0) ? 'close' : 'cancel' }}
      fields={[{ name: 'action', label: 'Action', type: 'select', options: [{ value: 'cancel', label: 'Cancel (nothing received)' }, { value: 'close', label: 'Close (stop receiving the rest)' }] },
        { name: 'reason', label: 'Reason', type: 'textarea', required: true }]} onSubmit={(v: any) => procurement.post(`orders/${id}/${v.action}`, v)} onDone={() => void q.refetch()} />}
  </div>}</Load></Dialog>;
}

// ---------------------------------------------------------------------------------------------------------------------
export function Receiving() {
  const [params, setParams] = useSearchParams();
  const tab = (params.get('tab') ?? 'goods') as 'goods' | 'services' | 'open';
  const q = useP('receipts');
  const open = useP('orders', { receivable: '1' }, tab === 'open');
  const [inspect, setInspect] = useState<any>(null);
  const [decide, setDecide] = useState<any>(null);
  return <>{PT('Receiving', 'Goods and service receipts, partial deliveries and quality inspection.')}
    <Tabs value={tab} onChange={(t) => setParams({ tab: t })} items={[{ value: 'open', label: 'Awaiting receipt' }, { value: 'goods', label: 'Goods receipts' }, { value: 'services', label: 'Service confirmations' }]} />
    {tab === 'open' && <Load q={open}>{() => <Card flush><DataTable rows={open.data.results} empty="Nothing awaiting receipt" columns={[{ key: 'n', label: 'PO', render: (p: any) => <Link to={`/procurement/orders?open=${p.id}`} className="mono">{p.number}</Link> },
      { key: 's', label: 'Supplier', render: (p: any) => p.supplier }, { key: 'd', label: 'Expected', render: (p: any) => <span style={{ color: p.overdue ? 'var(--c-danger)' : undefined }}>{fmtDate(p.expectedDelivery)}</span> },
      { key: 'st', label: 'Status', render: (p: any) => p.statusLabel }]} /></Card>}</Load>}
    {tab !== 'open' && <Load q={q}>{() => tab === 'goods' ? <Card flush><DataTable rows={q.data.goods} empty="No receipts" columns={[
      { key: 'n', label: 'Receipt', render: (g: any) => <><span className="mono">{g.number}</span><div className="xs muted">{g.order} · {g.supplier}</div></> },
      { key: 'd', label: 'Date', render: (g: any) => fmtDate(g.date) }, { key: 'l', label: 'Lines', render: (g: any) => <span className="xs">{g.lines.map((l: any) => `${l.description}: ${Number(l.received)} recv, ${Number(l.rejected) + Number(l.damaged)} rej`).join(' · ')}</span> },
      { key: 'b', label: 'By', render: (g: any) => <span className="xs">{g.by}</span> },
      { key: 's', label: 'Status', render: (g: any) => <><Status value={tone(g.status === 'inspection' ? 'pending' : g.status)} label={humanize(g.status)} />{g.inventory === 'pending' && <div className="xs muted">Inventory update pending</div>}</> },
      { key: 'a', label: '', render: (g: any) => g.status === 'inspection' && q.data.canInspect && <Button size="sm" onClick={() => setInspect(g)}>Inspect</Button> }]} /></Card>
      : <Card flush><DataTable rows={q.data.services} empty="No service confirmations" columns={[{ key: 'n', label: 'Confirmation', render: (s: any) => <><span className="mono">{s.number}</span><div className="xs muted">{s.order} · {s.supplier}</div></> },
        { key: 'd', label: 'Deliverables', render: (s: any) => <span className="small">{s.deliverables}</span> }, { key: 'a', label: 'Value', num: true, render: (s: any) => money(s.amount) },
        { key: 's', label: 'Status', render: (s: any) => <Status value={tone(s.status)} label={humanize(s.status)} /> },
        { key: 'x', label: '', render: (s: any) => s.canDecide && <Button size="sm" onClick={() => setDecide(s)}>Accept / reject</Button> }]} /></Card>}</Load>}
    {inspect && <FormDialog title={`Inspect ${inspect.number}`} onClose={() => setInspect(null)} initial={{ result: 'accepted' }}
      fields={[{ name: 'result', label: 'Result', type: 'select', options: [{ value: 'accepted', label: 'Accepted' }, { value: 'partial', label: 'Partially accepted' }, { value: 'rejected', label: 'Rejected' }] },
        ...inspect.lines.map((l: any, i: number) => ({ name: `rej${i}`, label: `Rejected at inspection — ${l.description}`, type: 'number' as const, half: true })),
        { name: 'notes', label: 'Findings', type: 'textarea' }, { name: 'corrective_action', label: 'Corrective action', type: 'textarea' }]}
      onSubmit={(v: any) => procurement.post(`receipts/${inspect.id}/inspect`, { result: v.result, notes: v.notes, correctiveAction: v.correctiveAction,
        rejections: Object.fromEntries(inspect.lines.map((l: any, i: number) => [l.id, v[`rej${i}`] || 0])) })} onDone={() => void q.refetch()} />}
    {decide && <FormDialog title={`Service ${decide.number}`} onClose={() => setDecide(null)} initial={{ decision: 'accepted' }}
      fields={[{ name: 'decision', label: 'Decision', type: 'select', options: [{ value: 'accepted', label: 'Accept' }, { value: 'rejected', label: 'Reject' }] }, { name: 'note', label: 'Note', type: 'textarea' }]}
      onSubmit={(v) => procurement.post(`receipts/${decide.id}/decide`, v)} onDone={() => void q.refetch()} />}
    {tab === 'goods' && !q.data?.goods?.length && !q.isPending && <Empty title="Receipts appear here" message="Receive goods from a purchase order." />}</>;
}
