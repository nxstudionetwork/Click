/* eslint-disable @typescript-eslint/no-explicit-any */
/** Finance — money movement: receivables, payables, payments, settlements, statements, agreements, disputes, expenses,
 * budgets, assets and reconciliation. */
import { useRef, useState } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { Button, Icon, useToast } from '@click/ui';
import { apiMessage, finance, people } from '../../lib/api';
import { fmtDate, humanize } from '../../lib/format';
import { DataTable, FormDialog } from '../../components/forms';
import { DownloadButton, Kpis, money, useAction } from '../../components/ModuleShell';
import { Alert, Card, Dialog, Empty, Pager, Status, Tabs } from '../../components/ui';
import { Aging, FK, FT, LinesEditor, Load, Range, monthStart, today, useF, useLookups } from './index';

const tone = (s: string) => (['paid', 'issued', 'approved', 'active', 'settled', 'matched', 'resolved', 'reconciled'].includes(s) ? 'approved'
  : ['rejected', 'void', 'failed', 'exception', 'cancelled'].includes(s) ? 'rejected' : 'pending');

// ---------------------------------------------------------------------------------------------------------------------
function DocList({ kind }: { kind: 'receivable' | 'payable' }) {
  const [params, setParams] = useSearchParams();
  const [f, setF] = useState({ status: '', q: '', page: 1 });
  const overdue = params.get('overdue') === '1';
  const q = useF('invoices', { kind, status: f.status || undefined, q: f.q || undefined, page: f.page, overdue: overdue ? '1' : undefined });
  const aging = useF('reports', { r: kind === 'receivable' ? 'ar' : 'ap' });
  const [tab, setTab] = useState<'docs' | 'aging'>('docs');
  const open = params.get('open');
  const lk = useLookups();
  const [form, setForm] = useState<any>({ partyType: kind === 'payable' ? 'supplier' : 'customer', revenueType: 'service_fee' });
  const [lines, setLines] = useState<any[]>([{}]);
  const create = useAction((b: any) => finance.post('invoices', b), [FK], kind === 'payable' ? 'Bill saved as draft' : 'Invoice saved as draft');
  return <>
    {FT(kind === 'receivable' ? 'Receivables & invoices' : 'Payables & vendor bills',
      kind === 'receivable' ? 'Customer and partner invoices, credit and debit notes, receipts and aging.' : 'Vendor bills are matched to the PO and receipt, approved, then paid in a payment run.',
      <><DownloadButton api={finance} path="invoices" query={{ kind }} filename={`${kind}s.csv`} /><Button onClick={() => setParams({ new: '1' })}><Icon name="plus" size={16} />{kind === 'receivable' ? 'New invoice' : 'New bill'}</Button></>)}
    <Tabs value={tab} onChange={setTab} items={[{ value: 'docs', label: kind === 'receivable' ? 'Invoices & notes' : 'Bills' }, { value: 'aging', label: 'Aging' }]} />
    {tab === 'aging' ? <Load q={aging}>{() => <Aging d={aging.data.data} />}</Load> : <Card flush>
      <div className="toolbar"><div className="search-input"><Icon name="search" size={16} /><input value={f.q} onChange={(e) => setF({ ...f, q: e.target.value, page: 1 })} placeholder="Number or party" aria-label="Search" /></div>
        <select className="field__input" aria-label="Status" value={f.status} onChange={(e) => setF({ ...f, status: e.target.value, page: 1 })}><option value="">All</option>
          {['draft', 'pending_approval', 'issued', 'partially_paid', 'paid', 'disputed', 'void'].map((s) => <option key={s} value={s}>{humanize(s)}</option>)}</select>
        {overdue && <span className="chip">Overdue only <button className="icon-btn" aria-label="Clear" onClick={() => setParams({})}><Icon name="close" size={12} /></button></span>}</div>
      <Load q={q}>{() => <><DataTable rows={q.data.results} onRow={(i: any) => setParams({ open: i.id })} empty="Nothing here" columns={[
        { key: 'n', label: 'Document', render: (i: any) => <><span className="mono">{i.number || 'Draft'}</span>{i.supplierInvoiceNumber && <span className="xs muted"> · {i.supplierInvoiceNumber}</span>}<div className="xs muted">{i.kindLabel}{i.original ? ` for ${i.original}` : ''}</div></> },
        { key: 'p', label: 'Party', render: (i: any) => i.party }, { key: 'd', label: 'Due', render: (i: any) => <span style={{ color: i.overdue ? 'var(--c-danger)' : undefined }}>{fmtDate(i.dueDate)}</span> },
        { key: 't', label: 'Total', num: true, render: (i: any) => money(i.total, i.currency) }, { key: 'o', label: 'Outstanding', num: true, render: (i: any) => money(i.outstanding, i.currency) },
        ...(kind === 'payable' ? [{ key: 'm', label: 'Match', render: (i: any) => <Status value={i.matchStatus === 'matched' ? 'approved' : i.matchStatus === 'exception' ? 'rejected' : 'neutral'} label={humanize(i.matchStatus)} /> }] : []),
        { key: 's', label: 'Status', render: (i: any) => <Status value={tone(i.status)} label={humanize(i.status)} /> }]} />
        <Pager page={q.data.page} hasNext={q.data.hasNext} count={q.data.count} onPage={(p) => setF({ ...f, page: p })} /></>}</Load></Card>}
    {open && <DocDrawer id={open} onClose={() => setParams({})} />}
    {params.get('new') === '1' && <Dialog title={kind === 'receivable' ? 'New invoice' : 'New vendor bill'} wide onClose={() => setParams({})} footer={<>
      <Button variant="outline" onClick={() => setParams({})}>Cancel</Button>
      <Button loading={create.isPending} onClick={() => create.mutate({ ...form, kind: kind === 'payable' ? 'vendor_bill' : (form.partyType === 'partner' ? 'partner_invoice' : 'customer_invoice'), lines },
        { onSuccess: () => { setParams({}); setLines([{}]); } })}>Save draft</Button></>}>
      <div className="form-grid">
        <label className="field"><span className="field__label">{kind === 'payable' ? 'Supplier' : 'Bill to'}</span><input className="field__input" value={form.partyName ?? ''} onChange={(e) => setForm({ ...form, partyName: e.target.value })} /></label>
        {kind === 'receivable' ? <label className="field"><span className="field__label">Party type</span><select className="field__input" value={form.partyType} onChange={(e) => setForm({ ...form, partyType: e.target.value })}>
          <option value="customer">Customer / business</option><option value="partner">Click partner</option><option value="other">Other</option></select></label>
          : <label className="field"><span className="field__label">Supplier invoice number</span><input className="field__input" value={form.supplierInvoiceNumber ?? ''} onChange={(e) => setForm({ ...form, supplierInvoiceNumber: e.target.value })} /></label>}
        {kind === 'receivable' && <label className="field"><span className="field__label">Revenue type</span><select className="field__input" value={form.revenueType} onChange={(e) => setForm({ ...form, revenueType: e.target.value })}>
          {['platform_commission', 'service_fee', 'subscription', 'advertising', 'sponsored', 'booking_fee', 'membership', 'other'].map((v) => <option key={v} value={v}>{humanize(v)}</option>)}</select></label>}
        <label className="field"><span className="field__label">Issue date</span><input type="date" className="field__input" value={form.issueDate ?? today()} onChange={(e) => setForm({ ...form, issueDate: e.target.value })} /></label>
        <label className="field"><span className="field__label">Due date</span><input type="date" className="field__input" value={form.dueDate ?? ''} onChange={(e) => setForm({ ...form, dueDate: e.target.value })} /></label>
        <label className="field"><span className="field__label">Cost center</span><select className="field__input" value={form.costCenterId ?? ''} onChange={(e) => setForm({ ...form, costCenterId: e.target.value })}>
          <option value="">—</option>{(lk.data?.costCenters ?? []).map((c: any) => <option key={c.id} value={c.id}>{c.code} {c.name}</option>)}</select></label>
      </div>
      <LinesEditor lines={lines} setLines={setLines} kind="document" />
    </Dialog>}
  </>;
}
export const Receivables = () => <DocList kind="receivable" />;
export const Payables = () => <DocList kind="payable" />;

