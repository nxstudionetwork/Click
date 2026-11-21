import { Link, useNavigate } from 'react-router-dom';
import { useAuth } from '../../auth/AuthProvider';
import { Icon, type IconName } from '../../components/ui';
import { CLICK_FEATURES } from '../../config/services';
import { ExploreBanner } from './ExploreBanner';
import { YourClickBadges } from './YourClickBadges';
import { useT } from '../../i18n';
import type { Key } from '../../i18n/en';

const QUICK: { to: string; key: Key; icon: IconName }[] = [
  { to: '/orders', key: 'quick.orders', icon: 'bag' }, { to: '/bookings/mine', key: 'quick.bookings', icon: 'ticket' },
  { to: '/parcels/history', key: 'quick.parcels', icon: 'parcel' }, { to: '/wishlist', key: 'quick.wishlist', icon: 'heart' },
  { to: '/cart', key: 'quick.cart', icon: 'bag' }, { to: '/account/invoices', key: 'quick.invoices', icon: 'receipt' },
  { to: '/account/reviews', key: 'quick.reviews', icon: 'star' }, { to: '/help', key: 'quick.help', icon: 'help' },
];
/** Shown as live badges in "Your Click.", so the feature grid doesn't repeat them. */
const IN_BADGES = new Set(['wallet', 'rewards', 'activity', 'offers']);
/** Reachable from Quick actions, Account or the header. */
const ELSEWHERE = new Set(['cart', 'invoices', 'reviews', 'safety', 'search']);
const FEATURES = CLICK_FEATURES.filter((f) => !IN_BADGES.has(f.id) && !ELSEWHERE.has(f.id));
const ACCOUNT: { to: string; title: Key; hint?: Key; icon: IconName }[] = [
  { to: '/account', title: 'account.profile', hint: 'account.profileHint', icon: 'user' },
  { to: '/account/addresses', title: 'account.addresses', hint: 'account.addressesHint', icon: 'pin' },
  { to: '/account/payments', title: 'account.payments', hint: 'account.paymentsHint', icon: 'card' },
  { to: '/notifications', title: 'account.notifications', hint: 'account.notificationsHint', icon: 'bell' },
  { to: '/settings', title: 'account.settings', hint: 'account.settingsHint', icon: 'settings' },
  { to: '/safety', title: 'account.security', hint: 'account.securityHint', icon: 'shield' },
  { to: '/about', title: 'account.about', icon: 'book' }, { to: '/terms', title: 'account.terms', icon: 'receipt' }, { to: '/privacy', title: 'account.privacy', icon: 'eye' },
];

/**
 * Explore content, shared by the bottom sheet (opened from the bottom navigation) and the /explore deep link.
 * Discovery (banner + every feature, A–Z) → Your Click. → Account → brand. Features come from the central
 * registry (config/services.ts); nothing is hand-ordered here. `onNavigate` lets the sheet close on any tap.
 */
export function ExploreContent({ titleId = 'explore-h', onNavigate }: { titleId?: string; onNavigate?: () => void }) {
  const t = useT();
  const { logout } = useAuth();
  const navigate = useNavigate();
  return (
    <div className="explore" onClick={(e) => { if (onNavigate && (e.target as HTMLElement).closest('a')) onNavigate(); }}>
      <header className="explore__head">
        <h1 id={titleId}>{t('explore.title')}</h1>
        <p>{t('explore.subtitle')}</p>
      </header>

      <section className="explore__sec" aria-labelledby={`${titleId}-quick`}>
        <h2 id={`${titleId}-quick`} className="explore__h">{t('explore.quick')}</h2>
        <ul className="xquick">{QUICK.map((q) => (
          <li key={q.to}><Link to={q.to} className="xquick__item"><span className="xquick__icon"><Icon name={q.icon} size={20} /></span><span>{t(q.key)}</span></Link></li>
        ))}</ul>
      </section>

      <ExploreBanner />

      <section className="explore__sec" aria-labelledby={`${titleId}-features`}>
        <h2 id={`${titleId}-features`} className="explore__h">{t('explore.features')}</h2>
        <ul className="xfeatures">
          {FEATURES.map((f) => (
            <li key={f.id}>
              <Link to={f.path} className={`xfeature ${f.status === 'soon' ? 'xfeature--soon' : ''}`} data-theme={f.theme}
                title={f.status === 'soon' ? `${f.name}: coming soon` : f.tagline}
                aria-label={`${f.name}: ${f.status === 'soon' ? 'coming soon' : f.tagline}`}>
                <span className="xfeature__icon"><Icon name={f.icon} size={22} /></span>
                <span className="xfeature__name">{f.name}</span>
                {f.status === 'soon' && <span className="xfeature__soon">Soon</span>}
              </Link>
            </li>
          ))}
        </ul>
      </section>

      <section className="explore__sec" aria-labelledby={`${titleId}-yours`}>
        <h2 id={`${titleId}-yours`} className="explore__h">{t('explore.yours')}</h2>
        <YourClickBadges />
      </section>

      <section className="explore__sec" aria-labelledby={`${titleId}-account`}>
        <h2 id={`${titleId}-account`} className="explore__h">{t('explore.account')}</h2>
        <nav className="xaccount" aria-label="Account">
          {ACCOUNT.map((a) => (
            <Link key={a.to} to={a.to} className="xaccount__row">
              <span className="xaccount__icon"><Icon name={a.icon} size={20} /></span>
              <span className="xaccount__text"><strong>{t(a.title)}</strong>{a.hint && <span>{t(a.hint)}</span>}</span>
              <Icon name="right" size={18} className="xaccount__chev" />
            </Link>
          ))}
          <button type="button" className="xaccount__row" onClick={() => { onNavigate?.(); void logout().then(() => navigate('/')); }}>
            <span className="xaccount__icon"><Icon name="logout" size={20} /></span>
            <span className="xaccount__text"><strong>{t('account.logout')}</strong></span>
          </button>
        </nav>
      </section>

      <footer className="explore__brand">
        <img src="/brand/click-icon-96.png" width={36} height={36} alt="" loading="lazy" />
        <p className="explore__tagline">Everything you need.<br /><span>One Click. away.</span></p>
        <p className="explore__venture">A venture of IFX Group</p>
      </footer>
    </div>
  );
}
