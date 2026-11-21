import { Link, useParams } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { ErrorState, Icon, Skeleton } from '../components/ui';
import { MoneyHead, Pill, Section, dateTimeOf, money, signed, toneOfPayment } from '../features/money/parts';
import { api } from '../lib/api';

const STATUS_NOTE: Record<string, string> = {
  pending: 'The payment hasn’t been confirmed yet. Nothing is assumed: this updates when the payment provider or Click. confirms it.',
  pay_later: 'Nothing has been charged. You pay when the order is delivered or at the venue.',
  failed: 'The payment didn’t go through and the order or booking wasn’t paid. If money left your account, your bank or payment app returns it as per their timelines.',
  cancelled: 'This payment was cancelled before any money was taken.',
};

/** One payment: amount, method, status, breakdown, wallet movements, refunds, receipt and help. */
export function PaymentDetailPage() {
  const { id = '' } = useParams();
  const q = useQuery({ queryKey: ['payments', 'detail', id], queryFn: () => api.money.payments.get(id) });
  if (q.isError) return <div className="mn-page"><MoneyHead title="Payment" back="/account/payments" /><ErrorState error={q.error} onRetry={() => q.refetch()} /></div>;
  if (!q.data) return <div className="mn-page"><MoneyHead title="Payment" back="/account/payments" /><Skeleton height={160} radius={20} /><Skeleton height={240} /></div>;
  const p = q.data;
  return (
    <div className="mn-page">
      <MoneyHead title="Payment" back="/account/payments" action={p.receipt ? <button type="button" className="mn-head__home" onClick={() => window.print()} aria-label="Print receipt"><Icon name="download" size={20} /></button> : undefined} />
      <section className="mn-card mn-hero-amt">
        <span className="small mn-muted">{p.label}</span>
        <strong>{money(p.amount)}</strong>
        <span>{p.methodLabel} · {dateTimeOf(p.createdAt)}</span>
        <Pill tone={toneOfPayment(p.status)}>{p.statusLabel}</Pill>
      </section>
      {STATUS_NOTE[p.status] && <div className={`mn-banner ${p.status === 'failed' ? 'mn-banner--bad' : ''}`}><Icon name={p.status === 'failed' ? 'alert' : 'clock'} size={20} /><p className="small">{STATUS_NOTE[p.status]}</p></div>}
      {p.retry && <Link to={p.retry.path} className="btn btn--primary">{p.retry.label}</Link>}

      <section className="mn-card">
        <dl className="mn-dl">
          <div><dt>Payment reference</dt><dd className="mn-mono">{p.reference}</dd></div>
          <div><dt>For</dt><dd><Link to={p.link} className="mn-link">{p.label} · {p.orderReference}</Link></dd></div>
          <div><dt>Method</dt><dd>{p.methodLabel}</dd></div>
          {p.providerReference && <div><dt>Provider reference</dt><dd className="mn-mono">{p.providerReference}</dd></div>}
        </dl>
      </section>

      {p.breakdown && (
        <Section title="Breakdown" id="mn-bd">
          <dl className="mn-dl mn-card">
            {p.breakdown.lines.map((l) => <div key={l.label} className={l.label === 'Total' ? 'mn-dl__total' : ''}><dt>{l.label}</dt><dd>{l.label === 'Discount' ? `−${money(l.amount)}` : money(l.amount)}</dd></div>)}
            {p.breakdown.offer && <div><dt>Offer</dt><dd>{p.breakdown.offer}</dd></div>}
          </dl>
        </Section>
      )}

      {p.walletEntries.length > 0 && (
        <Section title="Click. Wallet" id="mn-we">
          <ul className="mn-list">{p.walletEntries.map((t) => (
            <li key={t.id}><Link to={`/wallet/activity/${t.id}`} className="mn-row"><span className="mn-row__icon"><Icon name="wallet" size={18} /></span>
              <span className="mn-row__text"><strong>{t.kindLabel}</strong><span className="small mn-muted">{t.bucket === 'promo' ? 'Promo credit' : 'Wallet balance'}</span></span>
              <strong className={Number(t.amount) > 0 ? 'mn-ok' : ''}>{signed(t.amount)}</strong></Link></li>
          ))}</ul>
        </Section>
      )}

      {p.refunds.length > 0 && (
        <Section title="Refunds" id="mn-rf">
          <ul className="mn-list">{p.refunds.map((r) => (
            <li key={r.id} className="mn-row mn-row--static"><span className="mn-row__icon mn-row__icon--ok"><Icon name="history" size={18} /></span>
              <span className="mn-row__text"><strong>{money(r.amount)} to {r.to}</strong><span className="small mn-muted">{r.description} · {dateTimeOf(r.creditedAt)}</span></span>
              <Pill tone="ok">{r.statusLabel}</Pill></li>
          ))}</ul>
        </Section>
      )}

      <div className="mn-list">
        {p.tickets.map((x) => (
          <Link key={x.id} to={`/help/tickets/${x.id}`} className="mn-row"><span className="mn-row__icon"><Icon name="help" size={18} /></span>
            <span className="mn-row__text"><strong>Support request {x.reference}</strong><span className="small mn-muted">{x.status.replace('_', ' ')}</span></span><Icon name="right" size={16} /></Link>
        ))}
        <Link to={`/help/new?category=payment&related=payment:${p.id}`} className="mn-row"><span className="mn-row__icon"><Icon name="alert" size={18} /></span>
          <span className="mn-row__text"><strong>Report a problem with this payment</strong><span className="small mn-muted">Charged but not confirmed, wrong amount, refund not received</span></span><Icon name="right" size={16} /></Link>
      </div>
    </div>
  );
}
