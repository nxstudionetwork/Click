import { Link } from 'react-router-dom';
import { Icon, type IconName } from '../../components/ui';
import { CLICK_FEATURES } from '../../config/services';
import { ExploreBanner } from './ExploreBanner';
import { YourClickBadges } from './YourClickBadges';

const ACCOUNT: { to: string; title: string; hint: string; icon: IconName }[] = [
  { to: '/account/payments', title: 'Payments', hint: 'Manage your payment methods', icon: 'card' },
  { to: '/settings', title: 'Settings', hint: 'Preferences, appearance and account controls', icon: 'settings' },
  { to: '/help', title: 'Help & Support', hint: 'Get help from Click.', icon: 'help' },
  { to: '/account/addresses', title: 'Addresses', hint: 'Manage saved locations', icon: 'pin' },
];

/**
 * Explore content, shared by the bottom sheet (opened from the bottom navigation) and the /explore deep link.
 * Discovery (banner + every feature, A–Z) → Your Click. → Account → brand. Features come from the central
 * registry (config/services.ts); nothing is hand-ordered here. `onNavigate` lets the sheet close on any tap.
 */
export function ExploreContent({ titleId = 'explore-h', onNavigate }: { titleId?: string; onNavigate?: () => void }) {
  return (
    <div className="explore" onClick={(e) => { if (onNavigate && (e.target as HTMLElement).closest('a')) onNavigate(); }}>
      <header className="explore__head">
        <h1 id={titleId}>Explore</h1>
        <p>Everything Click. can do for you</p>
      </header>

      <ExploreBanner />

      <section className="explore__sec" aria-labelledby={`${titleId}-features`}>
        <h2 id={`${titleId}-features`} className="explore__h">Click. Features</h2>
        <ul className="xfeatures">
          {CLICK_FEATURES.map((f) => (
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
        <h2 id={`${titleId}-yours`} className="explore__h">Your Click.</h2>
        <YourClickBadges />
      </section>

      <section className="explore__sec" aria-labelledby={`${titleId}-account`}>
        <h2 id={`${titleId}-account`} className="explore__h">Account</h2>
        <nav className="xaccount" aria-label="Account">
          {ACCOUNT.map((a) => (
            <Link key={a.to} to={a.to} className="xaccount__row">
              <span className="xaccount__icon"><Icon name={a.icon} size={20} /></span>
              <span className="xaccount__text"><strong>{a.title}</strong><span>{a.hint}</span></span>
              <Icon name="right" size={18} className="xaccount__chev" />
            </Link>
          ))}
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