function DocDrawer({ id, onClose }: { id: string; onClose: () => void }) {
  const q = useF(`invoices/${id}`);
  const lk = useLookups();
  const act = useAction((b: any) => finance.post(`invoices/${id}/${b.action}`, b), [FK], 'Done');
  const [dlg, setDlg] = useState<'' | 'note' | 'receive' | 'submit' | 'pay'>('');
  const d = q.data;
  return <Dialog title={d ? `${d.number || 'Draft'} · ${d.party}` : 'Document'} onClose={onClose} wide><Load q={q}>{() => <div className="stack">
    <div className="row row--wrap"><Status value={tone(d.status)} label={humanize(d.status)} /><span className="chip">{d.kindLabel}</span>
      {d.kind === 'vendor_bill' && <Status value={d.matchStatus === 'matched' ? 'approved' : d.matchStatus === 'exception' ? 'rejected' : 'neutral'} label={`Match: ${humanize(d.matchStatus)}`} />}
      <span className="small muted">Issued {fmtDate(d.issueDate)} · due {fmtDate(d.dueDate)}{d.source ? ` · from ${d.source}` : ''}</span></div>
    {d.matchDetail?.issues?.length > 0 && <Alert tone={d.matchStatus === 'overridden' ? 'warning' : 'error'}>{d.matchDetail.issues.join(' · ')}{d.matchDetail.overrideReason ? ` — exception: ${d.matchDetail.overrideReason}` : ''}</Alert>}
    <DataTable rows={d.lines.map((l: any, i: number) => ({ ...l, id: String(i) }))} columns={[{ key: 'd', label: 'Line', render: (l: any) => <>{l.description}<div className="xs muted">{l.account}</div></> },
      { key: 'q', label: 'Qty', num: true, render: (l: any) => Number(l.quantity) }, { key: 'p', label: 'Price', num: true, render: (l: any) => money(l.unitPrice) },
      { key: 't', label: 'Tax', num: true, render: (l: any) => money(l.taxAmount) }, { key: 'a', label: 'Amount', num: true, render: (l: any) => money(l.lineTotal) }]} />
    <p className="small" style={{ textAlign: 'right' }}>Subtotal {money(d.subtotal)} · Tax {money(d.taxTotal)} · <strong>Total {money(d.total)}</strong> · Paid {money(d.paid)}</p>
    {d.journalId && <Link to={`/finance/journals?open=${d.journalId}`} className="small">Ledger entry {d.journal} →</Link>}
    {d.notes.length > 0 && <Card title="Credit & debit notes" flush><DataTable rows={d.notes} columns={[{ key: 'n', label: 'Note', render: (n: any) => <span className="mono">{n.number || 'Pending'}</span> },
      { key: 't', label: 'Amount', num: true, render: (n: any) => money(n.total) }, { key: 's', label: 'Status', render: (n: any) => humanize(n.status) }]} /></Card>}
    {d.payments.length > 0 && <Card title="Payments" flush><DataTable rows={d.payments} columns={[{ key: 'n', label: 'Payment', render: (p: any) => <span className="mono">{p.number}</span> },
      { key: 'd', label: 'Date', render: (p: any) => fmtDate(p.date) }, { key: 'a', label: 'Amount', num: true, render: (p: any) => money(p.amount) }, { key: 's', label: 'Status', render: (p: any) => humanize(p.status) }]} /></Card>}
    <div className="row row--wrap">
      {d.status === 'draft' && d.kind !== 'vendor_bill' && <Button onClick={() => act.mutate({ action: 'issue' })}>Issue & post</Button>}
      {d.status === 'draft' && d.kind === 'vendor_bill' && <><Button variant="outline" onClick={() => act.mutate({ action: 'match' })}>Check three-way match</Button><Button onClick={() => setDlg('submit')}>Submit for approval</Button></>}
      {['issued', 'partially_paid'].includes(d.status) && d.kind !== 'vendor_bill' && !d.original && <Button variant="outline" onClick={() => setDlg('receive')}>Record receipt</Button>}
      {['issued', 'partially_paid'].includes(d.status) && d.kind === 'vendor_bill' && <Button variant="outline" onClick={() => setDlg('pay')}>Prepare payment</Button>}
      {['issued', 'partially_paid', 'paid'].includes(d.status) && !d.original && <Button variant="ghost" onClick={() => setDlg('note')}>Credit / debit note</Button>}
      {d.status === 'draft' && <Button variant="ghost" onClick={() => act.mutate({ action: 'void', reason: 'Draft discarded' })}>Discard draft</Button>}
    </div>
    {dlg === 'submit' && <FormDialog title="Submit bill" onClose={() => setDlg('')} submitLabel="Submit"
      intro={<p className="small muted">The bill is checked against its purchase order and receipt. If it doesn’t match, give a reason to request an approved exception.</p>}
      fields={[{ name: 'override_reason', label: 'Exception reason (only if it doesn’t match)', type: 'textarea' }]} onSubmit={(v) => finance.post(`invoices/${id}/submit`, v)} onDone={() => void q.refetch()} />}
    {dlg === 'note' && <FormDialog title="Credit or debit note" onClose={() => setDlg('')} submitLabel="Send for approval" initial={{ kind: 'credit_note' }}
      fields={[{ name: 'kind', label: 'Type', type: 'select', options: [{ value: 'credit_note', label: 'Credit note (reduce)' }, { value: 'debit_note', label: 'Debit note (increase)' }] },
        { name: 'amount', label: 'Amount incl. tax', type: 'number', required: true }, { name: 'reason', label: 'Reason', type: 'textarea', required: true }]}
      onSubmit={(v) => finance.post(`invoices/${id}/${v.kind}`, v)} onDone={() => void q.refetch()} />}
    {dlg === 'receive' && <FormDialog title="Record receipt" onClose={() => setDlg('')} initial={{ amount: d.outstanding, date: today() }}
      fields={[{ name: 'amount', label: 'Amount', type: 'number', required: true, half: true }, { name: 'date', label: 'Date', type: 'date', half: true },
        { name: 'bank_account_id', label: 'Into', type: 'select', required: true, options: (lk.data?.bankAccounts ?? []).map((b: any) => ({ value: b.id, label: `${b.name} ${b.masked}` })) },
        { name: 'reference', label: 'Reference (UTR / cheque)' }]} onSubmit={(v) => finance.post(`invoices/${id}/receive`, v)} onDone={() => void q.refetch()} />}
    {dlg === 'pay' && <FormDialog title="Prepare payment" onClose={() => setDlg('')} submitLabel="Send for approval" initial={{ amount: d.outstanding }}
      intro={<p className="small muted">Someone else approves it, and someone with release rights pays it.</p>}
      fields={[{ name: 'amount', label: 'Amount', type: 'number', half: true }, { name: 'bank_account_id', label: 'From', type: 'select', half: true, options: (lk.data?.bankAccounts ?? []).map((b: any) => ({ value: b.id, label: b.name })) },
        { name: 'confirm_not_duplicate', label: 'I checked this isn’t a duplicate payment', type: 'checkbox' }]}
      onSubmit={(v) => finance.post('payments', { ...v, invoiceId: id })} onDone={() => void q.refetch()} />}
  </div>}</Load></Dialog>;
}

