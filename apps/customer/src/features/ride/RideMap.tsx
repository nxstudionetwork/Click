import { useEffect, useRef, useState } from 'react';
import type { Map as MLMap, Marker, GeoJSONSource, StyleSpecification } from 'maplibre-gl';
import type { RidePlace } from '@click/api';
import { Icon } from '../../components/ui';

/**
 * Click. map (MapLibre GL, open source; no Google services). Vector tiles from OpenFreeMap by default (free, no key):
 * crisp at every zoom, 3D buildings, tilt and rotate, light and dark styles that follow the app's appearance.
 * Production can point VITE_MAP_STYLE_URL / VITE_MAP_STYLE_DARK_URL at its own style.
 *
 * `route` draws the real road line from the server (apps.geo). Without it, a dashed straight preview connects the points
 * and is never presented as a road. A driver marker appears only where the driver's app reported a position.
 * In "picking" mode a fixed centre pin marks the spot; panning the map moves the point underneath it.
 */
const STYLE_LIGHT = import.meta.env.VITE_MAP_STYLE_URL || 'https://tiles.openfreemap.org/styles/liberty';
const STYLE_DARK = import.meta.env.VITE_MAP_STYLE_DARK_URL || 'https://tiles.openfreemap.org/styles/dark';
const DEFAULT_CENTER: [number, number] = [77.5946, 12.9716]; // lng, lat (Bengaluru)
type LngLat = [number, number];

export interface RideMapProps {
  pickup?: RidePlace | null;
  drop?: RidePlace | null;
  stops?: RidePlace[];
  driver?: { lat: number; lng: number } | null;
  /** Road route from the server as [lat, lng] pairs. */
  route?: [number, number][] | null;
  /** Fallback centre (e.g. the active saved location) when no points are chosen yet. */
  center?: { lat: number; lng: number } | null;
  /** Pin selection: reports the point under the centre pin as the map moves (and where the map is tapped). */
  onPick?: (p: { lat: number; lng: number }) => void;
  className?: string;
}

// The app resolves White / Dark / Match device itself and marks dark with data-appearance="dark".
const isDark = () => document.documentElement.dataset.appearance === 'dark';

function webglAvailable(): boolean {
  try {
    const c = document.createElement('canvas');
    return !!(c.getContext('webgl2') || c.getContext('webgl'));
  } catch {
    return false;
  }
}

function pinEl(kind: 'pickup' | 'drop' | 'stop' | 'driver' | 'me', label?: string, title?: string) {
  const el = document.createElement('div');
  el.className = `rmap-pin rmap-pin--${kind}`;
  if (title) el.title = title;
  el.innerHTML = kind === 'driver' ? '<span class="rmap-pin__car"></span>' : kind === 'me' ? '<span class="rmap-pin__me"></span>'
    : `<span class="rmap-pin__dot">${label ?? ''}</span>${title && kind !== 'stop' ? `<span class="rmap-pin__tag">${escapeHtml(title.split(': ').pop() ?? '')}</span>` : ''}`;
  return el;
}
const escapeHtml = (s: string) => s.replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]!));

const lineData = (coords: LngLat[]) => ({ type: 'Feature' as const, properties: {}, geometry: { type: 'LineString' as const, coordinates: coords } });

