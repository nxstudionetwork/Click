import { Link } from 'react-router-dom';
import { Icon } from '../components/ui';
import { PageHeader } from '../components/shell/PageHeader';
import { SERVICES, serviceById } from '../config/services';
import { ServiceCard } from '../features/services/ServiceCard';

/**
 * Honest page for services that are not live yet: what's coming, and what the customer can do today.
 * No fake inventory, prices or availability. Each service replaces this route with its feature module at launch.
 */
export function ServiceComingSoonPage({ serviceId }: { serviceId: string }) {
  const service = serviceById(serviceId)!;
  return (
    <div className="stack">
      <PageHeader band title={service.name} subtitle={`${service.tagline}. Coming to Click soon.`} back={{ to: '/', label: 'Home' }}
        actions={<span className="badge" style={{ background: 'rgb(255 255 255 / 20%)', color: '#fff' }}>Not live yet</span>} />
      {service.upcoming && (
        <section className="card card--pad stack" style={{ gap: 'var(--s-3)' }}>
          <h3>What’s coming</h3>
          <ul className="stack" style={{ gap: 'var(--s-2)', margin: 0, paddingLeft: 0, listStyle: 'none' }}>
            {service.upcoming.map((u) => (
              <li key={u} className="row"><span className="list-row__icon" style={{ width: 28, height: 28, color: 'var(--c-theme)' }}><Icon name="check" size={16} /></span>{u}</li>
            ))}
          </ul>
          <p className="small muted">You can’t book {service.name.toLowerCase()} yet. We’ll tell you in Notifications when it launches near you.</p>
        </section>
      )}
      <section className="section">
        <div className="section__head"><h2>Available on Click now</h2><Link to="/explore">Explore all</Link></div>
        <div className="services">{SERVICES.filter((s) => s.status === 'live').map((s) => <ServiceCard key={s.id} service={s} detailed />)}</div>
      </section>
    </div>
  );
}
