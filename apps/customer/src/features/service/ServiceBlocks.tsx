import { useState } from 'react';
import type { StoreCategory } from '@click/api';
import { Icon, Sheet } from '../../components/ui';
import type { ServicePageConfig, ServiceSort } from '../../config/servicePages';
import { SORTS } from '../../config/servicePages';
import { CameraSearch } from '../assist/CameraSearch';
import { VoiceInput } from '../assist/VoiceInput';

/** Title + fixed tagline: tells the customer which Click. service they're in. */
export function ServiceIntro({ config }: { config: ServicePageConfig }) {
  return (
    <header className="svc-intro">
      <h1>{config.title}</h1>
      <p>{config.quote}</p>
    </header>
  );
}

/** Horizontal, scrollable categories from the API ("All" first); selection lives in the URL. */
export function HorizontalDiscovery({ config, categories, loading, selected, onSelect }: {
  config: ServicePageConfig; categories: StoreCategory[]; loading: boolean; selected: string; onSelect: (slug: string) => void;
}) {
  return (
    <nav className="svc-cats" aria-label={config.categoriesLabel}>
      <ul>
        <li>
          <button type="button" className="svc-cat" aria-pressed={!selected} onClick={() => onSelect('')}>
            <span className="svc-cat__icon"><Icon name="menu" size={22} /></span><span className="svc-cat__name">All</span>
          </button>
        </li>
        {loading ? Array.from({ length: 6 }, (_, i) => <li key={i}><span className="skeleton svc-cat__skel" /></li>) : categories.map((c) => (
          <li key={c.id}>
            <button type="button" className="svc-cat" aria-pressed={selected === c.slug} onClick={() => onSelect(selected === c.slug ? '' : c.slug)}>
              <span className="svc-cat__icon"><Icon name={config.categoryIcons[c.slug] ?? config.fallbackIcon} size={22} /></span>
              <span className="svc-cat__name">{c.name}</span>
            </button>
          </li>
        ))}
      </ul>
    </nav>
  );
}

/** Service-specific search (after the categories). Typing is debounced by the page; voice/camera reuse Click.'s flows. */
export function ServiceSearch({ config, value, onChange }: { config: ServicePageConfig; value: string; onChange: (v: string) => void }) {
  const [panel, setPanel] = useState<'voice' | 'camera' | null>(null);
  return (
    <>
      <div className="svc-search" role="search">
        <Icon name="search" size={20} className="svc-search__lead" />
        <input value={value} onChange={(e) => onChange(e.target.value)} placeholder={config.searchPlaceholder} aria-label={config.searchPlaceholder} enterKeyHint="search" />
        {value && <button type="button" className="gsearch__tool" aria-label="Clear text" onClick={() => onChange('')}><Icon name="close" size={18} /></button>}
        <button type="button" className="gsearch__tool" aria-label="Search by voice" onClick={() => setPanel('voice')}><Icon name="mic" size={18} /></button>
        <button type="button" className="gsearch__tool" aria-label="Search with camera" onClick={() => setPanel('camera')}><Icon name="camera" size={18} /></button>
      </div>
      <Sheet open={panel !== null} onClose={() => setPanel(null)} label={panel === 'voice' ? 'Voice search' : 'Scan with camera'}>
        <div className="stack" style={{ padding: 'var(--s-5)' }}>
          <div className="spread"><h2>{panel === 'voice' ? `Search ${config.title}` : 'Scan with camera'}</h2>
            <button className="icon-btn" aria-label="Close" onClick={() => setPanel(null)}><Icon name="close" /></button></div>
          {panel === 'voice' && <VoiceInput onText={(t) => { setPanel(null); onChange(t); }} placeholder={config.searchPlaceholder} />}
          {panel === 'camera' && <CameraSearch onDone={() => setPanel(null)} />}
        </div>
      </Sheet>
    </>
  );
}

export interface ServiceFilters { veg: boolean; rating: boolean; offers: boolean; open: boolean; budget: boolean; sort: ServiceSort }

/** Filters and sort the API genuinely supports. Distance sort appears only when the location has coordinates. */
export function FilterBar({ config, filters, onChange, hasLocation }: {
  config: ServicePageConfig; filters: ServiceFilters; onChange: (patch: Partial<ServiceFilters>) => void; hasLocation: boolean;
}) {
  const chips: { key: keyof ServiceFilters; label: string; show: boolean }[] = [
    { key: 'veg', label: 'Pure veg', show: config.vegFilter },
    { key: 'rating', label: 'Rating 4.0+', show: true },
    { key: 'offers', label: 'Offers', show: true },
    { key: 'open', label: 'Open now', show: true },
    { key: 'budget', label: 'Budget (₹–₹₹)', show: true },
  ];
  return (
    <div className="svc-filters">
      <label className="svc-sort">
        <Icon name="chart" size={16} />
        <span className="visually-hidden">Sort by</span>
        <select value={filters.sort} onChange={(e) => onChange({ sort: e.target.value as ServiceSort })} aria-label="Sort by">
          {SORTS.filter((s) => !s.needsLocation || hasLocation).map((s) => <option key={s.id} value={s.id}>{s.label}</option>)}
        </select>
      </label>
      <div className="chips" role="group" aria-label="Filters">
        {chips.filter((c) => c.show).map((c) => (
          <button key={c.key} type="button" className="chip" aria-pressed={!!filters[c.key]} onClick={() => onChange({ [c.key]: !filters[c.key] })}>
            {filters[c.key] && <Icon name="check" size={14} />} {c.label}
          </button>
        ))}
      </div>
    </div>
  );
}
