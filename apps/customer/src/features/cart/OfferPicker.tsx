import { useMutation, useQueryClient } from '@tanstack/react-query';
import { ApiError, type Cart } from '@click/api';
import { Button, Icon, useToast } from '../../components/ui';
import { api } from '../../lib/api';
import { formatMoney } from '../../lib/format';
import { cartKey } from './useCart';

/** Offers for the cart's store. Applying is validated by the server; the bill updates from its response. */
export function OfferPicker({ cart }: { cart: Cart }) {
  const qc = useQueryClient();
  const toast = useToast();
  const currency = cart.groups[0]?.store.currency ?? cart.store?.currency ?? 'INR';
  const sellers = new Map(cart.groups.map((g) => [g.store.id, g.store.name]));
  const multi = cart.groups.length > 1;
  const onSuccess = (c: Cart) => qc.setQueryData(cartKey, c);
  const onError = (e: unknown) => toast(e instanceof ApiError ? e.message : 'Couldn’t update the offer. Try again.', 'error');
  const apply = useMutation({ mutationFn: api.customer.cart.applyOffer, onSuccess: (c) => { onSuccess(c); toast('Offer applied'); }, onError });
  const remove = useMutation({ mutationFn: api.customer.cart.removeOffer, onSuccess, onError });
  const applied = cart.offer;

  if (!applied && cart.offers.length === 0) {
    return <p className="small muted">No offers from {multi ? 'these sellers' : cart.groups[0]?.store.name ?? 'this store'} right now.</p>;
  }
  return (
    <div className="offer-pick">
      {applied?.problem && (
        <p className="offer-pick__warn" role="alert"><Icon name="alert" size={16} />“{applied.title}” no longer applies: {applied.problem}</p>
      )}
      {cart.offers.map((o) => {
        const on = applied?.id === o.id && !applied.problem;
        return (
          <div key={o.id} className={`offer-pick__row ${on ? 'is-on' : ''} ${o.problem ? 'is-off' : ''}`}>
            <span className="offer-pick__icon"><Icon name="tag" size={18} /></span>
            <span className="offer-pick__text">
              <strong>{o.title}{multi && <span className="muted" style={{ fontWeight: 400 }}> · {sellers.get(o.storeId)}</span>}</strong>
              <span>{on ? `Applied · you save ${formatMoney(cart.totals.discount, currency)}` : o.problem ?? (o.saving ? `Save ${formatMoney(o.saving, currency)} on this order` : o.description)}</span>
            </span>
            {on ? (
              <Button size="sm" variant="ghost" loading={remove.isPending} onClick={() => remove.mutate()}>Remove</Button>
            ) : (
              <Button size="sm" variant="secondary" disabled={!!o.problem} loading={apply.isPending && apply.variables === o.id} onClick={() => apply.mutate(o.id)}>Apply</Button>
            )}
          </div>
        );
      })}
    </div>
  );
}
