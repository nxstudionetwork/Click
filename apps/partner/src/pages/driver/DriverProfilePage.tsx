import { Link } from 'react-router-dom';
import { Button, Icon, Skeleton } from '@click/ui';
import { AppShell } from '../../components/AppShell';
import { useDriverProfile } from '../../features/driver/queries';
import { Module } from '../../features/home/sections';
import { apiMessage } from '../../lib/format';

const rate = (v: number | null) => (v === null ? '—' : `${v}%`);

/** The driver's profile and vehicle, with exactly what riders see (the same card the Customer App shows). */
export function DriverProfilePage() {
  const q = useDriverProfile();
  const p = q.data;
  return (
    <AppShell>
      <div className="page">
        <div className="page__head"><h1>Profile & vehicle</h1></div>
        {q.isPending ? <Skeleton height={300} radius={22} /> : q.isError ? (
          <div className="dash__error" role="alert"><h2>Couldn’t load your profile</h2><p className="muted">{apiMessage(q.error)}</p>
            <Button onClick={() => void q.refetch()}>Try again</Button></div>
        ) : p && (
          <>
            {p.blockedReason && (
              <div className="notice notice--warning" role="alert"><Icon name="alert" size={18} />
                <span>{p.blockedReason} <Link to="/documents">Update documents</Link></span></div>
            )}
            <Module id="rider-view" title="What riders see" icon="eye">
              <div className="rider-card">
                <span className="rider-card__avatar" aria-hidden="true">{p.public.name.slice(0, 1)}</span>
                <div>
                  <p className="rider-card__name">{p.public.name} {p.public.rating ? <span className="small">· {p.public.rating}★ ({p.public.ratingCount})</span> : <span className="small muted">· New driver</span>}</p>
                  <p className="small">{[p.public.vehicleColor, p.public.vehicleModel].filter(Boolean).join(' ') || p.vehicle.typeLabel}</p>
                  <p className="plate">{p.public.plate || 'No plate on file'}</p>
                </div>
              </div>
              <p className="small muted">Riders never see your phone number, address or documents.</p>
            </Module>
            <Module id="veh" title="My vehicle" icon="car">
              <dl className="ledger">
                <div><dt>Type</dt><dd>{p.vehicle.typeLabel}</dd></div>
                <div><dt>Make & model</dt><dd>{p.vehicle.model || '—'}</dd></div>
                <div><dt>Colour</dt><dd>{p.vehicle.color || '—'}</dd></div>
                <div><dt>Registration</dt><dd className="mono">{p.vehicle.number || '—'}</dd></div>
                <div><dt>Ride types you get</dt><dd>{p.vehicle.rideTypes.join(', ') || 'None for this vehicle type'}</dd></div>
                <div><dt>Approved for</dt><dd>{p.capabilities.map((c) => c.label).join(', ') || 'Nothing yet'}</dd></div>
              </dl>
              <p className="small muted">To change your vehicle, contact Click Partner support with your Partner ID {p.partnerCode}; Click re-verifies it.</p>
            </Module>
            <Module id="perf" title="Performance (last 30 days)" icon="chart">
              <div className="metrics">
                <div className="metric"><span className="small muted">Rating</span><strong>{p.public.rating ? `${p.public.rating}★` : 'No ratings yet'}</strong></div>
                <div className="metric"><span className="small muted">Acceptance</span><strong>{rate(p.stats.acceptanceRate)}</strong>
                  <span className="metric__hint">{p.stats.missedRequests} missed</span></div>
                <div className="metric"><span className="small muted">Completion</span><strong>{rate(p.stats.completionRate)}</strong>
                  <span className="metric__hint">{p.stats.cancelledByYou} cancelled by you</span></div>
                <div className="metric"><span className="small muted">All-time trips</span><strong>{p.stats.completedTrips}</strong>
                  <span className="metric__hint">{p.stats.distanceKm.toFixed(0)} km</span></div>
              </div>
              {p.recentFeedback.map((f) => (
                <blockquote key={f.at} className="quote"><strong>{f.stars}★</strong> {f.compliment && <em>{f.compliment}. </em>}{f.comment}</blockquote>
              ))}
            </Module>
            <Link to="/documents" className="more__item">
              <span className="quick__icon" aria-hidden="true"><Icon name="card" size={20} /></span>
              <span><strong>Documents</strong><span className="small muted">
                {p.documents.filter((d) => d.state === 'verified').length} of {p.documents.length} verified</span></span>
              <Icon name="right" size={16} />
            </Link>
          </>
        )}
      </div>
    </AppShell>
  );
}
