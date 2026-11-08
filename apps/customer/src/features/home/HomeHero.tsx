import { Link } from 'react-router-dom';
import { useAuth } from '../../auth/AuthProvider';
import { Icon, type IconName } from '../../components/ui';
import { greetingFor } from '../../config/home';

const ORBIT: { icon: IconName; theme: string; label: string }[] = [
  { icon: 'food', theme: 'food', label: 'Food' },
  { icon: 'ride', theme: 'ride', label: 'Rides' },
  { icon: 'shop', theme: 'shopping', label: 'Shopping' },
  { icon: 'ticket', theme: 'movies', label: 'Movies' },
  { icon: 'grocery', theme: 'grocery', label: 'Groceries' },
];

/** Personal greeting + the Click. promise, with the brand icon at the centre of its services. */
export function HomeHero() {
  const { user, status } = useAuth();
  const first = user?.fullName?.trim().split(/\s+/)[0];
  return (
    <section className="home-hero" aria-labelledby="home-hero-h">
      <div className="home-hero__copy">
        <p className="home-hero__hello">{greetingFor()}{first ? `, ${first}` : ''} <span aria-hidden="true">👋</span></p>
        <h1 id="home-hero-h">Everything you need.<br /><span>One Click. away.</span></h1>
        <p className="home-hero__sub">Food, rides, shopping, entertainment and more, all connected.</p>
        {status === 'anonymous' && (
          <div className="row" style={{ flexWrap: 'wrap' }}>
            <Link to="/login" className="btn btn--light">Sign in</Link>
            <Link to="/explore" className="btn btn--glass">Explore Click.</Link>
          </div>
        )}
      </div>
      <div className="home-hero__visual" aria-hidden="true">
        <span className="home-hero__ring" />
        <img src="/brand/click-icon-192.png" srcSet="/brand/click-icon-192.png 1x, /brand/click-icon-512.png 2x" width={112} height={112} alt="" className="home-hero__mark" />
        {ORBIT.map((o, i) => (
          <span key={o.label} className={`home-hero__orbit home-hero__orbit--${i}`} data-theme={o.theme}><Icon name={o.icon} size={18} /></span>
        ))}
      </div>
    </section>
  );
}
