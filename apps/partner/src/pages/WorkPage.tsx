import { Link, useSearchParams } from 'react-router-dom';
import { Button, Icon } from '@click/ui';
import { AppShell } from '../components/AppShell';
import { useHome, useWork } from '../features/home/queries';
import { Empty, listSkeleton, WorkList } from '../features/home/sections';
import { apiMessage } from '../lib/format';

const TITLE: Record<string, string> = { ride: 'Rides', order: 'Orders', booking: 'Shows & bookings' };

/** The partner's work queue: same items and actions as Home, filtered by the workspace's own views. */
export function WorkPage() {
  const [params, setParams] = useSearchParams();
  const requested = params.get('view') ?? '';
  const work = useWork(requested);
  const home = useHome();
  const data = work.data;
  const view = data?.view ?? requested;
  const title = TITLE[home.data?.workspace.workNoun ?? ''] ?? 'Work';

  return (
    <AppShell>
      <div className="page">
        <div className="page__head">
          <h1>{title}</h1>
          <p className="muted small">Updates every few seconds while this page is open.</p>
        </div>
        {data && data.views.length > 0 && (
          <div className="tabs" role="tablist" aria-label={`${title} views`}>
            {data.views.map((v) => (
              <button key={v.key} type="button" role="tab" aria-selected={v.key === view} className={`tabs__tab ${v.key === view ? 'is-active' : ''}`}
                onClick={() => setParams(v.key ? { view: v.key } : {}, { replace: true })}>
                {v.label}{v.count ? <span className="tabs__count">{v.count}</span> : null}
              </button>
            ))}
          </div>
        )}
        <div role="tabpanel" aria-live="polite">
          {work.isPending ? listSkeleton : work.isError ? (
            <div className="dash__error" role="alert">
              <h2>Couldn’t load your work</h2><p className="muted">{apiMessage(work.error)}</p>
              <Button onClick={() => void work.refetch()}>Try again</Button>
            </div>
          ) : data!.state !== 'live' ? (
            <Empty icon="clock" title="Not live yet" message={data!.message} action={<Link to="/home" className="text-btn">Back to Home</Link>} />
          ) : data!.items.length === 0 ? (
            <Empty icon="check" title="Nothing here right now." message="New work appears here as soon as customers request it." />
          ) : <WorkList items={data!.items} />}
        </div>
        <Link to="/home" className="text-btn page__back"><Icon name="back" size={14} /> Home</Link>
      </div>
    </AppShell>
  );
}
