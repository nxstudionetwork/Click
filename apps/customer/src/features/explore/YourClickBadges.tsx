import { useState } from 'react';
import { Link } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { Icon, type IconName } from '../../components/ui';
import type { Theme } from '../../config/services';
import { api } from '../../lib/api';
import { formatMoney } from '../../lib/format';
import { useWallet } from '../wallet/useWallet';

function Badge({ to, theme, icon, title, value, label }: { to: string; theme: Theme; icon: IconName; title: string; value: React.ReactNode; label: string }) {
  return (
    <Link to={to} className="ybadge" data-theme={theme} aria-label={label}>
      <span className="ybadge__icon"><Icon name={icon} size={20} /></span>
      <span className="ybadge__title">{title}</span>
      <span className="ybadge__value">{value}</span>
    </Link>
  );
}

const Loading = () => <span className="skeleton ybadge__skel" aria-hidden="true" />;

/** Wallet, Rewards, Activity and Offers: real figures from the customer's own ledgers (never invented). */
export function YourClickBadges() {
  const wallet = useWallet();
  const rewards = useQuery({ queryKey: ['customer', 'rewards'], queryFn: api.customer.rewards });
  const offers = useQuery({ queryKey: ['offers', 'all'], queryFn: () => api.catalog.offers() });
  const [showBalance, setShowBalance] = useState(false);

  const balance = wallet.data ? formatMoney(wallet.data.balance, wallet.data.currency) : '';
  const offerCount = offers.data?.count ?? offers.data?.results.length ?? 0;

  return (
    <div className="ybadges">
      <div className="ybadge-wrap">
        <Badge
          to="/wallet" theme="wallet" icon="wallet" title="Wallet"
          label={wallet.data ? `Wallet${showBalance ? `, balance ${balance}` : ', balance hidden'}. Open wallet` : 'Open wallet'}
          value={wallet.isPending ? <Loading /> : wallet.isError ? 'Open wallet' : showBalance ? balance : '₹ ••••'}
        />
        {wallet.data && (
          <button type="button" className="ybadge__reveal" aria-pressed={showBalance} aria-label={showBalance ? 'Hide wallet balance' : 'Show wallet balance'} onClick={() => setShowBalance((v) => !v)}>
            <Icon name={showBalance ? 'eyeOff' : 'eye'} size={14} />
          </button>
        )}
      </div>
      <Badge
        to="/rewards" theme="rewards" icon="star" title="Rewards" label="Open rewards"
        value={rewards.isPending ? <Loading /> : rewards.isError ? 'View rewards' : `${rewards.data.balance.toLocaleString('en-IN')} pts`}
      />
      <Badge to="/activity" theme="activity" icon="history" title="Activity" label="Open your activity" value="Orders & bookings" />
      <Badge
        to="/offers" theme="offers" icon="tag" title="Offers" label="Open offers"
        value={offers.isPending ? <Loading /> : offers.isError ? 'See offers' : offerCount === 0 ? 'None right now' : `${offerCount} live`}
      />
    </div>
  );
}
