import { useQuery } from '@tanstack/react-query';
import type { StoreType } from '@click/api';
import { Icon, Skeleton } from '../../components/ui';
import { api } from '../../lib/api';
import { ProductCard } from '../stores/ProductCard';

/**
 * Filters that belong to the chosen category, built from the live menus of its stores: Bakery shows "Cakes, Breads,
 * Under ₹200"; Biryani shows "Biryani, Kebabs, Under ₹300". Picking one shows the matching dishes right away.
 */
export function useCategoryFacets(type: StoreType, category: string) {
  return useQuery({ queryKey: ['catalog', 'facets', type, category], queryFn: () => api.catalog.facets(type, category), enabled: !!category, staleTime: 5 * 60_000 });
}

export function CategoryFacets({ type, category, categoryName, section, under, onChange }: {
  type: StoreType; category: string; categoryName: string; section: string; under: string;
  onChange: (patch: { section?: string; under?: string }) => void;
}) {
  const facets = useCategoryFacets(type, category);
  if (!category) return null;
  if (facets.isPending) return <div className="svc-facets"><Skeleton height={34} radius={999} /></div>;
  const f = facets.data;
  if (!f || (f.sections.length < 2 && f.priceBands.length === 0)) return null;
  return (
    <div className="svc-facets" role="group" aria-label={`Filters for ${categoryName}`}>
      <span className="svc-facets__label">In {categoryName}</span>
      <div className="svc-facets__chips">
        {f.sections.length > 1 && f.sections.map((s) => (
          <button key={s.name} type="button" className="chip" aria-pressed={section === s.name} onClick={() => onChange({ section: section === s.name ? '' : s.name })}>
            {section === s.name && <Icon name="check" size={14} />} {s.name}<span className="svc-facets__n">{s.count}</span>
          </button>
        ))}
        {f.priceBands.map((b) => (
          <button key={b.max} type="button" className="chip" aria-pressed={under === String(b.max)} onClick={() => onChange({ under: under === String(b.max) ? '' : String(b.max) })}>
            {under === String(b.max) && <Icon name="check" size={14} />} {b.label}
          </button>
        ))}
      </div>
    </div>
  );
}

/** The dishes / products matching the category filters, shown above the store list. */
export function FacetResults({ type, category, section, under, veg, label, onClear }: {
  type: StoreType; category: string; section: string; under: string; veg: boolean; label: string; onClear: () => void;
}) {
  const dishes = useQuery({
    queryKey: ['catalog', 'dishes', type, category, section, under, veg],
    queryFn: () => api.catalog.dishes({ type, category, section: section || undefined, maxPrice: under ? Number(under) : undefined, veg }),
    enabled: !!(category && (section || under)), placeholderData: (prev) => prev,
  });
  if (!category || !(section || under)) return null;
  const title = [section, under ? `under ₹${Number(under).toLocaleString('en-IN')}` : ''].filter(Boolean).join(' ') || label;
  return (
    <section className="stack svc-dishes" aria-labelledby="svc-dishes-h" aria-live="polite">
      <div className="spread">
        <h2 id="svc-dishes-h">{title[0]!.toUpperCase() + title.slice(1)}</h2>
        <button className="btn btn--ghost btn--sm" onClick={onClear}><Icon name="close" size={16} /> Clear</button>
      </div>
      {dishes.isPending ? <Skeleton height={180} /> : (dishes.data?.results.length ?? 0) === 0 ? (
        <p className="small muted">Nothing matches these filters right now. Try another one.</p>
      ) : (
        <div className="rail" role="list" aria-label={title}>
          {dishes.data!.results.map((p) => (
            <div key={p.id} className="rail__item" role="listitem"><ProductCard product={p} currency={p.store.currency} showStore /></div>
          ))}
        </div>
      )}
    </section>
  );
}
