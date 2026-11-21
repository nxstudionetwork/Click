import { useState } from 'react';
import { Link } from 'react-router-dom';
import { Button, Icon, Skeleton } from '@click/ui';
import { AppShell } from '../../components/AppShell';
import { useDriverEarnings } from '../../features/driver/queries';
import { Module } from '../../features/home/sections';
import { apiMessage } from '../../lib/format';
import { formatMoney } from '../../lib/money';

/** Driver earnings by period from completed trips, split into cash collected and paid via Click. Nothing estimated. */
export function DriverEarningsPage() {
  const q = useDriverEarnings();
  const [key, setKey] = useState<'today' | 'yesterday' | 'week' | 'month'>('today');
  const d = q.data;
  const p = d?.periods.find((x) => x.key === key);
  const max = Math.max(1, ...(d?.last7Days.map((x) => Number(x.total)) ?? [1]));

  return (
    <AppShell>
      <div className="page">
        <div className="page__head"><h1>Earnings</h1><p className="muted small">From your completed trips on Click.</p></div>
        {q.isPending ? <Skeleton height={260} radius={22} /> : q.isError ? (
          <div className="dash__error" role="alert"><h2>Couldn’t load earnings</h2><p className="muted">{apiMessage(q.error)}</p>
            <Button onClick={() => void q.refetch()}>Try again</Button></div>
        ) : d && p && (
          <>
            <div className="seg seg--wrap" role="group" aria-label="Period">
              {d.periods.map((x) => (
                <button key={x.key} type="button" className={`seg__btn ${x.key === key ? 'is-active' : ''}`} aria-pressed={x.key === key}
                  onClick={() => setKey(x.key)}>{x.label}</button>
              ))}
            </div>
            <section className="mod earn-hero" aria-labelledby="eh">
              <p id="eh" className="small muted">{p.label}</p>
              <p className="earn-hero__total">{formatMoney(p.total)}</p>
              <div className="metrics">
                <div className="metric"><span className="small muted">Trips</span><strong>{p.trips}</strong></div>
                <div className="metric"><span className="small muted">Online</span><strong>{p.onlineLabel}</strong></div>
                <div className="metric"><span className="small muted">Distance</span><strong>{p.distanceKm.toFixed(1)} km</strong></div>
                <div className="metric"><span className="small muted">Per trip</span><strong>{p.perTrip ? formatMoney(p.perTrip) : '—'}</strong></div>
              </div>
              <dl className="ledger">
                <div><dt>Cash collected from riders</dt><dd>{formatMoney(p.cashCollected)}</dd></div>
                <div><dt>Paid via Click (to be settled to you)</dt><dd>{formatMoney(p.paidViaClick)}</dd></div>
                <div><dt>Click commission, incentives, payouts</dt><dd className="muted">Not set up yet</dd></div>
              </dl>
            </section>
            <Module id="w7" title="Last 7 days" icon="chart">
              <ol className="bars" aria-label="Earnings per day">
                {d.last7Days.map((x) => (
                  <li key={x.date} className="bars__row">
                    <span className="bars__day">{new Date(`${x.date}T00:00:00`).toLocaleDateString('en-IN', { weekday: 'short', day: 'numeric' })}</span>
                    <span className="bars__track"><span className="bars__fill" style={{ width: `${(Number(x.total) / max) * 100}%` }} /></span>
                    <span className="bars__value">{formatMoney(x.total)} · {x.trips}</span>
                  </li>
                ))}
              </ol>
            </Module>
            <p className="small muted">{d.note}</p>
            <Link to="/driver/rides?view=history" className="text-btn"><Icon name="history" size={14} /> Trip history</Link>
          </>
        )}
      </div>
    </AppShell>
  );
}
