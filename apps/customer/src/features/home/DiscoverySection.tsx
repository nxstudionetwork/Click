import { Link } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { Icon, type IconName } from '../../components/ui';
import { servicePhoto } from '../../config/media';
import { serviceForStoreType, type Theme } from '../../config/services';
import { api } from '../../lib/api';
import { useStores } from '../stores/hooks';
import { HomeSection, Rail, RailItem, RailSkeleton } from './HomeSection';

interface Tile { key: string; to: string; theme: Theme; tag: string; title: string; text: string; icon: IconName; cta: string; photo?: boolean }

/** "Discover something new": real shows, live events and newly added stores, so Click. feels bigger than a menu. */
export function DiscoverySection() {
  const movies = useQuery({ queryKey: ['events', 'discover', 'movie'], queryFn: () => api.events.list({ kind: 'movie', status: 'now_showing' }) });
  const live = useQuery({ queryKey: ['events', 'discover', 'event'], queryFn: () => api.events.list({ kind: 'event', status: 'now_showing' }) });
  const fresh = useStores({ sort: 'new', open: true });

  if (movies.isPending || live.isPending || fresh.isPending) {
    return <HomeSection id="discover" title="Discover something new" icon="compass" theme="explore"><RailSkeleton variant="tall" count={4} /></HomeSection>;
  }

  const tiles: Tile[] = [];
  const m = movies.data?.results[0];
  if (m) tiles.push({ key: m.id, to: `/showtime/${m.slug}`, theme: 'movies', tag: 'Now showing', title: m.title, text: m.tagline || m.genres.join(' · '), icon: 'film', cta: 'Book seats', photo: true });
  const e = live.data?.results[0];
  if (e) tiles.push({ key: e.id, to: `/showtime/${e.slug}`, theme: 'movies', tag: 'Live event', title: e.title, text: e.tagline || e.genres.join(' · '), icon: 'ticket', cta: 'Get tickets', photo: true });
  for (const s of (fresh.data?.results ?? []).slice(0, 2)) {
    const svc = serviceForStoreType(s.storeType);
    tiles.push({ key: s.id, to: `/stores/${s.slug}`, theme: svc.theme, tag: 'New on Click.', title: s.name, text: `${s.categories.map((c) => c.name).slice(0, 2).join(', ')} · ${s.locality || s.city}`, icon: svc.icon, cta: svc.id === 'food' ? 'Order now' : 'Shop now' });
  }
  tiles.push({ key: 'explore', to: '/explore', theme: 'explore', tag: 'All of Click.', title: 'Explore every service', text: 'Rides, parcels, services and what’s launching next', icon: 'compass', cta: 'Explore' });

  return (
    <HomeSection id="discover" title="Discover something new" subtitle="Shows, events and new places on Click." icon="compass" theme="explore">
      <Rail label="Discover" variant="tall">
        {tiles.map((t) => {
          const photo = servicePhoto(t.theme);
          return (
            <RailItem key={t.key}>
              <Link to={t.to} className="discover" data-theme={t.theme}>
                {photo && t.photo && <img className="discover__photo" src={photo.src} srcSet={photo.srcSet} sizes="260px" alt="" loading="lazy" decoding="async" />}
                {!t.photo && <span className="discover__art" aria-hidden="true"><Icon name={t.icon} size={72} /></span>}
                <span className="discover__shade" aria-hidden="true" />
                <span className="discover__tag"><Icon name={t.icon} size={14} />{t.tag}</span>
                <span className="discover__body">
                  <strong>{t.title}</strong>
                  <span>{t.text}</span>
                  <span className="discover__cta">{t.cta} <Icon name="right" size={14} /></span>
                </span>
              </Link>
            </RailItem>
          );
        })}
      </Rail>
    </HomeSection>
  );
}
