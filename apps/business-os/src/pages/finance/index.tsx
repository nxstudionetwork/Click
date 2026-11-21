/* eslint-disable @typescript-eslint/no-explicit-any */
/** Module 4 — Finance workspace (accounting, reporting, control). Money screens live in ./money.tsx. */
import { useState } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { Button, Icon } from '@click/ui';
import { finance } from '../../lib/api';
import { fmtDate, fmtDateTime, humanize } from '../../lib/format';
import { DataTable, FormDialog, StatGrid } from '../../components/forms';
import { DownloadButton, Kpis, ModuleShell, ModuleTitle, money, useAction } from '../../components/ModuleShell';
import { Alert, Card, Dialog, Empty, LoadingRows, Pager, QueryError, Status, Tabs } from '../../components/ui';

export const FK = ['os', 'finance'];
export const FT = (title: string, desc?: React.ReactNode, actions?: React.ReactNode) => <ModuleTitle module="Finance" root="/finance" title={title} desc={desc} actions={actions} />;

export function useF<T = any>(path: string, query: Record<string, any> = {}, enabled = true) {
  return useQuery<T>({ queryKey: [...FK, path, query], queryFn: () => finance.get<T>(path, query), enabled });
}
export function Load({ q, children }: { q: any; children: () => React.ReactNode }) {
  if (q.isPending) return <Card><LoadingRows /></Card>;
  if (q.error) return <QueryError error={q.error} />;
  return <>{children()}</>;
}
export const today = () => new Date().toISOString().slice(0, 10);
export const monthStart = () => today().slice(0, 8) + '01';
export function useLookups() { return useF('lookups'); }

export function FinanceLayout() { return <ModuleShell api={finance} label="Finance" root="/finance" icon="receipt" />; }

export function Range({ v, set }: { v: { from: string; to: string }; set: (v: { from: string; to: string }) => void }) {
  return <span className="row"><input type="date" className="field__input" aria-label="From" value={v.from} onChange={(e) => set({ ...v, from: e.target.value })} />
    <input type="date" className="field__input" aria-label="To" value={v.to} onChange={(e) => set({ ...v, to: e.target.value })} /></span>;
}

/** Line editor for journals, invoices and bills. */
export function LinesEditor({ lines, setLines, kind }: { lines: any[]; setLines: (l: any[]) => void; kind: 'journal' | 'document' }) {
  const lk = useLookups();
  const upd = (i: number, k: string, v: string) => setLines(lines.map((l, j) => (j === i ? { ...l, [k]: v } : l)));
  const accounts = lk.data?.accounts ?? [];
  const dr = lines.reduce((a, l) => a + Number(l.debit || 0), 0);
  const cr = lines.reduce((a, l) => a + Number(l.credit || 0), 0);
  return (
    <div className="stack" style={{ gap: 6 }}>
      {lines.map((l, i) => (
        <div key={i} className="row row--wrap" style={{ gap: 6 }}>
          <select className="field__input" aria-label="Account" value={l.accountId ?? ''} onChange={(e) => upd(i, 'accountId', e.target.value)} style={{ minWidth: 220 }}>
            <option value="">Account…</option>{accounts.map((a: any) => <option key={a.id} value={a.id}>{a.code} {a.name}</option>)}</select>
          <input className="field__input" placeholder="Description" aria-label="Description" value={l.description ?? ''} onChange={(e) => upd(i, 'description', e.target.value)} />
          {kind === 'journal' ? <>
            <input className="field__input" type="number" placeholder="Debit" aria-label="Debit" style={{ width: 120 }} value={l.debit ?? ''} onChange={(e) => upd(i, 'debit', e.target.value)} />
            <input className="field__input" type="number" placeholder="Credit" aria-label="Credit" style={{ width: 120 }} value={l.credit ?? ''} onChange={(e) => upd(i, 'credit', e.target.value)} />
          </> : <>
            <input className="field__input" type="number" placeholder="Qty" aria-label="Quantity" style={{ width: 80 }} value={l.quantity ?? '1'} onChange={(e) => upd(i, 'quantity', e.target.value)} />
            <input className="field__input" type="number" placeholder="Unit price" aria-label="Unit price" style={{ width: 120 }} value={l.unitPrice ?? ''} onChange={(e) => upd(i, 'unitPrice', e.target.value)} />
            <select className="field__input" aria-label="Tax" value={l.taxRuleId ?? ''} onChange={(e) => upd(i, 'taxRuleId', e.target.value)}>
              <option value="">No tax</option>{(lk.data?.taxRules ?? []).map((t: any) => <option key={t.id} value={t.id}>{t.code}</option>)}</select>
          </>}
          <button className="icon-btn" aria-label="Remove line" onClick={() => setLines(lines.filter((_, j) => j !== i))}><Icon name="close" size={14} /></button>
        </div>
      ))}
      <div className="row"><Button size="sm" variant="ghost" onClick={() => setLines([...lines, {}])}><Icon name="plus" size={14} />Add line</Button>
        {kind === 'journal' && <span className={`small ${dr === cr && dr > 0 ? '' : 'muted'}`} style={{ marginLeft: 'auto', color: dr !== cr ? 'var(--c-danger)' : undefined }}>
          Debits {dr.toFixed(2)} · Credits {cr.toFixed(2)} {dr === cr && dr > 0 ? '✓ balanced' : '— must balance'}</span>}</div>
    </div>
  );
}

