import { Link, useParams } from 'react-router-dom';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { ApiError } from '@click/api';
import { useAuth } from '../auth/AuthProvider';
import { EmptyState, ErrorState, Icon, Skeleton, useToast } from '../components/ui';
import { useThemeOverride } from '../components/layout/AppShell';
import { WishlistButton } from '../features/wishlist/WishlistButton';
import { AddControl, BasketBar, GroceryImage, Price, Rail, Section, StatusPill } from '../features/groceries/parts';
import { useGroceryAt } from '../features/groceries/useGroceries';
import { api } from '../lib/api';
import { formatMoney } from '../lib/format';

/** A store's listing: price/MRP, stock, freshness, details, the same pack at other nearby stores, and related items. */
export function GroceryProductPage() {
  useThemeOverride('grocery');
  const { id = '' } = useParams();
  const { at, key } = useGroceryAt();
  const { status } = useAuth();
  const toast = useToast();
  const qc = useQueryClient();
  const q = useQuery({ queryKey: ['groceries', 'product', id, key, status], queryFn: () => api.groceries.product(id, at) });
  const notify = useMutation({
    mutationFn: () => api.groceries.alert({ productId: id }),
    onSuccess: () => { toast('We’ll notify you when it’s back in stock.'); qc.invalidateQueries({ queryKey: ['groceries', 'product', id] }); },
    onError: (e) => toast(e instanceof ApiError ? e.message : 'Couldn’t set the reminder.', 'error'),
  });

  if (q.isError) {
    return q.error instanceof ApiError && q.error.status === 404
      ? <EmptyState icon="grocery" title="Product not found" message="The store may have removed it." action={<Link to="/groceries" className="btn btn--outline">Browse Groceries</Link>} />
      : <ErrorState error={q.error} onRetry={() => q.refetch()} />;
  }
  if (q.isPending) return <div className="gr-page" data-theme="grocery"><Skeleton height={320} radius={24} /><Skeleton height={120} /></div>;
  const p = q.data;
  const nutrition = Object.entries(p.nutrition ?? {});
  const others = p.compare.filter((c) => c.id !== p.id);

  return (
    <div className="gr-page" data-theme="grocery">
      <Link to={`/groceries/store/${p.store.slug}`} className="gr-back"><Icon name="back" size={18} /> {p.store.name}</Link>
      <article className="gr-pdp">
        <div className="gr-pdp__media"><GroceryImage l={p} large /></div>
        <div className="gr-pdp__info">
          <div className="spread" style={{ alignItems: 'flex-start' }}>
            <div>
              {p.brand && <span className="gr-card__brand">{p.brand}</span>}
              <h1>{p.name}</h1>
              <p className="muted">{p.size}{p.perUnit ? ` · ${p.perUnit}` : ''}</p>
            </div>
            <WishlistButton target={{ productId: p.id }} name={p.name} />
          </div>
          <Price l={p} />
          {p.dealEndsAt && <p className="small">Deal ends {new Date(p.dealEndsAt).toLocaleDateString('en-IN', { day: 'numeric', month: 'short' })}</p>}
          <div className="gr-pdp__tags">
            {p.freshToday && <span className="gr-badge gr-badge--fresh">Received today</span>}
            {!p.freshToday && p.receivedOn && <span className="gr-badge">Received {new Date(p.receivedOn).toLocaleDateString('en-IN', { day: 'numeric', month: 'short' })}</span>}
            {p.attributes.map((a) => <span key={a} className="gr-badge">{a}</span>)}
            {p.dietary === 'veg' && <span className="gr-badge">Vegetarian</span>}
            {p.dietary === 'vegan' && <span className="gr-badge">Vegan</span>}
            {p.stockLeft != null && <span className="gr-badge gr-badge--warn">Only {p.stockLeft} left</span>}
          </div>
          {p.pricingNote && <p className="small gr-note"><Icon name="alert" size={14} /> {p.pricingNote}</p>}
          <div className="gr-pdp__buy">
            {p.inStock ? <AddControl l={p} /> : (
              <div className="row">
                <span className="gr-oos">Out of stock</span>
                {status === 'authenticated' && (p.alertSet ? <span className="small muted">We’ll notify you.</span>
                  : <button type="button" className="btn btn--sm btn--primary" onClick={() => notify.mutate()} disabled={notify.isPending}>Notify me</button>)}
              </div>
            )}
          </div>
          <div className="gr-pdp__store">
            <Icon name="store" size={16} />
            <span>Sold by <Link to={`/groceries/store/${p.store.slug}`}><strong>{p.store.name}</strong></Link></span>
            <StatusPill status={p.delivery.status} />
            {p.delivery.etaLabel && <span className="small muted">{p.delivery.etaLabel}</span>}
          </div>
          {!p.delivery.deliverable && p.delivery.reason && <p className="small gr-note">{p.delivery.reason}</p>}
          {!p.delivery.etaLabel && p.delivery.deliverable && <p className="small muted">Estimated delivery shown at checkout.</p>}
        </div>
      </article>

      {others.length > 0 && (
        <Section title="Compare nearby" subtitle={`The same ${p.brand ? `${p.brand} ` : ''}${p.name}, ${p.size}, at other stores near you.`}>
          <div className="gr-compare">
            {p.compare.map((c) => (
              <Link key={c.id} to={`/groceries/p/${c.id}`} className={`gr-compare__row${c.id === p.id ? ' is-current' : ''}`}>
                <strong>{c.store.name}</strong>
                <span className="small muted">{c.distanceKm != null ? `${c.distanceKm.toFixed(1)} km` : ''}{c.store.etaLabel ? ` · ${c.store.etaLabel}` : ''}</span>
                <span>{c.inStock ? formatMoney(c.price) : 'Out of stock'}</span>
              </Link>
            ))}
          </div>
        </Section>
      )}

      {(p.description || p.ingredients || nutrition.length > 0) && (
        <section className="card card--pad stack gr-details">
          <h2 className="gr-h3">Product details</h2>
          {p.description && <p className="small">{p.description}</p>}
          {p.ingredients && <p className="small"><strong>Ingredients:</strong> {p.ingredients}</p>}
          {nutrition.length > 0 && (
            <table className="gr-nutrition"><caption className="small muted">Nutrition per 100 g/ml</caption>
              <tbody>{nutrition.map(([k, v]) => <tr key={k}><th scope="row">{k}</th><td>{v}</td></tr>)}</tbody></table>
          )}
          {p.imageCredit && p.imageSource && <p className="small muted">Photo: <a href={p.imageSource} target="_blank" rel="noreferrer">{p.imageCredit}</a> (illustrative of the product type)</p>}
        </section>
      )}

      {p.together.length > 0 && <Section title="Frequently bought together" subtitle="From orders placed on Click."><Rail items={p.together} /></Section>}
      {p.similar.length > 0 && <Section title="Similar products"><Rail items={p.similar} /></Section>}
      {p.reviews.length > 0 && (
        <Section title="Reviews">
          <div className="stack">{p.reviews.map((r) => <p key={r.id} className="small"><Icon name="star" size={12} /> {r.rating} · {r.title || r.body} — {r.author}</p>)}</div>
        </Section>
      )}
      <BasketBar />
    </div>
  );
}
