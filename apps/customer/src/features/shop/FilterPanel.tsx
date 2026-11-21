import { useEffect, useState } from 'react';
import type { ShopFacets } from '@click/api';
import { Button } from '../../components/ui';

export type Params = URLSearchParams;
type Set = (mutate: (p: URLSearchParams) => void) => void;

const toggleIn = (p: URLSearchParams, key: string, value: string) => {
  const cur = (p.get(key) ?? '').split(',').filter(Boolean);
  const next = cur.includes(value) ? cur.filter((v) => v !== value) : [...cur, value];
  if (next.length) p.set(key, next.join(',')); else p.delete(key);
};

/**
 * Filters for the current results, built only from the facets the backend returned (so a category shows its own
 * specs, e.g. Size and Fabric for clothing, Noise cancellation for audio). Everything lives in the URL.
 */
export function FilterPanel({ facets, params, update, hideCategories = false }: { facets: ShopFacets; params: Params; update: Set; hideCategories?: boolean }) {
  const has = (key: string, v: string) => (params.get(key) ?? '').split(',').includes(v);
  const [min, setMin] = useState(params.get('min_price') ?? '');
  const [max, setMax] = useState(params.get('max_price') ?? '');
  useEffect(() => { setMin(params.get('min_price') ?? ''); setMax(params.get('max_price') ?? ''); }, [params]);
  const active = [...params.keys()].some((k) => !['q', 'sort', 'page'].includes(k));

  return (
    <div className="shop-filters" data-theme="shopping">
      {!hideCategories && facets.categories.length > 1 && (
        <Group title="Category">
          {facets.categories.map((c) => (
            <button key={c.slug} type="button" className="chip" aria-pressed={params.get('category') === c.slug}
              onClick={() => update((p) => (p.get('category') === c.slug ? p.delete('category') : p.set('category', c.slug)))}>{c.name}<small>{c.count}</small></button>
          ))}
        </Group>
      )}
      <Group title="Price">
        <form className="shop-filters__price" onSubmit={(e) => { e.preventDefault(); update((p) => { min ? p.set('min_price', min) : p.delete('min_price'); max ? p.set('max_price', max) : p.delete('max_price'); }); }}>
          <input inputMode="numeric" pattern="[0-9]*" aria-label="Minimum price" placeholder={facets.price.min ? `₹${Math.floor(Number(facets.price.min))}` : 'Min'} value={min} onChange={(e) => setMin(e.target.value.replace(/\D/g, ''))} />
          <span aria-hidden="true">–</span>
          <input inputMode="numeric" pattern="[0-9]*" aria-label="Maximum price" placeholder={facets.price.max ? `₹${Math.ceil(Number(facets.price.max))}` : 'Max'} value={max} onChange={(e) => setMax(e.target.value.replace(/\D/g, ''))} />
          <Button type="submit" size="sm" variant="secondary">Go</Button>
        </form>
      </Group>
      {facets.brands.length > 1 && (
        <Group title="Brand">
          {facets.brands.map((b) => <button key={b.slug} type="button" className="chip" aria-pressed={has('brand', b.slug)} onClick={() => update((p) => toggleIn(p, 'brand', b.slug))}>{b.name}<small>{b.count}</small></button>)}
        </Group>
      )}
      {facets.options.map((o) => (
        <Group key={o.code} title={o.name}>
          {o.values.map((v) => <button key={v.value} type="button" className="chip" aria-pressed={has(`opt_${o.code}`, v.value)} onClick={() => update((p) => toggleIn(p, `opt_${o.code}`, v.value))}>{v.value}</button>)}
        </Group>
      ))}
      {facets.attributes.map((a) => (
        <Group key={a.code} title={a.name}>
          {a.values.map((v) => <button key={v.value} type="button" className="chip" aria-pressed={has(`attr_${a.code}`, v.value)} onClick={() => update((p) => toggleIn(p, `attr_${a.code}`, v.value))}>{v.value}<small>{v.count}</small></button>)}
        </Group>
      ))}
      {facets.ratings.some((r) => r.count > 0) && (
        <Group title="Customer rating">
          {facets.ratings.filter((r) => r.count > 0).map((r) => (
            <button key={r.value} type="button" className="chip" aria-pressed={params.get('rating') === String(r.value)}
              onClick={() => update((p) => (p.get('rating') === String(r.value) ? p.delete('rating') : p.set('rating', String(r.value))))}>{r.value}★ & up<small>{r.count}</small></button>
          ))}
        </Group>
      )}
      {facets.discounts.some((d) => d.count > 0) && (
        <Group title="Discount">
          {facets.discounts.filter((d) => d.count > 0).map((d) => (
            <button key={d.value} type="button" className="chip" aria-pressed={params.get('discount') === String(d.value)}
              onClick={() => update((p) => (p.get('discount') === String(d.value) ? p.delete('discount') : p.set('discount', String(d.value))))}>{d.value}% or more<small>{d.count}</small></button>
          ))}
        </Group>
      )}
      <Group title="Availability">
        <button type="button" className="chip" aria-pressed={params.get('in_stock') === '1'} onClick={() => update((p) => (p.get('in_stock') ? p.delete('in_stock') : p.set('in_stock', '1')))}>In stock only</button>
        <button type="button" className="chip" aria-pressed={params.get('deals') === '1'} onClick={() => update((p) => (p.get('deals') ? p.delete('deals') : p.set('deals', '1')))}>Deals</button>
      </Group>
      {facets.sellers.length > 1 && (
        <Group title="Seller">
          {facets.sellers.map((s) => (
            <button key={s.slug} type="button" className="chip" aria-pressed={params.get('seller') === s.slug}
              onClick={() => update((p) => (p.get('seller') === s.slug ? p.delete('seller') : p.set('seller', s.slug)))}>{s.name}<small>{s.count}</small></button>
          ))}
        </Group>
      )}
      {active && <Button variant="ghost" size="sm" onClick={() => update((p) => { [...p.keys()].filter((k) => !['q', 'sort'].includes(k)).forEach((k) => p.delete(k)); })}>Clear all filters</Button>}
    </div>
  );
}

function Group({ title, children }: { title: string; children: React.ReactNode }) {
  return <div className="shop-filters__group" role="group" aria-label={title}><h4>{title}</h4><div className="shop-filters__opts">{children}</div></div>;
}