// ---------------------------------------------------------------------------------------------------------------------
export function Payments() {
  const [f, setF] = useState({ status: '', page: 1 });
  const q = useF('payments', { status: f.status || undefined, page: f.page });
  const lk = useLookups();
  const [run, setRun] = useState(false);
  const [exec, setExec] = useState<any>(null);
  const execRun = useAction((id: string) => finance.post(`payment-runs/${id}/execute`), [FK], 'Payment run released');
  return <>{FT('Payments & payment runs', 'Prepared by one person, approved by another, released by someone with release rights. Duplicates are blocked.',
    <Button onClick={() => setRun(true)}><Icon name="plus" size={16} />New payment run</Button>)}
    <Load q={q}>{() => <div className="stack stack--lg">
      {q.data.runs.length > 0 && <Card title="Payment runs" flush><DataTable rows={q.data.runs} columns={[{ key: 'n', label: 'Run', render: (r: any) => <span className="mono">{r.number}</span> },
        { key: 'p', label: 'Payments', num: true, render: (r: any) => r.payments }, { key: 't', label: 'Total', num: true, render: (r: any) => money(r.total) },
        { key: 's', label: 'Status', render: (r: any) => <Status value={tone(r.status)} label={humanize(r.status)} /> },
        { key: 'a', label: '', render: (r: any) => <>{r.approvalId && <Link to={`/approvals/${r.approvalId}`} className="small">Approval</Link>}
          {r.status === 'approved' && <Button size="sm" onClick={() => execRun.mutate(r.id)}>Release</Button>}</> }]} /></Card>}
      <Card flush><div className="toolbar"><select className="field__input" aria-label="Status" value={f.status} onChange={(e) => setF({ status: e.target.value, page: 1 })}><option value="">All</option>
        {['pending_approval', 'approved', 'paid', 'failed', 'void'].map((s) => <option key={s} value={s}>{humanize(s)}</option>)}</select></div>
        <DataTable rows={q.data.results} empty="No payments" columns={[{ key: 'n', label: 'Payment', render: (p: any) => <><span className="mono">{p.number}</span><div className="xs muted">{humanize(p.purpose)}{p.invoice ? ` · ${p.invoice}` : ''}{p.run ? ` · ${p.run}` : ''}</div></> },
          { key: 'p', label: 'Party', render: (p: any) => p.party }, { key: 'd', label: 'Direction', render: (p: any) => (p.direction === 'in' ? 'Received' : 'Paid out') },
          { key: 'a', label: 'Amount', num: true, render: (p: any) => money(p.amount) }, { key: 'r', label: 'Reconciled', render: (p: any) => (p.reconciled ? '✓' : '') },
          { key: 's', label: 'Status', render: (p: any) => <Status value={tone(p.status)} label={humanize(p.status)} /> },
          { key: 'x', label: '', render: (p: any) => p.status === 'approved' && !p.run && <Button size="sm" onClick={() => setExec(p)}>Release</Button> }]} />
        <Pager page={q.data.page} hasNext={q.data.hasNext} count={q.data.count} onPage={(p) => setF({ ...f, page: p })} /></Card>
    </div>}</Load>
    {run && <FormDialog title="New payment run" onClose={() => setRun(false)} submitLabel="Create & send for approval" initial={{ due_by: today(), include_reimbursements: true }}
      intro={<p className="small muted">Collects approved bills due by the date (not those with match exceptions) and approved expense claims.</p>}
      fields={[{ name: 'due_by', label: 'Bills due by', type: 'date', half: true }, { name: 'bank_account_id', label: 'Pay from', type: 'select', half: true, options: (lk.data?.bankAccounts ?? []).map((b: any) => ({ value: b.id, label: b.name })) },
        { name: 'include_reimbursements', label: 'Include approved expense reimbursements', type: 'checkbox' }]} onSubmit={(v) => finance.post('payment-runs', v)} onDone={() => void q.refetch()} />}
    {exec && <FormDialog title={`Release ${exec.number}`} onClose={() => setExec(null)} submitLabel={`Pay ${money(exec.amount)}`}
      fields={[{ name: 'bank_account_id', label: 'From', type: 'select', required: true, options: (lk.data?.bankAccounts ?? []).map((b: any) => ({ value: b.id, label: `${b.name} ${b.masked}` })) },
        { name: 'reference', label: 'Bank reference (UTR)' }]} onSubmit={(v) => finance.post(`payments/${exec.id}/execute`, v)} onDone={() => void q.refetch()} />}</>;
}

