import { useQuery } from '@tanstack/react-query';
import { api } from '../../lib/api';
import { ShopCard } from '../shop/ShopCard';
import { HomeSection } from './HomeSection';

/** Home's Shopping discovery: the live Shopping deals (or, without deals, today's popular picks). Hidden when empty. */
export function ShoppingPicks() {
  const home = useQuery({ queryKey: ['shop', 'home'], queryFn: api.shop.home, staleTime: 60_000 });
  const section = home.data?.sections.find((s) => s.id === 'deals' && s.kind === 'products')
    ?? home.data?.sections.find((s) => s.id === 'for_you' && s.kind === 'products');
  if (!section || section.kind !== 'products' || section.products.length === 0) return null;
  const deals = section.id === 'deals';
  return (
    <HomeSection id="shop-picks" title={deals ? 'Shopping deals' : 'Popular in Shopping'} icon="shop" theme="shopping" to="/shopping"
      subtitle={deals ? 'Limited-time prices from Click. sellers.' : 'Picked from Click. Shopping.'} linkLabel="Open Shopping">
      <div className="shop-rail">{section.products.slice(0, 8).map((p) => <ShopCard key={p.id} p={p} />)}</div>
    </HomeSection>
  );
}
