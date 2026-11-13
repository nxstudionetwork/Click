import { useEffect } from 'react';
import { Link, useNavigate, useSearchParams } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { Button, EmptyState, ErrorState, Icon, Skeleton } from '../components/ui';
import { useThemeOverride } from '../components/layout/AppShell';
import { compareStore } from '../features/shop/compare';
import { Price, Stars } from '../features/shop/ShopCard';
import { ShopImage } from '../features/shop/ShopImage';
import { useShopActions } from '../features/shop/useShopActions';
import { api } from '../lib/api';

/** Side-by-side comparison of 2-4 products, using only their real attributes, prices, ratings and terms. */
export function ShopComparePage() {
  useThemeOverride('shopping');
  const [params] = useSearchParams();
  const ids = (params.get('ids') ?? '').split(',').filter(Boolean).slice(0, 4);
  const cmp = useQuery({ queryKey: ['shop', 'compare', ids], queryFn: () => api.shop.compare(ids), enabled: ids.length >= 2 });
  const { addToCart, addedSheet } = useShopActions();
  const navigate = useNavigate();
  const remove = (id: string) => {
    compareStore.remove(id);
    const rest = ids.filter((x) => x !== id);
    navigate(rest.length >= 2 ? `/shopping/compare?ids=${rest.join(',')}` : '/shopping', { replace: true });
  };
  useEffect(() => { if (cmp.data) cmp.data.products.forEach((p) => compareStore.add({ id: p.id, name: p.name, categorySlug: p.categorySlug })); }, [cmp.data]);

  if (ids.length < 2) return <EmptyState icon="compare" title="Choose products to compare" message="Tick “Compare” on two to four products in the same category." action={<Link to="/shopping" className="btn btn--primary">Go to Shopping</Link>} />;
  if (cmp.isError) return <ErrorState error={cmp.error} onRetry={() => cmp.refetch()} />;
  if (cmp.isPending) return <Skeleton height={320} radius={18} />;
  const { products, rows } = cmp.data;

  return (
    <div className="stack" data-theme="shopping">
      <Link to="/shopping" className="btn btn--ghost btn--sm" style={{ alignSelf: 'flex-start', paddingLeft: 4 }}><Icon name="back" size={18} /> Shopping</Link>
      <h1>Compare products</h1>
      <p className="small muted">Rows that differ are highlighted. Missing details are shown as “—”; nothing is filled in for a seller.</p>
      <div className="ctable-wrap">
        <table className="ctable">
          <thead>
            <tr>
              <th scope="col"><span className="visually-hidden">Detail</span></th>
              {products.map((p) => (
                <td key={p.id}>
                  <div className="stack" style={{ gap: 6 }}>
                    <Link to={`/products/${p.id}`} style={{ position: 'relative', display: 'block', aspectRatio: '1', borderRadius: 14, overflow: 'hidden', background: 'var(--c-surface-2)' }}>
                      <ShopImage image={p.image} alt={p.name} icon={p.categoryIcon} brand={p.brand} sizes="160px" />
                    </Link>
                    <span className="pcard__brand">{p.brand}</span>
                    <Link to={`/products/${p.id}`} className="pcard__name">{p.name}</Link>
                    <Button size="sm" onClick={() => addToCart(p)} disabled={!p.inStock}>{p.hasVariants ? 'Choose options' : p.inStock ? 'Add to cart' : 'Out of stock'}</Button>
                    <button type="button" className="btn btn--ghost btn--sm" onClick={() => remove(p.id)}>Remove</button>
                  </div>
                </td>
              ))}
            </tr>
          </thead>
          <tbody>
            <tr><th scope="row">Price</th>{products.map((p) => <td key={p.id}><Price p={p} /></td>)}</tr>
            <tr><th scope="row">Rating</th>{products.map((p) => <td key={p.id}><Stars rating={p.rating} count={p.ratingCount} /></td>)}</tr>
            {rows.map((r) => (
              <tr key={r.label} className={r.differs ? 'is-diff' : ''}>
                <th scope="row">{r.label}</th>
                {r.values.map((v, i) => <td key={i} className={v ? '' : 'missing'}>{v ?? '—'}</td>)}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {addedSheet}
    </div>
  );
}