// ---------------------------------------------------------------------------------------------------------------------
export function Settlements() {
  const [params, setParams] = useSearchParams();
  const q = useF('settlements');
  const lk = useLookups();
  const open = params.get('open');
  const d = useF(`settlements/${open}`, {}, !!open);
  const [create, setCreate] = useState(false);
  const [pay, setPay] = useState(false);
  const [adj, setAdj] = useState(false);
  const partners = useF('partners', {}, adj);
  return <>{FT('Partner settlements', 'Eligible transactions → commission & fees → refunds & deductions → net partner payable → approval → payment → reconciliation.',
    <><Button variant="outline" onClick={() => setAdj(true)}>Partner adjustment</Button><Button onClick={() => setCreate(true)}><Icon name="plus" size={16} />New settlement batch</Button></>)}
    <Load q={q}>{() => <div className="stack stack--lg">
      <Kpis items={[{ label: 'Partner payable (liability)', value: money(q.data.liability) }, { label: 'Waiting to be batched', value: money(q.data.pendingPool.partnerShare),
        hint: `${q.data.pendingPool.transactions} transactions · ${q.data.pendingPool.partners} partners` }]} />
      <Card title="Batches" flush><DataTable rows={q.data.results} onRow={(b: any) => setParams({ open: b.id })} empty="No settlement batches yet" columns={[
        { key: 'n', label: 'Batch', render: (b: any) => <><span className="mono">{b.number}</span><div className="xs muted">up to {fmtDate(b.periodTo)} · by {b.createdBy}</div></> },
        { key: 'p', label: 'Partners', num: true, render: (b: any) => b.partners }, { key: 'g', label: 'Partner share', num: true, render: (b: any) => money(b.gross) },
        { key: 'r', label: 'Refunds', num: true, render: (b: any) => money(b.refunds) }, { key: 'd', label: 'Deductions', num: true, render: (b: any) => money(b.deductions) },
        { key: 'net', label: 'Net payable', num: true, render: (b: any) => <strong>{money(b.netPayable)}</strong> }, { key: 's', label: 'Status', render: (b: any) => <Status value={tone(b.status)} label={humanize(b.status)} /> }]} /></Card>
    </div>}</Load>
    {open && <Dialog title={d.data ? `Settlement ${d.data.number}` : 'Settlement'} wide onClose={() => setParams({})}><Load q={d}>{() => <div className="stack">
      <div className="row row--wrap"><Status value={tone(d.data.status)} label={humanize(d.data.status)} /><span className="small">Net payable <strong>{money(d.data.netPayable)}</strong></span>
        {d.data.approvalId && <Link to={`/approvals/${d.data.approvalId}`} className="small">Approval</Link>}
        <span style={{ marginLeft: 'auto' }} className="row"><DownloadButton api={finance} path={`settlements/${open}`} filename={`settlement-${d.data.number}.csv`} />
          {d.data.status === 'approved' && <Button onClick={() => setPay(true)}>Pay partners</Button>}</span></div>
      <DataTable rows={d.data.lines} columns={[{ key: 'p', label: 'Partner', render: (l: any) => <Link to={`/finance/statements?partner=${l.partnerId}`}>{l.partner}</Link> },
        { key: 't', label: 'Txns', num: true, render: (l: any) => l.transactions }, { key: 'g', label: 'Sales', num: true, render: (l: any) => money(l.gross) },
        { key: 'c', label: 'Commission + fees', num: true, render: (l: any) => money(Number(l.commission) + Number(l.platformFee) + Number(l.feeTax)) },
        { key: 'r', label: 'Refunds', num: true, render: (l: any) => money(l.refunds) }, { key: 'a', label: 'Adjustments', num: true, render: (l: any) => money(l.adjustments) },
        { key: 'n', label: 'Net payable', num: true, render: (l: any) => <strong>{money(l.netPayable)}</strong> }, { key: 's', label: '', render: (l: any) => l.payment && <span className="mono xs">{l.payment}</span> }]} />
    </div>}</Load></Dialog>}
    {create && <FormDialog title="New settlement batch" onClose={() => setCreate(false)} submitLabel="Calculate & send for approval" initial={{ period_to: today() }}
      intro={<p className="small muted">Includes unsettled sales and refunds up to the date. Partners whose balance is zero or negative are carried forward.</p>}
      fields={[{ name: 'period_to', label: 'Settle transactions up to', type: 'date', required: true }]} onSubmit={(v) => finance.post('settlements', v)} onDone={() => void q.refetch()} />}
    {pay && <FormDialog title="Pay partners" onClose={() => setPay(false)} submitLabel="Release payouts"
      intro={<p className="small muted">The person who prepared the batch can’t release it.</p>}
      fields={[{ name: 'bank_account_id', label: 'From', type: 'select', required: true, options: (lk.data?.bankAccounts ?? []).map((b: any) => ({ value: b.id, label: `${b.name} ${b.masked}` })) },
        { name: 'reference', label: 'Bank batch reference' }]} onSubmit={(v) => finance.post(`settlements/${open}/pay`, v)} onDone={() => { void q.refetch(); void d.refetch(); }} />}
    {adj && <FormDialog title="Partner adjustment" onClose={() => setAdj(false)} submitLabel="Post adjustment" initial={{ kind: 'deduction' }}
      intro={<p className="small muted">Negative = deduction (penalty, advertising charge). Positive = Click owes more. Posted immediately and included in the next batch.</p>}
      fields={[{ name: 'partner_id', label: 'Partner', type: 'select', required: true, options: (partners.data?.results ?? []).map((p: any) => ({ value: p.id, label: p.name })) },
        { name: 'kind', label: 'Type', type: 'select', half: true, options: ['penalty', 'advertising', 'deduction', 'correction', 'incentive'].map((k) => ({ value: k, label: humanize(k) })) },
        { name: 'amount', label: 'Amount (− deduction)', type: 'number', required: true, half: true }, { name: 'reason', label: 'Reason', type: 'textarea', required: true }]}
      onSubmit={(v) => finance.post('adjustments', v)} onDone={() => void q.refetch()} />}</>;
}

