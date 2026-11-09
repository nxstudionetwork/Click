import { useEffect, useState } from 'react';
import type { DeliveryEstimate } from '@click/api';

/** The current time, re-rendering every `ms` (deal countdowns tick from the backend end time, never a fake timer). */
export function useNow(ms = 30_000) {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    const t = setInterval(() => setNow(Date.now()), ms);
    return () => clearInterval(t);
  }, [ms]);
  return now;
}

/** "Ends in 5h 12m" / "Ends in 2d 4h" / "Ended" from an ISO end time. */
export function timeLeft(endsAt: string, now: number): string {
  const s = Math.floor((new Date(endsAt).getTime() - now) / 1000);
  if (s <= 0) return 'Ended';
  const d = Math.floor(s / 86400), h = Math.floor((s % 86400) / 3600), m = Math.floor((s % 3600) / 60);
  if (d > 0) return `Ends in ${d}d ${h}h`;
  if (h > 0) return `Ends in ${h}h ${m}m`;
  return `Ends in ${m}m ${s % 60}s`;
}

const day = (iso: string) => new Date(`${iso}T12:00:00`).toLocaleDateString('en-IN', { weekday: 'short', day: 'numeric', month: 'short' });

/** "Thu, 12 Nov – Sat, 14 Nov" (always a range: it is an estimate). */
export const deliveryWindow = (e: Pick<DeliveryEstimate, 'fromDate' | 'toDate'>) =>
  e.fromDate === e.toDate ? day(e.fromDate) : `${day(e.fromDate)} – ${day(e.toDate)}`;

export const ESTIMATE_BASIS: Record<DeliveryEstimate['basis'], string> = {
  distance: 'from the seller’s location to yours',
  same_city: 'seller and delivery in the same city',
  region: 'seller in another region',
};
