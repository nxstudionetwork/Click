import { Link } from 'react-router-dom';
import type { BuzzItem } from '@click/api';
import { Icon, type IconName } from '../../components/ui';
import { servicePhoto } from '../../config/media';

const KIND_ICON: Record<BuzzItem['kind'], IconName> = { offer: 'tag', event: 'film', store: 'store', product: 'bag', post: 'play' };
const THEME_ICON: Partial<Record<BuzzItem['theme'], IconName>> = { food: 'food', grocery: 'grocery', shopping: 'shop', movies: 'film', services: 'wrench', ride: 'ride', parcel: 'parcel' };

/**
 * Media for an instant: the item's own image/video when it has one. Without it, a show gets the cinema photograph
 * (it describes the category) while a store or offer gets a branded gradient with its service icon, so a stock
 * photo is never passed off as a particular store's own picture.
 */
export function BuzzMedia({ item, eager = false }: { item: BuzzItem; eager?: boolean }) {
  if (item.mediaType === 'video' && item.mediaUrl) {
    // Videos never autoplay in bulk: the viewer starts playback.
    return <video className="buzz-media" src={item.mediaUrl} preload="none" playsInline controls muted />;
  }
  if (item.mediaType === 'image' && item.mediaUrl) {
    return <img className="buzz-media" src={item.mediaUrl} alt="" loading={eager ? 'eager' : 'lazy'} decoding="async" />;
  }
  const photo = item.kind === 'event' ? servicePhoto(item.theme) : null;
  if (!photo) return <span className="buzz-media buzz-media--art" aria-hidden="true"><Icon name={THEME_ICON[item.theme] ?? KIND_ICON[item.kind]} size={64} /></span>;
  return <img className="buzz-media buzz-media--ambient" src={photo.src} srcSet={photo.srcSet} sizes="(min-width: 720px) 420px, 100vw" alt="" loading={eager ? 'eager' : 'lazy'} decoding="async" />;
}

/** Compact 9:16 preview used on Home. */
export function BuzzPreviewCard({ item }: { item: BuzzItem }) {
  return (
    <Link to={`/buzz?item=${encodeURIComponent(item.id)}`} className="buzz-card" data-theme={item.theme} aria-label={`${item.title}, ${item.tag}. Open in Buzz`}>
      <BuzzMedia item={item} />
      <span className="buzz-card__shade" aria-hidden="true" />
      <span className="buzz-card__tag"><Icon name={KIND_ICON[item.kind]} size={12} />{item.tag}</span>
      <span className="buzz-card__body">
        <span className="buzz-card__handle">@{item.source.handle}</span>
        <strong>{item.title}</strong>
        <span className="buzz-card__action">{item.action.label}</span>
      </span>
    </Link>
  );
}

export { KIND_ICON };
