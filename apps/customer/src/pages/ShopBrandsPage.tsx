import { Link } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { EmptyState, ErrorState, Icon, Skeleton } from '../components/ui';
import { useThemeOverride } from '../components/layout/AppShell';
import { BrandCard } from '../features/shop/ShopBlocks';
import { api } from '../lib/api';

/** Every brand with live listings on Click. Shopping (listing a brand implies no partnership with it). */
export function ShopBrandsPage() {
  useThemeOverride('shopping');
  const brands = useQuery({ queryKey: ['shop', 'brands'], queryFn: api.shop.brands });
  return (
    <div className="stack" data-theme="shopping">
      <Link to="/shopping" className="btn btn--ghost btn--sm" style={{ alignSelf: 'flex-start', paddingLeft: 4 }}><Icon name="back" size={18} /> Shopping</Link>
      <h1>Brands</h1>
      <p className="small muted">Brands sold by Click. sellers, most products first.</p>
      {brands.isError ? <ErrorState error={brands.error} onRetry={() => brands.refetch()} />
        : brands.isPending ? <div className="brand-grid">{Array.from({ length: 12 }, (_, i) => <Skeleton key={i} height={120} radius={18} />)}</div>
        : brands.data.results.length === 0 ? <EmptyState icon="tag" title="No brands yet" />
        : <div className="brand-grid">{brands.data.results.map((b) => <BrandCard key={b.slug} b={b} />)}</div>}
    </div>
  );
}
