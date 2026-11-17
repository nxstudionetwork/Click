import { useEffect, useRef, useState } from 'react';
import { Button, Icon, useToast } from '@click/ui';
import type { Dietary, MenuItem, MenuItemInput, MenuOptionGroup, PartnerMenuCategory } from '@click/api';
import { apiMessage, fieldErrors } from '../../lib/format';
import { useSaveItem } from './queries';

const DIETARY: { key: Dietary; label: string }[] = [
  { key: 'veg', label: 'Veg' }, { key: 'non_veg', label: 'Non-veg' }, { key: 'vegan', label: 'Vegan' }, { key: 'unspecified', label: 'Not specified' },
];

const blankGroup = (): MenuOptionGroup => ({ name: '', minSelect: 0, maxSelect: 1, options: [{ name: '', priceDelta: '0' }] });

/**
 * Add or edit a menu item. Prices, names and option groups are validated again by the server; nothing is shown as
 * saved until Click confirms it. Option groups cover both variants (e.g. Size, choose 1) and add-ons (choose up to n).
 */
export function ItemEditor({ open, item, categories, defaultCategory, onClose }: {
  open: boolean; item: MenuItem | null; categories: PartnerMenuCategory[]; defaultCategory?: string; onClose: () => void;
}) {
  const ref = useRef<HTMLDialogElement>(null);
  const save = useSaveItem();
  const toast = useToast();
  const [form, setForm] = useState<MenuItemInput>({});
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const d = ref.current;
    if (open) {
      setErrors({}); setError(null);
      setForm(item ? {
        name: item.name, categoryId: item.categoryId ?? undefined, price: item.price, description: item.description, imageUrl: item.imageUrl,
        dietary: item.dietary, isAvailable: item.isAvailable, isFeatured: item.isFeatured,
        optionGroups: item.optionGroups.map((g) => ({ ...g, options: g.options.map((o) => ({ ...o })) })),
      } : { name: '', categoryId: defaultCategory ?? categories[0]?.id, price: '', description: '', imageUrl: '', dietary: 'veg',
        isAvailable: true, isFeatured: false, optionGroups: [] });
      if (d && !d.open) d.showModal?.();
    } else if (d?.open) d.close();
  }, [open, item, categories, defaultCategory]);

  const set = (patch: Partial<MenuItemInput>) => setForm((f) => ({ ...f, ...patch }));
  const groups = form.optionGroups ?? [];
  const setGroup = (gi: number, patch: Partial<MenuOptionGroup>) =>
    set({ optionGroups: groups.map((g, i) => (i === gi ? { ...g, ...patch } : g)) });

  function submit(e: React.FormEvent) {
    e.preventDefault();
    setError(null); setErrors({});
    save.mutate({ id: item?.id, body: form }, {
      onSuccess: (saved) => { toast(item ? `${saved.name} saved` : `${saved.name} added to your menu`); onClose(); },
      onError: (err) => { setErrors(fieldErrors(err)); setError(apiMessage(err)); },
    });
  }

  return (
    <dialog ref={ref} className="dialog dialog--wide" aria-labelledby="item-t" onCancel={(e) => { e.preventDefault(); onClose(); }}>
      {open && (
        <form className="dialog__body editor" onSubmit={submit} noValidate>
          <h2 id="item-t">{item ? `Edit ${item.name}` : 'Add item'}</h2>
          <div className="editor__grid">
            <label className="field">
              <span className="field__label">Item name</span>
              <input className="field__input" value={form.name ?? ''} onChange={(e) => set({ name: e.target.value })} maxLength={150} required
                aria-invalid={!!errors.name} />
              {errors.name && <span className="field__error">{errors.name}</span>}
            </label>
            <label className="field">
              <span className="field__label">Price (₹)</span>
              <input className="field__input" inputMode="decimal" value={form.price ?? ''} onChange={(e) => set({ price: e.target.value })} required
                aria-invalid={!!errors.price} />
              {errors.price && <span className="field__error">{errors.price}</span>}
            </label>
            <label className="field">
              <span className="field__label">Category</span>
              <select className="field__input" value={form.categoryId ?? ''} onChange={(e) => set({ categoryId: e.target.value })}
                aria-invalid={!!errors.categoryId}>
                {categories.map((c) => <option key={c.id} value={c.id}>{c.name}{c.isActive ? '' : ' (hidden)'}</option>)}
              </select>
              {errors.categoryId && <span className="field__error">{errors.categoryId}</span>}
            </label>
            <fieldset className="field">
              <legend className="field__label">Food type</legend>
              <div className="seg seg--wrap">
                {DIETARY.map((d) => (
                  <button key={d.key} type="button" className={`seg__btn ${form.dietary === d.key ? 'is-active' : ''}`} aria-pressed={form.dietary === d.key}
                    onClick={() => set({ dietary: d.key })}>{d.label}</button>
                ))}
              </div>
            </fieldset>
          </div>
          <label className="field">
            <span className="field__label">Description <span className="muted">(optional)</span></span>
            <textarea className="field__input" rows={2} maxLength={300} value={form.description ?? ''} onChange={(e) => set({ description: e.target.value })} />
            {errors.description && <span className="field__error">{errors.description}</span>}
          </label>
          <label className="field">
            <span className="field__label">Photo link <span className="muted">(optional, https://)</span></span>
            <input className="field__input" type="url" value={form.imageUrl ?? ''} onChange={(e) => set({ imageUrl: e.target.value })} />
            {errors.imageUrl && <span className="field__error">{errors.imageUrl}</span>}
          </label>
          <div className="editor__toggles">
            <label className="check"><input type="checkbox" checked={!!form.isAvailable} onChange={(e) => set({ isAvailable: e.target.checked })} /> Available to order</label>
            <label className="check"><input type="checkbox" checked={!!form.isFeatured} onChange={(e) => set({ isFeatured: e.target.checked })} /> Featured</label>
          </div>

          <fieldset className="editor__groups">
            <legend className="section-label">Sizes and add-ons</legend>
            {groups.length === 0 && <p className="small muted">E.g. “Size” (choose 1: Half, Full) or “Add-ons” (choose up to 3).</p>}
            {groups.map((g, gi) => (
              <div key={gi} className="group">
                <div className="group__head">
                  <input className="field__input" placeholder="Group name, e.g. Size" aria-label={`Option group ${gi + 1} name`} value={g.name}
                    onChange={(e) => setGroup(gi, { name: e.target.value })} />
                  <label className="check small"><input type="checkbox" checked={g.minSelect > 0}
                    onChange={(e) => setGroup(gi, { minSelect: e.target.checked ? 1 : 0 })} /> Required</label>
                  <label className="small group__max">Up to
                    <input type="number" min={1} max={Math.max(g.options.length, 1)} className="field__input ops__num" value={g.maxSelect}
                      onChange={(e) => setGroup(gi, { maxSelect: Number(e.target.value) })} />
                  </label>
                  <button type="button" className="icon-btn" aria-label={`Remove option group ${g.name || gi + 1}`}
                    onClick={() => set({ optionGroups: groups.filter((_, i) => i !== gi) })}><Icon name="close" size={16} /></button>
                </div>
                {g.options.map((o, oi) => (
                  <div key={oi} className="group__opt">
                    <input className="field__input" placeholder="Choice, e.g. Full" aria-label={`Choice ${oi + 1} name`} value={o.name}
                      onChange={(e) => setGroup(gi, { options: g.options.map((x, i) => (i === oi ? { ...x, name: e.target.value } : x)) })} />
                    <span className="small muted">+₹</span>
                    <input className="field__input ops__num" inputMode="decimal" aria-label={`Choice ${oi + 1} extra price`} value={o.priceDelta}
                      onChange={(e) => setGroup(gi, { options: g.options.map((x, i) => (i === oi ? { ...x, priceDelta: e.target.value } : x)) })} />
                    <button type="button" className="icon-btn" aria-label={`Remove choice ${o.name || oi + 1}`} disabled={g.options.length <= 1}
                      onClick={() => setGroup(gi, { options: g.options.filter((_, i) => i !== oi) })}><Icon name="close" size={14} /></button>
                  </div>
                ))}
                <button type="button" className="text-btn small" onClick={() => setGroup(gi, { options: [...g.options, { name: '', priceDelta: '0' }] })}>
                  <Icon name="plus" size={14} /> Add choice
                </button>
              </div>
            ))}
            {groups.length < 6 && (
              <button type="button" className="btn btn--outline btn--sm" onClick={() => set({ optionGroups: [...groups, blankGroup()] })}>
                <Icon name="plus" size={16} /> Add option group
              </button>
            )}
            {Object.entries(errors).filter(([k]) => k.startsWith('optionGroups') || k.startsWith('option_groups') || k === 'minSelect' || k === 'maxSelect').map(([k, v]) => (
              <p key={k} className="field__error">{v}</p>
            ))}
          </fieldset>

          {error && <p className="field__error" role="alert">{error}</p>}
          <div className="dialog__actions">
            <button type="button" className="btn btn--ghost" onClick={onClose}>Cancel</button>
            <Button type="submit" loading={save.isPending}>{item ? 'Save changes' : 'Add to menu'}</Button>
          </div>
        </form>
      )}
    </dialog>
  );
}
