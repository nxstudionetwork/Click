import { Link } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { useAuth } from '../../auth/AuthProvider';
import { Icon } from '../../components/ui';
import { api } from '../../lib/api';

/** Checkout's Rewards step. Points can't be spent directly on an order: they're redeemed for Click. Wallet credit,
 *  which then pays at checkout. This shows what this order will earn and what you can redeem — nothing invented. */
export function CheckoutRewards({ subtotal }: { subtotal: string | number }) {
  const { status } = useAuth();
  const q = useQuery({ queryKey: ['customer', 'rewards'], queryFn: api.money.rewards.get, enabled: status === 'authenticated', staleTime: 60_000 });
  if (!q.data) return null;
  const r = q.data;
  const earn = Math.floor((Number(subtotal) / 100) * r.rules.pointsPer100 * Number(r.tier.multiplier));
  const redeemable = r.catalog.filter((c) => c.available).sort((a, b) => b.pointsCost - a.pointsCost)[0];
  return (
    <section className="card card--pad stack" aria-labelledby="rw-h">
      <h3 id="rw-h"><Icon name="star" size={16} /> Rewards</h3>
      <p className="small">You’ll earn about <strong>{earn.toLocaleString('en-IN')} points</strong> when this is delivered ({r.tier.name}, {r.tier.multiplier}×).</p>
      <p className="small muted">You have {r.balance.toLocaleString('en-IN')} points.{redeemable ? ` Redeem ${redeemable.pointsCost.toLocaleString('en-IN')} for ${redeemable.title} and pay with Click. Wallet.` : ''}</p>
      {redeemable && <Link to="/rewards?tab=redeem" className="small" style={{ color: 'var(--c-brand)', fontWeight: 600 }}>Redeem points</Link>}
    </section>
  );
}
