import { useState } from 'react';
import { Button, Icon, Skeleton, useToast } from '@click/ui';
import type { MenuItem, PartnerMenuCategory } from '@click/api';
import { AppShell } from '../../components/AppShell';
import { ConfirmDialog } from '../../components/ConfirmDialog';
import { Empty } from '../../features/home/sections';
import { ItemEditor } from '../../features/restaurant/ItemEditor';
import {
  useCreateCategory, useDeleteCategory, useMenu, useReorderCategories, useReorderItems, useSaveItem, useUpdateCategory,
} from '../../features/restaurant/queries';
import { apiMessage } from '../../lib/format';
import { formatMoney } from '../../lib/money';

const DIET_LABEL: Record<string, string> = { veg: 'Veg', non_veg: 'Non-veg', vegan: 'Vegan' };

function move<T>(list: T[], from: number, to: number): T[] {
  const next = [...list];
  const [x] = next.splice(from, 1);
  next.splice(to, 0, x!);
  return next;
}

/** One menu row: the quick availability switch is the most common change, so it is one tap. */
function ItemRow({ item, index, count, onEdit, onMove }: {
  item: MenuItem; index: number; count: number; onEdit: () => void; onMove: (to: number) => void;
}) {
  const save = useSaveItem();
  const toast = useToast();
  const toggle = () => save.mutate({ id: item.id, body: { isAvailable: !item.isAvailable } }, {
    onSuccess: (s) => toast(`${s.name} is ${s.isAvailable ? 'available' : 'marked unavailable'}`),
    onError: (e) => toast(apiMessage(e), 'error'),
  });
  const groups = item.optionGroups.map((g) => g.name).join(', ');
  return (
    <li className={`mitem ${item.isAvailable ? '' : 'mitem--off'}`}>
      <div className="mitem__main">
        {item.dietary !== 'unspecified' && (
          <span className={`diet diet--${item.dietary}`} role="img" aria-label={DIET_LABEL[item.dietary]} title={DIET_LABEL[item.dietary]} />
        )}
        <div className="mitem__text">
          <p className="mitem__name">{item.name}{item.isFeatured && <span className="tag tag--info">Featured</span>}</p>
          <p className="small muted">
            {formatMoney(item.price, true)}{groups && ` · ${groups}`}{item.unitsSold ? ` · ${item.unitsSold} sold` : ''}
          </p>
        </div>
      </div>
      <div className="mitem__actions">
        <label className="switch" title={item.isAvailable ? 'Available' : 'Unavailable'}>
          <input type="checkbox" role="switch" checked={item.isAvailable} disabled={save.isPending} onChange={toggle}
            aria-label={`${item.name} available to order`} />
          <span className="switch__track" aria-hidden="true" />
          <span className="switch__text small">{item.isAvailable ? 'In stock' : 'Unavailable'}</span>
        </label>
        <button type="button" className="icon-btn icon-btn--sm" aria-label={`Move ${item.name} up`} disabled={index === 0} onClick={() => onMove(index - 1)}>
          <Icon name="chevron" size={14} className="rot-180" />
        </button>
        <button type="button" className="icon-btn icon-btn--sm" aria-label={`Move ${item.name} down`} disabled={index === count - 1} onClick={() => onMove(index + 1)}>
          <Icon name="chevron" size={14} />
        </button>
        <button type="button" className="icon-btn icon-btn--sm" aria-label={`Edit ${item.name}`} onClick={onEdit}><Icon name="edit" size={16} /></button>
      </div>
    </li>
  );
}