// ---------------------------------------------------------------------------------------------------------------------
export function FinanceHome() {
  const q = useF('home');
  return <>{FT('Finance', 'What is happening financially, what needs attention, and what is due.')}
    <Load q={q}>{() => q.data.mode === 'self' ? (
      <Card title="My expense claims" actions={<Link to="/finance/expenses?new=1" className="small">New claim</Link>} flush>
        <DataTable rows={q.data.claims} empty="No claims yet" columns={[{ key: 'n', label: 'Claim', render: (c: any) => <>{c.purpose}<div className="xs muted mono">{c.number}</div></> },
          { key: 'a', label: 'Amount', num: true, render: (c: any) => money(c.amount) }, { key: 's', label: 'Status', render: (c: any) => <Status value={c.status} label={c.statusLabel} /> }]} /></Card>
    ) : (
      <div className="stack stack--lg">
        {q.data.pulse ? <Card title="Financial pulse · month to date"><StatGrid items={q.data.pulse.metrics.map((m: any) => ({
          key: m.key, label: m.label, value: typeof m.value === 'number' ? m.value : money(m.value), hint: m.hint, to: m.path }))} /></Card>
          : <Alert tone="info">Company-wide figures need organization-wide finance access. You see your region’s documents and approvals.</Alert>}
        <div className="grid grid--2">
          <Card title="Alerts & exceptions" flush>{!q.data.alerts.length ? <p className="muted small" style={{ padding: 16 }}>Nothing needs attention.</p> : (
            <ul className="list">{q.data.alerts.map((a: any, i: number) => <li key={i}><Link to={a.path} className="list-row"><span className={`sev sev--${a.severity}`} />
              <span className="grow small">{a.title}</span><span className="chip">{a.count}</span></Link></li>)}</ul>)}</Card>
          <Card title="My finance work"><Kpis items={[
            { label: 'Approvals waiting on you', value: q.data.myWork.approvals, to: '/approvals' },
            { label: 'Payments to release', value: q.data.myWork.paymentsToRelease ?? '—', to: '/finance/payments' },
            { label: 'Payment runs to release', value: q.data.myWork.runsToRelease ?? '—', to: '/finance/payments' },
            { label: 'Draft bills', value: q.data.myWork.billsToSubmit, to: '/finance/payables' },
            { label: 'Reconciliation exceptions', value: q.data.myWork.reconExceptions, to: '/finance/reconciliation' },
            { label: 'My close tasks', value: q.data.myWork.closeTasks, to: '/finance/periods' }]} />
            {Object.keys(q.data.myWork.approvalsByType).length > 0 && <p className="xs muted" style={{ marginTop: 8 }}>{Object.entries(q.data.myWork.approvalsByType).map(([k, v]) => `${k}: ${v}`).join(' · ')}</p>}</Card>
        </div>
      </div>)}</Load></>;
}

export function Platform() {
  const [r, setR] = useState({ from: monthStart(), to: today() });
  const q = useF('platform', r);
  const [bq, setBq] = useState({ kind: '', page: 1 });
  const bd = useF('breakdowns', { kind: bq.kind || undefined, page: bq.page });
  const sync = useAction(() => finance.post('platform/sync'), [FK], 'Payments brought into Finance');
  return <>{FT('Platform revenue & GTV', 'What customers paid through Click versus what Click actually earned. Gross transaction value is not revenue.',
    <><Range v={r} set={setR} /><Button variant="outline" loading={sync.isPending} onClick={() => sync.mutate(undefined)}>Sync payments</Button></>)}
    <Load q={q}>{() => <div className="stack stack--lg">
      <Kpis items={[{ label: 'Gross transaction value', value: money(q.data.grossTransactionValue), hint: `${q.data.transactions} transactions — not revenue` },
        { label: 'Partner earnings', value: money(q.data.partnerEarnings) }, { label: 'Click commission', value: money(q.data.clickCommission) },
        { label: 'Platform fees', value: money(q.data.platformFees) }, { label: 'Click revenue', value: money(q.data.clickRevenue) },
        { label: 'Payment costs', value: money(q.data.paymentCosts) }, { label: 'Click-funded discounts', value: money(q.data.clickFundedDiscounts) },
        { label: 'Refunds', value: money(q.data.refundsGross), hint: `${q.data.refundCount} refunds` },
        { label: 'Click net revenue', value: money(q.data.clickNetRevenue), tone: 'good' }, { label: 'Settlement liability', value: money(q.data.settlementLiability), to: '/finance/settlements' },
        { label: 'Customer stored value loaded', value: money(q.data.storedValueLoaded), hint: 'Wallet & gift cards — a liability' },
        { label: 'Tax on Click fees', value: money(q.data.taxOnFees) }]} />
      {Number(q.data.unclassified.total) > 0 && <Alert tone="info">{money(q.data.unclassified.total)} captured for {Object.keys(q.data.unclassified.byService).map(humanize).join(', ')}: {q.data.unclassified.note}</Alert>}
      <div className="grid grid--2">
        <Card title="Unit economics"><dl className="kv">
          {[['Average order value', money(q.data.unitEconomics.averageOrderValue)], ['Revenue per transaction', money(q.data.unitEconomics.revenuePerTransaction)],
            ['Net revenue per transaction', money(q.data.unitEconomics.netRevenuePerTransaction)], ['Take rate', q.data.unitEconomics.takeRatePct ? `${q.data.unitEconomics.takeRatePct}%` : '—'],
            ['Effective commission', q.data.unitEconomics.effectiveCommissionPct ? `${q.data.unitEconomics.effectiveCommissionPct}%` : '—'],
            ['Payment cost', q.data.unitEconomics.paymentCostPct ? `${q.data.unitEconomics.paymentCostPct}%` : '—'], ['Refund rate', q.data.unitEconomics.refundRatePct ? `${q.data.unitEconomics.refundRatePct}%` : '—']]
            .map(([k, v]) => <div key={k} style={{ display: 'contents' }}><dt>{k}</dt><dd>{v}</dd></div>)}</dl>
          <p className="xs muted" style={{ marginTop: 8 }}>Not shown: {q.data.unitEconomics.unavailable.join(', ')}. {q.data.unitEconomics.unavailableNote}</p></Card>
        <Card title="By commercial model" flush><DataTable rows={q.data.byModel.map((m: any) => ({ ...m, id: m.model }))} empty="No transactions" columns={[
          { key: 'm', label: 'Model', render: (m: any) => humanize(m.model) }, { key: 'g', label: 'GTV', num: true, render: (m: any) => money(m.gtv) },
          { key: 'r', label: 'Click revenue', num: true, render: (m: any) => money(m.revenue) }]} /></Card>
      </div>
      <Card title="Transaction breakdowns" flush actions={<select className="field__input" aria-label="Kind" value={bq.kind} onChange={(e) => setBq({ kind: e.target.value, page: 1 })}>
        <option value="">All</option><option value="sale">Sales</option><option value="refund">Refunds</option><option value="stored_value">Stored value</option></select>}>
        <Load q={bd}>{() => <><DataTable rows={bd.data.results} empty="No platform payments yet" columns={[
          { key: 'd', label: 'Date', render: (b: any) => fmtDate(b.date) }, { key: 's', label: 'Partner / store', render: (b: any) => <>{b.partner ?? '—'}<div className="xs muted">{b.store} · {humanize(b.kind)} · {b.method}</div></> },
          { key: 'g', label: 'Paid', num: true, render: (b: any) => money(b.gross) }, { key: 'c', label: 'Commission + fees', num: true, render: (b: any) => money(Number(b.commission) + Number(b.platformFee)) },
          { key: 'p', label: 'Partner share', num: true, render: (b: any) => money(b.partnerShare) }, { key: 'n', label: 'Click net', num: true, render: (b: any) => money(b.clickNet) },
          { key: 'st', label: 'Settlement', render: (b: any) => <Status value={b.settlement === 'settled' ? 'approved' : b.settlement === 'na' ? 'neutral' : 'pending'} label={humanize(b.settlement)} /> },
          { key: 'j', label: 'Journal', render: (b: any) => b.journalId && <Link to={`/finance/journals?open=${b.journalId}`} className="mono xs">{b.journal}</Link> }]} />
          <Pager page={bd.data.page} hasNext={bd.data.hasNext} count={bd.data.count} onPage={(p) => setBq({ ...bq, page: p })} /></>}</Load></Card>
      <p className="xs muted">{q.data.note}</p>
    </div>}</Load></>;
}

