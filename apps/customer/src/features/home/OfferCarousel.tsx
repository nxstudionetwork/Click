import { useState } from 'react';
import { Link } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import type { OfferWithStore } from '@click/api';
import { Icon, Sheet } from '../../components/ui';
import { servicePhoto } from '../../config/media';
import { serviceForStoreType } from '../../config/services';
import { formatDateTime } from '../../lib/format';
import { api } from '../../lib/api';
import { HomeSection, Rail, RailItem, RailSkeleton, SectionEmpty, SectionError } from './HomeSection';

/** Splits an offer title into a bold headline ("20% OFF") and the rest, when it starts with a value. */
export function offerHeadline(title: string): { big: string; rest: string } {
  const m = title.match(/^((?:flat\s+)?(?:₹\s?\d[\d,]*|\d+%)\s*(?:off)?|free delivery|buy \d+ get \d+(?: free)?)/i);
  if (!m) return { big: '', rest: title };
  return { big: m[1]!.trim().toUpperCase(), rest: title.slice(m[1]!.length).replace(/^[\s,:–-]+/, '') };
}

/** Open stores first, then alternate services (food, groceries, shopping) so the row shows Click.'s range. */
export function interleaveOffers(offers: OfferWithStore[]): OfferWithStore[] {
  const groups = new Map<string, OfferWithStore[]>();
  for (const o of [...offers].sort((a, b) => Number(b.store.isOpen) - Number(a.store.isOpen))) {
    const k = o.store.storeType;
    groups.set(k, [...(groups.get(k) ?? []), o]);
  }
  const order = ['restaurant', 'grocery', 'retail'].filter((k) => groups.has(k)).concat([...groups.keys()].filter((k) => !['restaurant', 'grocery', 'retail'].includes(k)));
  const out: OfferWithStore[] = [];
  for (let i = 0; out.length < offers.length; i++) for (const k of order) { const o = groups.get(k)![i]; if (o) out.push(o); }
  return out;
}

export function OfferCarousel() {
  const offers = useQuery({ queryKey: ['offers', 'all'], queryFn: () => api.catalog.offers() });
  const [open, setOpen] = useState<OfferWithStore | null>(null);
  return (
    <HomeSection id="offers" title="Offers for you" subtitle="More ways to save on Click." to="/offers" icon="tag" theme="rewards">
      {offers.isPending ? <RailSkeleton variant="wide" count={3} /> : offers.isError ? <SectionError onRetry={() => offers.refetch()} /> :
        offers.data.results.length === 0 ? <SectionEmpty icon="tag" title="No offers right now" text="New deals from stores near you will show up here." /> : (
          <Rail label="Offers" variant="wide">
            {interleaveOffers(offers.data.results).slice(0, 10).map((o) => <RailItem key={o.id}><OfferTile offer={o} onOpen={() => setOpen(o)} /></RailItem>)}
          </Rail>
        )}
      <OfferSheet offer={open} onClose={() => setOpen(null)} />
    </HomeSection>
  );
}

function OfferTile({ offer, onOpen }: { offer: OfferWithStore; onOpen: () => void }) {
  const svc = serviceForStoreType(offer.store.storeType);
  const photo = servicePhoto(svc.theme);
  const { big, rest } = offerHeadline(offer.title);
  return (
    <button className={`offer ${offer.store.isOpen ? '' : 'offer--closed'}`} data-theme={svc.theme} onClick={onOpen} aria-label={`${offer.title} at ${offer.store.name}. View offer`}>
      {photo && <img className="offer__photo" src={photo.src} srcSet={photo.srcSet} sizes="320px" alt="" loading="lazy" decoding="async" />}
      <span className="offer__shade" aria-hidden="true" />
      <span className="offer__body">
        <span className="offer__svc"><Icon name={svc.icon} size={14} />{svc.short ?? svc.name}</span>
        {big && <span className="offer__big">{big}</span>}
        <span className="offer__title">{rest || offer.title}</span>
        <span className="offer__store">{offer.store.name}</span>
        <span className="offer__cta">View offer <Icon name="right" size={14} /></span>
      </span>
    </button>
  );
}

function OfferSheet({ offer, onClose }: { offer: OfferWithStore | null; onClose: () => void }) {
  if (!offer) return null;
  const svc = serviceForStoreType(offer.store.storeType);
  return (
    <Sheet open onClose={onClose} label={`Offer: ${offer.title}`}>
      <div className="offer-sheet" data-theme={svc.theme}>
        <div className="offer-sheet__band">
          <span className="offer__svc"><Icon name={svc.icon} size={14} />{svc.name}</span>
          <h2>{offer.title}</h2>
          <p>{offer.store.name}</p>
          <button className="icon-btn offer-sheet__close" aria-label="Close" onClick={onClose}><Icon name="close" /></button>
        </div>
        <div className="stack" style={{ padding: 'var(--s-5)' }}>
          {offer.description && <p>{offer.description}</p>}
          <dl className="offer-sheet__terms">
            <div><dt>Where</dt><dd>{offer.store.name} on Click. {svc.name}</dd></div>
            <div><dt>Valid</dt><dd>{offer.endsAt ? `Until ${formatDateTime(offer.endsAt)}` : 'While the store runs it'}</dd></div>
            <div><dt>Status</dt><dd>{offer.store.isOpen ? 'Store is open now' : 'Store is closed right now'}</dd></div>
          </dl>
          <p className="small muted">Offers are set by the store. Your bill at checkout shows exactly what is applied before you pay.</p>
          <Link to={`/stores/${offer.store.slug}`} className="btn btn--primary btn--block" onClick={onClose}>
            {offer.store.isOpen ? (svc.id === 'food' ? 'Order from this store' : 'Shop this store') : 'View store'}
          </Link>
        </div>
      </div>
    </Sheet>
  );
}
