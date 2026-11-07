import { useEffect, useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import { keepPreviousData, useQuery } from '@tanstack/react-query';
import { EmptyState, ErrorState, Icon, Skeleton } from '../components/ui';
import { PageHeader } from '../components/shell/PageHeader';
import { EventCard } from '../features/bookings/EventCard';
import { api } from '../lib/api';
import { useDeliveryLocation } from '../location/LocationProvider';

const TABS = [
  { id: 'now', label: 'Now showing', q: { kind: 'movie', status: 'now_showing' } },
  { id: 'soon', label: 'Coming soon', q: { kind: 'movie', status: 'coming_soon' } },
  { id: 'events', label: 'Live events', q: { kind: 'event' } },
] as const;

export function MoviesPage() {
  const [params, setParams] = useSearchParams();
  const tab = TABS.find((t) => t.id === params.get('tab')) ?? TABS[0];
  const { selected } = useDeliveryLocation();
  const city = selected?.city;
  const [search, setSearch] = useState('');
  const [debounced, setDebounced] = useState('');
  useEffect(() => { const t = setTimeout(() => setDebounced(search.trim()), 300); return () => clearTimeout(t); }, [search]);

  const events = useQuery({
    queryKey: ['events', tab.id, debounced, city],
    queryFn: () => api.events.list({ ...tab.q, search: debounced || undefined, city: tab.id === 'soon' ? undefined : city }),
    placeholderData: keepPreviousData,
  });

  return (
    <div className="stack">
      <PageHeader band title="Movies & Events" subtitle={city ? `Showing in ${city}` : 'Shows near you'} back={{ to: '/', label: 'Home' }} />
      <div className="search" role="search"><Icon name="search" /><input value={search} onChange={(e) => setSearch(e.target.value)} placeholder="Search movies, genres, cast" aria-label="Search movies and events" /></div>
      <div className="tabs" role="tablist" aria-label="Show type">
        {TABS.map((t) => <button key={t.id} role="tab" aria-selected={tab.id === t.id} onClick={() => setParams(t.id === 'now' ? {} : { tab: t.id }, { replace: true })}>{t.label}</button>)}
      </div>
      {events.isError ? <ErrorState error={events.error} onRetry={() => events.refetch()} />
        : events.isPending ? <div className="event-grid">{Array.from({ length: 4 }, (_, i) => <Skeleton key={i} height={320} radius={16} />)}</div>
        : events.data.results.length === 0 ? <EmptyState icon="ticket" title={debounced ? 'No matches' : 'Nothing here yet'} message={debounced ? 'Try another title or genre.' : city ? `No shows listed in ${city} right now.` : 'Check back soon.'} />
        : <div className="event-grid" style={{ opacity: events.isPlaceholderData ? 0.6 : 1 }}>{events.data.results.map((e) => <EventCard key={e.id} event={e} />)}</div>}
    </div>
  );
}
