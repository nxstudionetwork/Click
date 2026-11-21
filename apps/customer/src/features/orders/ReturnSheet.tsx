import { useEffect, useState } from 'react';
import { useMutation } from '@tanstack/react-query';
import { ApiError, type OrderDetail, type ReturnKind, type ReturnReason } from '@click/api';
import { Button, Icon, Sheet, TextArea, useToast } from '../../components/ui';
import { api } from '../../lib/api';

const REASONS: { id: ReturnReason; label: string }[] = [
  { id: 'damaged', label: 'Arrived damaged' }, { id: 'wrong_item', label: 'Wrong item' }, { id: 'not_as_described', label: 'Not as described' },
  { id: 'size_fit', label: 'Size or fit issue' }, { id: 'defective', label: 'Doesn’t work' }, { id: 'changed_mind', label: 'No longer needed' },
];

/** Request a return or replacement for a delivered Shopping item. The seller/Click. reviews it; nothing is refunded automatically. */
export function ReturnSheet({ order, itemId, onClose, onDone }: { order: OrderDetail; itemId: string | null; onClose: () => void; onDone: (o: OrderDetail) => void }) {
  const item = order.items.find((i) => i.id === itemId);
  const [kind, setKind] = useState<ReturnKind>('return');
  const [reason, setReason] = useState<ReturnReason | null>(null);
  const [qty, setQty] = useState(1);
  const [details, setDetails] = useState('');
  const toast = useToast();
  useEffect(() => { if (item) { setKind(item.replacementOnly ? 'replacement' : 'return'); setReason(null); setQty(1); setDetails(''); } }, [item]);
  const send = useMutation({
    mutationFn: () => api.customer.orders.requestReturn(order.id, item!.id, { kind, reason: reason!, details, quantity: qty }),
    onSuccess: (o) => { onDone(o); toast('Request sent. We’ll update you.'); onClose(); },
    onError: (e) => toast(e instanceof ApiError ? e.message : 'Couldn’t send the request.', 'error'),
  });
  return (
    <Sheet open={!!item} onClose={onClose} label="Return or replace">
      {item && (
        <form className="stack" onSubmit={(e) => { e.preventDefault(); if (reason) send.mutate(); }}>
          <div className="spread"><h2>Return or replace</h2><button type="button" className="icon-btn" aria-label="Close" onClick={onClose}><Icon name="close" /></button></div>
          <p className="small">{item.productName}{item.optionsSummary ? ` · ${item.optionsSummary}` : ''}</p>
          <div className="chips" role="radiogroup" aria-label="What would you like?">
            {!item.replacementOnly && <button type="button" role="radio" aria-checked={kind === 'return'} className="chip" aria-pressed={kind === 'return'} onClick={() => setKind('return')}>Return for refund</button>}
            <button type="button" role="radio" aria-checked={kind === 'replacement'} className="chip" aria-pressed={kind === 'replacement'} onClick={() => setKind('replacement')}>Replacement</button>
          </div>
          {item.replacementOnly && <p className="small muted">This item can be replaced, not refunded.</p>}
          <fieldset className="stack" style={{ gap: 6, border: 0, padding: 0 }}>
            <legend className="small" style={{ fontWeight: 600, marginBottom: 6 }}>Reason</legend>
            {REASONS.map((r) => (
              <label key={r.id} className="option"><input type="radio" name="reason" checked={reason === r.id} onChange={() => setReason(r.id)} /><span>{r.label}</span></label>
            ))}
          </fieldset>
          {item.quantity > 1 && (
            <label className="small">How many? <select className="shop-select" value={qty} onChange={(e) => setQty(Number(e.target.value))}>
              {Array.from({ length: item.quantity }, (_, i) => <option key={i + 1} value={i + 1}>{i + 1}</option>)}</select></label>
          )}
          <TextArea label="Details (optional)" maxLength={500} value={details} onChange={(e) => setDetails(e.target.value)} />
          <p className="small muted">{kind === 'return' ? 'Once approved, the amount you paid for it is refunded to your Click. Wallet.' : 'Once approved, the seller sends a replacement.'}</p>
          <Button type="submit" block disabled={!reason} loading={send.isPending}>Send request</Button>
        </form>
      )}
    </Sheet>
  );
}
