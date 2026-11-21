import { Link, useSearchParams } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { EmptyState, ErrorState, Icon, Skeleton } from '../components/ui';
import { useThemeOverride } from '../components/layout/AppShell';
import { ParcelRow } from '../features/parcels/parts';
import { api } from '../lib/api';

/** Every parcel in the account, active or past (the same orders also appear in Profile → Activity). */
export function ParcelHistoryPage() {
  useThemeOverride('parcel');
  const [params, setParams] = useSearchParams();
  const when = params.get('when') === 'active' ? 'active' : 'past';
  const q = useQuery({ queryKey: ['customer', 'parcels', when], queryFn: () => api.parcels.list(when) });
  return (
    <div className="pc-page" data-theme="parcel">
      <Link to="/parcels" className="pc-back"><Icon name="back" size={18} /> Parcel</Link>
      <h1 className="pc-title">Your parcels</h1>
      <div className="pc-tabs" role="tablist">
        {(['active', 'past'] as const).map((w) => <button key={w} role="tab" type="button" className="chip" aria-selected={when === w} aria-pressed={when === w}
          onClick={() => setParams(w === 'past' ? {} : { when: w }, { replace: true })}>{w === 'active' ? 'Active' : 'Past'}</button>)}
      </div>
      {q.isError ? <ErrorState error={q.error} onRetry={() => q.refetch()} /> : q.isPending ? <Skeleton height={200} /> : q.data.results.length === 0 ? (
        <EmptyState icon="parcel" title={when === 'active' ? 'No active parcels' : 'No recent deliveries'} action={<Link to="/parcels" className="btn btn--primary">Send a parcel</Link>} />
      ) : (
        <div className="pc-rows">{q.data.results.map((p) => <ParcelRow key={p.id} p={p} actions={<Link to={`/parcels/${p.id}`} className="btn btn--ghost btn--sm">View</Link>} />)}</div>
      )}
    </div>
  );
}
