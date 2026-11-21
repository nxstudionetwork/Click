import { useState, type ReactNode } from 'react';
import { Link } from 'react-router-dom';
import { Button, Icon, Skeleton, useToast, type IconName } from '@click/ui';
import type { HomeSection, PartnerHome, WorkItem } from '@click/api';
import { ConfirmDialog } from '../../components/ConfirmDialog';
import { apiMessage } from '../../lib/format';
import { countOf, formatMoney, timeAgo } from '../../lib/money';
import { WorkCard } from '../work/WorkCard';
import { useSetAvailability } from './queries';

const KNOWN_ICONS = new Set<string>(['bell', 'ride', 'history', 'wallet', 'food', 'parcel', 'check', 'clock', 'grocery', 'chart', 'film', 'ticket', 'receipt']);
const asIcon = (name: string): IconName => (KNOWN_ICONS.has(name) ? name : 'right') as IconName;

/** A titled Home module with its own loading, error and "not live yet" states. */
export function Module({ id, title, icon, action, children, className = '' }: {
  id: string; title: string; icon?: IconName; action?: ReactNode; children: ReactNode; className?: string;
}) {
  return (
    <section className={`mod ${className}`} aria-labelledby={id}>
      <div className="mod__head">
        <h2 id={id} className="mod__title">{icon && <Icon name={icon} size={18} />}{title}</h2>
        {action}
      </div>
      {children}
    </section>
  );
}

export function SectionBody<T>({ section, loading, skeleton, empty, children }: {
  section: HomeSection<T> | undefined; loading: boolean; skeleton: ReactNode; empty?: (data: T) => ReactNode | null;
  children: (data: T) => ReactNode;
}) {
  if (loading || !section) return <>{skeleton}</>;
  if (section.status !== 'ok') {
    return (
      <p className={`mod__note ${section.status === 'error' ? 'mod__note--error' : ''}`} role={section.status === 'error' ? 'alert' : undefined}>
        <Icon name={section.status === 'error' ? 'alert' : 'clock'} size={16} /> {section.message}
      </p>
    );
  }
  const e = empty?.(section.data);
  return <>{e ?? children(section.data)}</>;
}

export const listSkeleton = (
  <div className="stack-sm" aria-hidden="true"><Skeleton height={112} radius={18} /><Skeleton height={112} radius={18} /></div>
);

export function Empty({ icon, title, message, action }: { icon: IconName; title: string; message?: string; action?: ReactNode }) {
  return (
    <div className="mod__empty" role="status">
      <span className="mod__empty-icon" aria-hidden="true"><Icon name={icon} size={20} /></span>
      <div><p className="mod__empty-title">{title}</p>{message && <p className="small muted">{message}</p>}</div>
      {action}
    </div>
  );
}

export function WorkList({ items, emphasis = false }: { items: WorkItem[]; emphasis?: boolean }) {
  return <div className="work-list">{items.map((i) => <WorkCard key={`${i.kind}-${i.id}`} item={i} emphasis={emphasis} />)}</div>;
}

// --- availability ----------------------------------------------------------------------------------------------

export function AvailabilityCard({ home }: { home: PartnerHome }) {
  const a = home.availability;
  const set = useSetAvailability();
  const toast = useToast();
  const [confirm, setConfirm] = useState(false);
  const [error, setError] = useState<string | null>(null);

  function change(next: boolean) {
    setError(null);
    set.mutate(next, {
      onSuccess: (r) => { setConfirm(false); toast(r.availability.label === a.label ? 'No change' : `You’re now ${r.availability.label.toLowerCase()}`); },
      onError: (err) => { const m = apiMessage(err); if (confirm) setError(m); else toast(m, 'error'); },
    });
  }

  return (
    <section className={`avail ${a.isOn ? 'is-on' : ''} ${a.canChange ? '' : 'is-blocked'}`} aria-labelledby="avail-h">
      <div className="avail__state">
        <span className="avail__dot" aria-hidden="true" />
        <div>
          <p id="avail-h" className="avail__label">Status</p>
          <p className="avail__value" aria-live="polite">{a.canChange ? a.label : home.workspace.state === 'live' ? a.label : 'Not live yet'}</p>
          <p className="avail__hint small">{a.blockedReason || a.hint}</p>
        </div>
      </div>
      {a.canChange && (
        <Button className="avail__btn" variant={a.isOn ? 'outline' : 'primary'} loading={set.isPending}
          aria-pressed={a.isOn} onClick={() => (a.isOn && a.confirmOff ? setConfirm(true) : change(!a.isOn))}>
          {a.isOn ? a.turnOff : a.turnOn}
        </Button>
      )}
      <ConfirmDialog open={confirm} title={`${a.turnOff}?`} message={a.confirmOff} confirmLabel={a.turnOff}
        pending={set.isPending} error={error} onConfirm={() => change(false)} onClose={() => setConfirm(false)} />
    </section>
  );
}

