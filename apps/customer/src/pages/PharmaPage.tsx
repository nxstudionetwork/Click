import { useRef, useState } from 'react';
import { Link, useNavigate, useParams, useSearchParams } from 'react-router-dom';
import { keepPreviousData, useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { ApiError, type PharmaProduct } from '@click/api';
import { useAuth } from '../auth/AuthProvider';
import { Button, EmptyState, ErrorState, Icon, Sheet, Skeleton, SmartImage, useConfirm, useToast } from '../components/ui';
import { useThemeOverride } from '../components/layout/AppShell';
import { cartKey, isStoreConflict, useCartActions } from '../features/cart/useCart';
import { MoneyHead, Pill, Section, dateOf, money } from '../features/money/parts';
import { api } from '../lib/api';

function RxBadge() {
  return <span className="ph-rx" title="Needs a prescription verified by the pharmacy">Rx · Prescription required</span>;
}

function useAdd() {
  const { add, clear } = useCartActions();
  const toast = useToast();
  const confirm = useConfirm();
  const nav = useNavigate();
  return (p: PharmaProduct) => add.mutate({ productId: p.id, quantity: 1 }, {
    onSuccess: () => toast(`${p.name} added`),
    onError: async (e) => {
      if (isStoreConflict(e) && await confirm({ title: 'Start a new cart?', message: 'Your cart has items from another store. Clear it to add this?', confirmLabel: 'Clear and add' })) {
        clear.mutate(undefined, { onSuccess: () => add.mutate({ productId: p.id, quantity: 1 }, { onSuccess: () => toast(`${p.name} added`) }) });
      } else if (e instanceof ApiError && !isStoreConflict(e)) toast(e.message, 'error');
      else if (!(e instanceof ApiError)) nav('/login?next=/pharma');
    },
  });
}

export function PharmaProductCard({ p }: { p: PharmaProduct }) {
  const { status } = useAuth();
  const add = useAdd();
  const nav = useNavigate();
  return (
    <div className="ph-card">
      <Link to={`/pharma/p/${p.id}`} className="ph-card__main">
        {p.image ? <SmartImage src={p.image} alt="" className="ph-card__img" /> : <span className="ph-card__img ph-card__img--icon"><Icon name="plus" size={26} /></span>}
        <strong className="ph-card__name">{p.name}</strong>
        <span className="small mn-muted">{[p.packSize, p.pharmacy.name].filter(Boolean).join(' · ')}</span>
        {p.requiresPrescription && <RxBadge />}
      </Link>
      <div className="ph-card__foot">
        <strong>{money(p.price)}</strong>
        <Button size="sm" variant="secondary" disabled={!p.available || !p.pharmacy.open} onClick={() => (status === 'authenticated' ? add(p) : nav('/login?next=/pharma'))}>
          {p.available && p.pharmacy.open ? 'Add' : 'Unavailable'}</Button>
      </div>
    </div>
  );
}

/** Click. Pharma: medicines and health essentials from licensed local pharmacies, through the shared cart and
 *  checkout. Prescription-only medicines need a prescription the pharmacy's pharmacist verifies first. */
export function PharmaPage() {
  useThemeOverride('pharma');
  const { status } = useAuth();
  const [params, setParams] = useSearchParams();
  const cat = params.get('category') ?? '';
  const [q, setQ] = useState(params.get('q') ?? '');
  const home = useQuery({ queryKey: ['pharma', 'home', status], queryFn: api.money.pharma.home, enabled: status !== 'loading' });
  const term = params.get('q') ?? '';
  const list = useQuery({ queryKey: ['pharma', 'products', cat, term], queryFn: () => api.money.pharma.products({ category: cat, q: term }), enabled: !!(cat || term), placeholderData: keepPreviousData });
  const [upload, setUpload] = useState(false);
  const h = home.data;
  return (
    <div className="mn-page ph-page" data-theme="pharma">
      <MoneyHead title="Pharma" back="/" />
      <section className="ph-hero">
        <h2>Medicines and health essentials, from pharmacies near you.</h2>
        <form className="mn-search" role="search" onSubmit={(e) => { e.preventDefault(); setParams(q.trim() ? { q: q.trim() } : {}); }}>
          <Icon name="search" size={18} /><input type="search" value={q} onChange={(e) => setQ(e.target.value)} placeholder="Search medicines, salt name or health products" aria-label="Search Pharma" />
        </form>
        <div className="mn-row2">
          <Button onClick={() => (status === 'authenticated' ? setUpload(true) : undefined)} disabled={status !== 'authenticated'}><Icon name="camera" size={16} /> Upload prescription</Button>
          {status === 'authenticated' && <Link to="/pharma/prescriptions" className="btn btn--outline">My prescriptions</Link>}
        </div>
      </section>
      {(cat || term) ? (
        <Section title={term ? `Results for “${term}”` : h?.categories.find((c) => c.code === cat)?.label ?? 'Products'} id="ph-list">
          <button type="button" className="mn-link small" onClick={() => { setQ(''); setParams({}); }}>← All of Pharma</button>
          {list.isError ? <ErrorState error={list.error} onRetry={() => list.refetch()} /> : !list.data ? <Skeleton height={240} /> : list.data.results.length === 0
            ? <EmptyState icon="search" title="No products found" message="Try the medicine’s salt name, or another word." />
            : <div className="ph-grid">{list.data.results.map((p) => <PharmaProductCard key={p.id} p={p} />)}</div>}
        </Section>
      ) : home.isError ? <ErrorState error={home.error} onRetry={() => home.refetch()} /> : !h ? <Skeleton height={400} /> : h.pharmacies.length === 0 ? (
        <EmptyState icon="plus" title="No pharmacies here yet" message="Pharmacies near you will appear here as they join Click." />
      ) : (
        <>
          <Section title="Shop by category" id="ph-cats">
            <div className="ph-cats">{h.categories.map((c) => <button key={c.code} type="button" className="ph-cat" onClick={() => setParams({ category: c.code })}>
              <Icon name={c.icon as Parameters<typeof Icon>[0]['name']} size={20} /><span>{c.label}</span></button>)}</div>
          </Section>
          {h.orderAgain.length > 0 && <Section title="Order again" id="ph-again"><div className="ph-rail">{h.orderAgain.map((p) => <PharmaProductCard key={p.id} p={p} />)}</div></Section>}
          <Section title="Pharmacies near you" id="ph-near">
            <ul className="mn-list">{h.pharmacies.map((s) => (
              <li key={s.id}><Link to={`/stores/${s.slug}`} className="mn-row"><span className="mn-row__icon mn-row__icon--theme"><Icon name="plus" size={18} /></span>
                <span className="mn-row__text"><strong>{s.name}{s.verified && <Pill tone="ok">Verified</Pill>}</strong>
                  <span className="small mn-muted">{s.locality} · {s.eta}{s.rating ? ` · ★ ${s.rating}` : ''}{s.open ? '' : ' · Closed now'}</span></span><Icon name="right" size={16} /></Link></li>
            ))}</ul>
          </Section>
          {h.trending.length > 0 && <Section title="Health essentials" id="ph-trend"><div className="ph-rail">{h.trending.map((p) => <PharmaProductCard key={p.id} p={p} />)}</div></Section>}
          <p className="small mn-muted ph-disclaimer"><Icon name="shield" size={14} /> {h.disclaimer}</p>
        </>
      )}
      {upload && <UploadSheet onClose={() => setUpload(false)} pharmacies={h?.pharmacies ?? []} />}
    </div>
  );
}

function UploadSheet({ onClose, pharmacies, defaultPharmacy }: { onClose: () => void; pharmacies: { id: string; name: string; open: boolean }[]; defaultPharmacy?: string }) {
  const qc = useQueryClient();
  const toast = useToast();
  const [pharmacy, setPharmacy] = useState(defaultPharmacy ?? pharmacies[0]?.id ?? '');
  const [file, setFile] = useState<File | null>(null);
  const [note, setNote] = useState('');
  const ref = useRef<HTMLInputElement>(null);
  const send = useMutation({
    mutationFn: () => api.money.pharma.upload(file!, pharmacy, note),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['pharma'] }); toast('Prescription sent for review'); onClose(); },
  });
  const bad = file && (!['image/jpeg', 'image/png', 'image/webp', 'application/pdf'].includes(file.type) || file.size > 10 * 1024 * 1024);
  return (
    <Sheet open onClose={onClose} label="Upload prescription">
      <div className="mn-sheet mn-form" data-theme="pharma">
        <h2>Upload prescription</h2>
        <ul className="mn-bullets small">
          <li>Upload a clear, readable prescription from a qualified doctor, with the date and doctor’s details visible.</li>
          <li>The pharmacy’s pharmacist reviews it. Uploading doesn’t guarantee your order is accepted.</li>
          <li>Only you and that pharmacy can see it.</li>
        </ul>
        <label className="mn-field"><span>Pharmacy that will review it</span>
          <select value={pharmacy} onChange={(e) => setPharmacy(e.target.value)}>{pharmacies.map((p) => <option key={p.id} value={p.id}>{p.name}{p.open ? '' : ' (closed now)'}</option>)}</select></label>
        <input ref={ref} type="file" accept="image/jpeg,image/png,image/webp,application/pdf" capture="environment" hidden onChange={(e) => setFile(e.target.files?.[0] ?? null)} />
        {file ? <div className="mn-file"><Icon name="receipt" size={18} /><span className="truncate">{file.name}</span><button type="button" className="mn-link small" onClick={() => setFile(null)}>Change</button></div>
          : <button type="button" className="btn btn--outline" onClick={() => ref.current?.click()}><Icon name="camera" size={16} /> Take a photo or choose a file</button>}
        {bad && <p className="mn-error small">Use a JPEG, PNG or WebP photo, or a PDF, up to 10 MB.</p>}
        <label className="mn-field"><span>Note for the pharmacist <span className="mn-muted small">(optional)</span></span><textarea rows={2} maxLength={500} value={note} onChange={(e) => setNote(e.target.value)} /></label>
        {send.isError && <p className="mn-error small" role="alert">{send.error instanceof ApiError ? send.error.message : 'Couldn’t upload. Try again.'}</p>}
        <Button block disabled={!file || !!bad || !pharmacy} loading={send.isPending} onClick={() => send.mutate()}>Send for review</Button>
      </div>
    </Sheet>
  );
}

