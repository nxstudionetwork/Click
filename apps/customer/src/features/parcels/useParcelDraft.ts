import { useEffect, useMemo, useRef, useState } from 'react';
import { keepPreviousData, useQuery } from '@tanstack/react-query';
import type { ParcelDraft, ParcelMode, ParcelPackageInput, ParcelQuoteInput, SavedRecipient } from '@click/api';
import { useAuth } from '../../auth/AuthProvider';
import { api } from '../../lib/api';
import { useDeliveryLocation } from '../../location/LocationProvider';

export interface Spot { label: string; address: string; lat: number; lng: number }
export interface Contact { name: string; phone: string; altPhone: string; instructions: string }
const EMPTY: Contact = { name: '', phone: '', altPhone: '', instructions: '' };
export const PHONE = /^\+?[0-9][0-9 -]{7,15}$/;

/**
 * The parcel being booked. Locations come only from real sources (saved addresses, Click places, the device's current
 * position, a map pin or a store's listing); the customer's own side defaults to the selected delivery location.
 * The quote is fetched from the server whenever the inputs that affect price change.
 */
export function useParcelDraft() {
  const { user } = useAuth();
  const { selected } = useDeliveryLocation();
  const [mode, setModeState] = useState<ParcelMode>('send');
  const [pickup, setPickup] = useState<Spot | null>(null);
  const [drop, setDrop] = useState<Spot | null>(null);
  const [stops, setStops] = useState<(Spot & { name: string; phone: string })[]>([]);
  const [sender, setSender] = useState<Contact>(EMPTY);
  const [recipient, setRecipient] = useState<Contact>(EMPTY);
  const [store, setStore] = useState<{ id: string; name: string } | null>(null);
  const [storeReference, setStoreReference] = useState('');
  const [pkg, setPkg] = useState<ParcelPackageInput>({ category: '', size: '', weightKg: '', notes: '' });
  const [service, setService] = useState<string>('');
  const [scheduledFor, setScheduledFor] = useState<string | null>(null);
  const [vehicle, setVehicle] = useState<string>('');
  const [repeatOf, setRepeatOf] = useState<string | null>(null);
  const seeded = useRef(false);

  const mine = useMemo<Spot | null>(() => selected && selected.latitude && selected.longitude ? {
    label: selected.label.charAt(0).toUpperCase() + selected.label.slice(1), address: [selected.line1, selected.line2, selected.city].filter(Boolean).join(', '),
    lat: Number(selected.latitude), lng: Number(selected.longitude) } : null, [selected]);
  const me = useMemo<Contact>(() => ({ name: selected?.recipientName || user?.fullName || '', phone: selected?.phone || user?.phone || '', altPhone: '', instructions: '' }),
    [selected, user]);

  // The customer's own side starts at the selected delivery location (pickup for Send, drop for Receive / Store pickup).
  useEffect(() => {
    if (seeded.current || !mine) return;
    seeded.current = true;
    if (mode === 'send') { setPickup(mine); setSender(me); } else { setDrop(mine); setRecipient(me); }
  }, [mine, me, mode]);

  const setMode = (m: ParcelMode) => {
    if (m === mode) return;
    setModeState(m);
    setVehicle('');
    if (m === 'send') {
      setPickup(mine); setSender(me); setDrop(null); setRecipient(EMPTY); setStore(null);
    } else {
      setDrop(mine); setRecipient(me); setPickup(null); setSender(EMPTY); setStops([]);
    }
  };

  const applyRecipient = (r: SavedRecipient) => {
    setRecipient({ name: r.name, phone: r.phone, altPhone: r.altPhone, instructions: r.instructions });
    if (r.lat && r.lng) setDrop({ label: r.label || r.name, address: r.address, lat: Number(r.lat), lng: Number(r.lng) });
  };

  const loadDraft = (d: ParcelDraft) => {
    setModeState(d.mode); seeded.current = true;
    setPickup({ label: d.pickup.label, address: d.pickup.address ?? '', lat: d.pickup.lat, lng: d.pickup.lng });
    setDrop({ label: d.drop.label, address: d.drop.address ?? '', lat: d.drop.lat, lng: d.drop.lng });
    setSender({ ...EMPTY, name: d.pickup.name ?? '', phone: d.pickup.phone ?? '', instructions: d.pickup.instructions ?? '' });
    setRecipient({ name: d.drop.name ?? '', phone: d.drop.phone ?? '', altPhone: d.drop.altPhone ?? '', instructions: d.drop.instructions ?? '' });
    setStops((d.stops ?? []).map((s) => ({ label: s.label, address: s.address ?? '', lat: s.lat, lng: s.lng, name: s.name ?? '', phone: s.phone ?? '' })));
    setPkg({ ...d.package, weightKg: d.package?.weightKg ?? '' });
    setService(d.service ?? ''); setVehicle(d.vehicle ?? ''); setRepeatOf(d.repeatOf ?? null);
    if (d.storeId) setStore({ id: d.storeId, name: d.pickup.label });
  };

  const placeReady = mode === 'store_pickup' ? !!store && !!drop : !!pickup && !!drop;
  const pkgReady = !!pkg.category && !!pkg.size && !!pkg.weightKg && Number(pkg.weightKg) > 0;
  const input: ParcelQuoteInput | null = placeReady ? {
    mode, storeId: store?.id ?? null,
    pickup: mode === 'store_pickup' ? { label: store!.name, lat: 0, lng: 0 } : { ...pickup!, name: sender.name, phone: sender.phone, instructions: sender.instructions },
    drop: { ...drop!, name: recipient.name, phone: recipient.phone, altPhone: recipient.altPhone, instructions: recipient.instructions },
    stops: stops.filter((s) => s.lat).map((s) => ({ label: s.label, address: s.address, lat: s.lat, lng: s.lng, name: s.name, phone: s.phone })),
    package: pkg, service: service || undefined, scheduledFor,
  } : null;
  // Only what changes the price re-quotes (contacts and notes don't).
  const priceKey = input ? JSON.stringify([mode, store?.id, pickup, drop, stops.filter((s) => s.lat).map((s) => [s.lat, s.lng]), pkg.category, pkg.size, pkg.weightKg,
    pkg.lengthCm, pkg.widthCm, pkg.heightCm, pkg.declaredValue, service, scheduledFor]) : null;
  const [debouncedKey, setDebouncedKey] = useState(priceKey);
  useEffect(() => { const t = setTimeout(() => setDebouncedKey(priceKey), 350); return () => clearTimeout(t); }, [priceKey]);
  const latest = useRef(input);
  latest.current = input;
  const quote = useQuery({
    queryKey: ['parcels', 'quote', debouncedKey],
    queryFn: () => api.parcels.quote(latest.current!),
    enabled: !!debouncedKey && !!latest.current, placeholderData: keepPreviousData, staleTime: 30_000, retry: false,
  });

  // Keep the chosen service / vehicle valid against what the server says is available.
  useEffect(() => {
    const q = quote.data;
    if (!q) return;
    if (q.service && q.service !== service && !q.services.find((s) => s.code === service)?.available) setService(q.service);
    const ok = q.vehicles.filter((v) => v.available && v.fare);
    if (!ok.find((v) => v.code === vehicle)) setVehicle(ok[0]?.code ?? '');
  }, [quote.data]); // eslint-disable-line react-hooks/exhaustive-deps

  return {
    mode, setMode, pickup, setPickup, drop, setDrop, stops, setStops, sender, setSender, recipient, setRecipient, store, setStore,
    storeReference, setStoreReference, pkg, setPkg, service, setService, scheduledFor, setScheduledFor, vehicle, setVehicle,
    repeatOf, applyRecipient, loadDraft, input, placeReady, pkgReady, quote, mine, me,
  };
}
export type ParcelDraftState = ReturnType<typeof useParcelDraft>;