// --- quick actions / metrics / earnings / performance / activity ----------------------------------------------

export function QuickActions({ home }: { home: PartnerHome }) {
  if (!home.quickActions.length) return null;
  return (
    <nav className="quick" aria-label="Quick actions">
      {home.quickActions.map((q) => (
        <Link key={q.key} to={q.to} className="quick__item">
          <span className="quick__icon" aria-hidden="true"><Icon name={asIcon(q.icon)} size={20} /></span>
          <span className="quick__label">{q.label}</span>
          {q.count ? <span className="quick__count" aria-label={`${q.count} waiting`}>{q.count}</span> : null}
        </Link>
      ))}
    </nav>
  );
}

const metricSkeleton = (
  <div className="metrics" aria-hidden="true">{[0, 1, 2, 3].map((i) => <Skeleton key={i} height={86} radius={16} />)}</div>
);

export function Overview({ home, loading }: { home?: PartnerHome; loading: boolean }) {
  return (
    <Module id="overview-h" title="Today’s overview" icon="chart">
      <SectionBody section={home?.metrics} loading={loading} skeleton={metricSkeleton}>
        {(metrics) => (
          <dl className="metrics">
            {metrics.map((m) => (
              <div key={m.key} className="metric">
                <dt>{m.label}</dt>
                <dd>{m.display}</dd>
                {m.hint && <span className="metric__hint">{m.hint}</span>}
              </div>
            ))}
          </dl>
        )}
      </SectionBody>
    </Module>
  );
}

export function EarningsCard({ home, loading }: { home?: PartnerHome; loading: boolean }) {
  const label = home?.earnings.status === 'ok' ? home.earnings.data.label : 'Earnings';
  return (
    <Module id="earn-h" title={label} icon="wallet" className="mod--earn"
      action={home?.earnings.status === 'ok' ? <Link to="/earnings" className="text-btn">View details <Icon name="right" size={14} /></Link> : undefined}>
      <SectionBody section={home?.earnings} loading={loading} skeleton={<Skeleton height={96} radius={16} />}>
        {(e) => (
          <div className="earn">
            <p className="earn__today">{formatMoney(e.today)}</p>
            <p className="small muted">{e.todayCount ? `${countOf(e.todayCount, e.countLabel)} today` : 'Nothing recorded yet today.'}</p>
            <dl className="earn__row"><div><dt>This week</dt><dd>{formatMoney(e.week)}</dd></div><div><dt className="earn__cap">{e.countLabel} this week</dt><dd>{e.weekCount}</dd></div></dl>
            {e.note && <p className="earn__note small">{e.note}</p>}
          </div>
        )}
      </SectionBody>
    </Module>
  );
}

export function Performance({ home, loading }: { home?: PartnerHome; loading: boolean }) {
  return (
    <Module id="perf-h" title="Performance" icon="star">
      <SectionBody section={home?.performance} loading={loading} skeleton={<Skeleton height={72} radius={16} />}
        empty={(d) => (d.length ? null : <p className="small muted">No performance data yet.</p>)}>
        {(items) => (
          <dl className="perf">
            {items.map((m) => <div key={m.key}><dt>{m.label}</dt><dd>{m.display}</dd><span className="metric__hint">{m.hint}</span></div>)}
          </dl>
        )}
      </SectionBody>
    </Module>
  );
}

export function Activity({ home, loading }: { home?: PartnerHome; loading: boolean }) {
  return (
    <Module id="act-h" title="Recent activity" icon="history">
      <SectionBody section={home?.activity} loading={loading} skeleton={<Skeleton height={140} radius={16} />}
        empty={(d) => (d.length ? null : <p className="small muted">No activity yet. Updates on your work will show here.</p>)}>
        {(items) => (
          <ol className="timeline">
            {items.map((a) => (
              <li key={a.id} className={`timeline__item tone-${a.tone}`}>
                <div className="timeline__text"><p className="timeline__title">{a.title}</p>{a.body && <p className="small muted">{a.body}</p>}</div>
                <div className="timeline__meta small">
                  {a.amount && <strong>{formatMoney(a.amount)}</strong>}
                  <time dateTime={a.at} className="muted">{timeAgo(a.at)}</time>
                </div>
              </li>
            ))}
          </ol>
        )}
      </SectionBody>
    </Module>
  );
}
