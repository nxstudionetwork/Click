import { useEffect, useState } from 'react';
import { Link, useParams, useSearchParams } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { Button, EmptyState, ErrorState, Icon, Skeleton, useToast } from '../components/ui';
import { MoneyHead, Pill, THEME, dateOf, dateTimeOf, iconFor, money } from '../features/money/parts';
import { api } from '../lib/api';

const LABEL: Record<string, string> = {
  food: 'Food', groceries: 'Groceries', shop: 'Shop', ride: 'Ride', travel: 'Travel', hotels: 'Hotels', shows: 'Shows', events: 'Events',
  services: 'Services', parcel: 'Parcel', bookings: 'Bookings', gift_cards: 'Gift Cards',
};
const STATUS = [['', 'Any status'], ['generated', 'Generated'], ['refund_document', 'Refund document'], ['pending', 'Pending'], ['cancelled', 'No charge']];
const tone = (s: string) => (s === 'generated' ? 'ok' : s === 'refund_document' ? 'info' : s === 'pending' ? 'pending' : 'info') as 'ok' | 'info' | 'pending';

/** Invoice Center (Profile → Invoices): a card for everything you bought or booked, with its invoice state. Invoices
 *  are built on the server from the payment and the order / booking it paid for. */
export function InvoicesPage() {
  const [params, setParams] = useSearchParams();
  const [q, setQ] = useState(params.get('q') ?? '');
  const service = params.get('service') ?? '', status = params.get('status') ?? '', from = params.get('from') ?? '', to = params.get('to') ?? '';
  const set = (k: string, v: string) => { const n = new URLSearchParams(params); if (v) n.set(k, v); else n.delete(k); setParams(n, { replace: true }); };
  useEffect(() => { const t = setTimeout(() => { if ((params.get('q') ?? '') !== q.trim()) set('q', q.trim()); }, 350); return () => clearTimeout(t); }); // eslint-disable-line react-hooks/exhaustive-deps
  const list = useQuery({ queryKey: ['invoices', service, status, params.get('q') ?? '', from, to], queryFn: () => api.money.invoices.list({ service, status, q: params.get('q') ?? '', from, to }) });
  return (
    <div className="mn-page">
      <MoneyHead title="Invoices" />
      <div className="mn-search"><Icon name="search" size={18} />
        <input type="search" value={q} onChange={(e) => setQ(e.target.value)} placeholder="Invoice number, order or booking ID, vendor" aria-label="Search invoices" /></div>
      {list.data && (
        <div className="mn-chips" role="tablist" aria-label="Service">
          <button type="button" role="tab" className="mn-chip" aria-pressed={!service} aria-selected={!service} onClick={() => set('service', '')}>All</button>
          {list.data.services.map((s) => <button key={s} type="button" role="tab" className="mn-chip" aria-pressed={service === s} aria-selected={service === s} onClick={() => set('service', s)}>
            <Icon name={iconFor(s)} size={15} />{LABEL[s] ?? s}</button>)}
        </div>
      )}
      <div className="mn-selects">
        <select value={status} onChange={(e) => set('status', e.target.value)} aria-label="Invoice status">{STATUS.map(([v, l]) => <option key={v} value={v}>{l}</option>)}</select>
        <input type="date" value={from} max={to || undefined} onChange={(e) => set('from', e.target.value)} aria-label="From date" />
        <input type="date" value={to} min={from || undefined} onChange={(e) => set('to', e.target.value)} aria-label="To date" />
      </div>
      {list.isError ? <ErrorState error={list.error} onRetry={() => list.refetch()} /> : !list.data ? <Skeleton height={320} /> : list.data.results.length === 0 ? (
        <EmptyState icon="receipt" title="No invoices here" message="Invoices appear for orders and bookings once they’re paid." />
      ) : (
        <div className="inv-grid">{list.data.results.map((c) => {
          const body = (<>
            <div className="inv-card__top"><span className="inv-card__icon"><Icon name={iconFor(c.service)} size={18} /></span><strong>{c.label}</strong><Pill tone={tone(c.invoiceStatus)}>{c.invoiceStatusLabel}</Pill></div>
            <span className="inv-card__vendor truncate">{c.vendor}</span>
            <dl className="inv-card__facts">
              <div><dt>Ref</dt><dd className="mn-mono">{c.reference}</dd></div>
              <div><dt>Date</dt><dd>{dateOf(c.date)}</dd></div>
              <div><dt>Total</dt><dd><strong>{money(c.amount)}</strong></dd></div>
              {c.number && <div><dt>Invoice</dt><dd className="mn-mono">{c.number}</dd></div>}
            </dl>
            {c.refunded && <span className="small mn-ok">Refunded {money(c.refunded)}</span>}
            <span className="inv-card__cta small">{c.id ? 'View invoice' : 'View order / booking'} <Icon name="right" size={14} /></span>
          </>);
          return c.id ? <Link key={c.paymentId} to={`/account/invoices/${c.id}`} className="inv-card" data-theme={THEME[c.service]}>{body}</Link>
            : <Link key={c.paymentId} to={c.link} className="inv-card inv-card--muted" data-theme={THEME[c.service]}>{body}</Link>;
        })}</div>
      )}
    </div>
  );
}