export function RideMap({ pickup, drop, stops = [], driver, route, center, onPick, className = '' }: RideMapProps) {
  const el = useRef<HTMLDivElement>(null);
  const map = useRef<MLMap | null>(null);
  const lib = useRef<typeof import('maplibre-gl') | null>(null);
  const markers = useRef<Marker[]>([]);
  const driverMarker = useRef<Marker | null>(null);
  const meMarker = useRef<Marker | null>(null);
  const pickHandler = useRef(onPick);
  pickHandler.current = onPick;
  const [ready, setReady] = useState(false);
  const [failed, setFailed] = useState(false);
  const [tilted, setTilted] = useState(false);
  const [locating, setLocating] = useState(false);

  // Create the map once (MapLibre is loaded on demand so pages without a map never download it).
  useEffect(() => {
    if (!el.current || map.current) return;
    if (!webglAvailable()) { setFailed(true); return; }
    let cancelled = false;
    let ro: ResizeObserver | null = null;
    let mo: MutationObserver | null = null;
    void Promise.all([import('maplibre-gl'), import('maplibre-gl/dist/maplibre-gl.css')]).then(([ml]) => {
      if (cancelled || !el.current) return;
      lib.current = ml;
      let dark = isDark();
      const m = new ml.Map({
        container: el.current, style: dark ? STYLE_DARK : STYLE_LIGHT,
        center: center ? [center.lng, center.lat] : DEFAULT_CENTER, zoom: 13.5, attributionControl: { compact: true },
        maxPitch: 65, dragRotate: true, cooperativeGestures: false,
      });
      m.addControl(new ml.NavigationControl({ showCompass: true, visualizePitch: true }), 'top-right');
      m.on('click', (e) => { if (pickHandler.current) m.easeTo({ center: e.lngLat }); });
      m.on('moveend', () => { if (pickHandler.current) { const c = m.getCenter(); pickHandler.current({ lat: +c.lat.toFixed(6), lng: +c.lng.toFixed(6) }); } });
      // Some styles reference decorative pattern images they don't ship; an empty image keeps the console clean.
      m.on('styleimagemissing', (e) => { if (!m.hasImage(e.id)) m.addImage(e.id, { width: 1, height: 1, data: new Uint8Array(4) }); });
      m.on('error', (e) => { if (String(e?.error?.message ?? '').includes('style')) setFailed(true); });
      const addLayers = () => {
        if (m.getSource('click-route')) return;
        m.addSource('click-route', { type: 'geojson', data: lineData([]) });
        m.addLayer({ id: 'click-route-casing', type: 'line', source: 'click-route', layout: { 'line-cap': 'round', 'line-join': 'round' },
          paint: { 'line-color': '#ffffff', 'line-width': 9, 'line-opacity': 0.9 } });
        m.addLayer({ id: 'click-route-line', type: 'line', source: 'click-route', layout: { 'line-cap': 'round', 'line-join': 'round' },
          paint: { 'line-color': '#0ea5e9', 'line-width': 5 } });
        m.addSource('click-preview', { type: 'geojson', data: lineData([]) });
        m.addLayer({ id: 'click-preview-line', type: 'line', source: 'click-preview', layout: { 'line-cap': 'round' },
          paint: { 'line-color': '#0ea5e9', 'line-width': 3, 'line-dasharray': [0.5, 2.2] } });
        // 3D buildings where the style has building heights.
        const src = Object.entries(m.getStyle().sources ?? {}).find(([, s]) => (s as { type?: string }).type === 'vector')?.[0];
        if (src && !m.getLayer('click-3d') && m.getStyle().layers?.some((l) => (l as { 'source-layer'?: string })['source-layer'] === 'building')) {
          m.addLayer({ id: 'click-3d', type: 'fill-extrusion', source: src, 'source-layer': 'building', minzoom: 15,
            paint: { 'fill-extrusion-color': dark ? '#26324d' : '#dfe4ee', 'fill-extrusion-height': ['coalesce', ['get', 'render_height'], 8],
              'fill-extrusion-base': ['coalesce', ['get', 'render_min_height'], 0], 'fill-extrusion-opacity': 0.75 } });
        }
        setReady(true);
      };
      m.on('load', addLayers);
      m.on('style.load', addLayers);
      // Follow the app's White / Dark appearance live.
      const restyle = () => { const d = isDark(); if (d !== dark) { dark = d; setReady(false); m.setStyle((d ? STYLE_DARK : STYLE_LIGHT) as unknown as StyleSpecification); } };
      mo = new MutationObserver(restyle);
      mo.observe(document.documentElement, { attributes: true, attributeFilter: ['data-appearance'] });
      ro = new ResizeObserver(() => m.resize());
      ro.observe(el.current);
      map.current = m;
    }).catch(() => setFailed(true));
    return () => {
      cancelled = true; ro?.disconnect(); mo?.disconnect();
      map.current?.remove(); map.current = null; setReady(false);
    };
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  // Markers, route and camera.
  useEffect(() => {
    const m = map.current, ml = lib.current;
    if (!m || !ml || !ready) return;
    markers.current.forEach((x) => x.remove());
    markers.current = [];
    const pts: LngLat[] = [];
    const add = (p: RidePlace, kind: 'pickup' | 'drop' | 'stop', label?: string, title?: string) => {
      pts.push([p.lng, p.lat]);
      markers.current.push(new ml.Marker({ element: pinEl(kind, label, title), anchor: 'center' }).setLngLat([p.lng, p.lat]).addTo(m));
    };
    if (pickup && !onPick) add(pickup, 'pickup', undefined, `Pickup: ${pickup.label}`);
    stops.forEach((s, i) => add(s, 'stop', String(i + 1), `Stop ${i + 1}: ${s.label}`));
    if (drop) add(drop, 'drop', undefined, `Drop: ${drop.label}`);
    if (pickup && onPick) pts.unshift([pickup.lng, pickup.lat]);
    const road: LngLat[] = (route ?? []).map(([lat, lng]) => [lng, lat]);
    (m.getSource('click-route') as GeoJSONSource | undefined)?.setData(lineData(road));
    (m.getSource('click-preview') as GeoJSONSource | undefined)?.setData(lineData(road.length > 1 || onPick ? [] : pts.length > 1 ? pts : []));
    if (onPick) return; // the customer is moving the map; don't fight them
    const all: LngLat[] = [...pts, ...road, ...(driver ? [[driver.lng, driver.lat] as LngLat] : [])];
    if (all.length > 1) {
      const b = new ml.LngLatBounds(all[0], all[0]);
      all.forEach((p) => b.extend(p));
      m.fitBounds(b, { padding: { top: 60, bottom: 110, left: 90, right: 90 }, maxZoom: 16, duration: 700 });
    } else if (all.length === 1) m.easeTo({ center: all[0], zoom: 15.5, duration: 600 });
    else if (center) m.easeTo({ center: [center.lng, center.lat], zoom: 14, duration: 600 });
  }, [pickup, drop, stops, route, center, ready, onPick]); // eslint-disable-line react-hooks/exhaustive-deps

  // The driver moves smoothly without refitting the whole map on every position report.
  useEffect(() => {
    const m = map.current, ml = lib.current;
    if (!m || !ml || !ready) return;
    if (!driver) { driverMarker.current?.remove(); driverMarker.current = null; return; }
    if (!driverMarker.current) driverMarker.current = new ml.Marker({ element: pinEl('driver', undefined, 'Driver'), anchor: 'center' }).setLngLat([driver.lng, driver.lat]).addTo(m);
    else driverMarker.current.setLngLat([driver.lng, driver.lat]);
  }, [driver, ready]);

  // Pin mode: jump to the current pickup (or saved location) so the pin starts somewhere sensible.
  useEffect(() => {
    const m = map.current;
    if (!m || !ready || !onPick) return;
    const start = pickup ?? center;
    if (start) m.jumpTo({ center: [start.lng, start.lat], zoom: Math.max(m.getZoom(), 16) });
  }, [!!onPick, ready]); // eslint-disable-line react-hooks/exhaustive-deps

  function toggleTilt() {
    const m = map.current;
    if (!m) return;
    const next = !tilted;
    setTilted(next);
    m.easeTo({ pitch: next ? 55 : 0, bearing: next ? -17 : 0, zoom: next ? Math.max(m.getZoom(), 16) : m.getZoom(), duration: 800 });
  }

  function locateMe() {
    const m = map.current, ml = lib.current;
    if (!m || !ml || !('geolocation' in navigator)) return;
    setLocating(true);
    navigator.geolocation.getCurrentPosition((p) => {
      setLocating(false);
      const at: LngLat = [p.coords.longitude, p.coords.latitude];
      if (!meMarker.current) meMarker.current = new ml.Marker({ element: pinEl('me', undefined, 'You are here'), anchor: 'center' }).setLngLat(at).addTo(m);
      else meMarker.current.setLngLat(at);
      m.easeTo({ center: at, zoom: 16, duration: 700 });
    }, () => setLocating(false), { enableHighAccuracy: true, timeout: 10_000, maximumAge: 30_000 });
  }

  if (failed) {
    return (
      <div className={`rmap rmap--off ${className}`} role="img" aria-label="Map unavailable">
        <Icon name="pin" size={22} /><span>The map can’t be shown on this device. Search or choose places from the list.</span>
      </div>
    );
  }
  return (
    <div className={`rmap ${onPick ? 'rmap--picking' : ''} ${className}`}>
      <div ref={el} className="rmap__canvas" role="application" aria-label="Map. Drag to move, pinch or use the buttons to zoom." />
      {!ready && <span className="rmap__loading skeleton" aria-hidden="true" />}
      {onPick && <span className="rmap__center-pin" aria-hidden="true"><span /></span>}
      <div className="rmap__tools">
        <button type="button" className="rmap__tool" onClick={locateMe} aria-label="Show my location" disabled={locating}><Icon name="locate" size={18} /></button>
        <button type="button" className={`rmap__tool ${tilted ? 'is-on' : ''}`} onClick={toggleTilt} aria-pressed={tilted} aria-label="3D view">3D</button>
      </div>
    </div>
  );
}