export function PharmaProductPage() {
  useThemeOverride('pharma');
  const { id = '' } = useParams();
  const { status } = useAuth();
  const nav = useNavigate();
  const add = useAdd();
  const toast = useToast();
  const q = useQuery({ queryKey: ['pharma', 'product', id], queryFn: () => api.money.pharma.product(id) });
  const [days, setDays] = useState(30);
  const refill = useMutation({ mutationFn: () => api.money.pharma.addRefill(id, days), onSuccess: (r) => toast(`We’ll remind you on ${dateOf(r.nextOn)}`) });
  if (q.isError) return <div className="mn-page"><MoneyHead title="Pharma" back="/pharma" /><ErrorState error={q.error} onRetry={() => q.refetch()} /></div>;
  if (!q.data) return <div className="mn-page"><MoneyHead title="Pharma" back="/pharma" /><Skeleton height={360} /></div>;
  const p = q.data;
  return (
    <div className="mn-page ph-page" data-theme="pharma">
      <MoneyHead title={p.pharmacy.name} back="/pharma" />
      <section className="mn-card">
        {p.requiresPrescription && <RxBadge />}
        <h2 className="ph-title">{p.name}</h2>
        <dl className="mn-dl">
          {p.composition && <div><dt>Composition</dt><dd>{p.composition}</dd></div>}
          {p.packSize && <div><dt>Pack</dt><dd>{p.packSize}</dd></div>}
          {p.manufacturer && <div><dt>Manufacturer</dt><dd>{p.manufacturer}</dd></div>}
          <div><dt>Category</dt><dd>{p.categoryLabel}</dd></div>
          <div><dt>Price</dt><dd><strong>{money(p.price)}</strong></dd></div>
          {p.maxPerOrder && <div><dt>Limit</dt><dd>Up to {p.maxPerOrder} per order</dd></div>}
          <div><dt>Sold by</dt><dd><Link to={`/stores/${p.pharmacy.slug}`} className="mn-link">{p.pharmacy.name}</Link></dd></div>
        </dl>
        {p.requiresPrescription && <p className="small ph-rxnote">This is a prescription-only medicine. Add it to your cart, then attach a prescription {p.pharmacy.name} has verified before checkout.</p>}
        <Button block disabled={!p.available || !p.pharmacy.open} onClick={() => (status === 'authenticated' ? add(p) : nav(`/login?next=/pharma/p/${p.id}`))}>{p.available ? 'Add to cart' : 'Currently unavailable'}</Button>
      </section>
      {p.sameComposition.length > 0 && (
        <Section title="Same composition at other pharmacies" id="ph-same">
          <p className="small mn-muted">Same salt and strength listed by another pharmacy. Ask your doctor or pharmacist before switching brands.</p>
          <div className="ph-rail">{p.sameComposition.map((x) => <PharmaProductCard key={x.id} p={x} />)}</div>
        </Section>
      )}
      {status === 'authenticated' && (
        <section className="mn-card"><strong>Refill reminder</strong>
          <div className="mn-row2"><select value={days} onChange={(e) => setDays(Number(e.target.value))} aria-label="Remind me every">{[7, 15, 30, 60, 90].map((d) => <option key={d} value={d}>Every {d} days</option>)}</select>
            <Button size="sm" variant="secondary" loading={refill.isPending} onClick={() => refill.mutate()}>Remind me</Button></div></section>
      )}
      <p className="small mn-muted ph-disclaimer"><Icon name="shield" size={14} /> {p.disclaimer}</p>
    </div>
  );
}