export function InvoicePage() {
  const { id = '' } = useParams();
  const toast = useToast();
  const q = useQuery({ queryKey: ['invoices', 'detail', id], queryFn: () => api.money.invoices.get(id) });
  const [busy, setBusy] = useState(false);
  if (q.isError) return <div className="mn-page"><MoneyHead title="Invoice" back="/account/invoices" /><ErrorState error={q.error} onRetry={() => q.refetch()} /></div>;
  if (!q.data) return <div className="mn-page"><MoneyHead title="Invoice" back="/account/invoices" /><Skeleton height={420} /></div>;
  const d = q.data;
  const t = d.totals;
  const download = async () => {
    setBusy(true);
    try {
      const b = await api.money.invoices.document(d.id);
      const url = URL.createObjectURL(b);
      const a = document.createElement('a');
      a.href = url; a.download = `${d.number}.html`; document.body.appendChild(a); a.click(); a.remove();
      setTimeout(() => URL.revokeObjectURL(url), 60_000);
    } catch { toast('Couldn’t download the invoice. Try again.', 'error'); } finally { setBusy(false); }
  };
  const share = async () => {
    const text = `${d.title} ${d.number} · ${d.label} ${d.reference} · ${money(t.total)}`;
    try { if (navigator.share) await navigator.share({ title: d.number, text }); else { await navigator.clipboard.writeText(text); toast('Invoice details copied'); } } catch { /* cancelled */ }
  };
  return (
    <div className="mn-page">
      <MoneyHead title={d.number} back="/account/invoices" />
      <article className="inv-doc">
        <header className="inv-doc__top">
          <div><div className="inv-doc__brand">Click<b>.</b></div><h2>{d.title}</h2></div>
          <dl className="mn-dl"><div><dt>Invoice no.</dt><dd className="mn-mono">{d.number}</dd></div><div><dt>Date</dt><dd>{dateTimeOf(d.issuedAt)}</dd></div>
            <div><dt>For</dt><dd>{d.label} {d.reference}</dd></div><div><dt>Status</dt><dd>{d.statusLabel}</dd></div></dl>
        </header>
        <div className="inv-doc__parties">
          <div><span className="inv-k">Seller</span><strong>{d.seller.name}</strong>{d.seller.address && <span>{d.seller.address}</span>}
            {d.seller.partnerId && <span className="small mn-muted">Partner ID {d.seller.partnerId}</span>}{d.seller.gstin && <span>GSTIN {d.seller.gstin}</span>}</div>
          <div><span className="inv-k">Billed to</span><strong>{d.buyer.name}</strong>{d.buyer.address && <span>{d.buyer.address}</span>}
            <span>{d.buyer.email}</span>{d.buyer.phone && <span>{d.buyer.phone}</span>}<span className="small mn-muted">Click. ID {d.buyer.customerId}</span></div>
        </div>
        <div className="inv-table" role="table" aria-label="Items">
          <div className="inv-tr inv-th" role="row"><span role="columnheader">Item</span><span role="columnheader">Qty</span><span role="columnheader">Amount</span></div>
          {d.lines.map((l, i) => <div key={i} className="inv-tr" role="row"><span role="cell">{l.description}{l.unitPrice && <span className="small mn-muted"> · {money(l.unitPrice)} each</span>}</span>
            <span role="cell">{l.quantity}</span><span role="cell">{money(l.total)}</span></div>)}
        </div>
        <dl className="mn-dl inv-totals">
          <div><dt>Subtotal</dt><dd>{money(t.subtotal)}</dd></div>
          {Number(t.discount) > 0 && <div><dt>Discount{t.offer ? ` (${t.offer})` : ''}</dt><dd>−{money(t.discount)}</dd></div>}
          {Number(t.deliveryFee) > 0 && <div><dt>Delivery fee</dt><dd>{money(t.deliveryFee)}</dd></div>}
          {Number(t.fees) > 0 && <div><dt>Fees</dt><dd>{money(t.fees)}</dd></div>}
          {Number(t.tax) > 0 && <div><dt>Taxes</dt><dd>{money(t.tax)}</dd></div>}
          <div className="mn-dl__total"><dt>Total</dt><dd>{money(t.total)}</dd></div>
          <div><dt>Paid by {d.payment.method}</dt><dd>{money(t.paid)}</dd></div>
          <div><dt>Payment reference</dt><dd className="mn-mono">{d.payment.reference}</dd></div>
        </dl>
        {d.refunds.length > 0 && (
          <section className="inv-refunds"><h3>Refund documents</h3>
            {d.refunds.map((r) => <div key={r.number} className="inv-tr"><span><strong className="mn-mono">{r.number}</strong><span className="small mn-muted"> · {r.reason} · to {r.to} · {dateOf(r.at)}</span></span><span /><span className="mn-ok">{money(r.amount)}</span></div>)}
          </section>
        )}
        {d.gstNote && <p className="small mn-muted">{d.gstNote}</p>}
      </article>
      <div className="mn-row2">
        <Button loading={busy} onClick={download}><Icon name="download" size={16} /> Download invoice</Button>
        <Button variant="secondary" onClick={share}><Icon name="share" size={16} /> Share</Button>
      </div>
      <div className="mn-list">
        <Link to={d.link} className="mn-row"><span className="mn-row__icon"><Icon name="receipt" size={18} /></span><span className="mn-row__text"><strong>View {d.label.toLowerCase().split(' · ')[0]}</strong><span className="small mn-muted">{d.reference}</span></span><Icon name="right" size={16} /></Link>
        <Link to={`/account/payments/${d.payment.id}`} className="mn-row"><span className="mn-row__icon"><Icon name="card" size={18} /></span><span className="mn-row__text"><strong>Payment details</strong><span className="small mn-muted">{d.payment.reference}</span></span><Icon name="right" size={16} /></Link>
        <Link to={`/help/new?category=payment&related=payment:${d.payment.id}`} className="mn-row"><span className="mn-row__icon"><Icon name="help" size={18} /></span><span className="mn-row__text"><strong>Get help with this invoice</strong></span><Icon name="right" size={16} /></Link>
      </div>
    </div>
  );
}
