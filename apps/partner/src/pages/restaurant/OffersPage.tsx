import { useState } from 'react';
import { Button, Icon, Skeleton, useToast } from '@click/ui';
import type { OfferInput, RestaurantOffer } from '@click/api';
import { AppShell } from '../../components/AppShell';
import { Empty } from '../../features/home/sections';
import { useCreateOffer, useOfferPause, useOffers } from '../../features/restaurant/queries';
import { apiMessage, fieldErrors } from '../../lib/format';
import { formatMoney } from '../../lib/money';

const TONE: Record<string, string> = { live: 'success', pending: 'info', scheduled: 'info', paused: 'muted', ended: 'muted', rejected: 'urgent', inactive: 'muted' };

function terms(o: RestaurantOffer) {
  const value = o.discountType === 'percent' ? `${Number(o.discountValue)}% off${o.maxDiscount ? ` up to ${formatMoney(o.maxDiscount)}` : ''}`
    : o.discountType === 'flat' ? `${formatMoney(o.discountValue)} off` : o.discountType === 'free_delivery' ? 'Free delivery' : 'Display only';
  const min = Number(o.minOrderAmount) > 0 ? ` on orders over ${formatMoney(o.minOrderAmount)}` : '';
  const end = o.endsAt ? ` · until ${new Date(o.endsAt).toLocaleDateString('en-IN', { day: 'numeric', month: 'short' })}` : '';
  return `${value}${min}${end}`;
}

const inAWeek = () => {
  const d = new Date(Date.now() + 7 * 86_400_000);
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
};

function NewOffer({ onDone }: { onDone: () => void }) {
  const create = useCreateOffer();
  const toast = useToast();
  const [f, setF] = useState<OfferInput & { endDate: string }>({ title: '', discountType: 'percent', discountValue: '20', maxDiscount: '100',
    minOrderAmount: '0', endsAt: '', endDate: inAWeek(), description: '' });
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [error, setError] = useState<string | null>(null);
  const set = (p: Partial<typeof f>) => setF((x) => ({ ...x, ...p }));

  return (
    <form className="mod editor" noValidate onSubmit={(e) => {
      e.preventDefault();
      setErrors({}); setError(null);
      const { endDate, ...body } = f;
      create.mutate({ ...body, endsAt: endDate ? `${endDate}T23:59:00` : '' }, {
        onSuccess: () => { toast('Offer sent to Click for review'); onDone(); },
        onError: (err) => { setErrors(fieldErrors(err)); setError(apiMessage(err)); },
      });
    }}>
      <h2 className="mod__title">New offer</h2>
      <label className="field">
        <span className="field__label">Title customers see</span>
        <input className="field__input" placeholder="e.g. Weekday lunch 20% off" value={f.title} maxLength={80} onChange={(e) => set({ title: e.target.value })} />
        {errors.title && <span className="field__error">{errors.title}</span>}
      </label>
      <fieldset className="field">
        <legend className="field__label">Discount</legend>
        <div className="seg seg--wrap">
          {([['percent', 'Percent off'], ['flat', 'Amount off'], ['free_delivery', 'Free delivery']] as const).map(([k, l]) => (
            <button key={k} type="button" className={`seg__btn ${f.discountType === k ? 'is-active' : ''}`} aria-pressed={f.discountType === k}
              onClick={() => set({ discountType: k })}>{l}</button>
          ))}
        </div>
      </fieldset>
      <div className="editor__grid">
        {f.discountType !== 'free_delivery' && (
          <label className="field">
            <span className="field__label">{f.discountType === 'percent' ? 'Percent (5–60)' : 'Amount off (₹)'}</span>
            <input className="field__input" inputMode="decimal" value={f.discountValue} onChange={(e) => set({ discountValue: e.target.value })} />
            {errors.discountValue && <span className="field__error">{errors.discountValue}</span>}
          </label>
        )}
        {f.discountType === 'percent' && (
          <label className="field">
            <span className="field__label">Maximum discount (₹)</span>
            <input className="field__input" inputMode="decimal" value={f.maxDiscount} onChange={(e) => set({ maxDiscount: e.target.value })} />
            {errors.maxDiscount && <span className="field__error">{errors.maxDiscount}</span>}
          </label>
        )}
        <label className="field">
          <span className="field__label">Minimum order (₹)</span>
          <input className="field__input" inputMode="decimal" value={f.minOrderAmount} onChange={(e) => set({ minOrderAmount: e.target.value })} />
          {errors.minOrderAmount && <span className="field__error">{errors.minOrderAmount}</span>}
        </label>
        <label className="field">
          <span className="field__label">Ends on</span>
          <input className="field__input" type="date" value={f.endDate} onChange={(e) => set({ endDate: e.target.value })} />
          {errors.endsAt && <span className="field__error">{errors.endsAt}</span>}
        </label>
      </div>
      <p className="small muted">Click checks every offer before customers see it, and calculates the discount itself at checkout.</p>
      {error && <p className="field__error" role="alert">{error}</p>}
      <div className="dialog__actions">
        <button type="button" className="btn btn--ghost" onClick={onDone}>Cancel</button>
        <Button type="submit" loading={create.isPending}>Send for review</Button>
      </div>
    </form>
  );
}

