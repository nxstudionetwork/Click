import { Link, useNavigate } from 'react-router-dom';
import type { BuddyAction, BuddyCard, BuddyMessage } from '@click/api';
import { Button, Icon } from '../../components/ui';
import { BookingCard } from '../bookings/BookingCard';
import { EventCard } from '../bookings/EventCard';
import { ProductCard as GroceryCard, StoreCard as GroceryStoreCard } from '../groceries/parts';
import { useAddToCart } from '../menu/useAddToCart';
import { OfferCard } from '../offers/OfferCard';
import { OrderCard } from '../orders/OrderCard';
import { ProductCard } from '../stores/ProductCard';
import { StoreCard } from '../stores/StoreCard';
import { formatMoney } from '../../lib/format';
import type { PendingAction } from './useBuddyChat';

export const QUICK = [
  { label: 'Find something', prompt: 'Find wireless earbuds under 2000', icon: 'search' },
  { label: 'Order food', prompt: 'Find vegetarian food near me', icon: 'food' },
  { label: 'Book a ride', prompt: 'Find a ride to the airport', icon: 'ride' },
  { label: 'Shop', prompt: 'Open Shop', icon: 'shop' },
  { label: 'Track parcel', prompt: 'Track my parcel', icon: 'parcel' },
  { label: 'Find a service', prompt: 'Find a plumber near my home', icon: 'wrench' },
  { label: 'Plan an event', prompt: 'Plan a birthday party for 30 people next Saturday', icon: 'gift' },
  { label: 'Find a hotel', prompt: 'Find a hotel in Hyderabad this weekend with breakfast', icon: 'hotel' },
] as const;

function Cards({ cards }: { cards: BuddyCard[] }) {
  const { addToCart, isAdding } = useAddToCart();
  const nav = useNavigate();
  if (!cards.length) return null;
  return (
    <div className="bd-cards">{cards.map((c, i) => {
      switch (c.type) {
        case 'store': return <StoreCard key={i} store={c.store} />;
        case 'product': return <ProductCard key={i} product={c.product} currency={c.product.store.currency} canOrder={c.product.store.isOpen} busy={isAdding} onAdd={() => addToCart(c.product)} showStore />;
        case 'event': return <EventCard key={i} event={c.event} />;
        case 'order': return <div key={i} className="card bd-wide"><OrderCard order={c.order} /></div>;
        case 'booking': return <div key={i} className="card bd-wide"><BookingCard booking={c.booking} /></div>;
        case 'offer': return <OfferCard key={i} offer={c.offer} />;
        case 'grocery': return <div key={i} className="gr-scope"><GroceryCard l={c.listing} /></div>;
        case 'grocery_store': return <div key={i} className="gr-scope"><GroceryStoreCard s={c.store} /></div>;
        case 'hotel': {
          const h = c.hotel;
          return (
            <button key={i} type="button" className="bd-hotel" onClick={() => nav(`/hotels/${h.id}`)}>
              <span className="bd-kicker">{h.typeLabel}{h.starRating ? ` · ${h.starRating}★` : ''} · {h.area}</span>
              <strong>{h.name}</strong>
              <span className="small">{h.rating ? `${h.rating.average}/10 ${h.rating.label} (${h.rating.count})` : 'New on Click.'}</span>
              <span className="bd-hotel__price"><strong>{formatMoney(h.price.perNight)}</strong><span className="small">/night · {formatMoney(h.price.total)} total incl. tax</span></span>
              <span className="small bd-muted">{h.freeCancellation ? 'Free cancellation · ' : ''}{h.mealLabel}</span>
            </button>
          );
        }
        case 'hotel_booking': {
          const b = c.booking;
          return (
            <Link key={i} to={`/hotels/bookings/${b.id}`} className="bd-hotel bd-wide">
              <span className="bd-kicker">{b.number} · {b.status}</span><strong>{b.property}</strong>
              <span className="small">{b.checkIn} → {b.checkOut} · {formatMoney(b.total)} · {b.payment}</span>
            </Link>
          );
        }
        case 'journey': {
          const j = c.journey;
          const t = (x: string) => new Date(x).toLocaleTimeString('en-IN', { hour: 'numeric', minute: '2-digit', timeZone: 'Asia/Kolkata' });
          return (
            <Link key={i} to={`/travel/journey/${j.journeyId}/${j.fromStopId}/${j.toStopId}`} className="bd-hotel">
              <span className="bd-kicker">{j.mode} · {j.operator} {j.number}</span>
              <strong>{t(j.departsAt)} {j.from} → {t(j.arrivesAt)} {j.to}</strong>
              <span className="small">{Math.floor(j.durationMinutes / 60)}h {j.durationMinutes % 60}m{j.mode === 'flight' ? ` · ${j.stops ? `${j.stops} stop` : 'non-stop'}` : ''} · {j.class}</span>
              {j.lowest && <span className="bd-hotel__price"><strong>{formatMoney(j.lowest)}</strong><span className="small">per person incl. GST</span></span>}
            </Link>
          );
        }
        case 'attraction': {
          const a = c.attraction;
          return (
            <Link key={i} to={`/bookings/places/${a.slug}`} className="bd-hotel">
              <span className="bd-kicker">{a.kindLabel} · {a.city}</span><strong>{a.name}</strong>
              <span className="small">{a.bookable ? `${a.bookingTypes.join(', ') || 'Tickets'}${a.fromPrice != null ? ` · ${Number(a.fromPrice) ? `from ${formatMoney(a.fromPrice)}` : 'free'}` : ''}` : 'Information only — booked through official channels'}</span>
              {a.rating && <span className="small bd-muted">★ {a.rating.average} ({a.rating.count} verified visits)</span>}
            </Link>
          );
        }
        case 'reservation': {
          const r = c.reservation;
          return (
            <Link key={i} to={r.link} className="bd-hotel bd-wide">
              <span className="bd-kicker">{r.kindLabel} · {r.reference} · {r.statusLabel}</span><strong>{r.title}</strong>
              <span className="small">{r.subtitle}{r.when ? ` · ${new Date(r.when).toLocaleString('en-IN', { weekday: 'short', day: 'numeric', month: 'short', hour: 'numeric', minute: '2-digit', timeZone: 'Asia/Kolkata' })}` : ''}</span>
            </Link>
          );
        }
        case 'action_result': {
          const r = c.result;
          const ok = r.status === 'done' || r.status === 'confirmed';
          return (
            <div key={i} className={`bd-result bd-wide bd-result--${ok ? 'ok' : r.status === 'cancelled' ? 'muted' : 'bad'}`} role="status">
              <Icon name={ok ? 'check' : 'alert'} size={16} />
              <span>{r.result.message || r.summary || r.error}</span>
              {r.result.next && <Link to={r.result.next.path} className="bd-link small">{r.result.next.label}</Link>}
            </div>
          );
        }
        default: return null;
      }
    })}</div>
  );
}

