import { Link } from 'react-router-dom';
import { Icon, type IconName } from '@click/ui';
import { AppShell } from '../../components/AppShell';
import { usePartnerSession } from '../../session/PartnerSession';

const LINKS: { to: string; label: string; hint: string; icon: IconName }[] = [
  { to: '/driver/profile', label: 'Profile & vehicle', hint: 'What riders see, vehicle, performance', icon: 'user' },
  { to: '/documents', label: 'Documents', hint: 'Licence, registration, insurance', icon: 'card' },
  { to: '/driver/safety', label: 'Safety', hint: 'Emergency help and reporting', icon: 'shield' },
  { to: '/driver/rides?view=history', label: 'Trip history', hint: 'Past trips, ratings', icon: 'history' },
  { to: '/notifications', label: 'Notifications', hint: 'Requests and account updates', icon: 'bell' },
  { to: '/card', label: 'Partner card', hint: 'Your Driver ID', icon: 'key' },
];

export function DriverMenuPage() {
  const { logout } = usePartnerSession();
  return (
    <AppShell>
      <div className="page">
        <div className="page__head"><h1>Menu</h1></div>
        <nav aria-label="Driver tools">
          <ul className="more">
            {LINKS.map((l) => (
              <li key={l.to}><Link to={l.to} className="more__item">
                <span className="quick__icon" aria-hidden="true"><Icon name={l.icon} size={20} /></span>
                <span><strong>{l.label}</strong><span className="small muted">{l.hint}</span></span>
                <Icon name="right" size={16} />
              </Link></li>
            ))}
          </ul>
        </nav>
        <button type="button" className="btn btn--outline" onClick={() => void logout()}><Icon name="logout" size={18} /> Sign out</button>
      </div>
    </AppShell>
  );
}

/** Safety centre: emergency first, then what Click does and how to report a trip. In a trip, Safety is on the trip card. */
export function DriverSafetyPage() {
  return (
    <AppShell>
      <div className="page">
        <div className="page__head"><h1>Safety</h1></div>
        <a className="btn btn--danger btn--block" href="tel:112"><Icon name="phone" size={18} /> Emergency: call 112</a>
        <section className="mod" aria-labelledby="sf1">
          <h2 id="sf1" className="mod__title"><Icon name="shield" size={18} />During a trip</h2>
          <ul className="help">
            <li>Tap <strong>Safety</strong> on your active trip to alert Click’s safety team with the trip details, or to report an issue.</li>
            <li>Start the trip only when the rider is in your vehicle. Check the pickup name before you start.</li>
            <li>If you feel unsafe before pickup, cancel the ride. Click finds the rider another driver.</li>
            <li>Riders never see your phone number or address.</li>
          </ul>
        </section>
        <section className="mod" aria-labelledby="sf2">
          <h2 id="sf2" className="mod__title"><Icon name="alert" size={18} />After a trip</h2>
          <p className="small">Open <Link to="/driver/rides?view=history">Trip history</Link> and tap <strong>Report</strong> on the trip.
            Click’s safety team reviews every report.</p>
        </section>
      </div>
    </AppShell>
  );
}