/** Restaurant offers: created here, reviewed by Click, then shown to customers; paused or resumed in one tap. */
export function OffersPage() {
  const offers = useOffers();
  const pause = useOfferPause();
  const toast = useToast();
  const [adding, setAdding] = useState(false);
  const list = offers.data?.offers ?? [];

  return (
    <AppShell>
      <div className="page">
        <div className="page__head spread">
          <div><h1>Offers</h1><p className="muted small">Offers bring customers to your menu on Click.</p></div>
          {!adding && <Button size="sm" onClick={() => setAdding(true)}><Icon name="plus" size={16} /> New offer</Button>}
        </div>
        {adding && <NewOffer onDone={() => setAdding(false)} />}
        {offers.isPending ? <Skeleton height={120} radius={20} /> : offers.isError ? (
          <div className="dash__error" role="alert"><h2>Couldn’t load offers</h2><p className="muted">{apiMessage(offers.error)}</p>
            <Button onClick={() => void offers.refetch()}>Try again</Button></div>
        ) : list.length === 0 ? (
          <Empty icon="tag" title="No offers yet." message="Create one, such as 20% off weekday lunches. Click reviews it before customers see it." />
        ) : (
          <ul className="work-list">
            {list.map((o) => (
              <li key={o.id} className={`work work--${TONE[o.state] ?? 'info'}`}>
                <div className="work__head">
                  <span className="work__icon" aria-hidden="true"><Icon name="tag" size={20} /></span>
                  <div className="work__title"><h3>{o.title}</h3><p className="muted small">{terms(o)}</p></div>
                  <div className="work__meta"><span className={`tag tag--${TONE[o.state] ?? 'info'}`}>{o.stateLabel}</span></div>
                </div>
                {o.reviewNote && <p className="small muted">Click: {o.reviewNote}</p>}
                {(o.state === 'live' || o.state === 'paused' || o.state === 'scheduled') && (
                  <div className="work__actions">
                    <Button size="sm" variant="outline" loading={pause.isPending && pause.variables?.id === o.id}
                      onClick={() => pause.mutate({ id: o.id, paused: o.state !== 'paused' }, {
                        onSuccess: (r) => toast(r.state === 'paused' ? 'Offer paused' : 'Offer resumed'), onError: (e) => toast(apiMessage(e), 'error'),
                      })}>{o.state === 'paused' ? 'Resume' : 'Pause'}</Button>
                  </div>
                )}
              </li>
            ))}
          </ul>
        )}
      </div>
    </AppShell>
  );
}