export function Statements() {
  const [params, setParams] = useSearchParams();
  const [term, setTerm] = useState('');
  const partners = useF('partners', { q: term || undefined });
  const pid = params.get('partner') ?? '';
  const [r, setR] = useState({ from: monthStart(), to: today() });
  const q = useF('statements', { partner: pid, ...r }, !!pid);
  return <>{FT('Partner statements', 'Opening balance, sales, commission, fees, refunds, adjustments, payouts and closing balance — drillable to each transaction.')}
    <Card><div className="row row--wrap"><div className="search-input"><Icon name="search" size={16} /><input value={term} onChange={(e) => setTerm(e.target.value)} placeholder="Find partner" aria-label="Find partner" /></div>
      <select className="field__input" aria-label="Partner" value={pid} onChange={(e) => setParams({ partner: e.target.value })}><option value="">Choose partner…</option>
        {(partners.data?.results ?? []).map((p: any) => <option key={p.id} value={p.id}>{p.name}</option>)}</select><Range v={r} set={setR} /></div></Card>
    <div style={{ height: 16 }} />
    {!pid ? <Empty icon="receipt" title="Choose a partner" /> : <Load q={q}>{() => <div className="stack stack--lg">
      <Card title={q.data.partner.name}><dl className="kv">{[['Opening balance', q.data.openingBalance], ['Sales (customer paid)', q.data.sales], ['Commission', q.data.commission], ['Platform fees', q.data.platformFees],
        ['Tax on fees', q.data.taxOnFees], ['Refunds', q.data.refunds], ['Deductions & penalties', q.data.penaltiesAndDeductions], ['Credits & incentives', q.data.creditsAndIncentives],
        ['Payouts', q.data.payments], ['Closing balance (Click owes)', q.data.closingBalance]].map(([k, v]) => <div key={k} style={{ display: 'contents' }}><dt>{k}</dt><dd>{money(v)}</dd></div>)}</dl>
        <p className="xs muted" style={{ marginTop: 8 }}>{q.data.check.note} Check: {money(q.data.check.openingPlusMovements)} {q.data.check.openingPlusMovements === q.data.closingBalance ? '✓' : '≠ closing — investigate'}</p></Card>
      <Card title="Transactions" flush><DataTable rows={q.data.detail.map((x: any, i: number) => ({ ...x, id: String(i) }))} empty="No transactions" columns={[
        { key: 'd', label: 'Date', render: (x: any) => fmtDate(x.date) }, { key: 'k', label: 'Kind', render: (x: any) => humanize(x.kind) }, { key: 'g', label: 'Paid', num: true, render: (x: any) => money(x.gross) },
        { key: 'c', label: 'Commission', num: true, render: (x: any) => money(x.commission) }, { key: 'p', label: 'Partner share', num: true, render: (x: any) => money(x.partnerShare) },
        { key: 's', label: 'Settlement', render: (x: any) => humanize(x.settlement) }, { key: 'j', label: 'Journal', render: (x: any) => <span className="mono xs">{x.journal}</span> }]} /></Card>
    </div>}</Load>}</>;
}

export function Agreements() {
  const q = useF('agreements');
  const [add, setAdd] = useState(false);
  const partners = useF('partners', {}, add);
  return <>{FT('Commission & partner agreements', 'Versioned commercial terms. Changes are approved and apply from a future date — past transactions keep the terms they were calculated with.',
    <Button onClick={() => setAdd(true)}><Icon name="plus" size={16} />Propose terms</Button>)}
    <Load q={q}>{() => <Card flush><DataTable rows={q.data.results} columns={[{ key: 'p', label: 'Partner', render: (a: any) => <>{a.partner}<div className="xs muted mono">{a.code} v{a.version}</div></> },
      { key: 'm', label: 'Model', render: (a: any) => humanize(a.commercialModel) }, { key: 'c', label: 'Commission', render: (a: any) => `${Number(a.commissionPct)}% + ${Number(a.platformFeePct)}% fee + ${money(a.fixedFee)}/txn` },
      { key: 't', label: 'Tax on fees', render: (a: any) => `${Number(a.taxOnFeesPct)}%` },
      { key: 'r', label: 'Promotions / refunds', render: (a: any) => <span className="xs">{humanize(a.promoFunding)} / {humanize(a.refundResponsibility)}</span> },
      { key: 'e', label: 'Effective', render: (a: any) => `${fmtDate(a.effectiveFrom)}${a.effectiveTo ? ` → ${fmtDate(a.effectiveTo)}` : ''}` },
      { key: 's', label: 'Status', render: (a: any) => <Status value={tone(a.status)} label={humanize(a.status)} /> }]} /></Card>}</Load>
    {add && <FormDialog title="Propose commercial terms" wide onClose={() => setAdd(false)} submitLabel="Send for approval"
      initial={{ commercial_model: 'marketplace', tax_on_fees_pct: 18, delivery_fee_to: 'click', promo_funding: 'partner', refund_responsibility: 'partner', settlement_frequency: 'weekly', effective_from: today() }}
      fields={[{ name: 'partner_id', label: 'Partner (blank = default for everyone)', type: 'select', options: (partners.data?.results ?? []).map((p: any) => ({ value: p.id, label: p.name })) },
        { name: 'commercial_model', label: 'Commercial model', type: 'select', half: true, options: ['marketplace', 'commission_partner', 'agency', 'click_operated', 'click_owned_inventory', 'third_party_fulfillment', 'other_approved'].map((m) => ({ value: m, label: humanize(m) })) },
        { name: 'effective_from', label: 'Effective from', type: 'date', required: true, half: true },
        { name: 'commission_pct', label: 'Commission %', type: 'number', half: true }, { name: 'platform_fee_pct', label: 'Platform fee %', type: 'number', half: true },
        { name: 'fixed_fee', label: 'Fixed fee per transaction', type: 'number', half: true }, { name: 'tax_on_fees_pct', label: 'Tax on Click fees %', type: 'number', half: true },
        { name: 'delivery_fee_to', label: 'Delivery fee belongs to', type: 'select', half: true, options: [{ value: 'click', label: 'Click' }, { value: 'partner', label: 'Partner' }] },
        { name: 'promo_funding', label: 'Discounts funded by', type: 'select', half: true, options: ['partner', 'click', 'shared'].map((x) => ({ value: x, label: humanize(x) })) },
        { name: 'refund_responsibility', label: 'Refunds borne by', type: 'select', half: true, options: ['partner', 'click', 'shared'].map((x) => ({ value: x, label: humanize(x) })) },
        { name: 'settlement_frequency', label: 'Settlement', type: 'select', half: true, options: ['daily', 'weekly', 'biweekly', 'monthly'].map((x) => ({ value: x, label: humanize(x) })) },
        { name: 'notes', label: 'Notes', type: 'textarea' }]} onSubmit={(v) => finance.post('agreements', v)} onDone={() => void q.refetch()} />}</>;
}

