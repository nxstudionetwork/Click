import { useState } from 'react';
import type { ProviderClient } from '@click/api';
import { useAuth } from '../../auth/AuthProvider';
import { Button, Icon } from '../../components/ui';

/**
 * Opens the connected payment provider's own checkout (Razorpay today). Card / UPI details go to the provider, never to
 * Click. Closing the window changes nothing: the payment's status only changes when the provider's signed webhook
 * reaches Click.'s server, and the page updates by itself.
 */
const RAZORPAY_JS = 'https://checkout.razorpay.com/v1/checkout.js';

interface RazorpayCtor { new (o: Record<string, unknown>): { open(): void; on(e: string, cb: (r: unknown) => void): void } }

function loadRazorpay(): Promise<RazorpayCtor> {
  const w = window as unknown as { Razorpay?: RazorpayCtor };
  if (w.Razorpay) return Promise.resolve(w.Razorpay);
  return new Promise((resolve, reject) => {
    const s = document.createElement('script');
    s.src = RAZORPAY_JS;
    s.async = true;
    s.onload = () => (w.Razorpay ? resolve(w.Razorpay) : reject(new Error('Razorpay unavailable')));
    s.onerror = () => reject(new Error('Razorpay unavailable'));
    document.head.appendChild(s);
  });
}

export function ProviderCheckout({ client, description, onClosed }: { client: ProviderClient; description: string; onClosed?: () => void }) {
  const { user } = useAuth();
  const [state, setState] = useState<'idle' | 'opening' | 'error'>('idle');
  if (client.provider !== 'razorpay' || !client.orderId || !client.keyId) {
    return <p className="small">Finish the payment in the provider’s window. This updates by itself once the provider confirms it.</p>;
  }
  const open = async () => {
    setState('opening');
    try {
      const Razorpay = await loadRazorpay();
      const rzp = new Razorpay({
        key: client.keyId, order_id: client.orderId, amount: client.amount, currency: client.currency ?? 'INR', name: client.name ?? 'Click.',
        description, prefill: { contact: user?.phone ?? '', email: user?.email ?? '', name: user?.fullName ?? '' },
        theme: { color: '#2f3cff' }, modal: { ondismiss: () => onClosed?.() },
        // Success here is only the browser's view; Click. waits for Razorpay's signed webhook before confirming.
        handler: () => undefined,
      });
      rzp.on('payment.failed', () => undefined);
      rzp.open();
      setState('idle');
    } catch {
      setState('error');
    }
  };
  return (
    <div className="stack" style={{ gap: 8 }}>
      <Button onClick={() => void open()} loading={state === 'opening'}><Icon name="shield" size={16} /> Pay securely with Razorpay</Button>
      {client.testMode && <p className="small muted">Razorpay test mode: use Razorpay’s test cards or UPI IDs. No real money moves.</p>}
      {state === 'error' && <p className="small" role="alert">Couldn’t open the payment window. Check your connection and try again.</p>}
      <p className="small muted">{client.instructions}</p>
    </div>
  );
}
