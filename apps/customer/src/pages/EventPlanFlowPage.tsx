import { useEffect, useMemo, useRef, useState } from 'react';
import { Link, useNavigate, useSearchParams } from 'react-router-dom';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { ApiError } from '@click/api';
import { Button, ErrorState, Icon, Skeleton, useToast } from '../components/ui';
import { useThemeOverride } from '../components/layout/AppShell';
import { evIcon, fmtDate } from '../features/events/parts';
import { api } from '../lib/api';
import { formatMoney } from '../lib/format';
import { useDeliveryLocation } from '../location/LocationProvider';

const STEPS = ['Event', 'Date', 'Location', 'Guests', 'Budget', 'Services', 'Details', 'Review'] as const;
const BUDGETS: { label: string; min: number | null; max: number | null }[] = [
  { label: 'Under ₹25,000', min: null, max: 25000 }, { label: '₹25,000 – ₹75,000', min: 25000, max: 75000 }, { label: '₹75,000 – ₹2 lakh', min: 75000, max: 200000 },
  { label: '₹2 – 5 lakh', min: 200000, max: 500000 }, { label: '₹5 – 15 lakh', min: 500000, max: 1500000 }, { label: 'Above ₹15 lakh', min: 1500000, max: null },
];
const MAX_PHOTOS = 6;

/**
 * Plan an Event: type → date (or flexible) → one of your saved addresses → guests → budget (optional) → services →
 * requirements and reference photos → review. Creates the plan on the server; then shows matching teams, or — when
 * opened from a provider or package — sends that provider the request / continues to booking, as the button says.
 */
