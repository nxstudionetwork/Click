import { useEffect, useState } from 'react';

/** Re-renders every `ms`; countdowns read the server's expiry time (never a client-made timer). */
export function useNowTick(ms = 1000) {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => { const t = setInterval(() => setNow(Date.now()), ms); return () => clearInterval(t); }, [ms]);
  return now;
}

export { dayOf, timeOf } from './parts';
