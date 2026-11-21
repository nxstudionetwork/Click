import { Link, useParams } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { ErrorState, Icon, Skeleton } from '../components/ui';
import { MoneyHead, Pill, dateTimeOf, money, signed } from '../features/money/parts';
import { api } from '../lib/api';

/** One wallet ledger entry: what happened, the balance before and after, and where it came from. */
export function WalletEntryPage() {
  const { id = '' } = useParams();
  const q = useQuery({ queryKey: ['wallet', 'transaction', id], queryFn: () => api.money.wallet.transaction(id) });
  if (q.isError) return <div className="mn-page"><MoneyHead title="Transaction" back="/wallet" /><ErrorState error={q.error} onRetry={() => q.refetch()} /></div>;
  if (!q.data) return <div className="mn-page"><MoneyHead title="Transaction" back="/wallet" /><Skeleton height={160} radius={20} /><Skeleton height={220} /></div>;
  const t = q.data;
  const credit = t.direction === 'credit';
  return (
    <div className="mn-page">
      <MoneyHead title="Transaction" back="/wallet" />
      <section className="mn-card mn-hero-amt">
        <span className="small mn-muted">{t.kindLabel}</span>
        <strong className={credit ? 'mn-ok' : ''}>{signed(t.amount)}</strong>
        <span>{t.description}</span>
        <Pill tone={t.status === 'completed' ? 'ok' : 'pending'}>{t.statusLabel}</Pill>
      </section>

      <section className="mn-card">
        <dl className="mn-dl">
          <div><dt>Date</dt><dd>{dateTimeOf(t.createdAt)}</dd></div>
          <div><dt>Reference</dt><dd className="mn-mono">{t.reference}</dd></div>
          <div><dt>From / to</dt><dd>{t.bucketLabel}</dd></div>
          <div><dt>Balance before</dt><dd>{money(t.balanceBefore)}</dd></div>
          <div><dt>Balance after</dt><dd>{money(t.balanceAfter)}</dd></div>
          {t.expiresAt && <div><dt>{t.credit?.expired ? 'Expired on' : 'Valid till'}</dt><dd>{dateTimeOf(t.expiresAt)}</dd></div>}
          {t.credit && <div><dt>Credit left</dt><dd>{money(t.credit.remaining)} <span className="small mn-muted">({money(t.credit.used)} used)</span></dd></div>}
          {t.fromCredit && <div><dt>Paid from</dt><dd><Link to={`/wallet/activity/${t.fromCredit.id}`} className="mn-link">{t.fromCredit.description}</Link></dd></div>}
          {t.topup && <div><dt>Added via</dt><dd>{t.topup.method.toUpperCase()} · <span className="mn-mono">{t.topup.providerReference}</span></dd></div>}
          {t.refund && <div><dt>Refund of</dt><dd>{money(t.refund.originalAmount)} paid by {t.refund.originalMethod} · {t.refund.statusLabel}</dd></div>}
          {t.reward && <div><dt>Rewards</dt><dd>{t.reward.points.toLocaleString('en-IN')} points → {t.reward.item}</dd></div>}
        </dl>
      </section>

      {t.service && (
        <div className="mn-list">
          {t.service.service !== 'wallet' && <Link to={t.service.link} className="mn-row"><span className="mn-row__icon"><Icon name="receipt" size={18} /></span>
            <span className="mn-row__text"><strong>{t.service.label}</strong><span className="small mn-muted">{t.service.reference}</span></span><Icon name="right" size={16} /></Link>}
          <Link to={`/account/payments/${t.service.paymentId}`} className="mn-row"><span className="mn-row__icon"><Icon name="card" size={18} /></span>
            <span className="mn-row__text"><strong>Payment details</strong><span className="small mn-muted">Breakdown, refunds and receipt</span></span><Icon name="right" size={16} /></Link>
        </div>
      )}

      <div className="mn-list">
        {t.tickets.map((x) => (
          <Link key={x.id} to={`/help/tickets/${x.id}`} className="mn-row"><span className="mn-row__icon"><Icon name="help" size={18} /></span>
            <span className="mn-row__text"><strong>Support request {x.reference}</strong><span className="small mn-muted">{x.status.replace('_', ' ')}</span></span><Icon name="right" size={16} /></Link>
        ))}
        <Link to={`/help/new?category=wallet&related=wallet_transaction:${t.id}`} className="mn-row"><span className="mn-row__icon"><Icon name="alert" size={18} /></span>
          <span className="mn-row__text"><strong>Report a problem with this transaction</strong><span className="small mn-muted">It’s attached to your request automatically</span></span><Icon name="right" size={16} /></Link>
      </div>
    </div>
  );
}
