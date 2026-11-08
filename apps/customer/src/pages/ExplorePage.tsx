import { Link } from 'react-router-dom';
import { Icon, type IconName } from '../components/ui';
import { CLICK_FEATURES } from '../config/services';
import { ExploreBanner } from '../features/explore/ExploreBanner';
import { YourClickBadges } from '../features/explore/YourClickBadges';

const ACCOUNT: { to: string; title: string; hint: string; icon: IconName }[] = [
  { to: '/account/payments', title: 'Payments', hint: 'Manage your payment methods', icon: 'card' },
  { to: '/settings', title: 'Settings', hint: 'Preferences, appearance and account controls', icon: 'settings' },
  { to: '/help', title: 'Help & Support', hint: 'Get help from Click.', icon: 'help' },
  { to: '/account/addresses', title: 'Addresses', hint: 'Manage saved locations', icon: 'pin' },
];

/**
 * Explore: Click.'s discovery and access hub (reached from the bottom navigation).
 * Discovery (banner + every feature, A–Z) → Your Click. (personal shortcuts) → Account → brand.
 * Features come from the central registry (config/services.ts); nothing is hand-ordered here.
 */
export function ExplorePage() {
  return (
    <div className="explore">
      <header className="explore__head">
        <h1>Explore</h1>
        <p>Everything Click. can do for you</p>
      </header>

      <ExploreBanner />

      <section className="explore__sec" aria-labelledby="features-h">
        <h2 id="features-h" className="explore__h">Click. Features</h2>
        <ul className="xfeatures">
          {CLICK_FEATURES.map((f) => (
            <li key={f.id}>
              <Link to={f.path} className={`xfeature ${f.status === 'soon' ? 'xfeature--soon' : ''}`} data-theme={f.theme}
                aria-label={`${f.name}: ${f.status === 'soon' ? 'coming soon' : f.tagline}`}>
                <span className="xfeature__icon"><Icon name={f.icon} size={24} /></span>
                <span className="xfeature__name">{f.name}</span>
                <span className="xfeature__hint">{f.status === 'soon' ? 'Coming soon' : f.tagline}</span>
              </Link>
            </li>
          ))}
        </ul>
      </section>

      <section className="explore__sec" aria-labelledby="yours-h">
        <h2 id="yours-h" className="explore__h">Your Click.</h2>
        <YourClickBadges />
      </section>

      <section className="explore__sec" aria-labelledby="account-h">
        <h2 id="account-h" className="explore__h">Account</h2>
        <nav className="xaccount" aria-labelledby="account-h">
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
