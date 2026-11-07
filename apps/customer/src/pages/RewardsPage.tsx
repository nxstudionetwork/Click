import { Link } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { EmptyState, ErrorState, Skeleton } from '../components/ui';
import { api } from '../lib/api';
import { formatDateTime } from '../lib/format';

export function RewardsPage() {
  const rewards = useQuery({ queryKey: ['customer', 'rewards'], queryFn: api.customer.rewards });
  if (rewards.isError) return <ErrorState error={rewards.error} onRetry={() => rewards.refetch()} />;
  if (rewards.isPending) return <div className="stack"><Skeleton height={140} radius={22} /><Skeleton height={200} /></div>;
  const r = rewards.data;

  return (
    <div className="stack">
      <h1>Rewards</h1>
      <section className="points-hero stack" style={{ gap: 'var(--s-2)' }}>
        <span>Your Click points</span>
        <span className="points-hero__value">{r.balance.toLocaleString('en-IN')}</span>
        <span className="small">{r.earned.toLocaleString('en-IN')} earned · {r.used.toLocaleString('en-IN')} used</span>
      </section>
      <section className="card card--pad stack" style={{ gap: 'var(--s-2)' }}>
        <h3>How it works</h3>
        <p className="small">Earn {r.rules.pointsPer100} points for every ₹100 of items in a delivered order. Points expire {r.rules.expiryDays} days after they’re earned.</p>
        <p className="small muted">{r.rules.redemptionAvailable ? 'Redeem points at checkout.' : 'Redeeming points at checkout is coming soon. Your points are saved until then.'}</p>
      </section>
      <section className="stack">
        <h2>History</h2>
        {r.history.length === 0 ? (
          <EmptyState icon="gift" title="No points yet" message="Points appear here after your first delivered order." action={<Link to="/explore" className="btn btn--primary">Start an order</Link>} />
        ) : (
          <div className="card list">
            {r.history.map((t) => (
              <div key={t.id} className="list-row" style={{ cursor: 'default' }}>
                <div style={{ flex: 1 }}>
                  <div>{t.description}</div>
                  <div className="small muted">{formatDateTime(t.createdAt)}{t.expiresAt && t.points > 0 ? ` · expires ${formatDateTime(t.expiresAt)}` : ''}</div>
                </div>
                <strong style={{ color: t.points > 0 ? 'var(--c-success)' : 'var(--c-ink-2)' }}>{t.points > 0 ? '+' : ''}{t.points}</strong>
              </div>
            ))}
          </div>
        )}
      </section>
    </div>
  );
}
