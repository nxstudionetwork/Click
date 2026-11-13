import { useEffect } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { ApiError, type PaymentIntent } from '@click/api';
import { Button, Icon } from '../../components/ui';
import { useAuth } from '../../auth/AuthProvider';
import { api } from '../../lib/api';
import { formatMoney } from '../../lib/format';

/** Online methods a checkout may offer: only those the backend says a connected provider supports right now. */
export function useOnlineMethods() {
  const { status } = useAuth();
  const q = useQuery({ queryKey: ['payments', 'overview'], queryFn: api.money.payments.overview, enabled: status === 'authenticated', staleTime: 60_000 });
  return q.data?.onlineMethods ?? null;
}

export function OnlineMethodOptions({ value, onChange }: { value: string; onChange: (m: string) => void }) {
  const online = useOnlineMethods();
  if (!online) return null;
  if (!online.available) return <p className="small muted"><Icon name="shield" size={14} /> {online.note}</p>;
  return (
    <>
      {online.methods.map((m) => (
        <label key={m.code} className="option">
          <input type="radio" name="payment" checked={value === m.code} onChange={() => onChange(m.code)} />
          <div><strong>{m.label}</strong><div className="muted small">Pay on the payment provider’s page. Your order is placed once the payment is confirmed.</div></div>
        </label>
      ))}
      <p className="small muted"><Icon name="shield" size={14} /> Click. never sees or stores card numbers, CVVs or UPI PINs.</p>
    </>
  );
}

/** The "complete your payment" step for orders waiting on an online payment. It reads the payment state from the
 *  server (polling while pending) and only reports success once the provider's confirmation has been verified. */
export function PayOnline({ intent, onSettled }: { intent: PaymentIntent; onSettled?: (status: PaymentIntent['status']) => void }) {
  const qc = useQueryClient();
  const live = useQuery({
    queryKey: ['payments', 'intent', intent.reference], queryFn: () => api.money.payments.intent(intent.reference),
    initialData: intent, refetchInterval: (q) => (q.state.data?.status === 'pending' ? 4000 : false),
  });
  const decide = useMutation({
    mutationFn: (outcome: 'succeeded' | 'failed') => api.money.payments.sandbox(intent.reference, outcome),
    onSuccess: (d) => qc.setQueryData(['payments', 'intent', intent.reference], d),
  });
  const p = live.data;
  useEffect(() => {
    if (p.status !== 'pending') {
      qc.invalidateQueries({ queryKey: ['customer', 'orders'] });
      qc.invalidateQueries({ queryKey: ['customer', 'checkouts'] });
      onSettled?.(p.status);
    }
  }, [p.status, qc, onSettled]);

  if (p.status === 'succeeded') {
    return <div className="pay-online pay-online--ok" role="status"><Icon name="check" size={22} /><div><strong>Payment received</strong><p className="small">{formatMoney(p.amount)} by {p.methodLabel}. Your order is placed.</p></div></div>;
  }
  if (p.status === 'failed' || p.status === 'cancelled') {
    return <div className="pay-online pay-online--bad" role="alert"><Icon name="alert" size={22} /><div><strong>{p.status === 'failed' ? 'Payment didn’t go through' : 'Payment wasn’t completed'}</strong>
      <p className="small">The order wasn’t placed and nothing is due. If money left your account, your bank or payment app returns it.</p></div></div>;
  }
  return (
    <section className="pay-online" aria-labelledby="pay-online-h">
      <div className="pay-online__head"><Icon name="card" size={22} /><div><strong id="pay-online-h">Complete your payment</strong>
        <p className="small">{formatMoney(p.amount)} by {p.methodLabel} · reference <span className="mono">{p.reference}</span></p></div></div>
      {p.client?.testMode ? (
        <>
          <p className="small pay-online__test"><Icon name="alert" size={14} /> {p.client.instructions}</p>
          {decide.isError && <p className="small" role="alert">{decide.error instanceof ApiError ? decide.error.message : 'The payment provider didn’t respond. Try again.'}</p>}
          <div className="row" style={{ gap: 8, flexWrap: 'wrap' }}>
            <Button variant="secondary" loading={decide.isPending && decide.variables === 'failed'} onClick={() => decide.mutate('failed')}>Decline</Button>
            <Button loading={decide.isPending && decide.variables === 'succeeded'} onClick={() => decide.mutate('succeeded')}>Approve test payment</Button>
          </div>
        </>
      ) : <p className="small">Finish the payment in the provider’s window. This updates by itself once the provider confirms it.</p>}
      <p className="small muted">Not paid by {new Date(p.expiresAt).toLocaleTimeString('en-IN', { timeZone: 'Asia/Kolkata', hour: 'numeric', minute: '2-digit' })}? The order is cancelled and its items released.</p>
    </section>
  );
}