export function Disputes() {
  const q = useF('disputes');
  const [add, setAdd] = useState(false);
  const [upd, setUpd] = useState<any>(null);
  return <>{FT('Disputes & chargebacks', 'Customer, partner, vendor, refund, commission, tax and chargeback disputes with owners, deadlines and financial impact.',
    <Button onClick={() => setAdd(true)}><Icon name="plus" size={16} />New dispute</Button>)}
    <Load q={q}>{() => <Card flush><DataTable rows={q.data.results} onRow={(x: any) => setUpd(x)} empty="No disputes" columns={[{ key: 'n', label: 'Dispute', render: (x: any) => <><span className="mono">{x.number}</span><div className="xs muted">{x.kindLabel}</div></> },
      { key: 'p', label: 'Party', render: (x: any) => x.party }, { key: 'a', label: 'Amount', num: true, render: (x: any) => money(x.amount) },
      { key: 'd', label: 'Deadline', render: (x: any) => <span style={{ color: x.overdue ? 'var(--c-danger)' : undefined }}>{fmtDate(x.deadline)}</span> },
      { key: 'o', label: 'Owner', render: (x: any) => x.owner ?? '—' }, { key: 's', label: 'Status', render: (x: any) => <Status value={tone(x.status)} label={humanize(x.status)} /> }]} /></Card>}</Load>
    {add && <FormDialog title="New dispute" onClose={() => setAdd(false)} fields={[{ name: 'kind', label: 'Type', type: 'select', required: true, half: true,
      options: ['payment', 'chargeback', 'settlement', 'vendor', 'refund', 'commission', 'tax', 'invoice'].map((k) => ({ value: k, label: humanize(k) })) },
      { name: 'party_type', label: 'Party type', type: 'select', half: true, options: ['customer', 'partner', 'supplier', 'gateway'].map((k) => ({ value: k, label: humanize(k) })) },
      { name: 'party_name', label: 'Party', required: true, half: true }, { name: 'amount', label: 'Amount', type: 'number', required: true, half: true },
      { name: 'deadline', label: 'Response deadline', type: 'date', half: true }, { name: 'reason', label: 'Reason', type: 'textarea', required: true }]}
      onSubmit={(v) => finance.post('disputes', v)} onDone={() => void q.refetch()} />}
    {upd && <FormDialog title={`Update ${upd.number}`} onClose={() => setUpd(null)} initial={{ status: upd.status === 'open' ? 'investigating' : upd.status, resolution: upd.resolution }}
      fields={[{ name: 'status', label: 'Status', type: 'select', options: ['investigating', 'resolved', 'rejected'].map((k) => ({ value: k, label: humanize(k) })) },
        { name: 'resolution', label: 'Resolution', type: 'textarea' }, { name: 'impact', label: 'Financial impact (cost to Click)', type: 'number', half: true },
        { name: 'post_adjustment', label: 'Post the impact as an adjusting journal', type: 'checkbox' }]} onSubmit={(v) => finance.patch(`disputes/${upd.id}`, v)} onDone={() => void q.refetch()} />}</>;
}

// ---------------------------------------------------------------------------------------------------------------------
export function Expenses() {
  const [params, setParams] = useSearchParams();
  const [view, setView] = useState<'mine' | 'all'>('mine');
  const [page, setPage] = useState(1);
  const q = useF('expenses', { view, page });
  const lk = useLookups();
  return <>{FT('Expenses', 'Claim business expenses against company policy. Policy limits are explained before you submit, never silently applied.',
    <Button onClick={() => setParams({ new: '1' })}><Icon name="plus" size={16} />New claim</Button>)}
    {q.data?.canViewAll && <Tabs value={view} onChange={(v) => { setView(v); setPage(1); }} items={[{ value: 'mine', label: 'My claims' }, { value: 'all', label: 'All I can see' }]} />}
    <Load q={q}>{() => <Card flush><DataTable rows={q.data.results} empty="No expense claims" columns={[
      { key: 'n', label: 'Claim', render: (c: any) => <><strong>{c.purpose}</strong><div className="xs muted mono">{c.number} · {c.category}{view === 'all' ? ` · ${c.claimant}` : ''}</div></> },
      { key: 'd', label: 'Date', render: (c: any) => fmtDate(c.date) }, { key: 'a', label: 'Amount', num: true, render: (c: any) => money(c.amount) },
      { key: 'f', label: 'Policy', render: (c: any) => (c.policyFlags.length ? <span className="flag flag--due_soon" title={c.policyFlags.join('\n')}>{c.policyFlags.length} note(s)</span> : <span className="xs muted">Within policy</span>) },
      { key: 's', label: 'Status', render: (c: any) => <Status value={tone(c.status === 'submitted' ? 'pending' : c.status)} label={c.statusLabel} /> },
      { key: 'x', label: '', render: (c: any) => c.approvalId && <Link to={`/approvals/${c.approvalId}`} className="small">Approval</Link> }]} />
      <Pager page={q.data.page} hasNext={q.data.hasNext} count={q.data.count} onPage={setPage} /></Card>}</Load>
    {params.get('new') === '1' && <FormDialog title="New expense claim" onClose={() => setParams({})} submitLabel="Submit" initial={{ date: today() }}
      intro={q.data?.categories && <p className="xs muted">{q.data.categories.map((c: any) => `${c.name}: up to ${c.limit ? money(c.limit) : 'no limit'}, receipt above ${money(c.receiptAbove)}${c.note ? ` — ${c.note}` : ''}`).join(' · ')}</p>}
      fields={[{ name: 'category_id', label: 'Category', type: 'select', required: true, half: true, options: (q.data?.categories ?? []).map((c: any) => ({ value: c.id, label: c.name })) },
        { name: 'date', label: 'Date', type: 'date', required: true, half: true }, { name: 'amount', label: 'Amount (₹)', type: 'number', required: true, half: true },
        { name: 'distance_km', label: 'Distance (km, mileage only)', type: 'number', half: true }, { name: 'merchant', label: 'Merchant', half: true },
        { name: 'cost_center_id', label: 'Cost center', type: 'select', half: true, options: (lk.data?.costCenters ?? []).map((c: any) => ({ value: c.id, label: `${c.code} ${c.name}` })) },
        { name: 'purpose', label: 'Business purpose', type: 'textarea', required: true }, { name: 'has_receipt', label: 'I have the receipt and will attach it', type: 'checkbox' }]}
      onSubmit={(v) => finance.post('expenses', v)} onDone={() => void q.refetch()} />}</>;
}

