import { useState } from 'react';
import { Link, useParams, useSearchParams } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { EmptyState, ErrorState, Icon, Sheet, Skeleton } from '../components/ui';
import { useThemeOverride } from '../components/layout/AppShell';
import { AvailabilityPill, FavoriteButton, PRICING_HINT, ProAvatar, Rating, Section } from '../features/pros/parts';
import { api } from '../lib/api';
import { useDeliveryLocation } from '../location/LocationProvider';

const DAYS = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'];
const t12 = (t: string) => { const [h, m] = t.split(':').map(Number); return `${((h! + 11) % 12) + 1}${m ? `:${String(m).padStart(2, '0')}` : ''} ${h! < 12 ? 'AM' : 'PM'}`; };

/** The professional: who they are (their own photo or a monogram), the trust layer, what they do and charge,
 *  portfolio, hours and reviews. Only facts from the server; rates are shown once there's enough history. */
export function ProProfilePage() {
  useThemeOverride('services');
  const { id = '' } = useParams();
  const [sp] = useSearchParams();
  const job = sp.get('job');
  const { selected } = useDeliveryLocation();
  const q = useQuery({ queryKey: ['services', 'provider', id, selected?.id], queryFn: () => api.services.provider(id, selected?.id) });
  const [photo, setPhoto] = useState<number | null>(null);

  if (q.isError) return <div className="sv-page"><ErrorState error={q.error} onRetry={() => q.refetch()} /></div>;
  if (!q.data) return <div className="sv-page"><Skeleton height={200} radius={22} /><Skeleton height={300} radius={22} /></div>;
  const p = q.data;
  const book = (jobId?: string | null) => `/services/book?pro=${p.id}${jobId ? `&job=${jobId}` : ''}`;
  const since = new Date(p.since).toLocaleDateString('en-IN', { month: 'short', year: 'numeric' });

  return (
    <div className="sv-page" data-theme="services" style={{ ['--sv-accent' as string]: p.accent }}>
      <Link to={p.categories[0] ? `/services/${p.categories[0]}` : '/services'} className="sv-back"><Icon name="back" size={18} /> Back</Link>
      <header className="sv-profile">
        <ProAvatar p={p} size={104} />
        <div className="sv-profile__id">
          <h1>{p.name}</h1>
          <p>{p.profession}{p.verified && <span className="sv-verified"><Icon name="shield" size={13} /> ID verified by Click.</span>}</p>
          <Rating r={p.rating} />
          <AvailabilityPill a={p.availability} label={p.availability === 'now' && p.etaMinutes ? `Available now · ~${p.etaMinutes} min` : p.availabilityLabel} />
        </div>
        <FavoriteButton id={p.id} favoriteId={p.favoriteId} name={p.name} />
      </header>

      <div className="sv-trust">
        {p.experienceYears != null && <div><strong>{p.experienceYears} yrs</strong><span className="small sv-muted">experience</span></div>}
        <div><strong>{p.jobsCompleted.toLocaleString('en-IN')}</strong><span className="small sv-muted">jobs on Click.</span></div>
        {p.rates.completionRate != null && <div><strong>{p.rates.completionRate}%</strong><span className="small sv-muted">completion</span></div>}
        {p.rates.responseRate != null && <div><strong>{p.rates.responseRate}%</strong><span className="small sv-muted">response</span></div>}
        {p.distanceKm != null && <div><strong>{p.distanceKm.toFixed(1)} km</strong><span className="small sv-muted">away</span></div>}
      </div>

      {p.servesLocation === false && <p className="sv-note"><Icon name="alert" size={14} /> {p.name.split(' ')[0]} doesn’t serve your selected address ({p.serviceArea}, {p.serviceRadiusKm} km).</p>}

      <div className="sv-cta">
        <Link to={book(job)} className={`sv-btn sv-btn--big${p.servesLocation === false ? ' is-disabled' : ''}`} aria-disabled={p.servesLocation === false}>
          {p.availability === 'now' ? 'Book now' : 'Book a time'}
        </Link>
      </div>

      {p.about && <Section title="About"><p className="sv-about">{p.about}</p>
        <p className="small sv-muted">{[p.languages.length ? `Speaks ${p.languages.join(', ')}` : '', `Serves ${p.serviceArea} · ${p.serviceRadiusKm} km`, `On Click. since ${since}`].filter(Boolean).join(' · ')}</p></Section>}
      {p.skills.length > 0 && <div className="sv-tags">{p.skills.map((s) => <span key={s} className="sv-chip">{s}</span>)}</div>}
      {p.certificates.length > 0 && (
        <Section title="Certificates" kicker="Checked by Click.">
          <ul className="sv-certs">{p.certificates.map((c) => <li key={c.name}><Icon name="check" size={14} /> {c.name}{c.issuer && <span className="sv-muted"> · {c.issuer}</span>}</li>)}</ul>
        </Section>
      )}

      {p.services.map((cat) => (
        <Section key={cat.slug} title={cat.name} kicker="Services & prices">
          <div className="sv-pricelist">{cat.jobs.map((j) => (
            <div key={j.id} className={`sv-pricerow${j.id === job ? ' is-on' : ''}`}>
              <span><strong>{j.name}</strong><span className="small sv-muted">{PRICING_HINT[j.pricing]}</span></span>
              <span className="sv-pricerow__end"><strong>{j.priceLabel}</strong><Link to={book(j.id)} className="sv-btn sv-btn--sm">Book</Link></span>
            </div>
          ))}</div>
        </Section>
      ))}

      <Section title="Past work" kicker="Photos from the professional">
        {p.portfolio.length === 0 ? <p className="small sv-muted">No work photos uploaded yet.</p> : (
          <div className="sv-portfolio">{p.portfolio.map((x, i) => (
            <button key={x.id} type="button" onClick={() => setPhoto(i)} aria-label={x.caption || 'Open photo'}><img src={x.thumb} alt={x.caption} loading="lazy" /></button>
          ))}</div>
        )}
      </Section>

      <Section title="Working hours">
        {p.hours.length === 0 ? <p className="small sv-muted">No hours set.</p> : (
          <ul className="sv-hours">{DAYS.map((d, i) => {
            const w = p.hours.filter((h) => h.weekday === i);
            return <li key={d}><span>{d}</span><span className={w.length ? '' : 'sv-muted'}>{w.length ? w.map((h) => `${t12(h.starts)} – ${t12(h.ends)}`).join(', ') : 'Off'}</span></li>;
          })}</ul>
        )}
      </Section>

      <Section title="Reviews" kicker={p.rating ? `${p.rating.average} from ${p.rating.count} customers` : 'Verified customers only'}>
        {(p.aspects.quality || p.aspects.behaviour || p.aspects.timeliness) && (
          <div className="sv-aspects">
            {([['quality', 'Work quality'], ['behaviour', 'Behaviour'], ['timeliness', 'On time']] as const).map(([k, l]) => p.aspects[k] != null && (
              <div key={k}><span className="small">{l}</span><span className="sv-bar"><span style={{ width: `${(p.aspects[k]! / 5) * 100}%` }} /></span><strong className="small">{p.aspects[k]}</strong></div>
            ))}
          </div>
        )}
        {p.reviews.length === 0 ? <EmptyState icon="star" title="No reviews yet" message="Reviews come only from customers who booked through Click." /> : (
          <ul className="sv-reviews">{p.reviews.map((r) => (
            <li key={r.id}>
              <div className="sv-reviews__top"><strong>{r.author}</strong><span className="sv-rating"><Icon name="star" size={12} /> {r.overall}</span></div>
              <span className="small sv-muted">{r.job} · {new Date(r.createdAt).toLocaleDateString('en-IN', { day: 'numeric', month: 'short', year: 'numeric' })}</span>
              {r.comment && <p>{r.comment}</p>}
            </li>
          ))}</ul>
        )}
      </Section>

      <Sheet open={photo != null} onClose={() => setPhoto(null)} label="Work photo">
        {photo != null && p.portfolio[photo] && <figure className="sv-photo"><img src={p.portfolio[photo]!.src} alt={p.portfolio[photo]!.caption} /><figcaption>{p.portfolio[photo]!.caption}</figcaption></figure>}
      </Sheet>
    </div>
  );
}
