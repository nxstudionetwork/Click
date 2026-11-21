import { Link } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { useAuth } from '../../auth/AuthProvider';
import { Icon, type IconName } from '../../components/ui';
import { serviceForStoreType, type Theme } from '../../config/services';
import { formatDateTime, formatMoney } from '../../lib/format';
import { api } from '../../lib/api';
import { useWallet } from '../wallet/useWallet';
import { HomeSection, SectionEmpty, SectionError } from './HomeSection';

interface ActivityRow { key: string; at: string; to: string; theme: Theme; icon: IconName; title: string; meta: string; status: string }

const label = (s: string) => s.replace(/_/g, ' ').replace(/^\w/, (c) => c.toUpperCase());

/** The customer's latest orders and bookings, newest first (real records only). */
export function RecentActivity() {
  const orders = useQuery({ queryKey: ['customer', 'orders', 'list', 'recent'], queryFn: () => api.customer.orders.list() });
  const bookings = useQuery({ queryKey: ['customer', 'bookings', 'recent'], queryFn: () => api.customer.bookings.list() });
  const failed = orders.isError || bookings.isError;
  const rows: ActivityRow[] = [
    ...(orders.data?.results ?? []).map((o): ActivityRow => {
      const svc = serviceForStoreType(o.store.storeType);
      return { key: `o${o.id}`, at: o.createdAt, to: `/orders/${o.id}`, theme: svc.theme, icon: svc.icon, title: o.store.name, meta: `${svc.short ?? svc.name} order · ${formatMoney(o.total, o.currency)}`, status: label(o.status) };
    }),
    ...(bookings.data?.results ?? []).map((b): ActivityRow => ({
      key: `b${b.id}`, at: b.createdAt, to: `/bookings/${b.id}`, theme: 'movies', icon: b.event.kind === 'movie' ? 'film' : 'ticket',
      title: b.event.title, meta: `${b.event.kind === 'movie' ? 'Movie' : 'Event'} booking · ${formatDateTime(b.show.startsAt)}`, status: label(b.status),
    })),
  ].sort((a, b) => b.at.localeCompare(a.at)).slice(0, 4);

  return (
    <HomeSection id="activity" title="Your recent activity" to="/activity" linkLabel="All activity" icon="history">
      {failed ? <SectionError onRetry={() => { orders.refetch(); bookings.refetch(); }} /> :
        orders.isPending || bookings.isPending ? <div className="skeleton" style={{ height: 180, borderRadius: 18 }} /> :
          rows.length === 0 ? (
            <SectionEmpty icon="history" title="Nothing here yet." text="Your Click. activity will appear here." action={<Link to="/food" className="btn btn--primary btn--sm">Order food</Link>} />
          ) : (
            <ul className="activity">
              {rows.map((r) => (
                <li key={r.key}>
                  <Link to={r.to} className="activity__row" data-theme={r.theme}>
                    <span className="activity__icon"><Icon name={r.icon} size={18} /></span>
                    <span className="activity__text"><strong className="truncate">{r.title}</strong><span className="truncate">{r.meta}</span></span>
                    <span className="activity__status">{r.status}</span>
                  </Link>
                </li>
              ))}
            </ul>
          )}
    </HomeSection>
  );
}

/** Rewards and Wallet summaries. Numbers come only from the customer's own ledgers. */
export function MoneyCards() {
  const { status } = useAuth();
  const rewards = useQuery({ queryKey: ['customer', 'rewards'], queryFn: api.customer.rewards, enabled: status === 'authenticated' });
  const wallet = useWallet();
  if (status !== 'authenticated') return null;
  return (
    <div className="money" aria-label="Rewards and wallet">
      <Link to="/rewards" className="money__card" data-theme="rewards">
        <span className="money__top"><span className="money__icon"><Icon name="star" size={18} /></span>Click. Rewards</span>
        <span className="money__value">{rewards.isPending ? <span className="skeleton" style={{ display: 'inline-block', width: 90, height: 28 }} /> : rewards.isError ? '—' : `${rewards.data.balance.toLocaleString('en-IN')}`}<small> points</small></span>
        <span className="money__cta">{rewards.isError ? 'Couldn’t load. Open Rewards' : 'View rewards'} <Icon name="right" size={14} /></span>
      </Link>
      <Link to="/wallet" className="money__card" data-theme="wallet">
        <span className="money__top"><span className="money__icon"><Icon name="wallet" size={18} /></span>Click. Wallet</span>
        <span className="money__value"><small>Available </small>{wallet.isPending ? <span className="skeleton" style={{ display: 'inline-block', width: 110, height: 28 }} /> : wallet.isError ? '—' : formatMoney(wallet.data.balance, wallet.data.currency)}</span>
        <span className="money__cta">{wallet.isError ? 'Couldn’t load. Open Wallet' : 'Open wallet'} <Icon name="right" size={14} /></span>
      </Link>
    </div>
  );
}