export function Budgets() {
  const q = useF('budgets');
  const [add, setAdd] = useState(false);
  const lk = useLookups();
  const depts = useQuery({ queryKey: ['os', 'people', 'lookups'], queryFn: people.lookups, enabled: add });
  return <>{FT('Budgets & forecast', 'Budget vs actual vs committed vs forecast. Procurement checks and reserves against these before approval.',
    <Button onClick={() => setAdd(true)}><Icon name="plus" size={16} />New budget</Button>)}
    <Load q={q}>{() => <Card flush><DataTable rows={q.data.results} empty="No budgets" columns={[
      { key: 'n', label: 'Budget', render: (b: any) => <><strong>{b.name}</strong><div className="xs muted">{b.number} · {b.fiscalYear} · {b.department ?? b.unit ?? b.costCenter ?? 'Company'}{b.category ? ` · ${b.category}` : ''}</div></> },
      { key: 'b', label: 'Budget', num: true, render: (b: any) => money(b.budget) }, { key: 'a', label: 'Actual', num: true, render: (b: any) => money(b.actual) },
      { key: 'c', label: 'Committed', num: true, render: (b: any) => money(b.committed) },
      { key: 'v', label: 'Available', num: true, render: (b: any) => <span style={{ color: Number(b.available) < 0 ? 'var(--c-danger)' : undefined }}>{money(b.available)}</span> },
      { key: 'u', label: 'Used', render: (b: any) => <span className="row" style={{ gap: 6 }}><span className="progress" style={{ width: 90 }}><span style={{ width: `${Math.min(100, Number(b.usedPct ?? 0))}%`, background: Number(b.usedPct) > 100 ? 'var(--c-danger)' : undefined }} /></span><span className="xs">{b.usedPct ?? 0}%</span></span> },
      { key: 'f', label: 'Forecast', num: true, render: (b: any) => <span title={b.forecastNote}>{money(b.forecast)}*</span> },
      { key: 's', label: 'Status', render: (b: any) => <Status value={tone(b.status)} label={humanize(b.status)} /> }]} />
      <p className="xs muted" style={{ padding: 12 }}>* Forecasts are estimates (run-rate or actual + committed), not confirmed figures.</p></Card>}</Load>
    {add && <FormDialog title="New budget" onClose={() => setAdd(false)} submitLabel="Send for approval"
      fields={[{ name: 'name', label: 'Name', required: true }, { name: 'department_id', label: 'Department', type: 'select', half: true, options: (depts.data?.departments ?? []).map((d: any) => ({ value: d.id, label: d.name })) },
        { name: 'cost_center_id', label: 'Cost center', type: 'select', half: true, options: (lk.data?.costCenters ?? []).map((c: any) => ({ value: c.id, label: c.code })) },
        { name: 'category', label: 'Category (e.g. technology)', half: true }, { name: 'fiscal_year', label: 'Fiscal year starting', type: 'number', half: true },
        { name: 'amount', label: 'Annual amount', type: 'number', required: true, half: true }, { name: 'notes', label: 'Notes', type: 'textarea' }]}
      onSubmit={(v) => finance.post('budgets', { ...v, lines: [{ amount: v.amount }] })} onDone={() => void q.refetch()} />}</>;
}

export function Assets() {
  const q = useF('assets');
  const [add, setAdd] = useState(false);
  const act = useAction((b: any) => finance.post(`assets/${b.id}/${b.action}`, b), [FK], 'Done');
  return <>{FT('Fixed assets', 'Asset register, capitalisation, straight-line depreciation (run per period) and disposal. Procurement capital purchases arrive here awaiting capitalisation.',
    <Button onClick={() => setAdd(true)}><Icon name="plus" size={16} />Register asset</Button>)}
    <Load q={q}>{() => <Card flush><DataTable rows={q.data.results} empty="No assets" columns={[{ key: 'n', label: 'Asset', render: (a: any) => <><strong>{a.name}</strong><div className="xs muted mono">{a.number} · {humanize(a.category)}</div></> },
      { key: 'd', label: 'Acquired', render: (a: any) => fmtDate(a.acquired) }, { key: 'c', label: 'Cost', num: true, render: (a: any) => money(a.cost) },
      { key: 'x', label: 'Depreciation', num: true, render: (a: any) => money(a.accumulated) }, { key: 'b', label: 'Book value', num: true, render: (a: any) => money(a.bookValue) },
      { key: 'l', label: 'Where', render: (a: any) => <span className="xs">{a.department ?? '—'}{a.location ? ` · ${a.location}` : ''}</span> },
      { key: 's', label: 'Status', render: (a: any) => <Status value={tone(a.status === 'draft' ? 'pending' : a.status)} label={humanize(a.status)} /> },
      { key: 'a', label: '', render: (a: any) => a.status === 'draft' ? <Button size="sm" onClick={() => act.mutate({ id: a.id, action: 'capitalise' })}>Capitalise</Button>
        : a.status === 'active' ? <Button size="sm" variant="ghost" onClick={() => act.mutate({ id: a.id, action: 'dispose', proceeds: 0 })}>Dispose (scrap)</Button> : null }]} /></Card>}</Load>
    {add && <FormDialog title="Register asset" onClose={() => setAdd(false)} initial={{ category: 'computers', useful_life_months: 36, acquisition_date: today() }}
      intro={<p className="small muted">Registered as awaiting capitalisation; capitalising posts it to the ledger (credited to payables).</p>}
      fields={[{ name: 'name', label: 'Name', required: true }, { name: 'category', label: 'Category', type: 'select', half: true, options: ['computers', 'servers', 'office_equipment', 'vehicles', 'furniture', 'infrastructure', 'other'].map((k) => ({ value: k, label: humanize(k) })) },
        { name: 'acquisition_date', label: 'Acquired', type: 'date', half: true }, { name: 'cost', label: 'Cost', type: 'number', required: true, half: true },
        { name: 'useful_life_months', label: 'Useful life (months)', type: 'number', half: true }, { name: 'salvage_value', label: 'Salvage value', type: 'number', half: true },
        { name: 'serial_number', label: 'Serial number', half: true }]} onSubmit={(v) => finance.post('assets', v)} onDone={() => void q.refetch()} />}</>;
}

