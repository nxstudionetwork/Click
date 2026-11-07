import { SERVICES } from '../config/services';
import { ServiceCard } from '../features/services/ServiceCard';

export function ExplorePage() {
  const live = SERVICES.filter((s) => s.status === 'live');
  const soon = SERVICES.filter((s) => s.status === 'soon');
  return (
    <div className="stack">
      <div className="page-head"><div><h1>Explore Click</h1><p>Everything you can do with Click, in one place.</p></div></div>
      <section className="section" style={{ marginTop: 0 }}>
        <h2>Available now</h2>
        <div className="services">{live.map((s) => <ServiceCard key={s.id} service={s} detailed />)}</div>
      </section>
      <section className="section">
        <h2>Coming to Click</h2>
        <div className="services">{soon.map((s) => <ServiceCard key={s.id} service={s} detailed />)}</div>
      </section>
    </div>
  );
}
