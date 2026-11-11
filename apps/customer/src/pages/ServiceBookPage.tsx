import { useEffect, useMemo, useRef, useState } from 'react';
import { Link, useNavigate, useSearchParams } from 'react-router-dom';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { ApiError, type ServiceJobInfo } from '@click/api';
import { Button, EmptyState, ErrorState, Icon, Sheet, Skeleton, useToast } from '../components/ui';
import { useThemeOverride } from '../components/layout/AppShell';
import { catIcon, PRICING_HINT, ProAvatar, Rating } from '../features/pros/parts';
import { api } from '../lib/api';
import { formatMoney } from '../lib/format';
import { useDeliveryLocation } from '../location/LocationProvider';

const MAX_PHOTOS = 5;
const newKey = () => (globalThis.crypto?.randomUUID?.() ?? `${Date.now()}-${Math.random().toString(36).slice(2)}`);

/**
 * Requirement → when → summary → confirm. The price, the professionals who can take it and the free slots all come from
 * the server's estimate; the booking is sent with the amount the customer saw, so a price change is caught, not charged.
 * No payment happens here: the customer pays after the work is completed.
 */
export function ServiceBookPage() {
  useThemeOverride('services');
  const [sp] = useSearchParams();
  const navigate = useNavigate();
  const toast = useToast();
  const qc = useQueryClient();
  const { addresses, selected } = useDeliveryLocation();
  const proId = sp.get('pro');
  const rebookOf = sp.get('rebook');
  const [category, setCategory] = useState<string | null>(sp.get('category'));
  const [jobId, setJobId] = useState<string | null>(sp.get('job'));
  const [mode, setMode] = useState<'now' | 'scheduled'>(sp.get('mode') === 'scheduled' ? 'scheduled' : 'now');
  const [start, setStart] = useState<string | null>(null);
  const [day, setDay] = useState<string | null>(null);
  const [hours, setHours] = useState<number | null>(null);
  const [addressId, setAddressId] = useState<string | null>(selected?.id ?? null);
  const [description, setDescription] = useState('');
  const [photos, setPhotos] = useState<{ id: string; thumb: string }[]>([]);
  const [summaryOpen, setSummaryOpen] = useState(false);
  const idem = useRef(newKey());
  const fileRef = useRef<HTMLInputElement>(null);

  useEffect(() => { if (!addressId && selected) setAddressId(selected.id); }, [selected, addressId]);

  const rebook = useQuery({ queryKey: ['services', 'rebook', rebookOf], queryFn: () => api.services.rebook(rebookOf!), enabled: !!rebookOf });
  useEffect(() => {
    const r = rebook.data;
    if (!r) return;
    setCategory(r.category); setJobId(r.jobId); setDescription(r.description); setHours(r.hours);
    if (r.addressId) setAddressId(r.addressId);
  }, [rebook.data]);
  const effectivePro = proId ?? rebook.data?.providerId ?? null;

  const pro = useQuery({ queryKey: ['services', 'provider', effectivePro, addressId], queryFn: () => api.services.provider(effectivePro!, addressId), enabled: !!effectivePro });
  const home = useQuery({ queryKey: ['services', 'home', addressId], queryFn: () => api.services.home({ address: addressId }), enabled: !effectivePro && !category && !jobId });
  const cat = useQuery({ queryKey: ['services', 'category', category, { address: addressId ?? undefined }], queryFn: () => api.services.category(category!, { address: addressId ?? undefined }),
    enabled: !effectivePro && !!category });

  // Jobs on offer: the chosen professional's, or the chosen category's. A job id from the URL also tells us the category.
  const jobs: (ServiceJobInfo & { categoryName?: string })[] = useMemo(() => {
    if (effectivePro && pro.data) return pro.data.services.flatMap((s) => s.jobs.map((j) => ({ ...j, categoryName: s.name })));
    return cat.data?.jobs ?? [];
  }, [effectivePro, pro.data, cat.data]);
  const job = jobs.find((j) => j.id === jobId) ?? null;

  const input = { jobId: jobId!, providerId: effectivePro, addressId, mode, scheduledStart: mode === 'scheduled' ? start : null, hours: job?.pricing === 'hourly' ? hours ?? job.minHours : null };
  const est = useQuery({ queryKey: ['services', 'estimate', input], queryFn: () => api.services.estimate(input), enabled: !!jobId, placeholderData: (prev) => prev });
  const e = est.data;

  // A job only bookable one way switches the mode for the customer.
  useEffect(() => {
    if (!job) return;
    if (mode === 'now' && !job.instant && job.schedulable) setMode('scheduled');
    if (mode === 'scheduled' && !job.schedulable && job.instant) setMode('now');
  }, [job, mode]);

  // Arriving with only a job id (e.g. from search or Buddy): load that job's category so its details show.
  useEffect(() => { if (!effectivePro && !category && e?.job.categorySlug) setCategory(e.job.categorySlug); }, [effectivePro, category, e?.job.categorySlug]);

  const days = useMemo(() => [...new Set((e?.slots ?? []).map((s) => s.day))], [e?.slots]);
  const activeDay = day && days.includes(day) ? day : days[0] ?? null;

  const upload = useMutation({
    mutationFn: (f: File) => api.services.upload(f),
    onSuccess: (r) => setPhotos((ps) => [...ps, { id: r.id, thumb: r.thumb }]),
    onError: (err) => toast(err instanceof ApiError ? err.message : 'Couldn’t upload that photo.', 'error'),
  });
  const removePhoto = (id: string) => { setPhotos((ps) => ps.filter((p) => p.id !== id)); api.services.removeUpload(id).catch(() => undefined); };

  const book = useMutation({
    mutationFn: () => api.services.book({ ...input, addressId: addressId!, description: description.trim(), attachmentIds: photos.map((p) => p.id),
      expectedAmount: e?.agreed ?? null, idempotencyKey: idem.current, rebookOf }),
    onSuccess: (b) => {
      qc.invalidateQueries({ queryKey: ['services'] });
      navigate(`/services/bookings/${b.id}`, { replace: true, state: { justBooked: true } });
    },
    onError: (err) => {
      if (err instanceof ApiError && (err.code === 'price_changed' || err.code === 'not_available')) {
        qc.invalidateQueries({ queryKey: ['services', 'estimate'] });
        idem.current = newKey();
      }
      toast(err instanceof ApiError ? err.message : 'Couldn’t book.', 'error');
    },
  });

  if (rebook.isPending && rebookOf) return <div className="sv-page"><Skeleton height={300} radius={22} /></div>;

  const pickCategory = !effectivePro && !category;
  const hoursValue = hours ?? job?.minHours ?? 1;

  return (
    <div className="sv-page sv-book" data-theme="services">
      <Link to={effectivePro ? `/services/pro/${effectivePro}` : category ? `/services/${category}` : '/services'} className="sv-back"><Icon name="back" size={18} /> Back</Link>
      <h1 className="sv-title">{rebookOf ? 'Book again' : mode === 'now' && !jobId ? 'Get help now' : 'Book a professional'}</h1>

      {pro.data && (
        <div className="sv-bookpro">
          <ProAvatar p={pro.data} size={52} />
          <div><strong>{pro.data.name}</strong><span className="small sv-muted">{pro.data.profession}</span><Rating r={pro.data.rating} compact /></div>
          {!proId && rebookOf && <span className="sv-chip">Same professional</span>}
        </div>
      )}

      {/* 1 · Service */}
      <section className="sv-step" aria-labelledby="st-1">
        <h2 id="st-1"><span>1</span> What do you need?</h2>
        {pickCategory ? (
          home.isPending ? <Skeleton height={120} /> : home.isError ? <ErrorState error={home.error} onRetry={() => home.refetch()} /> : (
            <div className="sv-catgrid">
              {home.data!.categories.map((c) => (
                <button key={c.slug} type="button" className="sv-cat" style={{ ['--sv-accent' as string]: c.accent }} onClick={() => setCategory(c.slug)}>
                  <span className="sv-cat__icon"><Icon name={catIcon(c.icon)} size={22} /></span><span className="sv-cat__name">{c.name}</span>
                </button>
              ))}
              {home.data!.categories.length === 0 && <EmptyState icon="wrench" title="No professionals serve this address yet" action={<Link to="/services/request" className="btn btn--primary">Tell Click what you need</Link>} />}
            </div>
          )
        ) : (pro.isPending && effectivePro) || (cat.isPending && category) ? <Skeleton height={120} /> : (
          <>
            {!effectivePro && cat.data && <button type="button" className="sv-link small" onClick={() => { setCategory(null); setJobId(null); }}>{cat.data.name} · change</button>}
            <div className="sv-jobs" role="radiogroup" aria-label="Choose a job">
              {jobs.map((j) => (
                <button key={j.id} type="button" role="radio" aria-checked={j.id === jobId} className={`sv-job${j.id === jobId ? ' is-on' : ''}`} onClick={() => { setJobId(j.id); setStart(null); }}>
                  <span className="sv-job__name"><strong>{j.name}</strong></span>
                  <span className="sv-job__price">{j.priceLabel}<span className="small sv-muted"> · {j.pricingLabel}</span></span>
                </button>
              ))}
            </div>
          </>
        )}
        {job && <p className="small sv-hint"><Icon name="receipt" size={14} /> {PRICING_HINT[job.pricing]}</p>}
      </section>

      {job && (
        <>
          {/* 2 · Describe */}
          <section className="sv-step" aria-labelledby="st-2">
            <h2 id="st-2"><span>2</span> Describe the problem</h2>
            <textarea className="sv-textarea" rows={3} maxLength={1000} value={description} onChange={(ev) => setDescription(ev.target.value)}
              placeholder="e.g. The kitchen tap leaks from the base when it's turned on." aria-label="Describe the problem" />
            <div className="sv-photos">
              {photos.map((p) => (
                <span key={p.id} className="sv-thumb"><img src={p.thumb} alt="Your photo" /><button type="button" aria-label="Remove photo" onClick={() => removePhoto(p.id)}><Icon name="close" size={12} /></button></span>
              ))}
              {photos.length < MAX_PHOTOS && (
                <button type="button" className="sv-thumb sv-thumb--add" onClick={() => fileRef.current?.click()} disabled={upload.isPending}>
                  <Icon name="camera" size={20} /><span className="small">{upload.isPending ? 'Uploading…' : 'Add photo'}</span>
                </button>
              )}
              <input ref={fileRef} type="file" accept="image/jpeg,image/png,image/webp" hidden onChange={(ev) => { const f = ev.target.files?.[0]; if (f) upload.mutate(f); ev.target.value = ''; }} />
            </div>
            <p className="small sv-muted">Up to {MAX_PHOTOS} photos. Only you and the professional who takes the job can see them.</p>
          </section>

          {/* 3 · Where */}
          <section className="sv-step" aria-labelledby="st-3">
            <h2 id="st-3"><span>3</span> Where?</h2>
            {addresses.length === 0 ? <p className="small">No saved addresses. <Link to="/account/addresses">Add one</Link> to book.</p> : (
              <div className="sv-addrs" role="radiogroup" aria-label="Service address">
                {addresses.map((a) => (
                  <button key={a.id} type="button" role="radio" aria-checked={a.id === addressId} className={`sv-addr${a.id === addressId ? ' is-on' : ''}`} onClick={() => { setAddressId(a.id); setStart(null); }}>
                    <Icon name="pin" size={16} /><span><strong>{a.label}</strong><span className="small sv-muted">{[a.line1, a.city].filter(Boolean).join(', ')}</span></span>
                  </button>
                ))}
              </div>
            )}
          </section>

          {/* 4 · When */}
          <section className="sv-step" aria-labelledby="st-4">
            <h2 id="st-4"><span>4</span> When?</h2>
            <div className="sv-seg" role="tablist" aria-label="When">
              <button type="button" role="tab" aria-selected={mode === 'now'} disabled={!job.instant} onClick={() => setMode('now')}>Now</button>
              <button type="button" role="tab" aria-selected={mode === 'scheduled'} disabled={!job.schedulable} onClick={() => setMode('scheduled')}>Schedule</button>
            </div>
            {mode === 'now' ? (
              e && <p className="small">{e.professionals > 0 ? `${e.professionals} professional${e.professionals > 1 ? 's' : ''} free now${e.etaMinutes ? ` · first arrival in about ${e.etaMinutes} min` : ''}.` : e.problem}</p>
            ) : !e ? <Skeleton height={80} /> : e.slots.length === 0 ? <p className="small">No free slots in the next 7 days{effectivePro ? ' for this professional' : ''}.</p> : (
              <>
                <div className="sv-days">{days.map((d) => <button key={d} type="button" className={`sv-chipbtn${d === activeDay ? ' is-on' : ''}`} onClick={() => setDay(d)}>{d}</button>)}</div>
                <div className="sv-slots" role="radiogroup" aria-label="Start time">
                  {e.slots.filter((s) => s.day === activeDay).map((s) => (
                    <button key={s.start} type="button" role="radio" aria-checked={s.start === start} className={`sv-slot${s.start === start ? ' is-on' : ''}`} onClick={() => setStart(s.start)}>{s.label}</button>
                  ))}
                </div>
              </>
            )}
            {job.pricing === 'hourly' && (
              <div className="sv-hoursel">
                <span>Hours</span>
                <button type="button" aria-label="Fewer hours" disabled={hoursValue <= job.minHours} onClick={() => setHours(hoursValue - 1)}>−</button>
                <strong aria-live="polite">{hoursValue}</strong>
                <button type="button" aria-label="More hours" disabled={hoursValue >= 12} onClick={() => setHours(hoursValue + 1)}>+</button>
                <span className="small sv-muted">min {job.minHours} · never billed beyond this unless you approve more</span>
              </div>
            )}
          </section>
        </>
      )}

      {job && e && (
        <div className="sv-bookbar">
          <div>
            <strong>{e.estimatedTotal ? formatMoney(e.estimatedTotal) : e.priceLabel}</strong>
            <span className="small sv-muted">{e.estimatedTotal ? (job.pricing === 'starting' ? 'Estimated, incl. tax · may change only with your approval' : 'Estimated, incl. tax · pay after the work') : 'Quote after inspection'}</span>
          </div>
          <Button disabled={!e.bookable || est.isFetching} onClick={() => setSummaryOpen(true)}>{e.bookable ? 'Review booking' : mode === 'scheduled' && !start && !e.problem ? 'Pick a time' : 'Unavailable'}</Button>
        </div>
      )}
      {job && e && !e.bookable && e.problem && <p className="sv-note" role="status"><Icon name="alert" size={14} /> {e.problem}{e.problem.startsWith('No professional') && <> <Link to="/services/request">Tell Click what you need</Link>.</>}</p>}
      {est.isError && <ErrorState error={est.error} onRetry={() => est.refetch()} />}

      <Sheet open={summaryOpen && !!e} onClose={() => setSummaryOpen(false)} label="Booking summary">
        {e && job && (
          <div className="sv-sheet">
            <h2>Booking summary</h2>
            <dl className="sv-summary">
              <dt>Service</dt><dd>{e.job.name}<span className="small sv-muted">{e.job.category}</span></dd>
              <dt>Professional</dt><dd>{pro.data ? pro.data.name : `First available of ${e.professionals}`}</dd>
              <dt>When</dt><dd>{mode === 'now' ? `Now${e.etaMinutes ? ` · about ${e.etaMinutes} min` : ''}` : e.slots.find((s) => s.start === start) ? `${e.slots.find((s) => s.start === start)!.day}, ${e.slots.find((s) => s.start === start)!.label}` : ''}</dd>
              <dt>Where</dt><dd>{addresses.find((a) => a.id === addressId)?.line1}</dd>
              {photos.length > 0 && <><dt>Photos</dt><dd>{photos.length} attached</dd></>}
              <dt>Pricing</dt><dd>{e.priceLabel}{e.hours ? ` × ${e.hours} h` : ''}<span className="small sv-muted">{e.job.pricingLabel}</span></dd>
              {e.agreed && <><dt>Service charge</dt><dd>{formatMoney(e.agreed)}</dd></>}
              {e.offer && <><dt>{e.offer.title}</dt><dd>−{formatMoney(e.offer.discount)}</dd></>}
              {e.tax && <><dt>Tax (18%)</dt><dd>{formatMoney(e.tax)}</dd></>}
              {e.estimatedTotal && <><dt><strong>Estimated total</strong></dt><dd><strong>{formatMoney(e.estimatedTotal)}</strong></dd></>}
              {e.inspectionFee && <><dt>Visit fee</dt><dd>{formatMoney(e.inspectionFee)}<span className="small sv-muted">only if you decline the quote</span></dd></>}
            </dl>
            {e.additionalCharges.length > 0 && <p className="small sv-muted">Not included: {e.additionalCharges.join(' · ')}. Any extra needs your approval first.</p>}
            <p className="small"><Icon name="clock" size={13} /> {e.cancellation}</p>
            <p className="small"><Icon name="wallet" size={13} /> You pay after the work is completed — Click. Wallet or cash. Nothing is charged now.</p>
            <Button block loading={book.isPending} onClick={() => book.mutate()}>Confirm booking</Button>
          </div>
        )}
      </Sheet>
    </div>
  );
}