export function Cash() {
  const pos = useF('reports', { r: 'cash' });
  const fc = useF('reports', { r: 'forecast', days: 90 });
  return <>{FT('Cash position & forecast', 'Available cash excludes pending gateway funds and restricted balances.')}
    <div className="stack stack--lg">
      <Load q={pos}>{() => <><Kpis items={[{ label: 'Available cash', value: money(pos.data.data.available), tone: 'good' },
        { label: 'Pending / restricted', value: money(pos.data.data.pendingOrRestricted) }, { label: 'Cash in hand', value: money(pos.data.data.cashInHand) }]} />
        <Card title="Accounts" flush><DataTable rows={pos.data.data.accounts} columns={[{ key: 'n', label: 'Account', render: (a: any) => <>{a.name}<div className="xs muted">{a.bank} {a.last4 ? `••••${a.last4}` : ''}</div></> },
          { key: 't', label: 'Type', render: (a: any) => humanize(a.type) }, { key: 'b', label: 'Balance', num: true, render: (a: any) => money(a.balance, a.currency) },
          { key: 'r', label: '', render: (a: any) => a.restricted && <span className="flag">restricted / pending</span> }]} /></Card></>}</Load>
      <Load q={fc}>{() => <Card title="90-day forecast">
        <Alert tone="warning">{fc.data.data.label}</Alert>
        <dl className="kv" style={{ marginTop: 8 }}>{[['Starting cash', fc.data.data.startingCash], ['+ Expected receipts', fc.data.data.expectedReceipts], ['− Vendor payments', fc.data.data.vendorPayments],
          ['− Partner settlements', fc.data.data.partnerSettlements], ['− Reimbursements', fc.data.data.reimbursements], ['− Taxes', fc.data.data.taxes], ['Projected cash', fc.data.data.projectedCash],
          ['Average monthly burn', fc.data.data.averageMonthlyBurn]].map(([k, v]) => <div key={k} style={{ display: 'contents' }}><dt>{k}</dt><dd>{money(v)}</dd></div>)}
          <dt>Runway</dt><dd>{fc.data.data.runwayMonths ? `${fc.data.data.runwayMonths} months` : '—'}</dd></dl>
        <p className="xs muted" style={{ marginTop: 8 }}>Assumptions: {fc.data.data.assumptions.join(' · ')}</p></Card>}</Load>
    </div></>;
}