export function PrescriptionsPage() {
  useThemeOverride('pharma');
  const qc = useQueryClient();
  const toast = useToast();
  const q = useQuery({ queryKey: ['pharma', 'prescriptions'], queryFn: api.money.pharma.prescriptions });
  const home = useQuery({ queryKey: ['pharma', 'home', 'authenticated'], queryFn: api.money.pharma.home });
  const refills = useQuery({ queryKey: ['pharma', 'refills'], queryFn: api.money.pharma.refills });
  const [upload, setUpload] = useState(false);
  const cancel = useMutation({ mutationFn: api.money.pharma.cancel, onSuccess: () => qc.invalidateQueries({ queryKey: ['pharma'] }) });
  const stop = useMutation({ mutationFn: api.money.pharma.removeRefill, onSuccess: () => qc.invalidateQueries({ queryKey: ['pharma', 'refills'] }) });
  const open = async (id: string, name: string) => {
    try { const b = await api.money.pharma.file(id); const u = URL.createObjectURL(b); const a = document.createElement('a'); a.href = u; a.download = name; document.body.appendChild(a); a.click(); a.remove(); setTimeout(() => URL.revokeObjectURL(u), 60_000); }
    catch { toast('Couldn’t open the file.', 'error'); }
  };
  const tone = (s: string) => (s === 'verified' || s === 'partial' ? 'ok' : s === 'rejected' ? 'bad' : s === 'clarification' || s === 'under_review' ? 'pending' : 'info') as 'ok' | 'bad' | 'pending' | 'info';
  return (
    <div className="mn-page ph-page" data-theme="pharma">
      <MoneyHead title="My prescriptions" back="/pharma" action={<button type="button" className="mn-head__home" aria-label="Upload prescription" onClick={() => setUpload(true)}><Icon name="plus" size={20} /></button>} />
      {q.isError ? <ErrorState error={q.error} onRetry={() => q.refetch()} /> : !q.data ? <Skeleton height={240} /> : q.data.results.length === 0 ? (
        <EmptyState icon="receipt" title="No prescriptions yet" message="Upload one and the pharmacy’s pharmacist reviews it before you order prescription medicines."
          action={<Button onClick={() => setUpload(true)}>Upload prescription</Button>} />
      ) : (
        <ul className="mn-list">{q.data.results.map((r) => (
          <li key={r.id} className="mn-row mn-row--static ph-rxrow">
            <span className="mn-row__icon mn-row__icon--theme"><Icon name="receipt" size={18} /></span>
            <span className="mn-row__text"><strong>{r.reference} · {r.pharmacy.name}</strong>
              <span className="small mn-muted">Uploaded {dateOf(r.uploadedAt)}{r.validUntil ? ` · valid till ${dateOf(r.validUntil)}` : ''}{r.order ? ` · used for ${r.order.number}` : ''}</span>
              {r.pharmacistNote && <span className="small">Pharmacist: {r.pharmacistNote}</span>}
              {r.alternativeNote && <span className="small mn-warn">Alternative suggested: {r.alternativeNote} (nothing is changed without you)</span>}
              <span className="ph-rxrow__actions small"><button type="button" className="mn-link" onClick={() => open(r.id, r.fileName)}>View file</button>
                {['under_review', 'clarification', 'verified'].includes(r.status) && <button type="button" className="mn-link" onClick={() => cancel.mutate(r.id)}>Withdraw</button>}</span></span>
            <Pill tone={tone(r.status)}>{r.statusLabel}</Pill>
          </li>
        ))}</ul>
      )}
      {!!refills.data?.results.length && (
        <Section title="Refill reminders" id="ph-refills">
          <ul className="mn-list">{refills.data.results.map((x) => (
            <li key={x.id} className="mn-row mn-row--static"><span className="mn-row__icon"><Icon name="clock" size={18} /></span>
              <span className="mn-row__text"><strong>{x.product.name}</strong><span className="small mn-muted">Every {x.everyDays} days · next {dateOf(x.nextOn)}</span></span>
              <button type="button" className="mn-link small" onClick={() => stop.mutate(x.id)}>Stop</button></li>
          ))}</ul>
        </Section>
      )}
      {upload && <UploadSheet onClose={() => setUpload(false)} pharmacies={home.data?.pharmacies ?? []} />}
    </div>
  );
}

