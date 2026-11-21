import { createContext, useContext, useEffect, useMemo, useState, type ReactNode } from 'react';
import type { Address } from '@click/api';
import { useAuth } from '../auth/AuthProvider';
import { useAddresses } from '../features/addresses/useAddresses';

/**
 * The customer's selected delivery location, chosen from saved addresses.
 * The selection is a per-device preference (localStorage); addresses live on the server (PostgreSQL).
 * `point` is the selected address's saved coordinates: Home's "Near you" uses it only when it exists,
 * so proximity is never guessed. Device location is used only when the customer taps "Use current location".
 */
const KEY = 'click.selectedAddressId';

interface LocationValue {
  addresses: Address[];
  selected: Address | null;
  /** Coordinates of the selected address, when known. */
  point: { lat: number; lng: number } | null;
  isLoading: boolean;
  select: (id: string) => void;
}

const LocationContext = createContext<LocationValue>({ addresses: [], selected: null, point: null, isLoading: false, select: () => {} });

function readStored(): string | null {
  try {
    return localStorage.getItem(KEY);
  } catch {
    return null;
  }
}

export function LocationProvider({ children }: { children: ReactNode }) {
  const { status } = useAuth();
  const query = useAddresses(status === 'authenticated');
  const [selectedId, setSelectedId] = useState<string | null>(readStored);

  const addresses = useMemo(() => (status === 'authenticated' ? query.data ?? [] : []), [status, query.data]);
  const selected = addresses.find((a) => a.id === selectedId) ?? addresses.find((a) => a.isDefault) ?? addresses[0] ?? null;

  useEffect(() => {
    if (status === 'anonymous') setSelectedId(null);
  }, [status]);

  const value = useMemo<LocationValue>(() => ({
    addresses,
    selected,
    point: selected?.latitude && selected?.longitude ? { lat: Number(selected.latitude), lng: Number(selected.longitude) } : null,
    isLoading: status === 'loading' || (status === 'authenticated' && query.isPending),
    select: (id) => {
      setSelectedId(id);
      try { localStorage.setItem(KEY, id); } catch { /* storage unavailable */ }
    },
  }), [addresses, selected, status, query.isPending]);

  return <LocationContext.Provider value={value}>{children}</LocationContext.Provider>;
}

export const useDeliveryLocation = () => useContext(LocationContext);
