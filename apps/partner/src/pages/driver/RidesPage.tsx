import { useSearchParams } from 'react-router-dom';
import { Button, Icon, useToast } from '@click/ui';
import type { DriverTrip } from '@click/api';
import { AppShell } from '../../components/AppShell';
import { useRateRider, useDriverTrips } from '../../features/driver/queries';
import { TripSafety } from '../../features/driver/TripSafety';
import { useWork } from '../../features/home/queries';
import { Empty, listSkeleton, WorkList } from '../../features/home/sections';
import { apiMessage } from '../../lib/format';
import { formatMoney, timeAgo } from '../../lib/money';

const TABS = [{ key: 'requests', label: 'Requests' }, { key: 'active', label: 'Active trip' }, { key: 'history', label: 'History' }];

function RateRider({ trip }: { trip: DriverTrip }) {
  const rate = useRateRider();
  const toast = useToast();
  if (trip.riderRated) return <span className="small muted">You rated the rider {trip.riderRated}★</span>;
  if (!trip.canRateRider) return null;
  return (
    <div className="stars" role="group" aria-label="Rate the rider">
      <span className="small muted">Rate rider</span>
      {[1, 2, 3, 4, 5].map((s) => (
        <button key={s} type="button" className="stars__btn" aria-label={`${s} star${s > 1 ? 's' : ''}`} disabled={rate.isPending}
          onClick={() => rate.mutate({ id: trip.id, stars: s }, { onSuccess: () => toast('Thanks for rating'), onError: (e) => toast(apiMessage(e), 'error') })}>
          <Icon name="star" size={18} />
        </button>
      ))}
    </div>
  );
}

function History() {
  const [params, setParams] = useSearchParams();
  const page = Math.max(Number(params.get('page') ?? 1) || 1, 1);
  const status = params.get('status') ?? 'all';
  const trips = useDriverTrips({ status, page });
  const set = (p: Record<string, string>) => setParams({ view: 'history', status, ...p }, { replace: true });
  if (trips.isPending) return listSkeleton;
  if (trips.isError) {
    return <div className="dash__error" role="alert"><h2>Couldn’t load your trips</h2><p className="muted">{apiMessage(trips.error)}</p>
      <Button onClick={() => void trips.refetch()}>Try again</Button></div>;
  }
  const d = trips.data;
  return (
    <>
      <div className="seg" role="group" aria-label="Trip status">
        {[['all', 'All'], ['completed', 'Completed'], ['cancelled', 'Cancelled']].map(([k, l]) => (
          <button key={k} type="button" className={`seg__btn ${status === k ? 'is-active' : ''}`} aria-pressed={status === k}
            onClick={() => setParams({ view: 'history', status: k! }, { replace: true })}>{l}</button>
        ))}
      </div>
      {d.results.length === 0 ? <Empty icon="history" title="No trips yet." message="Completed and cancelled trips appear here." /> : (
        <ul className="work-list">
          {d.results.map((t) => (
            <li key={t.id} className={`work work--${t.status === 'completed' ? 'success' : 'muted'}`}>
              <div className="work__head">
                <span className="work__icon" aria-hidden="true"><Icon name="ride" size={20} /></span>
                <div className="work__title"><h3>{t.pickup} → {t.drop}</h3>
                  <p className="muted small">{t.rideType} · {t.distanceKm.toFixed(1)} km · {t.payment}</p></div>
                <div className="work__meta"><span className={`tag tag--${t.status === 'completed' ? 'success' : 'muted'}`}>{t.statusLabel}</span>
                  <strong className="work__amount">{formatMoney(t.fare)}</strong></div>
              </div>
              {t.cancelReason && <p className="small muted">{t.cancelReason}</p>}
              {t.ratingReceived && <p className="small">Rider gave you {t.ratingReceived.stars}★{t.ratingReceived.comment && ` · “${t.ratingReceived.comment}”`}</p>}
              <div className="work__actions">
                <RateRider trip={t} />
                <TripSafety trip={{ id: t.id, ref: t.number }} label="Report" />
              </div>
              <p className="work__time small muted">{timeAgo(t.at)} · {t.number}</p>
            </li>
          ))}
        </ul>
      )}
      {(page > 1 || d.hasMore) && (
        <nav className="pager" aria-label="Pages">
          <Button size="sm" variant="outline" disabled={page <= 1} onClick={() => set({ page: String(page - 1) })}>Previous</Button>
          <span className="small muted">Page {page}</span>
          <Button size="sm" variant="outline" disabled={!d.hasMore} onClick={() => set({ page: String(page + 1) })}>Next</Button>
        </nav>
      )}
    </>
  );
}

function Live({ view }: { view: 'requests' | 'active' }) {
  const work = useWork(view);
  if (work.isPending) return listSkeleton;
  if (work.isError) {
    return <div className="dash__error" role="alert"><h2>Couldn’t load rides</h2><p className="muted">{apiMessage(work.error)}</p>
      <Button onClick={() => void work.refetch()}>Try again</Button></div>;
  }
  const d = work.data;
  if (d.state !== 'live') return <Empty icon="clock" title="Not live yet" message={d.message} />;
  if (d.items.length === 0) {
    return <Empty icon="check" title={view === 'requests' ? 'No ride requests right now.' : 'No active trip.'}
      message={view === 'requests' ? 'Stay online. New requests near you appear here and on Home.' : undefined} />;
  }
  return (
    <>
      <WorkList items={d.items} emphasis={view === 'active'} />
      {view === 'active' && d.items[0] && <TripSafety trip={d.items[0]} />}
    </>
  );
}

/** Rides: live requests (with a countdown), the active trip, and trip history with rider ratings. */
export function RidesPage() {
  const [params, setParams] = useSearchParams();
  const view = (['requests', 'active', 'history'].includes(params.get('view') ?? '') ? params.get('view') : 'requests') as 'requests' | 'active' | 'history';
  return (
    <AppShell>
      <div className="page">
        <div className="page__head"><h1>Rides</h1><p className="muted small">Requests and your active trip update every few seconds.</p></div>
        <div className="tabs" role="tablist" aria-label="Rides">
          {TABS.map((t) => (
            <button key={t.key} type="button" role="tab" aria-selected={view === t.key} className={`tabs__tab ${view === t.key ? 'is-active' : ''}`}
              onClick={() => setParams({ view: t.key }, { replace: true })}>{t.label}</button>
          ))}
        </div>
        <div role="tabpanel" aria-live="polite">{view === 'history' ? <History /> : <Live view={view} />}</div>
      </div>
    </AppShell>
  );
}
