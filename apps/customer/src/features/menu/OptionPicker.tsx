import { useMemo, useState } from 'react';
import type { Product } from '@click/api';
import { formatMoney } from '../../lib/format';

/** True when a product has choices the customer must make before it can go in the cart. */
export const needsChoices = (p: Pick<Product, 'optionGroups'>) => (p.optionGroups ?? []).some((g) => g.minSelect > 0);
export const isCustomisable = (p: Pick<Product, 'optionGroups'>) => (p.optionGroups ?? []).length > 0;

/**
 * Selection state for a product's customisation groups. Required single-choice groups start on their first
 * available option. The price shown is a preview; the server prices the cart and order itself.
 */
export function useOptionSelection(product: Product) {
  const groups = product.optionGroups ?? [];
  const [chosen, setChosen] = useState<Record<string, string[]>>(() =>
    Object.fromEntries(groups.map((g) => {
      const first = g.options.find((o) => o.isAvailable);
      return [g.id, g.minSelect === 1 && g.maxSelect === 1 && first ? [first.id] : []];
    })),
  );
  const toggle = (groupId: string, optionId: string) => setChosen((c) => {
    const g = groups.find((x) => x.id === groupId)!;
    const cur = c[groupId] ?? [];
    if (g.maxSelect === 1) return { ...c, [groupId]: cur[0] === optionId && g.minSelect === 0 ? [] : [optionId] };
    if (cur.includes(optionId)) return { ...c, [groupId]: cur.filter((x) => x !== optionId) };
    return cur.length >= g.maxSelect ? c : { ...c, [groupId]: [...cur, optionId] };
  });
  const missing = groups.filter((g) => (chosen[g.id]?.length ?? 0) < g.minSelect).map((g) => g.name);
  const optionIds = useMemo(() => Object.values(chosen).flat(), [chosen]);
  const extra = groups.flatMap((g) => g.options).filter((o) => optionIds.includes(o.id)).reduce((s, o) => s + Number(o.priceDelta), 0);
  return { chosen, toggle, missing, optionIds, unitPrice: Number(product.price) + extra };
}

export function OptionPicker({ product, currency, selection }: {
  product: Product; currency: string; selection: ReturnType<typeof useOptionSelection>;
}) {
  if (!isCustomisable(product)) return null;
  return (
    <div className="opts">
      {product.optionGroups.map((g) => {
        const single = g.maxSelect === 1;
        const rule = g.minSelect > 0 ? (single ? 'Required · choose 1' : `Required · choose ${g.minSelect}–${g.maxSelect}`) : single ? 'Optional' : `Optional · up to ${g.maxSelect}`;
        const picked = selection.chosen[g.id] ?? [];
        return (
          <fieldset key={g.id} className="opts__group">
            <legend><strong>{g.name}</strong><span className={g.minSelect > 0 ? 'opts__req' : ''}>{rule}</span></legend>
            {g.options.map((o) => {
              const on = picked.includes(o.id);
              const full = !single && !on && picked.length >= g.maxSelect;
              return (
                <label key={o.id} className={`opts__opt ${on ? 'is-on' : ''} ${!o.isAvailable || full ? 'is-off' : ''}`}>
                  <input
                    type={single ? 'radio' : 'checkbox'} name={`opt-${g.id}`} checked={on}
                    disabled={!o.isAvailable || full} onChange={() => selection.toggle(g.id, o.id)}
                  />
                  <span className="opts__name">{o.name}{!o.isAvailable && <span className="muted"> · unavailable</span>}</span>
                  <span className="opts__price">{Number(o.priceDelta) ? `+${formatMoney(o.priceDelta, currency)}` : ''}</span>
                </label>
              );
            })}
          </fieldset>
        );
      })}
    </div>
  );
}
