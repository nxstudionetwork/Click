import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { Button, Skeleton } from '@click/ui';
import { AppShell } from '../components/AppShell';
import { Empty } from '../features/home/sections';
import { api } from '../lib/api';
import { apiMessage } from '../lib/format';
import { countOf, formatMoney } from '../lib/money';

const dayLabel = (iso: string) => new Date(`${iso}T00:00:00`).toLocaleDateString('en-IN', { weekday: 'short', day: 'numeric', month: 'short' });

/** Daily totals from the partner's completed work (server-computed); a simple bar list with text values for every day. */
export function EarningsPage() {
  const [days, setDays] = useState<7 | 30>(7);
  const q = useQuery({ queryKey: ['partner', 'earnings', days], queryFn: () => api.partner.earnings(days) });
  const d = q.data;
  const max = Math.max(1, ...(d?.days.map((x) => Number(x.amount)) ?? [1]));

  return (
    <AppShell>
      <div className="page">
        <div className="page__head spread">
          <h1>{d?.label ?? 'Earnings'}</h1>
          <div className="seg" role="group" aria-label="Period">
            {([7, 30] as const).map((n) => (
              <button key={n} type="button" aria-pressed={days === n} className={`seg__btn ${days === n ? 'is-active' : ''}`} onClick={() => setDays(n)}>
                {n} days
              </button>
            ))}
          </div>
        </div>
        {q.isPending ? <Skeleton height={260} radius={20} /> : q.isError ? (
          <div className="dash__error" role="alert"><h2>Couldn’t load your earnings</h2><p className="muted">{apiMessage(q.error)}</p>
            <Button onClick={() => void q.refetch()}>Try again</Button></div>
        ) : d!.state !== 'live' ? <Empty icon="clock" title="Not live yet" message={d!.message} /> : (
          <>
            <section className="mod" aria-labelledby="tot-h">
              <p id="tot-h" className="muted small">Last {days} days</p>
              <p className="earn__today">{formatMoney(d!.total)}</p>
              <p className="small muted">{countOf(d!.count, d!.countLabel)}</p>
              {d!.note && <p className="earn__note small">{d!.note}</p>}
            </section>
            <section className="mod" aria-labelledby="daily-h">
              <h2 id="daily-h" className="mod__title">By day</h2>
              {d!.count === 0 ? <p className="small muted">No earnings recorded yet in this period.</p> : (
                <ul className="bars">
                  {[...d!.days].reverse().map((x) => (
                    <li key={x.date} className="bars__row">
                      <span className="bars__day">{dayLabel(x.date)}</span>
                      <span className="bars__track" aria-hidden="true"><span className="bars__fill" style={{ width: `${(Number(x.amount) / max) * 100}%` }} /></span>
                      <span className="bars__value">{formatMoney(x.amount)}<span className="muted"> · {x.count}</span></span>
                    </li>
                  ))}
                </ul>
              )}
            </section>
            {d!.recent.length > 0 && (
              <section className="mod" aria-labelledby="recent-h">
                <h2 id="recent-h" className="mod__title">Recent</h2>
                <ul className="ledger">
                  {d!.recent.map((r) => (
                    <li key={r.ref}>
                      <div><p className="ledger__title">{r.title}</p><p className="small muted">{r.ref} · {r.detail} · {new Date(r.at).toLocaleString('en-IN', { day: 'numeric', month: 'short', hour: 'numeric', minute: '2-digit' })}</p></div>
                      <strong>{formatMoney(r.amount, true)}</strong>
                    </li>
                  ))}
                </ul>
              </section>
            )}
          </>
        )}
      </div>
    </AppShell>
  );
}
