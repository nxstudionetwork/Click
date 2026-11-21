import { useState } from 'react';
import { Button, Skeleton } from '@click/ui';
import { AppShell } from '../../components/AppShell';
import { Module } from '../../features/home/sections';
import { useInsights } from '../../features/restaurant/queries';
import { apiMessage } from '../../lib/format';
import { formatMoney } from '../../lib/money';

const PERIODS = [{ d: 1, l: 'Today' }, { d: 7, l: '7 days' }, { d: 30, l: '30 days' }] as const;

function Stat({ label, value, hint }: { label: string; value: string; hint?: string }) {
  return <div className="metric"><span className="small muted">{label}</span><strong>{value}</strong>{hint && <span className="metric__hint">{hint}</span>}</div>;
}

const rate = (v: number | null) => (v === null ? '—' : `${v}%`);

/** Restaurant insights from real orders, status history and ratings only. Nothing is estimated or invented. */
export function InsightsPage() {
  const [days, setDays] = useState<1 | 7 | 30>(7);
  const q = useInsights(days);
  const d = q.data;

  return (
    <AppShell>
      <div className="page">
        <div className="page__head spread">
          <div><h1>Insights</h1><p className="muted small">From your orders on Click.</p></div>
          <div className="seg" role="group" aria-label="Period">
            {PERIODS.map((p) => (
              <button key={p.d} type="button" className={`seg__btn ${days === p.d ? 'is-active' : ''}`} aria-pressed={days === p.d}
                onClick={() => setDays(p.d)}>{p.l}</button>
            ))}
          </div>
        </div>
        {q.isPending ? <Skeleton height={300} radius={22} /> : q.isError && !d ? (
          <div className="dash__error" role="alert"><h2>Couldn’t load insights</h2><p className="muted">{apiMessage(q.error)}</p>
            <Button onClick={() => void q.refetch()}>Try again</Button></div>
        ) : d && (
          <>
            <Module id="sales-h" title="Sales" icon="chart">
              <div className="metrics">
                <Stat label="Today" value={formatMoney(d.sales.today)} />
                <Stat label="Last 7 days" value={formatMoney(d.sales.week)} />
                <Stat label="Last 30 days" value={formatMoney(d.sales.month)} />
                <Stat label="Discounts given" value={formatMoney(d.money.discounts)} hint={`Period: ${PERIODS.find((p) => p.d === days)!.l}`} />
              </div>
              <p className="small muted">{d.note}</p>
            </Module>
            <Module id="orders-h" title="Orders" icon="receipt">
              <div className="metrics">
                <Stat label="Orders" value={String(d.orders.total)} />
                <Stat label="Completed" value={String(d.orders.completed)} />
                <Stat label="Cancelled" value={String(d.orders.cancelled)} hint={d.orders.rejected ? `${d.orders.rejected} declined by you` : undefined} />
                <Stat label="Average order" value={d.orders.averageValue ? formatMoney(d.orders.averageValue) : '—'} />
              </div>
            </Module>
            <Module id="ops-h2" title="Kitchen performance" icon="clock">
              <div className="metrics">
                <Stat label="Average preparation" value={d.operations.averagePrepMinutes === null ? '—' : `${d.operations.averagePrepMinutes} min`}
                  hint={`Target ${d.operations.targetMinutes} min`} />
                <Stat label="Ready on time" value={rate(d.operations.onTimeRate)} hint="Within target + 5 min" />
                <Stat label="Acceptance" value={rate(d.operations.acceptanceRate)} />
                <Stat label="Cancellation" value={rate(d.operations.cancellationRate)} />
              </div>
            </Module>
            <Module id="menu-h" title="Menu" icon="food">
              {d.menu.bestSellers.length === 0 ? <p className="small muted">No items sold in this period yet.</p> : (
                <ol className="rank">
                  {d.menu.bestSellers.map((b) => (
                    <li key={b.name}><span>{b.name}</span><span className="small muted">{b.quantity} sold · {formatMoney(b.revenue)}</span></li>
                  ))}
                </ol>
              )}
              {d.menu.notSelling.length > 0 && <p className="small"><strong>Not ordered in this period:</strong> {d.menu.notSelling.join(', ')}</p>}
              {d.menu.unavailable.length > 0 && <p className="small"><strong>Marked unavailable:</strong> {d.menu.unavailable.join(', ')}</p>}
            </Module>
            <Module id="cust-h" title="Customers" icon="star">
              <div className="metrics">
                <Stat label="Rating" value={d.customers.storeRating ? `${d.customers.storeRating.toFixed(1)}★` : 'No ratings yet'} />
                <Stat label="Ratings this period" value={String(d.customers.ratings)} />
                <Stat label="Customers" value={String(d.customers.customers)} />
                <Stat label="Ordered again" value={String(d.customers.repeatCustomers)} />
              </div>
              {d.customers.recentFeedback.map((f) => (
                <blockquote key={f.at} className="quote"><strong>{f.rating}★</strong> {f.comment}</blockquote>
              ))}
            </Module>
          </>
        )}
      </div>
    </AppShell>
  );
}