export function MessageView({ m, onPrompt, onAction, acting }: {
  m: BuddyMessage & { failed?: boolean }; onPrompt: (t: string) => void; onAction: (a: Extract<BuddyAction, { action: string }>) => void; acting: boolean;
}) {
  const nav = useNavigate();
  if (m.role === 'user') {
    return (
      <div className={`bd-msg bd-msg--user${m.failed ? ' is-failed' : ''}`}>
        {m.attachment?.label && <span className="bd-attach small"><Icon name="pin" size={12} /> {m.attachment.label}</span>}
        <p>{m.content}</p>
        {m.viaVoice && <span className="bd-muted small"><Icon name="mic" size={11} /> spoken</span>}
      </div>
    );
  }
  return (
    <div className="bd-msg bd-msg--buddy">
      <span className="bd-avatar" aria-hidden="true"><Icon name="sparkle" size={14} /></span>
      <div className="bd-msg__body">
        {m.content && <p>{m.content}</p>}
        <Cards cards={m.cards} />
        {m.actions.length > 0 && (
          <div className="bd-actions">{m.actions.map((a, i) => (
            'path' in a ? <button key={i} type="button" className={`bd-chip${i === 0 ? ' bd-chip--primary' : ''}`} onClick={() => nav(a.path)}>{a.label} <Icon name="right" size={12} /></button>
              : 'prompt' in a ? <button key={i} type="button" className="bd-chip" onClick={() => onPrompt(a.prompt)}>{a.label}</button>
                : <button key={i} type="button" className="bd-chip bd-chip--primary" disabled={acting} onClick={() => onAction(a)}><Icon name="sparkle" size={12} /> {a.label}</button>
          ))}</div>
        )}
      </div>
    </div>
  );
}

/** A confirmation-tier action: the server built the summary; nothing happens until the customer confirms. */
export function ConfirmCard({ p, onDecide, busy }: { p: PendingAction; onDecide: (d: 'confirm' | 'cancel') => void; busy: boolean }) {
  return (
    <div className="bd-confirm" role="alertdialog" aria-labelledby="bd-confirm-h" aria-describedby="bd-confirm-d">
      <span className="bd-kicker"><Icon name="shield" size={12} /> Needs your OK</span>
      <h3 id="bd-confirm-h">{p.label}</h3>
      <p id="bd-confirm-d">{p.run.summary}</p>
      {p.run.expiresAt && <span className="small bd-muted">Valid until {new Date(p.run.expiresAt).toLocaleTimeString('en-IN', { hour: 'numeric', minute: '2-digit' })}.</span>}
      <div className="bd-confirm__row">
        <Button variant="secondary" disabled={busy} onClick={() => onDecide('cancel')}>Not now</Button>
        <Button loading={busy} onClick={() => onDecide('confirm')}>Confirm</Button>
      </div>
    </div>
  );
}
