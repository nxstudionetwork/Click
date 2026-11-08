import { useState } from 'react';
import { Link } from 'react-router-dom';
import type { UseQueryResult } from '@tanstack/react-query';
import type { ProfileSummary } from '@click/api';
import { Icon, type IconName } from '../../components/ui';
import type { Theme } from '../../config/services';
import { formatMoney } from '../../lib/format';
import { useWallet } from '../wallet/useWallet';

function Badge({ to, theme, icon, title, value, hint }: { to: string; theme: Theme; icon: IconName; title: string; value: React.ReactNode; hint: string }) {
  return (
    <Link to={to} className="pbadge" data-theme={theme}>
      <span className="pbadge__icon"><Icon name={icon} size={20} /></span>
      <span className="pbadge__title">{title}</span>
      <span className="pbadge__value">{value}</span>
      <span className="pbadge__hint">{hint} <Icon name="right" size={12} /></span>
    </Link>
  );
}

const Skel = () => <span className="skeleton pbadge__skel" aria-hidden="true" />;

/** Activity, Wishlist, Rewards and Wallet: real counts from the profile summary; wallet stays masked until asked. */
export function ProfileBadges({ summary }: { summary: UseQueryResult<ProfileSummary> }) {
  const s = summary.data;
  const [reveal, setReveal] = useState(false);
  const wallet = useWallet(reveal);
  const plural = (n: number, one: string, many: string) => `${n.toLocaleString('en-IN')} ${n === 1 ? one : many}`;

  return (
    <div className="pbadges">
      <Badge to="/activity" theme="activity" icon="history" title="Activity"
        value={summary.isPending ? <Skel /> : s ? plural(s.activity.total, 'item', 'items') : '—'}
        hint={s && s.activity.total === 0 ? 'Nothing yet' : 'View all'} />
      <Badge to="/wishlist" theme="offers" icon="heart" title="Wishlist"
        value={summary.isPending ? <Skel /> : s ? plural(s.wishlist, 'saved', 'saved') : '—'}
        hint={s && s.wishlist === 0 ? 'Save things you love' : 'Open'} />
      <Badge to="/rewards" theme="rewards" icon="star" title="Rewards"
        value={summary.isPending ? <Skel /> : s ? `${s.rewardsBalance.toLocaleString('en-IN')} pts` : '—'}
        hint={s && s.rewardsBalance === 0 ? 'Start earning' : 'View rewards'} />
      <div className="pbadge-wrap">
        <Badge to="/wallet" theme="wallet" icon="wallet" title="Wallet"
          value={reveal ? (wallet.isPending ? <Skel /> : wallet.data ? formatMoney(wallet.data.balance, wallet.data.currency) : '—') : '₹ ••••'}
          hint="Open wallet" />
        <button type="button" className="pbadge__reveal" aria-pressed={reveal} aria-label={reveal ? 'Hide wallet balance' : 'Show wallet balance'} onClick={() => setReveal((v) => !v)}>
          <Icon name={reveal ? 'eyeOff' : 'eye'} size={14} />
        </button>
      </div>
    </div>
  );
}
