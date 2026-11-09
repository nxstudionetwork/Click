import { Link, useParams } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { EmptyState, Skeleton } from '../components/ui';
import { useThemeOverride } from '../components/layout/AppShell';
import { RouteLine, StatusChip, Timeline, when } from '../features/parcels/parts';
import { api } from '../lib/api';

/** A shared tracking link: status only (no phone numbers, PINs, prices or exact addresses). Valid for 7 days. */
export function ParcelSharedPage() {
  useThemeOverride('parcel');
  const { token = '' } = useParams();
  const q = useQuery({ queryKey: ['parcels', 'shared', token], queryFn: () => api.parcels.shared(token), retry: false,
    refetchInterval: (query) => (query.state.data && !['delivered', 'cancelled', 'failed', 'no_partner'].includes(query.state.data.status) ? 30_000 : false) });
  if (q.isError) return <EmptyState icon="parcel" title="This tracking link isn’t valid" message="It may have expired. Ask the sender for a new link." action={<Link to="/" className="btn btn--outline">Open Click.</Link>} />;
  if (q.isPending) return <div className="pc-page" data-theme="parcel"><Skeleton height={260} radius={24} /></div>;
  const p = q.data;
  return (
    <div className="pc-page" data-theme="parcel">
      <header className="pc-dhead">
        <div><span className="pc-kicker">Shared tracking · {p.service}</span><h1 className="pc-dhead__id">{p.number}</h1></div>
        <StatusChip status={p.status} label={p.statusLabel} />
      </header>
      <section className="pc-card">
        <RouteLine from={p.from} to={p.to} />
        {p.deliverBy && !p.deliveredAt && <p className="small">Delivery by {when(p.deliverBy)} (estimated)</p>}
        <Timeline steps={p.timeline} />
      </section>
      <p className="small muted">Shared by the sender from Click. Parcel. Only the delivery status is visible on this link.</p>
    </div>
  );
}