// ---------------------------------------------------------------------------------------------------------------------
export function Journals() {
  const [params, setParams] = useSearchParams();
  const [f, setF] = useState({ status: '', q: '', page: 1 });
  const q = useF('journals', { status: f.status || undefined, q: f.q || undefined, page: f.page });
  const open = params.get('open');
  const [form, setForm] = useState({ date: today(), description: '', kind: 'manual', reference: '' });
  const [lines, setLines] = useState<any[]>([{}, {}]);
  const create = useAction((b: any) => finance.post('journals', b), [FK], 'Journal sent for approval');
  return <>{FT('Journals & general ledger', 'Manual and adjusting entries need a second person to approve. Posted journals are never edited — reverse them.',
    <Button onClick={() => setParams({ new: '1' })}><Icon name="plus" size={16} />New journal</Button>)}
    <Card flush>
      <div className="toolbar"><div className="search-input"><Icon name="search" size={16} /><input value={f.q} onChange={(e) => setF({ ...f, q: e.target.value, page: 1 })} placeholder="JV number, description, reference" aria-label="Search journals" /></div>
        <select className="field__input" aria-label="Status" value={f.status} onChange={(e) => setF({ ...f, status: e.target.value, page: 1 })}><option value="">All</option>
          {['pending_approval', 'posted', 'reversed', 'rejected', 'draft'].map((s) => <option key={s} value={s}>{humanize(s)}</option>)}</select></div>
      <Load q={q}>{() => <><DataTable rows={q.data.results} onRow={(j: any) => setParams({ open: j.id })} empty="No journals" columns={[
        { key: 'n', label: 'Journal', render: (j: any) => <><span className="mono">{j.number || 'Draft'}</span><div className="xs muted">{j.description}</div></> },
        { key: 'd', label: 'Date', render: (j: any) => fmtDate(j.date) }, { key: 'k', label: 'Kind', render: (j: any) => <span className="small">{humanize(j.kind)}{j.source ? <div className="xs muted">{j.source}</div> : null}</span> },
        { key: 't', label: 'Amount', num: true, render: (j: any) => money(j.total) }, { key: 's', label: 'Status', render: (j: any) => <Status value={j.status} label={humanize(j.status)} /> },
        { key: 'b', label: 'By', render: (j: any) => <span className="xs">{j.createdBy}</span> }]} />
        <Pager page={q.data.page} hasNext={q.data.hasNext} count={q.data.count} onPage={(p) => setF({ ...f, page: p })} /></>}</Load>
    </Card>
    {open && <JournalDrawer id={open} onClose={() => setParams({})} />}
    {params.get('new') === '1' && <Dialog title="New journal" wide onClose={() => setParams({})} footer={<>
      <Button variant="outline" onClick={() => setParams({})}>Cancel</Button>
      <Button loading={create.isPending} onClick={() => create.mutate({ ...form, lines }, { onSuccess: () => { setParams({}); setLines([{}, {}]); } })}>Submit for approval</Button></>}>
      <div className="form-grid">
        <label className="field"><span className="field__label">Date</span><input type="date" className="field__input" value={form.date} onChange={(e) => setForm({ ...form, date: e.target.value })} /></label>
        <label className="field"><span className="field__label">Type</span><select className="field__input" value={form.kind} onChange={(e) => setForm({ ...form, kind: e.target.value })}>
          {['manual', 'adjusting', 'accrual', 'recurring'].map((k) => <option key={k} value={k}>{humanize(k)}</option>)}</select></label>
        <label className="field form-grid__full"><span className="field__label">Description</span><input className="field__input" value={form.description} onChange={(e) => setForm({ ...form, description: e.target.value })} /></label>
      </div>
      <LinesEditor lines={lines} setLines={setLines} kind="journal" />
    </Dialog>}</>;
}

export function JournalDrawer({ id, onClose }: { id: string; onClose: () => void }) {
  const q = useF(`journals/${id}`);
  const [rev, setRev] = useState(false);
  return <Dialog title={q.data ? `${q.data.number || 'Draft journal'} · ${q.data.description}` : 'Journal'} onClose={onClose} wide>
    <Load q={q}>{() => <div className="stack">
      <div className="row row--wrap"><Status value={q.data.status} label={humanize(q.data.status)} /><span className="chip">{humanize(q.data.kind)}</span>
        <span className="small muted">{fmtDate(q.data.date)} · period {q.data.period} · {q.data.createdBy}{q.data.postedBy ? ` · posted by ${q.data.postedBy} ${fmtDateTime(q.data.postedAt)}` : ''}</span></div>
      {q.data.source && <p className="xs muted">Source: {q.data.source} {q.data.sourceId}</p>}
      {q.data.reversalOf && <Alert tone="info">Reverses {q.data.reversalOf}: {q.data.reversalReason}</Alert>}
      {q.data.reversedBy && <Alert tone="warning">Reversed by {q.data.reversedBy}</Alert>}
      <DataTable rows={q.data.lines.map((l: any, i: number) => ({ ...l, id: String(i) }))} columns={[
        { key: 'a', label: 'Account', render: (l: any) => <Link to={`/finance/accounts?ledger=${l.accountId}`}>{l.account}</Link> },
        { key: 'd', label: 'Description', render: (l: any) => <span className="small">{l.description}{l.party && <div className="xs muted">{l.party}</div>}</span> },
        { key: 'dr', label: 'Debit', num: true, render: (l: any) => (Number(l.debit) ? money(l.debit) : '') }, { key: 'cr', label: 'Credit', num: true, render: (l: any) => (Number(l.credit) ? money(l.credit) : '') }]} />
      {q.data.approvalId && <Link to={`/approvals/${q.data.approvalId}`} className="small">Approval record →</Link>}
      {q.data.status === 'posted' && <div><Button variant="outline" onClick={() => setRev(true)}>Reverse</Button></div>}
      {rev && <FormDialog title={`Reverse ${q.data.number}`} onClose={() => setRev(false)} submitLabel="Post reversal" fields={[{ name: 'reason', label: 'Reason', type: 'textarea', required: true }]}
        onSubmit={(v) => finance.post(`journals/${id}/reverse`, v)} onDone={() => void q.refetch()} />}
    </div>}</Load></Dialog>;
}

