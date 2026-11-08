import { Link } from 'react-router-dom';
import { EmptyState, ErrorState, Icon, Skeleton, type IconName } from '../components/ui';
import { PageHeader } from '../components/shell/PageHeader';
import { useWallet } from '../features/wallet/useWallet';
import { formatDateTime, formatMoney } from '../lib/format';

const KIND: Record<string, { label: string; icon: IconName }> = {
  topup: { label: 'Money added', icon: 'plus' },
  refund: { label: 'Refund', icon: 'history' },
  promo: { label: 'Click credit', icon: 'gift' },
  payment: { label: 'Payment', icon: 'card' },
  adjustment: { label: 'Adjustment', icon: 'settings' },
};

export function WalletPage() {
  const wallet = useWallet();
  if (wallet.isError) return <ErrorState error={wallet.error} onRetry={() => wallet.refetch()} />;
  if (wallet.isPending) return <div className="stack"><Skeleton height={160} radius={22} /><Skeleton height={220} /></div>;
  const w = wallet.data;
  return (
    <div className="stack">
      <PageHeader title="Click Wallet" back={{ to: '/account', label: 'Account' }} />
      <section className="wallet-card">
        <span className="small" style={{ opacity: 0.8 }}>Available balance</span>
        <span className="wallet-card__value">{formatMoney(w.balance, w.currency)}</span>
        <span className="small" style={{ opacity: 0.8 }}>Use it at checkout for orders and bookings. Refunds for wallet payments return here instantly.</span>
        <button className="btn btn--sm" disabled style={{ alignSelf: 'flex-start', background: 'rgb(255 255 255 / 15%)', color: '#fff' }} title="Requires the payment-gateway integration">
          <Icon name="plus" size={16} /> Add money · coming soon
        </button>
      </section>
      <section className="stack">
        <h2>Transactions</h2>
        {w.transactions.length === 0 ? (
          <EmptyState icon="wallet" title="No wallet activity yet" message="Refunds and Click credits will appear here." action={<Link to="/explore" className="btn btn--outline">Explore Click</Link>} />
        ) : (
          <div className="card list">
            {w.transactions.map((t) => {
              const k = KIND[t.kind] ?? KIND.adjustment!;
              const credit = Number(t.amount) > 0;
              return (
                <div key={t.id} className="list-row" style={{ cursor: 'default' }}>
                  <span className="list-row__icon"><Icon name={k.icon} size={18} /></span>
                  <span style={{ flex: 1, minWidth: 0 }}>
                    <span style={{ display: 'block', fontWeight: 600 }}>{k.label}</span>
                    <span className="small muted">{t.description} · {formatDateTime(t.createdAt)}</span>
                  </span>
                  <strong style={{ color: credit ? 'var(--c-success)' : 'var(--c-ink)' }}>{credit ? '+' : '−'}{formatMoney(Math.abs(Number(t.amount)), t.currency)}</strong>
                </div>
              );
            })}
          </div>
        )}
      </section>
    </div>
  );
}
