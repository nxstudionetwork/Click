import { useEffect, useMemo, useState } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import { useInfiniteQuery } from '@tanstack/react-query';
import { Button, EmptyState, ErrorState, Icon, Skeleton } from '../components/ui';
import { MoneyHead, Pill, THEME, groupByDay, iconFor, money, signed, timeOf } from '../features/money/parts';
import { api } from '../lib/api';

const LABEL: Record<string, string> = {
  food: 'Food', groceries: 'Groceries', shop: 'Shop', ride: 'Rides', parcel: 'Parcel', services: 'Services', travel: 'Travel', hotels: 'Hotels', shows: 'Shows',
  events: 'Events', bookings: 'Bookings', payments: 'Payments', wallet: 'Wallet', rewards: 'Rewards', wishlist: 'Saved', buddy: 'Buddy', support: 'Support',
};
const START: Record<string, [string, string]> = {
  food: ['/food', 'Order food'], groceries: ['/groceries', 'Shop groceries'], shop: ['/shopping', 'Start shopping'], ride: ['/rides', 'Book a ride'],
  parcel: ['/parcels', 'Send a parcel'], services: ['/services', 'Book a professional'], travel: ['/travel', 'Plan a journey'], hotels: ['/hotels', 'Find a stay'],
  shows: ['/showtime', 'Book a show'], events: ['/events', 'Plan an event'], bookings: ['/bookings', 'Find a place to visit'],
};
const STATUSES = [['', 'Any'], ['ok', 'Completed'], ['pending', 'In progress'], ['bad', 'Cancelled / failed']];

/** Activity: everything you did on Click., newest first, read from each service's own records. A dedicated page with
 *  its own header (no app header or bottom navigation). Notifications are separate. */
export function ActivityPage() {
  const [params, setParams] = useSearchParams();
  const category = params.get('category') ?? params.get('filter') ?? '';
  const status = params.get('status') ?? '';
  const [q, setQ] = useState(params.get('q') ?? '');
  const [term, setTerm] = useState(q);
  useEffect(() => { const t = setTimeout(() => setTerm(q.trim()), 300); return () => clearTimeout(t); }, [q]);
  const set = (k: string, v: string) => { const n = new URLSearchParams(params); n.delete('filter'); if (v) n.set(k, v); else n.delete(k); setParams(n, { replace: true }); };

  const list = useInfiniteQuery({
    queryKey: ['activity', category, status, term],
    queryFn: ({ pageParam }) => api.money.activity({ category, status, q: term, cursor: pageParam }),
    initialPageParam: null as string | null,
    getNextPageParam: (l) => l.nextCursor,
  });
  const rows = useMemo(() => list.data?.pages.flatMap((p) => p.results) ?? [], [list.data]);
  const cats = list.data?.pages[0]?.categories ?? Object.keys(LABEL);
  const filtered = !!(status || term);

  return (
    <div className="mn-page mn-page--full">
      <MoneyHead title="Activity" back="/account" />
      <div className="mn-search"><Icon name="search" size={18} />
        <input type="search" value={q} onChange={(e) => setQ(e.target.value)} placeholder="Search orders, bookings, amounts, references" aria-label="Search activity" /></div>
      <div className="mn-chips" role="tablist" aria-label="Activity type">
        <button type="button" role="tab" className="mn-chip" aria-selected={!category} aria-pressed={!category} onClick={() => set('category', '')}>All</button>
        {cats.map((c) => <button key={c} type="button" role="tab" className="mn-chip" aria-selected={category === c} aria-pressed={category === c} onClick={() => set('category', c)}>
          <Icon name={iconFor(c)} size={15} />{LABEL[c] ?? c}</button>)}
      </div>
      <div className="mn-chips" role="group" aria-label="Status">
        {STATUSES.map(([v, l]) => <button key={v || 'any'} type="button" className="mn-chip mn-chip--sm" aria-pressed={status === v} onClick={() => set('status', v!)}>{l}</button>)}
      </div>

      {list.isError ? <ErrorState error={list.error} onRetry={() => list.refetch()} /> : !list.data ? <Skeleton height={300} /> : rows.length === 0 && !list.hasNextPage ? (
        <EmptyState icon="history" title={filtered ? 'Nothing matches' : 'No activity yet'}
          message={filtered ? 'Try another search or filter.' : category ? `Nothing in ${LABEL[category] ?? category} yet.` : 'Your orders, rides, bookings, payments and rewards appear here.'}
          action={!filtered && START[category] ? <Link to={START[category]![0]} className="btn btn--primary">{START[category]![1]}</Link> : undefined} />
      ) : (
        <>
          {groupByDay(rows, (r) => r.at).map((g) => (
            <div key={g.label} className="mn-group"><h3 className="mn-group__label">{g.label}</h3>
              <ul className="mn-list">{g.rows.map((r) => (
                <li key={r.id}><Link to={r.link} className="mn-row" data-theme={THEME[r.category]}>
                  <span className="mn-row__icon mn-row__icon--theme"><Icon name={iconFor(r.category)} size={18} /></span>
                  <span className="mn-row__text"><strong className="truncate">{r.title}</strong>
                    <span className="small mn-muted truncate">{[r.subtitle, r.reference, timeOf(r.at)].filter(Boolean).join(' · ')}</span></span>
                  <span className="mn-row__end">{r.amount && <strong className={r.category === 'wallet' && Number(r.amount) > 0 ? 'mn-ok' : ''}>{r.category === 'wallet' ? signed(r.amount) : money(r.amount)}</strong>}{r.status && <Pill tone={r.tone}>{r.status}</Pill>}</span>
                </Link></li>
              ))}</ul>
            </div>
          ))}
          {rows.length === 0 && <p className="small mn-muted">No matches in recent activity.</p>}
          {list.hasNextPage && <Button variant="secondary" block loading={list.isFetchingNextPage} onClick={() => list.fetchNextPage()}>{filtered && rows.length < 5 ? 'Search older activity' : 'Load more'}</Button>}
        </>
      )}
    </div>
  );
}