export function Accounts() {
  const [params, setParams] = useSearchParams();
  const q = useF('accounts', { balances: 'true' });
  const [add, setAdd] = useState(false);
  const ledgerId = params.get('ledger');
  const [r, setR] = useState({ from: today().slice(0, 4) + '-04-01', to: today() });
  const gl = useF(`ledger/${ledgerId}`, r, !!ledgerId);
  return <>{FT('Chart of accounts', 'Configurable accounts. System-mapped accounts receive automatic postings and can’t be deactivated.',
    <Button variant="outline" onClick={() => setAdd(true)}><Icon name="plus" size={16} />New account</Button>)}
    {ledgerId ? <Load q={gl}>{() => <Card title={`${gl.data.account.code} ${gl.data.account.name}`} flush actions={<span className="row"><Range v={r} set={setR} />
      <DownloadButton api={finance} path={`ledger/${ledgerId}`} query={r} filename={`ledger-${gl.data.account.code}.csv`} /><Button variant="ghost" onClick={() => setParams({})}>Back</Button></span>}>
      <p className="small" style={{ padding: '8px 16px' }}>Opening {money(gl.data.opening)} · Closing <strong>{money(gl.data.closing)}</strong></p>
      <DataTable rows={gl.data.rows.map((x: any, i: number) => ({ ...x, id: String(i) }))} empty="No postings in this range" columns={[
        { key: 'd', label: 'Date', render: (x: any) => fmtDate(x.date) }, { key: 'n', label: 'Journal', render: (x: any) => <Link to={`/finance/journals?open=${x.journalId}`} className="mono xs">{x.number}</Link> },
        { key: 'e', label: 'Description', render: (x: any) => <span className="small">{x.description}{x.party && <div className="xs muted">{x.party}</div>}</span> },
        { key: 'dr', label: 'Debit', num: true, render: (x: any) => (Number(x.debit) ? money(x.debit) : '') }, { key: 'cr', label: 'Credit', num: true, render: (x: any) => (Number(x.credit) ? money(x.credit) : '') },
        { key: 'b', label: 'Balance', num: true, render: (x: any) => money(x.balance) }]} /></Card>}</Load> : (
      <Load q={q}>{() => <Card flush><DataTable rows={q.data.results} onRow={(a: any) => a.postable && setParams({ ledger: a.id })} columns={[
        { key: 'c', label: 'Code', render: (a: any) => <span className="mono" style={{ paddingLeft: a.parent ? 16 : 0, fontWeight: a.postable ? 400 : 700 }}>{a.code}</span> },
        { key: 'n', label: 'Account', render: (a: any) => <>{a.name}{a.systemKey && <span className="xs muted mono"> · {a.systemKey}</span>}</> },
        { key: 't', label: 'Type', render: (a: any) => humanize(a.type) }, { key: 'b', label: 'Balance', num: true, render: (a: any) => (a.balance !== undefined ? money(a.balance) : '') },
        { key: 's', label: '', render: (a: any) => !a.active && <Status value="neutral" label="Inactive" /> }]} /></Card>}</Load>)}
    {add && <FormDialog title="New account" onClose={() => setAdd(false)} fields={[{ name: 'code', label: 'Code', required: true, half: true }, { name: 'name', label: 'Name', required: true, half: true },
      { name: 'type', label: 'Type', type: 'select', required: true, options: q.data?.types ?? [] },
      { name: 'parent_id', label: 'Under', type: 'select', options: (q.data?.results ?? []).filter((a: any) => !a.postable).map((a: any) => ({ value: a.id, label: `${a.code} ${a.name}` })) }]}
      onSubmit={(v) => finance.post('accounts', v)} onDone={() => void q.refetch()} />}</>;
}

