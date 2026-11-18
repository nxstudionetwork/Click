import { Link } from 'react-router-dom';
import { Icon, type IconName } from '@click/ui';
import { AppShell } from '../../components/AppShell';
import { usePartnerSession } from '../../session/PartnerSession';

const LINKS: { to: string; label: string; hint: string; icon: IconName }[] = [
  { to: '/restaurant/kitchen', label: 'Kitchen', hint: 'Live orders by stage', icon: 'food' },
  { to: '/restaurant/offers', label: 'Offers', hint: 'Create and pause offers', icon: 'tag' },
  { to: '/buzz', label: 'Buzz', hint: 'Promote dishes and offers with photos and videos', icon: 'sparkle' },
  { to: '/restaurant/insights', label: 'Insights', hint: 'Sales, kitchen performance, best sellers', icon: 'chart' },
  { to: '/earnings', label: 'Earnings', hint: 'Daily sales and recent orders', icon: 'wallet' },
  { to: '/notifications', label: 'Notifications', hint: 'New orders and account updates', icon: 'bell' },
  { to: '/documents', label: 'Documents', hint: 'FSSAI licence and verification documents', icon: 'card' },
  { to: '/card', label: 'Partner card', hint: 'Your Partner ID and verification', icon: 'card' },
];

/** Restaurant tools that don't fit the bottom bar. */
export function MorePage() {
  const { logout } = usePartnerSession();
  return (
    <AppShell>
      <div className="page">
        <div className="page__head"><h1>More</h1></div>
        <nav aria-label="Restaurant tools">
          <ul className="more">
            {LINKS.map((l) => (
              <li key={l.to}>
                <Link to={l.to} className="more__item">
                  <span className="quick__icon" aria-hidden="true"><Icon name={l.icon} size={20} /></span>
                  <span><strong>{l.label}</strong><span className="small muted">{l.hint}</span></span>
                  <Icon name="right" size={16} />
                </Link>
              </li>
            ))}
          </ul>
        </nav>
        <button type="button" className="btn btn--outline" onClick={() => void logout()}><Icon name="logout" size={18} /> Sign out</button>
      </div>
    </AppShell>
  );
}
