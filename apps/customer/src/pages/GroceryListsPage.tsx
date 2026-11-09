import { useEffect, useState } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { ApiError, type FindStorePlan, type ShoppingList } from '@click/api';
import { Button, EmptyState, ErrorState, Icon, Skeleton, useToast } from '../components/ui';
import { useThemeOverride } from '../components/layout/AppShell';
import { BasketBar, StatusPill } from '../features/groceries/parts';
import { useBasketActions } from '../features/groceries/useGroceries';
import { api } from '../lib/api';
import { formatMoney } from '../lib/format';
import { useDeliveryLocation } from '../location/LocationProvider';

const listsKey = ['customer', 'groceries', 'lists'] as const;

/**
 * Shopping list + "Find everything": Click. matches each line to real stock at stores that deliver to you, then shows
 * the store with the most of your list (and a split if no single store has it all). Nothing is added until you choose.
 * `?items=milk,bread` (from Buddy) starts a new list with those items, after you confirm.
 */
export function GroceryListsPage() {
  useThemeOverride('grocery');
  const qc = useQueryClient();
  const toast = useToast();
  const [params, setParams] = useSearchParams();
  const { selected } = useDeliveryLocation();
  const lists = useQuery({ queryKey: listsKey, queryFn: () => api.groceries.lists.all() });
  const [activeId, setActiveId] = useState<string | null>(null);
  const active = lists.data?.results.find((l) => l.id === activeId) ?? lists.data?.results[0] ?? null;
  const [text, setText] = useState('');
  const fail = (e: unknown) => toast(e instanceof ApiError ? e.message : 'Something went wrong. Try again.', 'error');
  const put = (l: ShoppingList) => qc.setQueryData(listsKey, (old: { results: ShoppingList[] } | undefined) =>
    ({ results: [l, ...(old?.results ?? []).filter((x) => x.id !== l.id)] }));
  const create = useMutation({ mutationFn: api.groceries.lists.create, onSuccess: (l) => { put(l); setActiveId(l.id); }, onError: fail });
  const addItem = useMutation({ mutationFn: (t: string) => api.groceries.lists.addItem(active!.id, { text: t }), onSuccess: (l) => { put(l); setText(''); }, onError: fail });
  const update = useMutation({ mutationFn: (v: { id: string; isDone?: boolean; quantity?: number }) => api.groceries.lists.updateItem(active!.id, v.id, v), onSuccess: put, onError: fail });
  const removeItem = useMutation({ mutationFn: (id: string) => api.groceries.lists.removeItem(active!.id, id), onSuccess: put, onError: fail });
  const find = useMutation({ mutationFn: () => api.groceries.lists.find(active!.id, selected?.id), onError: fail });
  const preset = params.get('items');
  useEffect(() => { find.reset(); }, [active?.id]); // eslint-disable-line react-hooks/exhaustive-deps

  return (
    <div className="gr-page" data-theme="grocery">
      <Link to="/groceries" className="gr-back"><Icon name="back" size={18} /> Groceries</Link>
      <header className="gr-intro"><h1>Shopping list<span>.</span></h1><p>Write what you need. Click. checks which nearby stores have it.</p></header>

      {preset && (
        <div className="gr-callout">
          <span>Start a list with: <strong>{preset.split(',').map((s) => s.trim()).filter(Boolean).join(', ')}</strong>?</span>
          <div className="row">
            <Button size="sm" onClick={() => { create.mutate({ name: 'From Buddy', items: preset.split(',').map((s) => s.trim()).filter(Boolean).slice(0, 30) }); setParams({}, { replace: true }); }}>Create list</Button>
            <Button size="sm" variant="ghost" onClick={() => setParams({}, { replace: true })}>Not now</Button>
          </div>
        </div>
      )}

      {lists.isError ? <ErrorState error={lists.error} onRetry={() => lists.refetch()} /> : lists.isPending ? <Skeleton height={200} /> : !active ? (
        <EmptyState icon="receipt" title="No lists yet" message="Make a list like “milk, rice, tomatoes, bread, eggs”."
          action={<Button onClick={() => create.mutate({ name: 'My list' })} loading={create.isPending}>New list</Button>} />
      ) : (
        <>
          {lists.data!.results.length > 1 && (
            <div className="gr-chips">{lists.data!.results.map((l) => <button key={l.id} type="button" className="chip" aria-pressed={l.id === active.id} onClick={() => setActiveId(l.id)}>{l.name}</button>)}
              <button type="button" className="chip" onClick={() => create.mutate({ name: `List ${lists.data!.results.length + 1}` })}>+ New</button></div>
          )}
          <section className="card card--pad stack">
            <div className="spread"><h2 className="gr-h3">{active.name}</h2>{lists.data!.results.length === 1 && <button type="button" className="link-btn small" onClick={() => create.mutate({ name: 'List 2' })}>+ New list</button>}</div>
            <form className="gr-listadd" onSubmit={(e) => { e.preventDefault(); if (text.trim()) addItem.mutate(text.trim()); }}>
              <input value={text} onChange={(e) => setText(e.target.value)} placeholder="Add an item, e.g. tomatoes" aria-label="Add an item to the list" maxLength={80} />
              <Button size="sm" type="submit" loading={addItem.isPending} disabled={!text.trim()}>Add</Button>
            </form>
            {active.items.length === 0 ? <p className="small muted">Your list is empty.</p> : (
              <ul className="gr-list">
                {active.items.map((i) => (
                  <li key={i.id} className={i.isDone ? 'is-done' : ''}>
                    <label><input type="checkbox" checked={i.isDone} onChange={() => update.mutate({ id: i.id, isDone: !i.isDone })} /> <span>{i.text}</span></label>
                    <div className="gr-qty gr-qty--sm" role="group" aria-label={`Quantity of ${i.text}`}>
                      <button type="button" aria-label="Fewer" disabled={i.quantity <= 1} onClick={() => update.mutate({ id: i.id, quantity: i.quantity - 1 })}>−</button>
                      <span>{i.quantity}</span>
                      <button type="button" aria-label="More" onClick={() => update.mutate({ id: i.id, quantity: i.quantity + 1 })}>+</button>
                    </div>
                    <button type="button" className="icon-btn" aria-label={`Remove ${i.text}`} onClick={() => removeItem.mutate(i.id)}><Icon name="close" size={16} /></button>
                  </li>
                ))}
              </ul>
            )}
            <Button onClick={() => find.mutate()} loading={find.isPending} disabled={!active.items.some((i) => !i.isDone)}>Find everything</Button>
            {!selected && <p className="small gr-warn">Choose a delivery location first so we can check stores near you.</p>}
          </section>

          {find.data && (
            <section className="gr-find stack" aria-live="polite">
              {!find.data.hasLocation ? <p className="small gr-warn">Your selected address has no map pin, so we can’t tell which stores deliver there.</p> : !find.data.best ? (
                <EmptyState icon="search" title="No nearby store has these items" message="Try simpler words like “milk” or “rice”." />
              ) : (
                <>
                  <h2 className="gr-h3">{find.data.complete ? `Best match: ${find.data.best.store.name}` : `Most of your list: ${find.data.best.store.name}`}</h2>
                  <Plan plan={find.data.best} lines={find.data.lines} />
                  {find.data.split.length > 0 && (
                    <>
                      <h3 className="gr-h3">Or split across {find.data.split.length} stores to get more of the list</h3>
                      <p className="small muted">Each store delivers separately, with its own fee and timing.</p>
                      {find.data.split.map((p) => <Plan key={p.store.id} plan={p} lines={find.data!.lines} />)}
                    </>
                  )}
                  {find.data.missing.length > 0 && <p className="small gr-warn">Not found nearby: {find.data.missing.map((m) => m.text).join(', ')}</p>}
                  {find.data.stores.length > 1 && (
                    <details className="small"><summary>Compare all {find.data.stores.length} stores</summary>
                      <ul className="gr-compare-list">{find.data.stores.map((s) => <li key={s.store.id}><strong>{s.store.name}</strong> · {s.found}/{find.data!.lines} items · {formatMoney(s.estimatedTotal)} incl. delivery{s.store.etaLabel ? ` · ${s.store.etaLabel}` : ''}{s.store.distanceKm != null ? ` · ${s.store.distanceKm.toFixed(1)} km` : ''}</li>)}</ul>
                    </details>
                  )}
                </>
              )}
            </section>
          )}
        </>
      )}
      <BasketBar />
    </div>
  );
}