export function Periods() {
  const q = useF('periods');
  const [open, setOpen] = useState<any>(null);
  const tasks = useF(`periods/${open?.id}/tasks`, {}, !!open);
  const act = useAction((b: any) => finance.post(`periods/${b.id}/${b.action}`, b), [FK], 'Period updated');
  const upd = useAction((b: any) => finance.patch(`close-tasks/${b.id}`, b), [FK], 'Saved');
  const [dlg, setDlg] = useState<{ p: any; kind: 'close' | 'reopen' } | null>(null);
  return <>{FT('Periods & close', 'Close checklist, soft close, close and lock. Reopening a closed period needs a reason and a second approver.')}
    <Load q={q}>{() => <Card flush><DataTable rows={q.data.results} onRow={(p: any) => setOpen(p)} columns={[
      { key: 'n', label: 'Period', render: (p: any) => <strong>{p.name}</strong> }, { key: 's', label: 'Status', render: (p: any) => <Status value={p.status === 'open' ? 'active' : p.status === 'locked' ? 'neutral' : 'pending'} label={p.statusLabel} /> },
      { key: 't', label: 'Checklist', render: (p: any) => `${p.tasksDone}/${p.tasksTotal || 12}` }, { key: 'j', label: 'Journals', num: true, render: (p: any) => p.journals },
      { key: 'c', label: 'Closed', render: (p: any) => <span className="xs">{p.closedBy ? `${p.closedBy} · ${fmtDate(p.closedAt)}` : '—'}{p.reopenReason && <div className="muted">Reopened: {p.reopenReason}</div>}</span> },
      { key: 'a', label: '', render: (p: any) => <span className="row" style={{ gap: 4 }} onClick={(e) => e.stopPropagation()}>
        {p.status === 'open' && <Button size="sm" variant="ghost" onClick={() => act.mutate({ id: p.id, action: 'soft_close' })}>Soft close</Button>}
        {['open', 'soft_closed'].includes(p.status) && <Button size="sm" variant="outline" onClick={() => setDlg({ p, kind: 'close' })}>Close</Button>}
        {p.status === 'closed' && <><Button size="sm" variant="ghost" onClick={() => act.mutate({ id: p.id, action: 'lock' })}>Lock</Button>
          <Button size="sm" variant="ghost" onClick={() => setDlg({ p, kind: 'reopen' })}>Request reopen</Button></>}
        {p.status !== 'locked' && <Button size="sm" variant="ghost" onClick={() => act.mutate({ id: p.id, action: 'depreciation' })}>Run depreciation</Button>}</span> }]} /></Card>}</Load>
    {open && <Card title={`Close checklist · ${open.name}`} flush actions={<Button size="sm" variant="ghost" onClick={() => setOpen(null)}>Close</Button>}>
      <Load q={tasks}>{() => <DataTable rows={tasks.data.results} columns={[{ key: 't', label: 'Task', render: (t: any) => t.title },
        { key: 'o', label: 'Owner', render: (t: any) => t.owner ?? '—' },
        { key: 's', label: 'Status', render: (t: any) => <select className="field__input" aria-label={`Status for ${t.title}`} value={t.status} onChange={(e) => upd.mutate({ id: t.id, status: e.target.value })}>
          <option value="todo">To do</option><option value="done">Done</option><option value="na">Not applicable</option></select> },
        { key: 'c', label: 'Completed', render: (t: any) => <span className="xs muted">{t.completedBy ? `${t.completedBy} · ${fmtDate(t.completedAt)}` : ''}</span> }]} />}</Load></Card>}
    {dlg?.kind === 'close' && <FormDialog title={`Close ${dlg.p.name}`} onClose={() => setDlg(null)} submitLabel="Close period"
      intro={<p className="small muted">Postings stop once closed. Open checklist items need a reason.</p>} fields={[{ name: 'override_reason', label: 'Reason if closing with open tasks', type: 'textarea' }]}
      onSubmit={(v) => finance.post(`periods/${dlg.p.id}/close`, v)} onDone={() => void q.refetch()} />}
    {dlg?.kind === 'reopen' && <FormDialog title={`Request to reopen ${dlg.p.name}`} onClose={() => setDlg(null)} submitLabel="Send for approval"
      fields={[{ name: 'reason', label: 'Why must it be reopened?', type: 'textarea', required: true }]} onSubmit={(v) => finance.post(`periods/${dlg.p.id}/reopen`, v)} />}</>;
}

// ---------------------------------------------------------------------------------------------------------------------
export function Reports() {
  const [params, setParams] = useSearchParams();
  const r = params.get('r') ?? 'pl';
  const [range, setRange] = useState({ from: today().slice(0, 4) + '-04-01', to: today() });
  const q = useF('reports', { r, ...range });
  return <>{FT('Financial reports', 'Straight from the posted ledger. Every account drills down to its journals and source transactions.',
    <><Range v={range} set={setRange} /><DownloadButton api={finance} path="reports" query={{ r, ...range }} filename={`${r}-${range.to}.csv`} /></>)}
    <Tabs value={r} onChange={(v) => setParams({ r: v })} items={(q.data?.available ?? [{ key: 'pl', label: 'Profit & loss' }]).map((x: any) => ({ value: x.key, label: x.label }))} />
    <Load q={q}>{() => <ReportBody r={r} d={q.data.data} />}</Load></>;
}

function AccRows({ rows }: { rows: any[] }) {
  return <DataTable rows={rows.map((x: any) => ({ ...x, id: x.accountId ?? x.code }))} empty="No postings" columns={[
    { key: 'c', label: 'Account', render: (x: any) => <Link to={`/finance/accounts?ledger=${x.accountId}`}>{x.code} {x.name}</Link> },
    { key: 'a', label: 'Amount', num: true, render: (x: any) => money(x.amount) }]} />;
}

