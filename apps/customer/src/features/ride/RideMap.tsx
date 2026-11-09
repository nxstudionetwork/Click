import { useEffect, useRef } from 'react';
import L from 'leaflet';
import 'leaflet/dist/leaflet.css';
import type { RidePlace } from '@click/api';

/**
 * Click. Ride map (Leaflet, open source; no Google services). Tiles come from VITE_MAP_TILE_URL; development defaults
 * to OpenStreetMap's public tiles (attribution required, light use only). Production needs its own tile provider.
 *
 * The line between points is a straight preview, not a road route: no routing provider is connected yet, and the
 * map never pretends otherwise. A driver marker appears only where the driver's app actually reported a position.
 */
const TILE_URL = import.meta.env.VITE_MAP_TILE_URL || 'https://tile.openstreetmap.org/{z}/{x}/{y}.png';
const TILE_ATTRIBUTION = import.meta.env.VITE_MAP_ATTRIBUTION || '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors';
const DEFAULT_CENTER: [number, number] = [12.9716, 77.5946];

const pin = (kind: 'pickup' | 'drop' | 'stop' | 'driver', label?: string) => L.divIcon({
  className: `rmap-pin rmap-pin--${kind}`,
  html: kind === 'driver' ? '<span class="rmap-pin__car"></span>' : `<span class="rmap-pin__dot">${label ?? ''}</span>`,
  iconSize: [28, 28], iconAnchor: [14, 14],
});

export interface RideMapProps {
  pickup?: RidePlace | null;
  drop?: RidePlace | null;
  stops?: RidePlace[];
  driver?: { lat: number; lng: number } | null;
  /** Fallback centre (e.g. the active saved location) when no points are chosen yet. */
  center?: { lat: number; lng: number } | null;
  /** When set, tapping the map reports a point (pin selection). */
  onPick?: (p: { lat: number; lng: number }) => void;
  className?: string;
}

export function RideMap({ pickup, drop, stops = [], driver, center, onPick, className = '' }: RideMapProps) {
  const el = useRef<HTMLDivElement>(null);
  const map = useRef<L.Map | null>(null);
  const layer = useRef<L.LayerGroup | null>(null);
  const pickHandler = useRef(onPick);
  pickHandler.current = onPick;

  useEffect(() => {
    if (!el.current || map.current) return;
    const m = L.map(el.current, { zoomControl: false, attributionControl: true }).setView(center ? [center.lat, center.lng] : DEFAULT_CENTER, 13);
    L.tileLayer(TILE_URL, { maxZoom: 19, attribution: TILE_ATTRIBUTION }).addTo(m);
    L.control.zoom({ position: 'bottomright' }).addTo(m);
    m.on('click', (e: L.LeafletMouseEvent) => pickHandler.current?.({ lat: e.latlng.lat, lng: e.latlng.lng }));
    layer.current = L.layerGroup().addTo(m);
    map.current = m;
    const ro = new ResizeObserver(() => m.invalidateSize());
    ro.observe(el.current);
    return () => { ro.disconnect(); m.remove(); map.current = null; };
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    const m = map.current, g = layer.current;
    if (!m || !g) return;
    m.invalidateSize(); // the container may have been sized after the map was created (lazy-loaded panels, sheets)
    g.clearLayers();
    const pts: [number, number][] = [];
    if (pickup) { pts.push([pickup.lat, pickup.lng]); L.marker([pickup.lat, pickup.lng], { icon: pin('pickup'), title: `Pickup: ${pickup.label}` }).addTo(g); }
    stops.forEach((s, i) => { pts.push([s.lat, s.lng]); L.marker([s.lat, s.lng], { icon: pin('stop', String(i + 1)), title: `Stop ${i + 1}: ${s.label}` }).addTo(g); });
    if (drop) { pts.push([drop.lat, drop.lng]); L.marker([drop.lat, drop.lng], { icon: pin('drop'), title: `Drop: ${drop.label}` }).addTo(g); }
    if (pts.length > 1) L.polyline(pts, { className: 'rmap-line', weight: 4, dashArray: '2 10', lineCap: 'round' }).addTo(g);
    if (driver) L.marker([driver.lat, driver.lng], { icon: pin('driver'), title: 'Driver' }).addTo(g);
    const all = driver ? [...pts, [driver.lat, driver.lng] as [number, number]] : pts;
    if (all.length > 1) m.fitBounds(L.latLngBounds(all), { padding: [48, 48], maxZoom: 15 });
    else if (all.length === 1) m.setView(all[0]!, 15);
    else if (center) m.setView([center.lat, center.lng], 13);
  }, [pickup, drop, stops, driver, center]);

  useEffect(() => { el.current?.classList.toggle('rmap--picking', !!onPick); }, [onPick]);

  return <div ref={el} className={`rmap ${className}`} role="application" aria-label="Map" />;
}
