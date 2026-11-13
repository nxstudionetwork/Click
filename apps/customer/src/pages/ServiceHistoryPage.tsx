import { Link, useSearchParams } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { EmptyState, ErrorState, Icon, Skeleton } from '../components/ui';
import { useThemeOverride } from '../components/layout/AppShell';
import { catIcon } from '../features/pros/parts';
import { api } from '../lib/api';
import { formatMoney } from '../lib/format';

const TABS = [['active', 'Active'], ['upcoming', 'Upcoming'], ['completed', 'Completed'], ['cancelled', 'Cancelled']] as const;
type Tab = (typeof TABS)[number][0];

/** Every service booking, by state, with a quick rebook on finished ones. */
export function ServiceHistoryPage() {
  useThemeOverride('services');
  const [sp, setSp] = useSearchParams();
  const tab = (TABS.find(([t]) => t === sp.get('tab'))?.[0] ?? 'active') as Tab;
  const q = useQuery({ queryKey: ['services', 'bookings', tab], queryFn: () => api.services.bookings(tab) });

  return (
    <div className="sv-page" data-theme="services">
      <Link to="/services" className="sv-back"><Icon name="back" size={18} /> Services</Link>
      <h1 className="sv-title">Service bookings</h1>
      <div className="sv-seg sv-seg--wide" role="tablist" aria-label="Bookings">
        {TABS.map(([t, l]) => <button key={t} type="button" role="tab" aria-selected={t === tab} onClick={() => setSp({ tab: t }, { replace: true })}>{l}</button>)}
      </div>
      {q.isError ? <ErrorState error={q.error} onRetry={() => q.refetch()} /> : q.isPending ? <Skeleton height={240} radius={20} /> : q.data.results.length === 0 ? (
        <EmptyState icon="wrench" title={`No ${TABS.find(([t]) => t === tab)![1].toLowerCase()} bookings`} action={<Link to="/services" className="btn btn--primary">Find a professional</Link>} />
      ) : (
        <ul className="sv-history">{q.data.results.map((b) => (
          <li key={b.id} style={{ ['--sv-accent' as string]: b.category.accent }}>
            <Link to={`/services/bookings/${b.id}`} className="sv-hrow">
              <span className="sv-cat__icon sv-cat__icon--sm"><Icon name={catIcon(b.category.icon)} size={18} /></span>
              <span className="sv-hrow__main">
                <strong>{b.job.name}</strong>
                <span className="small sv-muted">{b.provider?.name ?? (b.requestedProvider ? `Asked ${b.requestedProvider.name}` : 'Finding a professional')} · {new Date(b.scheduledStart ?? b.createdAt).toLocaleDateString('en-IN', { day: 'numeric', month: 'short' })}</span>
                <span className={`sv-status sv-status--${b.status} small`}>{b.statusLabel}</span>
              </span>
              <span className="sv-hrow__end">{b.total ? formatMoney(b.total) : b.agreedAmount ? formatMoney(b.agreedAmount) : ''}</span>
            </Link>
            {!b.isActive && b.status !== 'unassigned' && (
              <div className="sv-hrow__acts">
                <Link to={`/services/book?rebook=${b.id}`} className="sv-link small">Book again</Link>
                {b.status === 'paid' && !b.reviewed && <Link to={`/services/bookings/${b.id}`} className="sv-link small">Rate</Link>}
              </div>
            )}
          </li>
        ))}</ul>
      )}
    </div>
  );
}