function ReportBody({ r, d }: { r: string; d: any }) {
  if (r === 'pl') return <div className="stack">{d.sections.map((s: any) => <Card key={s.type} title={`${s.label} — ${money(s.total)}`} flush><AccRows rows={s.rows} /></Card>)}
    <Kpis items={[{ label: 'Revenue', value: money(d.revenue) }, { label: 'Gross profit', value: money(d.grossProfit) }, { label: 'Operating profit', value: money(d.operatingProfit) },
      { label: 'Net profit', value: money(d.netProfit), tone: Number(d.netProfit) >= 0 ? 'good' : 'alert' }]} /><p className="xs muted">{d.note}</p></div>;
  if (r === 'bs') return <div className="stack">{!d.balanced && <Alert tone="error">The balance sheet does not balance — check unposted or corrupted entries.</Alert>}
    <div className="grid grid--2"><Card title={`Assets — ${money(d.totalAssets)}`} flush><AccRows rows={d.assets} /></Card>
      <div className="stack"><Card title={`Liabilities — ${money(d.totalLiabilities)}`} flush><AccRows rows={d.liabilities} /></Card>
        <Card title={`Equity — ${money(d.totalEquity)}`} flush><AccRows rows={[...d.equity, { code: '', name: 'Current earnings', amount: d.currentEarnings }]} /></Card></div></div></div>;
  if (r === 'tb') return <Card flush title={d.balanced ? 'Balanced ✓' : 'NOT balanced'}><DataTable rows={d.rows.map((x: any) => ({ ...x, id: x.accountId }))} columns={[
    { key: 'c', label: 'Account', render: (x: any) => <Link to={`/finance/accounts?ledger=${x.accountId}`}>{x.code} {x.name}</Link> },
    { key: 'd', label: 'Debit', num: true, render: (x: any) => (Number(x.debit) ? money(x.debit) : '') }, { key: 'k', label: 'Credit', num: true, render: (x: any) => (Number(x.credit) ? money(x.credit) : '') }]} />
    <p className="small" style={{ padding: 12 }}>Totals: {money(d.totalDebit)} / {money(d.totalCredit)}</p></Card>;
  if (r === 'cf') return <><Kpis items={[{ label: 'Opening cash', value: money(d.openingCash) }, { label: 'Operating', value: money(d.operating) }, { label: 'Investing', value: money(d.investing) },
    { label: 'Financing', value: money(d.financing) }, { label: 'Closing cash', value: money(d.closingCash) }]} /><p className="xs muted">{d.note}</p></>;
  if (r === 'tax') return <TaxReport d={d} />;
  if (r === 'ar' || r === 'ap') return <Aging d={d} />;
  if (r === 'cash') return <Card flush><DataTable rows={d.accounts} columns={[{ key: 'n', label: 'Account', render: (a: any) => a.name }, { key: 'b', label: 'Balance', num: true, render: (a: any) => money(a.balance) }]} /></Card>;
  if (r === 'forecast') return <Alert tone="warning">{d.label} Projected: {money(d.projectedCash)}. Open Cash position for the detail.</Alert>;
  if (r === 'platform') return <Kpis items={[{ label: 'GTV (not revenue)', value: money(d.grossTransactionValue) }, { label: 'Click revenue', value: money(d.clickRevenue) },
    { label: 'Partner earnings', value: money(d.partnerEarnings) }, { label: 'Net revenue', value: money(d.clickNetRevenue) }]} />;
  return <Empty title="Choose a report" />;
}

export function Aging({ d }: { d: any }) {
  return <div className="stack"><Kpis items={d.buckets.map((b: any) => ({ label: b.bucket === 'current' ? 'Not yet due' : `${b.bucket} days`, value: money(b.amount), tone: b.bucket === '120+' && Number(b.amount) ? 'alert' : undefined }))} />
    <Card flush><DataTable rows={d.rows} empty="Nothing outstanding" columns={[{ key: 'n', label: 'Document', render: (x: any) => <><span className="mono">{x.number}</span><div className="xs muted">{x.party}</div></> },
      { key: 'd', label: 'Due', render: (x: any) => fmtDate(x.dueDate) }, { key: 'o', label: 'Days overdue', num: true, render: (x: any) => x.daysOverdue },
      { key: 'a', label: 'Outstanding', num: true, render: (x: any) => money(x.outstanding) }, { key: 'r', label: 'Risk', render: (x: any) => <span className={`sev sev--${x.risk === 'high' ? 'high' : x.risk === 'medium' ? 'medium' : 'low'}`} title={x.risk} /> }]} /></Card></div>;
}

function TaxReport({ d }: { d: any }) {
  return <div className="stack"><Alert tone="warning">{d.disclaimer}</Alert>
    <Kpis items={[{ label: 'Output tax', value: money(d.outputTax) }, { label: 'Input tax credit', value: money(d.inputTax) }, { label: 'Net payable', value: money(d.netPayable) },
      { label: 'Tax on platform fees', value: money(d.platformFeeTax) }, { label: 'Tax payable balance', value: money(d.taxPayableBalance) }]} />
    <Card flush><DataTable rows={d.rows.map((x: any) => ({ ...x, id: x.code }))} empty="No taxed documents in this range" columns={[{ key: 'c', label: 'Rule', render: (x: any) => <>{x.code}<div className="xs muted">{x.name}</div></> },
      { key: 'o', label: 'Output', num: true, render: (x: any) => money(x.outputTax) }, { key: 'i', label: 'Input', num: true, render: (x: any) => money(x.inputTax) }]} /></Card></div>;
}

export function Tax() {
  const rules = useF('tax-rules');
  const [range, setRange] = useState({ from: monthStart(), to: today() });
  const rep = useF('reports', { r: 'tax', ...range });
  const [add, setAdd] = useState(false);
  return <>{FT('Tax', 'Configurable, versioned tax rules and the tax report from the ledger.', <><Range v={range} set={setRange} />
    <Button variant="outline" onClick={() => setAdd(true)}>New rate version</Button></>)}
    <div className="stack stack--lg">
      <Load q={rep}>{() => <TaxReport d={rep.data.data} />}</Load>
      <Load q={rules}>{() => <Card title="Tax rules" flush><DataTable rows={rules.data.results} columns={[{ key: 'c', label: 'Code', render: (r: any) => <span className="mono">{r.code} v{r.version}</span> },
        { key: 'n', label: 'Name', render: (r: any) => r.name }, { key: 'r', label: 'Rate', num: true, render: (r: any) => `${Number(r.rate)}%` },
        { key: 'e', label: 'Effective', render: (r: any) => `${fmtDate(r.effectiveFrom)} → ${r.effectiveTo ? fmtDate(r.effectiveTo) : 'now'}` }]} />
        <p className="xs muted" style={{ padding: 12 }}>{rules.data.disclaimer}</p></Card>}</Load>
    </div>
    {add && <FormDialog title="New tax rate version" onClose={() => setAdd(false)} intro={<p className="small muted">The current version ends the day before; documents already issued keep their rate.</p>}
      fields={[{ name: 'code', label: 'Code (existing or new)', required: true, half: true }, { name: 'rate', label: 'Rate %', type: 'number', required: true, half: true },
        { name: 'effective_from', label: 'Effective from', type: 'date', required: true, half: true }, { name: 'name', label: 'Name (new codes)', half: true },
        { name: 'kind', label: 'Kind', type: 'select', options: ['gst', 'cgst', 'sgst', 'igst', 'utgst', 'tds', 'tcs', 'other'].map((k) => ({ value: k, label: k.toUpperCase() })) }]}
      onSubmit={(v) => finance.post('tax-rules', v)} onDone={() => void rules.refetch()} />}</>;
}

