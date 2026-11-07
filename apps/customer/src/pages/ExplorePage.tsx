import { PageHeader } from '../components/shell/PageHeader';
import { SERVICE_GROUPS, SERVICES } from '../config/services';
import { ServiceCard } from '../features/services/ServiceCard';

export function ExplorePage() {
  return (
    <div className="stack">
      <PageHeader title="Explore Click" subtitle="Everything you can do with Click, in one place." back={{ to: '/', label: 'Home' }} />
      {SERVICE_GROUPS.map((g) => {
        const items = SERVICES.filter((s) => s.group === g.id);
        return items.length ? (
          <section key={g.id} className="section" style={{ marginTop: 'var(--s-4)' }}>
            <h2>{g.label}</h2>
            <div className="services">{items.map((s) => <ServiceCard key={s.id} service={s} detailed />)}</div>
          </section>
        ) : null;
      })}
    </div>
  );
}
