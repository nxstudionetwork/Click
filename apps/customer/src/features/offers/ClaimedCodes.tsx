import { useQuery } from '@tanstack/react-query';
import { useAuth } from '../../auth/AuthProvider';
import { api } from '../../lib/api';

/** Codes the customer claimed in Click. Offers for this service, offered as one-tap fills for the coupon field. The
 *  service still validates the code when it's applied. */
export function ClaimedCodes({ service, current, onPick }: { service: string; current: string; onPick: (code: string) => void }) {
  const { status } = useAuth();
  const q = useQuery({ queryKey: ['offers', 'claimed', service], queryFn: () => api.money.offers.claimed(service), enabled: status === 'authenticated', staleTime: 60_000 });
  const rows = (q.data?.results ?? []).filter((r) => r.code !== current);
  if (!rows.length) return null;
  return (
    <div className="mn-claimed" aria-label="Your claimed codes">
      <span className="small">Your codes:</span>
      {rows.map((r) => <button key={r.offer} type="button" className="mn-claimed__code" onClick={() => onPick(r.code)} title={r.title}>{r.code} · {r.benefit}</button>)}
    </div>
  );
}