/** Cart step for pharmacy carts with prescription-only items: attach the prescription the pharmacy verified. */
export function CartPrescription({ required, attached, available, pharmacyId }: { required: boolean; attached: { reference: string } | null; available: { id: string; reference: string } | null; pharmacyId: string }) {
  const qc = useQueryClient();
  const toast = useToast();
  const [upload, setUpload] = useState(false);
  const home = useQuery({ queryKey: ['pharma', 'home', 'authenticated'], queryFn: api.money.pharma.home, enabled: upload });
  const attach = useMutation({ mutationFn: (id: string) => api.money.pharma.attach(id), onSuccess: () => { qc.invalidateQueries({ queryKey: cartKey }); toast('Prescription attached'); },
    onError: (e) => toast(e instanceof ApiError ? e.message : 'Couldn’t attach it.', 'error') });
  if (!required) return null;
  return (
    <section className="card card--pad stack ph-cartrx" data-theme="pharma" aria-labelledby="rx-h">
      <h3 id="rx-h"><Icon name="receipt" size={18} /> Prescription</h3>
      {attached ? <p className="small"><Icon name="check" size={14} /> Verified prescription {attached.reference} attached.</p>
        : available ? (<><p className="small">The pharmacy verified prescription {available.reference}.</p>
          <Button size="sm" loading={attach.isPending} onClick={() => attach.mutate(available.id)}>Attach {available.reference}</Button></>)
          : (<><p className="small">Your cart has prescription-only medicines. Upload your prescription; you can check out once the pharmacy’s pharmacist verifies it.</p>
            <div className="row" style={{ gap: 8, flexWrap: 'wrap' }}><Button size="sm" onClick={() => setUpload(true)}>Upload prescription</Button><Link to="/pharma/prescriptions" className="btn btn--outline btn--sm">My prescriptions</Link></div></>)}
      {upload && <UploadSheet onClose={() => setUpload(false)} pharmacies={(home.data?.pharmacies ?? []).filter((p) => p.id === pharmacyId)} defaultPharmacy={pharmacyId} />}
    </section>
  );
}
