import { useState } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import { Button, Icon } from '@click/ui';
import { AppShell } from '../../components/AppShell';
import { Empty, listSkeleton, WorkList } from '../../features/home/sections';
import { useRestaurantOrders } from '../../features/restaurant/queries';
import { apiMessage } from '../../lib/format';

/** The order queue and history: stage filters, search by order number, a date, and paging (never everything at once). */
export function OrdersPage() {
  const [params, setParams] = useSearchParams();
  const status = params.get('status') ?? 'new';
  const date = params.get('date') ?? '';
  const q = params.get('q') ?? '';
  const page = Math.max(Number(params.get('page') ?? 1) || 1, 1);
  const [text, setText] = useState(q);
  const orders = useRestaurantOrders({ status, q, date, page });
  const data = orders.data;

  function set(next: Record<string, string>) {
    const merged = { status, date, q, ...next };
    if (!('page' in next)) delete (merged as Record<string, string>).page;
    setParams(Object.fromEntries(Object.entries(merged).filter(([, v]) => v)), { replace: true });
  }

  return (
    <AppShell>
      <div className="page">
        <div className="page__head spread">
          <div>
            <h1>Orders</h1>
            <p className="muted small">Live orders refresh every few seconds.</p>
          </div>
          <Link to="/restaurant/kitchen" className="btn btn--outline btn--sm"><Icon name="food" size={16} /> Kitchen view</Link>
        </div>

        <form className="search-row" role="search" onSubmit={(e) => { e.preventDefault(); set({ q: text.trim() }); }}>
          <label className="visually-hidden" htmlFor="oq">Search by order number</label>
          <input id="oq" className="field__input" placeholder="Order number, e.g. 4F7K2Q" value={text} onChange={(e) => setText(e.target.value)}
            autoComplete="off" />
          <label className="visually-hidden" htmlFor="od">Date</label>
          <input id="od" type="date" className="field__input search-row__date" value={date} onChange={(e) => set({ date: e.target.value })} />
          <Button type="submit" size="sm">Search</Button>
          {(q || date) && <button type="button" className="text-btn" onClick={() => { setText(''); set({ q: '', date: '' }); }}>Clear</button>}
        </form>

        <div className="tabs" role="tablist" aria-label="Order status">
          {(data?.filters ?? [{ key: 'new', label: 'New', count: null }]).map((f) => (
            <button key={f.key} type="button" role="tab" aria-selected={f.key === status} className={`tabs__tab ${f.key === status ? 'is-active' : ''}`}
              onClick={() => set({ status: f.key })}>
              {f.label}{f.count ? <span className="tabs__count">{f.count}</span> : null}
            </button>
          ))}
        </div>

        <div role="tabpanel" aria-live="polite">
          {orders.isPending ? listSkeleton : orders.isError && !data ? (
            <div className="dash__error" role="alert">
              <h2>Couldn’t load orders</h2><p className="muted">{apiMessage(orders.error)}</p>
              <Button onClick={() => void orders.refetch()}>Try again</Button>
            </div>
          ) : data!.items.length === 0 ? (
            <Empty icon={q || date ? 'search' : 'check'} title={q || date ? 'No matching orders.' : 'Nothing here right now.'}
              message={q || date ? 'Check the order number or date.' : status === 'new' ? 'New orders appear here as soon as customers place them.' : undefined} />
          ) : (
            <>
              <p className="small muted">{data!.total} order{data!.total === 1 ? '' : 's'}</p>
              <WorkList items={data!.items} />
              {(page > 1 || data!.hasMore) && (
                <nav className="pager" aria-label="Pages">
                  <Button size="sm" variant="outline" disabled={page <= 1} onClick={() => set({ page: String(page - 1) })}>Previous</Button>
                  <span className="small muted">Page {page}</span>
                  <Button size="sm" variant="outline" disabled={!data!.hasMore} onClick={() => set({ page: String(page + 1) })}>Next</Button>
                </nav>
              )}
            </>
          )}
        </div>
      </div>
    </AppShell>
  );
}
