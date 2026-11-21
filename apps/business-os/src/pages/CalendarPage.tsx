import { useMemo, useState } from 'react';
import { Link } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { Button, Icon } from '@click/ui';
import { api } from '../lib/api';
import { fmtDateTime, fmtTime } from '../lib/format';
import { Card, Empty, LoadingRows, PageHeader, QueryError } from '../components/ui';

const DOW = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'];
const key = (d: Date) => `${d.getFullYear()}-${d.getMonth()}-${d.getDate()}`;

export function CalendarPage() {
  const now = new Date();
  const [cursor, setCursor] = useState({ y: now.getFullYear(), m: now.getMonth() });
  const q = useQuery({ queryKey: ['os', 'calendar', cursor], queryFn: () => api.calendar({ year: cursor.y, month: cursor.m + 1 }) });
  const days = useMemo(() => {
    const first = new Date(cursor.y, cursor.m, 1);
    const start = new Date(first);
    start.setDate(1 - ((first.getDay() + 6) % 7));
    return Array.from({ length: 42 }, (_, i) => { const d = new Date(start); d.setDate(start.getDate() + i); return d; });
  }, [cursor]);
  const byDay = useMemo(() => {
    const m = new Map<string, NonNullable<typeof q.data>['results']>();
    for (const it of q.data?.results ?? []) { const k = key(new Date(it.at)); m.set(k, [...(m.get(k) ?? []), it]); }
    return m;
  }, [q.data]);
  const label = new Date(cursor.y, cursor.m, 1).toLocaleDateString('en-IN', { month: 'long', year: 'numeric' });
  const shift = (d: number) => setCursor((c) => { const n = new Date(c.y, c.m + d, 1); return { y: n.getFullYear(), m: n.getMonth() }; });

  return (
    <>
      <PageHeader title="Calendar" description={`Deadlines from ${q.data?.sources.join(' and ').toLowerCase() ?? 'your tasks and approvals'}. Meetings and events connect here later.`}
        actions={<div className="row">
          <Button variant="outline" size="sm" onClick={() => shift(-1)} aria-label="Previous month"><Icon name="back" size={16} /></Button>
          <Button variant="outline" size="sm" onClick={() => setCursor({ y: now.getFullYear(), m: now.getMonth() })}>Today</Button>
          <Button variant="outline" size="sm" onClick={() => shift(1)} aria-label="Next month"><Icon name="right" size={16} /></Button>
        </div>} />
      <Card title={label} flush>
        {q.isPending ? <LoadingRows /> : q.error ? <QueryError error={q.error} onRetry={() => void q.refetch()} /> : (
          <>
            <div className="cal" role="grid" aria-label={label}>
              {DOW.map((d) => <div key={d} className="cal__dow">{d}</div>)}
              {days.map((d) => {
                const items = byDay.get(key(d)) ?? [];
                return (
                  <div key={d.toISOString()} className={`cal__day ${d.getMonth() !== cursor.m ? 'cal__day--out' : ''} ${key(d) === key(now) ? 'cal__day--today' : ''}`}>
                    <span className="cal__num">{d.getDate()}</span>
                    {items.slice(0, 3).map((it) => <Link key={it.id} to={it.path} className={`cal__ev ${it.kind === 'approval' ? 'cal__ev--approval' : ''}`} title={it.title}>{fmtTime(it.at)} {it.title}</Link>)}
                    {items.length > 3 && <span className="muted">+{items.length - 3} more</span>}
                  </div>
                );
              })}
            </div>
            <div className="cal-list">
              {q.data.results.length ? <ul className="list">{q.data.results.map((it) => (
                <li key={it.id}><Link to={it.path} className="list-row"><span className="list-row__main"><span className="list-row__title" style={{ display: 'block' }}>{it.title}</span><span className="list-row__sub" style={{ display: 'block' }}>{fmtDateTime(it.at)}</span></span></Link></li>
              ))}</ul> : <Empty icon="calendar" title="Nothing scheduled this month" />}
            </div>
          </>
        )}
      </Card>
    </>
  );
}