function CategoryBlock({ cat, index, count, onEdit, onAdd, onMoveCat }: {
  cat: PartnerMenuCategory; index: number; count: number; onEdit: (i: MenuItem) => void; onAdd: () => void; onMoveCat: (to: number) => void;
}) {
  const update = useUpdateCategory();
  const remove = useDeleteCategory();
  const reorder = useReorderItems();
  const toast = useToast();
  const [renaming, setRenaming] = useState(false);
  const [confirmDelete, setConfirmDelete] = useState(false);
  const fail = (e: unknown) => toast(apiMessage(e), 'error');
  return (
    <section className={`mod mcat ${cat.isActive ? '' : 'mcat--hidden'}`} aria-labelledby={`cat-${cat.id}`}>
      <div className="mod__head">
        <h2 id={`cat-${cat.id}`} className="mod__title">
          {cat.name} <span className="small muted">({cat.items.length})</span>
          {!cat.isActive && <span className="tag tag--muted">Hidden from customers</span>}
        </h2>
        <div className="mcat__actions">
          <button type="button" className="icon-btn icon-btn--sm" aria-label={`Move ${cat.name} up`} disabled={index === 0} onClick={() => onMoveCat(index - 1)}>
            <Icon name="chevron" size={14} className="rot-180" />
          </button>
          <button type="button" className="icon-btn icon-btn--sm" aria-label={`Move ${cat.name} down`} disabled={index === count - 1} onClick={() => onMoveCat(index + 1)}>
            <Icon name="chevron" size={14} />
          </button>
          <button type="button" className="text-btn small" onClick={() => setRenaming(true)}>Rename</button>
          <button type="button" className="text-btn small" disabled={update.isPending}
            onClick={() => update.mutate({ id: cat.id, body: { isActive: !cat.isActive } }, {
              onSuccess: () => toast(cat.isActive ? `${cat.name} hidden from customers` : `${cat.name} visible to customers`), onError: fail,
            })}>{cat.isActive ? 'Hide' : 'Show'}</button>
          {cat.items.length === 0 && <button type="button" className="text-btn small tone-danger" onClick={() => setConfirmDelete(true)}>Delete</button>}
        </div>
      </div>
      {cat.items.length === 0 ? <p className="small muted">No items yet.</p> : (
        <ul className="mlist">
          {cat.items.map((it, i) => (
            <ItemRow key={it.id} item={it} index={i} count={cat.items.length} onEdit={() => onEdit(it)}
              onMove={(to) => reorder.mutate({ categoryId: cat.id, ids: move(cat.items, i, to).map((x) => x.id) }, { onError: fail })} />
          ))}
        </ul>
      )}
      <button type="button" className="text-btn small mcat__add" onClick={onAdd}><Icon name="plus" size={14} /> Add item to {cat.name}</button>

      <ConfirmDialog open={renaming} title={`Rename ${cat.name}`} message="Customers see the new name on your menu." confirmLabel="Save" needsReason reasonLabel="New name"
        reasonError="Enter a name (at least 3 characters)."
        pending={update.isPending} error={null}
        onConfirm={(name) => update.mutate({ id: cat.id, body: { name: name ?? '' } }, { onSuccess: () => setRenaming(false), onError: fail })}
        onClose={() => setRenaming(false)} />
      <ConfirmDialog open={confirmDelete} title={`Delete ${cat.name}?`} message="This empty category will be removed from your menu." confirmLabel="Delete"
        tone="danger" pending={remove.isPending} error={null}
        onConfirm={() => remove.mutate(cat.id, { onSuccess: () => setConfirmDelete(false), onError: fail })} onClose={() => setConfirmDelete(false)} />
    </section>
  );
}

/** Menu management: categories and items customers order from. Every change is saved on Click and seen by customers. */
export function MenuPage() {
  const menu = useMenu();
  const create = useCreateCategory();
  const reorder = useReorderCategories();
  const toast = useToast();
  const [name, setName] = useState('');
  const [nameError, setNameError] = useState<string | null>(null);
  const [editing, setEditing] = useState<{ item: MenuItem | null; category?: string } | null>(null);
  const [filter, setFilter] = useState('');
  const data = menu.data;
  const term = filter.trim().toLowerCase();
  const cats = (data?.categories ?? []).map((c) => (term ? { ...c, items: c.items.filter((i) => i.name.toLowerCase().includes(term)) } : c));

  return (
    <AppShell>
      <div className="page">
        <div className="page__head spread">
          <div>
            <h1>Menu</h1>
            {data && (
              <p className="muted small">
                {data.counts.items} items · {data.counts.available} available{data.counts.unavailable ? ` · ${data.counts.unavailable} unavailable` : ''}
              </p>
            )}
          </div>
          <Button size="sm" disabled={!data?.categories.length} onClick={() => setEditing({ item: null })}><Icon name="plus" size={16} /> Add item</Button>
        </div>

        {menu.isPending ? <><Skeleton height={64} radius={18} /><Skeleton height={240} radius={22} /></> : menu.isError ? (
          <div className="dash__error" role="alert">
            <h2>Couldn’t load your menu</h2><p className="muted">{apiMessage(menu.error)}</p>
            <Button onClick={() => void menu.refetch()}>Try again</Button>
          </div>
        ) : (
          <>
            <div className="search-row">
              <label className="visually-hidden" htmlFor="mf">Find an item</label>
              <input id="mf" className="field__input" placeholder="Find an item" value={filter} onChange={(e) => setFilter(e.target.value)} />
            </div>
            {data!.categories.length === 0 && (
              <Empty icon="food" title="Start your menu" message="Add a category such as Starters, Main Course or Beverages, then add items to it." />
            )}
            {cats.map((c, i) => (
              <CategoryBlock key={c.id} cat={c} index={i} count={cats.length} onEdit={(item) => setEditing({ item })}
                onAdd={() => setEditing({ item: null, category: c.id })}
                onMoveCat={(to) => reorder.mutate(move(data!.categories, i, to).map((x) => x.id), { onError: (e) => toast(apiMessage(e), 'error') })} />
            ))}
            <form className="mod add-cat" onSubmit={(e) => {
              e.preventDefault();
              setNameError(null);
              create.mutate(name, { onSuccess: (c) => { setName(''); toast(`${c.name} added`); }, onError: (err) => setNameError(apiMessage(err)) });
            }}>
              <label className="field">
                <span className="field__label">New category</span>
                <input className="field__input" placeholder="e.g. Biryani" value={name} maxLength={80} onChange={(e) => setName(e.target.value)} />
                {nameError && <span className="field__error" role="alert">{nameError}</span>}
              </label>
              <Button type="submit" variant="outline" size="sm" loading={create.isPending} disabled={name.trim().length < 2}>Add category</Button>
            </form>
          </>
        )}
      </div>
      <ItemEditor open={!!editing} item={editing?.item ?? null} categories={data?.categories ?? []} defaultCategory={editing?.category}
        onClose={() => setEditing(null)} />
    </AppShell>
  );
}