export function Controls() {
  const q = useF('controls');
  return <>{FT('Controls & audit', 'Approval limits, segregation of duties, periods and sensitive financial events.')}
    <Load q={q}>{() => <div className="stack stack--lg">
      <Kpis items={[{ label: 'Trial balance', value: q.data.unbalancedCheck ? 'Balanced' : 'NOT balanced', tone: q.data.unbalancedCheck ? 'good' : 'alert' },
        { label: 'Journals awaiting approval', value: q.data.pendingJournals }, { label: 'Manual journals (30d)', value: q.data.manualJournals30d },
        { label: 'Bank detail changes (90d)', value: q.data.bankChanges90d, tone: q.data.bankChanges90d ? 'alert' : undefined }, { label: 'Commission changes (90d)', value: q.data.commissionChanges90d }]} />
      <Card title="How Finance protects the books"><ul className="small" style={{ margin: 0, paddingLeft: 18 }}>{q.data.principles.map((p: string) => <li key={p}>{p}</li>)}</ul></Card>
      <div className="grid grid--2">
        <Card title="Approval limits" flush actions={<Link to="/settings/roles" className="small">Roles</Link>}><DataTable rows={q.data.approvalLimits.map((x: any, i: number) => ({ ...x, id: String(i) }))} columns={[
          { key: 'r', label: 'Role', render: (x: any) => x.role }, { key: 't', label: 'Type', render: (x: any) => humanize(x.type) }, { key: 'm', label: 'Up to', num: true, render: (x: any) => (x.max === 'No limit' ? x.max : money(x.max)) }]} /></Card>
        <Card title="Segregation of duties" flush actions={<Link to="/access/sod" className="small">Manage</Link>}><DataTable rows={q.data.sodRules.map((x: any) => ({ ...x, id: x.name }))} columns={[
          { key: 'n', label: 'Rule', render: (x: any) => x.name }, { key: 's', label: 'Severity', render: (x: any) => humanize(x.severity) }]} /></Card>
      </div>
      <Card title="Sensitive financial events" flush><DataTable rows={q.data.sensitiveEvents.map((x: any, i: number) => ({ ...x, id: String(i) }))} empty="None, or you can’t see the audit trail" columns={[
        { key: 'a', label: 'Event', render: (x: any) => <span className="mono xs">{x.action}</span> }, { key: 'l', label: 'Record', render: (x: any) => x.label },
        { key: 'u', label: 'Who', render: (x: any) => x.actor }, { key: 't', label: 'When', render: (x: any) => fmtDateTime(x.at) }]} /></Card>
    </div>}</Load></>;
}

export function Settings() {
  const q = useF('settings');
  const ent = useF('entities');
  return <>{FT('Finance settings', 'Entities, cost centers, payment methods and expense policies. Accounts and tax rules have their own pages.')}
    <div className="stack stack--lg">
      <Load q={ent}>{() => <Card title="Financial entities" flush><DataTable rows={ent.data.results} columns={[{ key: 'n', label: 'Entity', render: (e: any) => <>{e.name}<div className="xs muted">{e.legalName}</div></> },
        { key: 'c', label: 'Currency', render: (e: any) => e.currency }, { key: 'f', label: 'Fiscal year starts', render: (e: any) => `Month ${e.fyStartMonth}` }, { key: 't', label: 'Tax registration', render: (e: any) => e.taxRegistration || '—' }]} /></Card>}</Load>
      <Load q={q}>{() => <div className="grid grid--2">
        <Card title="Cost centers & projects" flush><DataTable rows={q.data.costCenters} columns={[{ key: 'c', label: 'Code', render: (c: any) => <span className="mono">{c.code}</span> }, { key: 'n', label: 'Name', render: (c: any) => c.name },
          { key: 'k', label: 'Kind', render: (c: any) => humanize(c.kind) }, { key: 'd', label: 'Department', render: (c: any) => c.department ?? '—' }]} /></Card>
        <Card title="Payment methods (gateway cost)" flush><DataTable rows={q.data.paymentMethods.map((m: any) => ({ ...m, id: m.method }))} columns={[{ key: 'm', label: 'Method', render: (m: any) => m.label },
          { key: 'f', label: 'Fee', num: true, render: (m: any) => `${Number(m.feePct)}%` }, { key: 's', label: 'Settles in', render: (m: any) => `${m.settlementDays} days` }]} /></Card>
        <Card title="Expense policies" flush><DataTable rows={q.data.expenseCategories} columns={[{ key: 'n', label: 'Category', render: (c: any) => c.name },
          { key: 'l', label: 'Limit / claim', num: true, render: (c: any) => (c.limit ? money(c.limit) : '—') }, { key: 'r', label: 'Receipt above', num: true, render: (c: any) => money(c.receiptAbove) }]} /></Card>
      </div>}</Load>
    </div></>;
}
