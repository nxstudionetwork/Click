import { Link } from 'react-router-dom';
import { Icon } from '../components/ui';
import { SERVICES, serviceById } from '../config/services';
import { ServiceCard } from '../features/services/ServiceCard';

/**
 * Honest placeholder for services that are not live yet. No fake inventory,
 * prices or availability is shown. Each service replaces this route with
 * its real feature module when its backend domain launches.
 */
export function ServiceComingSoonPage({ serviceId }: { serviceId: string }) {
  const service = serviceById(serviceId)!;
  return (
    <div className="stack">
      <div className="state">
        <div className="state__icon"><Icon name={service.icon} /></div>
        <h1>{service.name} is coming to Click</h1>
        <p>{service.tagline}. We’re building it now and it isn’t available to book yet.</p>
        <Link to="/explore" className="btn btn--outline">Explore what’s live</Link>
      </div>
      <section className="section">
        <h2>Available now</h2>
        <div className="services">{SERVICES.filter((s) => s.status === 'live').map((s) => <ServiceCard key={s.id} service={s} />)}</div>
      </section>
    </div>
  );
}