function Plan({ plan, lines }: { plan: FindStorePlan; lines: number }) {
  const { addListing, busy } = useBasketActions();
  const toast = useToast();
  const [done, setDone] = useState(false);
  const addAll = async () => {
    let n = 0;
    for (const i of plan.items) if (await addListing(i.listing, i.quantity)) n += 1;
    if (n) { toast(`Added ${n} item${n > 1 ? 's' : ''} from ${plan.store.name}`); setDone(true); }
  };
  return (
    <div className="card card--pad stack gr-plan">
      <div className="spread"><strong>{plan.store.name}</strong><StatusPill status={plan.store.status} /></div>
      <p className="small muted">{plan.found} of {lines} items · items {formatMoney(plan.subtotal)} · about {formatMoney(plan.estimatedTotal)} with delivery{plan.store.etaLabel ? ` · ${plan.store.etaLabel}` : ''}{plan.store.distanceKm != null ? ` · ${plan.store.distanceKm.toFixed(1)} km` : ''}</p>
      <ul className="gr-plan__items">{plan.items.map((i) => <li key={i.lineId} className="small"><span className="muted">{i.text} →</span> {i.quantity} × {i.listing.brand ? `${i.listing.brand} ` : ''}{i.listing.name} {i.listing.size} · {formatMoney(i.listing.price)}</li>)}</ul>
      {plan.store.minOrder && Number(plan.subtotal) < Number(plan.store.minOrder) && <p className="small gr-warn">Below this store’s {formatMoney(plan.store.minOrder)} minimum.</p>}
      {done ? <Link to="/groceries/basket" className="btn btn--outline btn--sm">View basket</Link>
        : <Button size="sm" onClick={addAll} loading={busy}>Add these to basket</Button>}
    </div>
  );
}