export function EventPlanFlowPage() {
  useThemeOverride('events');
  const [sp] = useSearchParams();
  const navigate = useNavigate();
  const toast = useToast();
  const qc = useQueryClient();
  const { addresses, selected } = useDeliveryLocation();
  const registry = useQuery({ queryKey: ['eventhub', 'registry'], queryFn: () => api.eventHub.registry(), staleTime: 300_000 });
  const providerId = sp.get('provider');
  const packageId = sp.get('package');
  const provider = useQuery({ queryKey: ['eventhub', 'provider', providerId, {}], queryFn: () => api.eventHub.provider(providerId!), enabled: !!providerId });

  const [step, setStep] = useState(0);
  const [type, setType] = useState(sp.get('type') ?? '');
  const [title, setTitle] = useState('');
  const [date, setDate] = useState(sp.get('date') ?? '');
  const [flexible, setFlexible] = useState(false);
  const [dateNote, setDateNote] = useState('');
  const [time, setTime] = useState('');
  const [addressId, setAddressId] = useState<string>('');
  const [guests, setGuests] = useState(sp.get('guests') ?? '');
  const [budget, setBudget] = useState<number | 'flexible' | null>(null);
  const [services, setServices] = useState<string[]>(sp.get('services')?.split(',').filter(Boolean) ?? []);
  const [requirements, setRequirements] = useState(sp.get('note') ?? '');
  const [photos, setPhotos] = useState<{ id: string; thumb: string }[]>([]);
  const fileRef = useRef<HTMLInputElement>(null);
  const top = useRef<HTMLDivElement>(null);

  useEffect(() => { if (!addressId && selected) setAddressId(selected.id); }, [selected, addressId]);
  const reg = registry.data;
  const etype = reg?.eventTypes.find((t) => t.slug === type);
  // Choosing a type suggests its usual services (the customer can change them); a provider pre-selects theirs.
  useEffect(() => {
    if (services.length) return;
    if (provider.data) setServices(provider.data.services.map((s) => s.slug).slice(0, 4));
    else if (etype) setServices(etype.suggestedServices);
  }, [etype, provider.data]); // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => { top.current?.scrollIntoView({ block: 'start', behavior: 'smooth' }); }, [step]);

  const today = new Date(); today.setHours(0, 0, 0, 0);
  const minDate = new Date(today.getTime() + 86400000).toISOString().slice(0, 10);
  const guestN = Number(guests);
  const valid = [
    !!type, flexible || (!!date && date >= minDate), !!addressId, guestN >= 1 && guestN <= 100000, true, services.length > 0, true, true,
  ];
  const upload = useMutation({
    mutationFn: (f: File) => api.eventHub.upload(f),
    onSuccess: (r) => setPhotos((ps) => [...ps, { id: r.id, thumb: r.thumb }]),
    onError: (e) => toast(e instanceof ApiError ? e.message : 'Couldn’t upload that photo.', 'error'),
  });
  const b = typeof budget === 'number' ? BUDGETS[budget]! : null;
  const submit = useMutation({
    mutationFn: async () => {
      const plan = await api.eventHub.createPlan({
        eventType: type, title: title.trim(), date: flexible ? null : date, dateFlexible: flexible, dateNote: flexible ? dateNote : '',
        startTime: time || null, addressId, guests: guestN, budgetMin: b?.min != null ? String(b.min) : null, budgetMax: b?.max != null ? String(b.max) : null,
        budgetFlexible: budget === 'flexible' || budget === null, services, requirements: requirements.trim(), attachmentIds: photos.map((p) => p.id),
      });
      if (providerId && !packageId) await api.eventHub.enquire(plan.id, [providerId], requirements.trim().slice(0, 600));
      return plan;
    },
    onSuccess: (plan) => {
      qc.invalidateQueries({ queryKey: ['eventhub'] });
      if (packageId) navigate(`/events/book?package=${packageId}&plan=${plan.id}`, { replace: true });
      else navigate(`/events/plans/${plan.id}${providerId ? '' : '?tab=teams'}`, { replace: true, state: { created: true } });
    },
    onError: (e) => toast(e instanceof ApiError ? e.message : 'Couldn’t save your plan.', 'error'),
  });
  const typeOptions = useMemo(() => {
    const all = reg?.eventTypes ?? [];
    const planner = all.filter((t) => ['birthday', 'wedding', 'engagement', 'corporate', 'college', 'private-party', 'baby-shower', 'anniversary', 'other'].includes(t.slug));
    return [...planner, ...all.filter((t) => !planner.includes(t))];
  }, [reg]);

  if (registry.isError) return <div className="ev-page"><ErrorState error={registry.error} onRetry={() => registry.refetch()} /></div>;
  if (!reg) return <div className="ev-page"><Skeleton height={420} radius={24} /></div>;
  const cta = packageId ? 'Continue to booking' : providerId ? `Send request to ${provider.data?.name ?? 'this team'}` : 'Find Event Teams';

  return (
    <div className="ev-page ev-flow" data-theme="events" ref={top}>
      <Link to={providerId ? `/events/providers/${providerId}` : '/events'} className="ev-back"><Icon name="back" size={18} /> {providerId ? 'Back' : 'Events'}</Link>
      <header className="ev-flow__head">
        <span className="ev-kicker">Plan your event · step {step + 1} of {STEPS.length}</span>
        <h1>{['What are you planning?', 'When is it?', 'Where is it?', 'How many guests?', 'What’s your budget?', 'What do you need?', 'Anything else?', 'Review your request'][step]}</h1>
        {provider.data && <p className="small ev-muted">For {provider.data.name}</p>}
        <div className="ev-progress" role="progressbar" aria-valuemin={1} aria-valuemax={STEPS.length} aria-valuenow={step + 1} aria-label="Progress">
          {STEPS.map((s, i) => <span key={s} className={i <= step ? 'is-on' : ''} />)}
        </div>
      </header>

      <section className="ev-step">
        {step === 0 && (
          <>
            <div className="ev-typegrid" role="radiogroup" aria-label="Event type">
              {typeOptions.map((t) => (
                <button key={t.slug} type="button" role="radio" aria-checked={type === t.slug} className={`ev-typebtn${type === t.slug ? ' is-on' : ''}`}
                  style={{ ['--ev-accent' as string]: t.accent }} onClick={() => { setType(t.slug); if (!providerId) setServices(t.suggestedServices); }}>
                  <span className="ev-type__icon"><Icon name={evIcon(t.icon)} size={20} /></span><span>{t.name}</span>
                </button>
              ))}
            </div>
            <label className="ev-field">Give it a name (optional)
              <input value={title} maxLength={120} onChange={(e) => setTitle(e.target.value)} placeholder={etype ? `e.g. Aarav’s 6th ${etype.name.toLowerCase()}` : 'e.g. Aarav’s 6th birthday'} />
            </label>
          </>
        )}
        {step === 1 && (
          <>
            <div className="ev-seg" role="tablist" aria-label="Date">
              <button type="button" role="tab" aria-selected={!flexible} onClick={() => setFlexible(false)}>Specific date</button>
              <button type="button" role="tab" aria-selected={flexible} onClick={() => setFlexible(true)}>I’m flexible</button>
            </div>
            {flexible ? (
              <label className="ev-field">When roughly?<input value={dateNote} maxLength={120} onChange={(e) => setDateNote(e.target.value)} placeholder="e.g. Any Saturday in March" />
                <span className="small ev-muted">You can get quotes now; set a fixed date before booking.</span></label>
            ) : (
              <>
                <label className="ev-field">Date<input type="date" min={minDate} value={date} onChange={(e) => setDate(e.target.value)} /></label>
                <label className="ev-field">Start time (optional)<input type="time" value={time} onChange={(e) => setTime(e.target.value)} /></label>
              </>
            )}
          </>
        )}
        {step === 2 && (addresses.length === 0 ? (
          <div className="ev-note"><Icon name="pin" size={14} /> You have no saved addresses. <Link to="/account/addresses" className="ev-link">Add one in Profile → Addresses</Link>, then come back.</div>
        ) : (
          <>
            <p className="small ev-muted">Where the event happens — or where you’d like a venue nearby. Uses your saved addresses.</p>
            <div className="ev-addrs" role="radiogroup" aria-label="Location">
              {addresses.map((a) => (
                <button key={a.id} type="button" role="radio" aria-checked={a.id === addressId} className={`ev-addr${a.id === addressId ? ' is-on' : ''}`} onClick={() => setAddressId(a.id)}>
                  <Icon name="pin" size={16} /><span><strong>{a.label}</strong><span className="small ev-muted">{[a.line1, a.line2, a.city].filter(Boolean).join(', ')}</span></span>
                </button>
              ))}
            </div>
            <Link to="/account/addresses" className="ev-link small">Add another address</Link>
          </>
        ))}
        {step === 3 && (
          <>
            <div className="ev-bands" role="radiogroup" aria-label="Guest count">
              {reg.guestBands.map((g) => {
                const pick = g.max >= 100000 ? 600 : Math.round((g.min + g.max) / 2);
                const on = guestN >= g.min && guestN <= g.max;
                return <button key={g.code} type="button" role="radio" aria-checked={on} className={`ev-chipbtn${on ? ' is-on' : ''}`} onClick={() => setGuests(String(pick))}>{g.label}</button>;
              })}
            </div>
            <label className="ev-field">Exact number<input inputMode="numeric" value={guests} onChange={(e) => setGuests(e.target.value.replace(/\D/g, '').slice(0, 6))} placeholder="e.g. 40" /></label>
          </>
        )}
        {step === 4 && (
          <>
            <div className="ev-bands" role="radiogroup" aria-label="Budget">
              {BUDGETS.map((x, i) => <button key={x.label} type="button" role="radio" aria-checked={budget === i} className={`ev-chipbtn${budget === i ? ' is-on' : ''}`} onClick={() => setBudget(i)}>{x.label}</button>)}
              <button type="button" role="radio" aria-checked={budget === 'flexible'} className={`ev-chipbtn${budget === 'flexible' ? ' is-on' : ''}`} onClick={() => setBudget('flexible')}>Flexible</button>
            </div>
            <p className="small ev-muted">Optional. Teams see it so their quotes fit; it’s never charged.</p>
          </>
        )}
        {step === 5 && (
          <div className="ev-svcgrid" role="group" aria-label="Services needed">
            {reg.services.map((s) => {
              const on = services.includes(s.slug);
              return (
                <button key={s.slug} type="button" aria-pressed={on} className={`ev-svcbtn${on ? ' is-on' : ''}`} onClick={() => setServices(on ? services.filter((x) => x !== s.slug) : [...services, s.slug])}>
                  <Icon name={on ? 'check' : evIcon(s.icon)} size={16} /> {s.name}
                </button>
              );
            })}
          </div>
        )}
        {step === 6 && (
          <>
            <label className="ev-field">Your requirements
              <textarea className="ev-textarea" rows={5} maxLength={2000} value={requirements} onChange={(e) => setRequirements(e.target.value)}
                placeholder="e.g. I need a birthday setup for 40 people with a superhero theme." />
            </label>
            <div className="ev-photos">
              {photos.map((p) => (
                <span key={p.id} className="ev-thumb"><img src={p.thumb} alt="Reference" />
                  <button type="button" aria-label="Remove photo" onClick={() => { setPhotos((ps) => ps.filter((x) => x.id !== p.id)); api.eventHub.removeUpload(p.id).catch(() => undefined); }}><Icon name="close" size={12} /></button></span>
              ))}
              {photos.length < MAX_PHOTOS && (
                <button type="button" className="ev-thumb ev-thumb--add" onClick={() => fileRef.current?.click()} disabled={upload.isPending}>
                  <Icon name="camera" size={20} /><span className="small">{upload.isPending ? 'Uploading…' : 'Add reference'}</span>
                </button>
              )}
              <input ref={fileRef} type="file" accept="image/jpeg,image/png,image/webp" hidden onChange={(e) => { const f = e.target.files?.[0]; if (f) upload.mutate(f); e.target.value = ''; }} />
            </div>
            <p className="small ev-muted">Up to {MAX_PHOTOS} reference photos. Only teams you send the request to can see them.</p>
          </>
        )}
        {step === 7 && (
          <dl className="ev-dl ev-review">
            <dt>Event</dt><dd>{etype?.name}{title ? ` · ${title}` : ''}</dd>
            <dt>Date</dt><dd>{flexible ? `Flexible${dateNote ? ` · ${dateNote}` : ''}` : `${fmtDate(date)}${time ? `, ${time}` : ''}`}</dd>
            <dt>Location</dt><dd>{addresses.find((a) => a.id === addressId)?.line1}</dd>
            <dt>Guests</dt><dd>{guestN}</dd>
            <dt>Budget</dt><dd>{b ? b.label : 'Flexible'}</dd>
            <dt>Services</dt><dd>{services.map((s) => reg.services.find((x) => x.slug === s)?.name).join(', ')}</dd>
            <dt>Requirements</dt><dd>{requirements.trim() || '—'}</dd>
            <dt>Attachments</dt><dd>{photos.length ? `${photos.length} photo${photos.length > 1 ? 's' : ''}` : 'None'}</dd>
          </dl>
        )}
      </section>

      <div className="ev-flow__nav">
        {step > 0 && <Button variant="secondary" onClick={() => setStep(step - 1)}>Back</Button>}
        {step < STEPS.length - 1
          ? <Button disabled={!valid[step]} onClick={() => setStep(step + 1)}>{step === 4 && budget === null ? 'Skip' : 'Next'}</Button>
          : <Button loading={submit.isPending} onClick={() => submit.mutate()}>{cta}</Button>}
      </div>
      {step === 7 && <p className="small ev-muted">Nothing is booked or charged now. {providerId ? 'The team replies with a quote you can accept, change or decline.' : 'Next you’ll see teams and venues that can take this event.'}</p>}
      {step === 4 && b && <p className="small ev-muted">Teams will see {b.min ? formatMoney(String(b.min)) : 'up to'} {b.max ? `– ${formatMoney(String(b.max))}` : '+'}.</p>}
    </div>
  );
}