// ---------------------------------------------------------------------------------------------------------------------
export function Reconciliation() {
  const [tab, setTab] = useState<'bank' | 'lines' | 'exceptions'>('bank');
  const banks = useF('bank-accounts', {}, tab === 'bank');
  const [status, setStatus] = useState('unmatched');
  const lines = useF('bank-transactions', { status }, tab === 'lines');
  const exc = useF('exceptions', { status: 'open' }, tab === 'exceptions');
  const pays = useF('payments', { status: 'paid' }, tab === 'lines');
  const toast = useToast();
  const file = useRef<HTMLInputElement>(null);
  const [importTo, setImportTo] = useState<any>(null);
  const [change, setChange] = useState<any>(null);
  const [match, setMatch] = useState<any>(null);
  const [resolve, setResolve] = useState<any>(null);
  const detect = useAction(() => finance.post('exceptions'), [FK], 'Checks run');
  const reveal = async (b: any) => { try { const r = await finance.post(`bank-accounts/${b.id}/reveal`); toast(`${b.name}: ${r.accountNumber} (this view was recorded)`); } catch (e) { toast(apiMessage(e), 'error'); } };
  const doImport = async () => {
    const f = file.current?.files?.[0];
    if (!f || !importTo) return;
    const fd = new FormData();
    fd.append('file', f);
    try { const r = await finance.post(`bank-accounts/${importTo.id}/import`, fd); toast(`${r.created} lines imported, ${r.autoMatched} matched automatically`); setImportTo(null); void banks.refetch(); }
    catch (e) { toast(apiMessage(e), 'error'); }
  };
  return <>{FT('Reconciliation', 'Bank statements against payments, payment-gateway checks and exceptions. Nothing is matched silently.',
    <Button variant="outline" loading={detect.isPending} onClick={() => detect.mutate(undefined)}>Run gateway checks</Button>)}
    <Tabs value={tab} onChange={setTab} items={[{ value: 'bank', label: 'Bank accounts' }, { value: 'lines', label: 'Statement lines' }, { value: 'exceptions', label: 'Exceptions' }]} />
    {tab === 'bank' && <Load q={banks}>{() => <Card flush><DataTable rows={banks.data.results} columns={[
      { key: 'n', label: 'Account', render: (b: any) => <><strong>{b.name}</strong><div className="xs muted">{b.bank} {b.masked} {b.ifsc}</div></> },
      { key: 'b', label: 'Book balance', num: true, render: (b: any) => money(b.bookBalance) }, { key: 's', label: 'Statement movements', num: true, render: (b: any) => money(b.statementMovements) },
      { key: 'u', label: 'Unmatched lines', num: true, render: (b: any) => b.unmatched }, { key: 'r', label: 'Unreconciled payments', num: true, render: (b: any) => b.unreconciledPayments },
      { key: 'a', label: '', render: (b: any) => <span className="row" style={{ gap: 4 }}><Button size="sm" variant="outline" onClick={() => setImportTo(b)}>Import statement</Button>
        <Button size="sm" variant="ghost" onClick={() => void reveal(b)}>Reveal</Button><Button size="sm" variant="ghost" onClick={() => setChange(b)}>Change details</Button></span> }]} /></Card>}</Load>}
    {tab === 'lines' && <Load q={lines}>{() => <Card flush actions={<select className="field__input" aria-label="Status" value={status} onChange={(e) => setStatus(e.target.value)}>
      <option value="unmatched">Unmatched</option><option value="matched">Matched</option><option value="excluded">Excluded</option></select>}>
      <DataTable rows={lines.data.results} empty="Nothing here" columns={[{ key: 'd', label: 'Date', render: (t: any) => fmtDate(t.date) },
        { key: 'x', label: 'Description', render: (t: any) => <>{t.description}<div className="xs muted">{t.bank} · {t.reference}</div></> },
        { key: 'a', label: 'Amount', num: true, render: (t: any) => money(t.amount) },
        { key: 'm', label: 'Matched to', render: (t: any) => (t.matched ? <span className="mono xs">{t.matched} ({t.method})</span> : t.note || '—') },
        { key: 'b', label: '', render: (t: any) => t.status === 'unmatched' && <Button size="sm" variant="outline" onClick={() => setMatch(t)}>Match / exclude</Button> }]} /></Card>}</Load>}
    {tab === 'exceptions' && <Load q={exc}>{() => <Card flush><DataTable rows={exc.data.results} empty="No open exceptions" columns={[
      { key: 'k', label: 'Exception', render: (x: any) => <>{humanize(x.kind)}<div className="xs muted">{humanize(x.area)} · {x.source}</div></> },
      { key: 'd', label: 'Detail', render: (x: any) => <span className="small">{x.description}</span> }, { key: 'a', label: 'Amount', num: true, render: (x: any) => money(x.amount) },
      { key: 'r', label: '', render: (x: any) => <Button size="sm" variant="outline" onClick={() => setResolve(x)}>Resolve</Button> }]} /></Card>}</Load>}
    {importTo && <Dialog title={`Import statement · ${importTo.name}`} onClose={() => setImportTo(null)} footer={<><Button variant="outline" onClick={() => setImportTo(null)}>Cancel</Button><Button onClick={() => void doImport()}>Import</Button></>}>
      <p className="small">CSV with columns <code>date, description, amount, reference</code> (amount: + in, − out). Duplicate lines are ignored.</p>
      <input ref={file} type="file" accept=".csv,text/csv" className="field__input" aria-label="Statement file" /></Dialog>}
    {change && <FormDialog title={`Change bank details · ${change.name}`} onClose={() => setChange(null)} submitLabel="Save"
      intro={<Alert tone="warning">Every bank administrator is notified and the change is audited. Payments approved earlier still need re-checking.</Alert>}
      fields={[{ name: 'account_number', label: 'Account number', required: true }, { name: 'ifsc', label: 'IFSC' }]} onSubmit={(v) => finance.post(`bank-accounts/${change.id}/change-number`, v)} onDone={() => void banks.refetch()} />}
    {match && <FormDialog title={`Match ${money(match.amount)} · ${match.description}`} onClose={() => setMatch(null)} submitLabel="Save"
      fields={[{ name: 'payment_id', label: 'Payment', type: 'select', options: (pays.data?.results ?? []).filter((p: any) => !p.reconciled && Number(p.amount) === Math.abs(Number(match.amount)))
        .map((p: any) => ({ value: p.id, label: `${p.number} · ${p.party} · ${fmtDate(p.date)}` })) }, { name: 'exclude_reason', label: '…or exclude it, because', type: 'textarea' }]}
      onSubmit={(v) => finance.post(`bank-transactions/${match.id}/match`, v)} onDone={() => void lines.refetch()} />}
    {resolve && <FormDialog title={`Resolve: ${humanize(resolve.kind)}`} onClose={() => setResolve(null)} initial={{ status: 'resolved' }}
      fields={[{ name: 'status', label: 'Outcome', type: 'select', options: [{ value: 'resolved', label: 'Resolved' }, { value: 'ignored', label: 'Accepted — no action' }] },
        { name: 'resolution', label: 'What was done', type: 'textarea', required: true }]} onSubmit={(v) => finance.patch(`exceptions/${resolve.id}`, v)} onDone={() => void exc.refetch()} />}</>;
}
