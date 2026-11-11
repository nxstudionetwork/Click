import { useState } from 'react';
import { Link, useParams, useSearchParams } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { EmptyState, ErrorState, Icon, Sheet, Skeleton } from '../components/ui';
import { useThemeOverride } from '../components/layout/AppShell';
import { fmtDate, PackageCardView, ProviderMark, RatingLine, SaveButton, Section } from '../features/events/parts';
import { api } from '../lib/api';
import { useDeliveryLocation } from '../location/LocationProvider';

/** An event team, specialist or venue: trust signals, services, packages, venue details, portfolio (their own uploads
 *  only), reviews from completed bookings, FAQs, and Request quote / Book. No personal phone numbers are shown. */
export function EventProviderPage() {
  useThemeOverride('events');
  const { id = '' } = useParams();
  const [sp] = useSearchParams();
  const { selected } = useDeliveryLocation();
  const params = { address: selected?.id, date: sp.get('date') ?? undefined, guests: sp.get('guests') ?? undefined };
  const q = useQuery({ queryKey: ['eventhub', 'provider', id, params], queryFn: () => api.eventHub.provider(id, params) });
  const [photo, setPhoto] = useState<number | null>(null);
  const [faq, setFaq] = useState<number | null>(0);

  if (q.isError) return <div className="ev-page"><ErrorState error={q.error} onRetry={() => q.refetch()} /></div>;
  if (!q.data) return <div className="ev-page"><Skeleton height={240} radius={26} /><Skeleton height={320} radius={22} /></div>;
  const p = q.data;
  const v = p.venue;
  const upcomingOff = p.unavailableDates.slice(0, 6);

  return (
    <div className="ev-page" data-theme="events" style={{ ['--ev-accent' as string]: p.accent }}>
      <Link to={p.kind === 'venue' ? '/events/venues' : '/events/teams'} className="ev-back"><Icon name="back" size={18} /> {p.kind === 'venue' ? 'Venues' : 'Event teams'}</Link>
      <header className="ev-profile">
        <div className="ev-profile__cover">{p.coverUrl ? <img src={p.coverUrl} alt="" /> : <span className="ev-card__pattern" aria-hidden="true" />}</div>
        <div className="ev-profile__id">
          <ProviderMark p={p} size={88} />
          <div>
            <span className="ev-kicker">{p.kindLabel}{v ? ` · ${v.spaceType}` : ''}</span>
            <h1>{p.name}</h1>
            {p.tagline && <p className="ev-muted">{p.tagline}</p>}
            <div className="ev-profile__trust">
              <RatingLine r={p.rating} />
              {p.verified && <span className="ev-verified"><Icon name="shield" size={13} /> Verified by Click.</span>}
              {p.featured && <span className="ev-badge ev-badge--gold">Featured</span>}
            </div>
          </div>
          <SaveButton target={{ eventProviderId: p.id }} favoriteId={p.favoriteId} name={p.name} />
        </div>
      </header>

      <div className="ev-stats">
        <div><strong>{p.eventsCompleted}</strong><span className="small ev-muted">events on Click.</span></div>
        {p.experienceYears != null && <div><strong>{p.experienceYears} yrs</strong><span className="small ev-muted">experience</span></div>}
        {v ? <div><strong>{v.seated}–{v.floating}</strong><span className="small ev-muted">guests (seated–floating)</span></div>
          : p.teamSize != null && <div><strong>{p.teamSize}</strong><span className="small ev-muted">team size</span></div>}
        <div><strong>{p.serviceRadiusKm} km</strong><span className="small ev-muted">from {p.area}</span></div>
      </div>
      {p.response && <p className="ev-note"><Icon name="clock" size={14} /> {p.response}</p>}
      {p.availability && <p className={`ev-note ev-note--${p.availability.state}`}><Icon name="ticket" size={14} /> {p.availability.label} ({fmtDate(sp.get('date'))})</p>}

      <div className="ev-cta">
        <Link to={`/events/plan?provider=${p.id}`} className="ev-btn ev-btn--big">Request quote</Link>
        {p.packages.length > 0 && <a href="#packages" className="ev-btn ev-btn--ghost ev-btn--big">Book a package</a>}
      </div>

      {p.about && <Section title="About"><p className="ev-about">{p.about}</p>{p.languages.length > 0 && <p className="small ev-muted">Speaks {p.languages.join(', ')}</p>}</Section>}

      <Section title={v ? 'What’s available' : 'Services'}>
        <div className="ev-chips">{p.services.map((s) => <span key={s.slug} className="ev-chip ev-chip--lg">{s.name}</span>)}</div>
        {p.eventTypes.length > 0 && <p className="small ev-muted">Event types: {p.eventTypes.join(', ')}</p>}
        <p className="small ev-muted">Takes {p.guestsRange[0] ?? 1}–{p.guestsRange[1] ?? 'any number of'} guests · {p.minNoticeDays} days’ notice · up to {p.maxEventsPerDay} event{p.maxEventsPerDay > 1 ? 's' : ''} a day</p>
      </Section>

      {v && (
        <Section title="Venue details">
          <dl className="ev-dl">
            <dt>Address</dt><dd>{v.address}</dd>
            <dt>Space</dt><dd>{[v.indoor && 'Indoor', v.outdoor && 'Outdoor'].filter(Boolean).join(' + ')} · {v.spaceType}</dd>
            <dt>Capacity</dt><dd>{v.seated} seated · {v.floating} floating</dd>
            {v.hours && <><dt>Hours</dt><dd>{v.hours}</dd></>}
            {v.parking && <><dt>Parking</dt><dd>{v.parking}</dd></>}
            <dt>Catering</dt><dd>{v.cateringPolicy}</dd>
          </dl>
          {v.amenities.length > 0 && <div className="ev-chips">{v.amenities.map((a) => <span key={a} className="ev-chip"><Icon name="check" size={12} /> {a}</span>)}</div>}
          {v.rules.length > 0 && <ul className="ev-rules">{v.rules.map((r) => <li key={r} className="small">{r}</li>)}</ul>}
        </Section>
      )}

      <Section id="packages" title="Packages" kicker={p.packages.length ? 'Prices set by the provider' : undefined}>
        {p.packages.length === 0 ? <p className="small ev-muted">No fixed packages — request a quote for your event.</p> : (
          <div className="ev-grid">{p.packages.map((pkg) => <PackageCardView key={pkg.id} pkg={pkg} action={<Link to={`/events/book?package=${pkg.id}`} className="ev-btn ev-btn--sm">Book</Link>} />)}</div>
        )}
      </Section>

      <Section title="Availability" kicker="From their calendar and Click. bookings">
        {upcomingOff.length === 0 ? <p className="small">No dates blocked in the coming weeks. Pick your date when you book or request a quote.</p>
          : <p className="small">Not available: {upcomingOff.map((d) => fmtDate(d, { day: 'numeric', month: 'short' })).join(', ')}{p.unavailableDates.length > 6 ? '…' : ''}</p>}
      </Section>

      <Section title="Portfolio" kicker="Photos uploaded by the provider">
        {p.portfolio.length === 0 ? <p className="small ev-muted">No portfolio photos uploaded yet.</p> : (
          <div className="ev-portfolio">{p.portfolio.map((x, i) => (
            <button key={x.id} type="button" onClick={() => setPhoto(i)} aria-label={x.caption || 'Open photo'}><img src={x.thumb} alt={x.caption} loading="lazy" /></button>
          ))}</div>
        )}
      </Section>

      <Section title="Reviews" kicker={p.rating ? `${p.rating.average} from ${p.rating.count} verified bookings` : 'From customers who booked through Click.'}>
        {Object.keys(p.aspects).length > 0 && (
          <div className="ev-aspects">{([['quality', 'Quality'], ['communication', 'Communication'], ['value', 'Value']] as const).map(([k, l]) => p.aspects[k] != null && (
            <div key={k}><span className="small">{l}</span><span className="ev-bar"><span style={{ width: `${(p.aspects[k]! / 5) * 100}%` }} /></span><strong className="small">{p.aspects[k]}</strong></div>
          ))}</div>
        )}
        {p.reviews.length === 0 ? <EmptyState icon="star" title="No reviews yet" message="Only customers with a completed booking can review." /> : (
          <ul className="ev-reviews">{p.reviews.map((r) => (
            <li key={r.id}>
              <div className="ev-reviews__top"><strong>{r.author}</strong><span className="ev-rating"><Icon name="star" size={12} /> {r.overall}</span></div>
              <span className="small ev-muted">{r.eventType} · {new Date(r.createdAt).toLocaleDateString('en-IN', { month: 'short', year: 'numeric' })} · <Icon name="check" size={11} /> Verified booking</span>
              {r.comment && <p>{r.comment}</p>}
            </li>
          ))}</ul>
        )}
      </Section>

      {p.faqs.length > 0 && (
        <Section title="FAQs">
          <div className="ev-faqs">{p.faqs.map((f, i) => (
            <div key={f.q} className="ev-faq">
              <button type="button" aria-expanded={faq === i} onClick={() => setFaq(faq === i ? null : i)}>{f.q}<Icon name="chevron" size={16} /></button>
              {faq === i && <p className="small">{f.a}</p>}
            </div>
          ))}</div>
          <p className="small ev-muted">Cancellation: free until {p.cancellation.freeDays} days before the event; after that {p.cancellation.feePercent}% is kept.</p>
        </Section>
      )}

      <Sheet open={photo != null} onClose={() => setPhoto(null)} label="Portfolio photo">
        {photo != null && p.portfolio[photo] && <figure className="ev-photo"><img src={p.portfolio[photo]!.src} alt={p.portfolio[photo]!.caption} /><figcaption className="small">{p.portfolio[photo]!.caption}</figcaption></figure>}
      </Sheet>
    </div>
  );
}
