import { useEffect, useState } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { ApiError, type Offer } from '@click/api';
import { useAuth } from '../auth/AuthProvider';
import { Button, EmptyState, ErrorState, Icon, Sheet, Skeleton, useToast } from '../components/ui';
import { MoneyHead, Section, THEME, dateOf, iconFor, money } from '../features/money/parts';
import { api } from '../lib/api';

const SORTS = [['recommended', 'Recommended'], ['ending_soon', 'Ending soon'], ['biggest', 'Biggest discount'], ['best_value', 'Best value'], ['newest', 'Newest']];
const KINDS = [['', 'All types'], ['coupon', 'Coupons'], ['cashback', 'Cashback'], ['discount', 'Discounts'], ['reward_boost', 'Points boosts']];
const BADGE: Record<string, string> = { click_offer: 'Click. offer', partner: 'Partner', coupon: 'Coupon', ending_soon: 'Ends soon', new: 'New', new_user: 'New users', cashback: 'Cashback' };

function endsLabel(iso: string | null) {
  if (!iso) return '';
  const h = (new Date(iso).getTime() - Date.now()) / 3_600_000;
  if (h <= 0) return 'Ended';
  if (h < 24) return `Ends in ${Math.max(1, Math.round(h))} h`;
  if (h < 72) return `Ends in ${Math.round(h / 24)} days`;
  return `Valid till ${dateOf(iso)}`;
}

/** Click. Offers: every live offer across Click. in one place, built from each service's own offer records. Badges
 *  and "best value" come from stated rules; each service still checks eligibility at its checkout. */
export function OffersPage() {
  const { status } = useAuth();
  const [params, setParams] = useSearchParams();
  const tab = params.get('tab') === 'mine' ? 'mine' : 'all';
  const service = params.get('service') ?? '', kind = params.get('kind') ?? '', sort = params.get('sort') ?? 'recommended';
  const [q, setQ] = useState(params.get('q') ?? '');
  const [term, setTerm] = useState(q);
  useEffect(() => { const t = setTimeout(() => setTerm(q.trim()), 300); return () => clearTimeout(t); }, [q]);
  const set = (k: string, v: string) => { const n = new URLSearchParams(params); if (v) n.set(k, v); else n.delete(k); setParams(n, { replace: true }); };
  const hub = useQuery({ queryKey: ['offers', 'hub', status, service, kind, sort, term], enabled: status !== 'loading',
    queryFn: () => api.money.offers.hub({ service: service || undefined, kind: kind || undefined, q: term || undefined, sort }) });
  const [open, setOpen] = useState<Offer | null>(null);
  const browsing = !!(service || kind || term || sort !== 'recommended');
  const h = hub.data;

  return (
    <div className="mn-page">
      <MoneyHead title="Offers" back="/" />
      {status === 'authenticated' && (
        <div className="mn-tabs" role="tablist">
          <button type="button" role="tab" className="mn-tab" aria-selected={tab === 'all'} onClick={() => set('tab', '')}>All offers</button>
          <button type="button" role="tab" className="mn-tab" aria-selected={tab === 'mine'} onClick={() => set('tab', 'mine')}>My offers & savings</button>
        </div>
      )}
      {tab === 'mine' ? <Mine onOpen={setOpen} /> : (
        <>
          <div className="mn-search"><Icon name="search" size={18} />
            <input type="search" value={q} onChange={(e) => { setQ(e.target.value); }} placeholder="Search: biryani, flights, cashback, STAYCLICK…" aria-label="Search offers" /></div>
          <div className="mn-chips" role="tablist" aria-label="Service">
            <button type="button" role="tab" className="mn-chip" aria-selected={!service} aria-pressed={!service} onClick={() => set('service', '')}>All{h ? ` · ${h.services.reduce((s, x) => s + x.count, 0)}` : ''}</button>
            {h?.services.map((s) => <button key={s.code} type="button" role="tab" className="mn-chip" aria-selected={service === s.code} aria-pressed={service === s.code} onClick={() => set('service', s.code)}>
              <Icon name={iconFor(s.code)} size={15} />{s.label} · {s.count}</button>)}
          </div>
          <div className="mn-selects">
            <select value={kind} onChange={(e) => set('kind', e.target.value)} aria-label="Offer type">{KINDS.map(([v, l]) => <option key={v} value={v}>{l}</option>)}</select>
            <select value={sort} onChange={(e) => set('sort', e.target.value === 'recommended' ? '' : e.target.value)} aria-label="Sort">{SORTS.map(([v, l]) => <option key={v} value={v}>{l}</option>)}</select>
          </div>
          {hub.isError ? <ErrorState error={hub.error} onRetry={() => hub.refetch()} /> : !h ? <Skeleton height={320} /> : browsing ? (
            h.results.length === 0 ? <EmptyState icon="tag" title="No offers match" message="Try another service or search." action={<button type="button" className="btn btn--outline" onClick={() => { setQ(''); setParams({}, { replace: true }); }}>Clear</button>} />
              : <><p className="small mn-muted">{h.count} offer{h.count === 1 ? '' : 's'}{sort === 'best_value' ? ` · ${h.bestValueRule}` : ''}</p><Grid rows={h.results} onOpen={setOpen} /></>
          ) : h.count === 0 ? <EmptyState icon="tag" title="No offers right now" message="New offers from Click. services appear here." /> : (
            <>
              {h.sections.hero.length > 0 && <div className="mn-hero-rail">{h.sections.hero.map((o) => <HeroCard key={o.id} o={o} onOpen={setOpen} />)}</div>}
              {h.sections.picked.length > 0 && <Rail title="Picked for you" sub={h.pickedReason} rows={h.sections.picked} onOpen={setOpen} />}
              {h.sections.endingSoon.length > 0 && <Rail title="Ending soon" rows={h.sections.endingSoon} onOpen={setOpen} />}
              {h.sections.coupons.length > 0 && <Rail title="Coupons" sub="Claim a code to keep it on your account; it’s suggested at that service’s checkout." rows={h.sections.coupons} onOpen={setOpen} />}
              {h.sections.cashback.length > 0 && <Rail title="Cashback with Click. Wallet" rows={h.sections.cashback} onOpen={setOpen} />}
              {h.sections.boosts.length > 0 && <Rail title="Points boosts" rows={h.sections.boosts} onOpen={setOpen} />}
              {h.sections.newUser.length > 0 && <Rail title="For new customers" rows={h.sections.newUser} onOpen={setOpen} />}
              {h.sections.partners.length > 0 && <Rail title="From Click. partners" rows={h.sections.partners} onOpen={setOpen} />}
              {h.sections.bestValue.length > 0 && <Rail title="Best value" sub={h.bestValueRule} rows={h.sections.bestValue} onOpen={setOpen} />}
              <Section title="Everything" id="mn-all-offers"><Grid rows={h.results} onOpen={setOpen} /></Section>
            </>
          )}
          <Link to="/gift-cards" className="mn-row mn-row--card"><span className="mn-row__icon"><Icon name="gift" size={18} /></span>
            <span className="mn-row__text"><strong>Gift Cards</strong><span className="small mn-muted">Give something they’ll love — for Food, Groceries or Shop</span></span><Icon name="right" size={16} /></Link>
          <p className="small mn-muted">Offers are set by Click. and its partners. Each one is checked again at checkout (dates, minimum spend, usage), so the price you see there is final.</p>
        </>
      )}
      {open && <OfferSheet offer={open} onClose={() => setOpen(null)} />}
    </div>
  );
}

function Badges({ o }: { o: Offer }) {
  return <span className="mn-badges-row">{o.badges.filter((b) => BADGE[b]).slice(0, 2).map((b) => <span key={b} className={`mn-tag mn-tag--${b}`}>{BADGE[b]}</span>)}</span>;
}

function HeroCard({ o, onOpen }: { o: Offer; onOpen: (o: Offer) => void }) {
  return (
    <button type="button" className="mn-offer-hero" data-theme={THEME[o.service]} onClick={() => onOpen(o)}>
      <span className="mn-offer-hero__svc"><Icon name={iconFor(o.service)} size={16} /> {o.serviceLabel}</span>
      <strong className="mn-offer-hero__benefit">{o.benefit}</strong>
      <span className="mn-offer-hero__title">{o.title}</span>
      <span className="small">{o.conditions[0] ?? o.description}{o.endsAt ? ` · ${endsLabel(o.endsAt)}` : ''}</span>
    </button>
  );
}

function Card({ o, onOpen }: { o: Offer; onOpen: (o: Offer) => void }) {
  return (
    <button type="button" className="mn-offer" data-theme={THEME[o.service]} onClick={() => onOpen(o)}>
      <span className="mn-offer__top"><span className="mn-offer__icon"><Icon name={iconFor(o.service)} size={18} /></span><Badges o={o} />{o.saved && <Icon name="heart" size={14} />}</span>
      <strong className="mn-offer__benefit">{o.benefit}</strong>
      <span className="mn-offer__title">{o.title}</span>
      <span className="small mn-muted">{o.partner?.name ?? o.serviceLabel}{o.endsAt ? ` · ${endsLabel(o.endsAt)}` : ''}</span>
      {o.code && <span className="mn-code">{o.code}</span>}
    </button>
  );
}

function Rail({ title, sub, rows, onOpen }: { title: string; sub?: string; rows: Offer[]; onOpen: (o: Offer) => void }) {
  return (
    <Section title={title} id={`mn-${title.replace(/\W+/g, '-').toLowerCase()}`}>
      {sub && <p className="small mn-muted">{sub}</p>}
      <div className="mn-rail">{rows.map((o) => <Card key={o.id} o={o} onOpen={onOpen} />)}</div>
    </Section>
  );
}

function Grid({ rows, onOpen }: { rows: Offer[]; onOpen: (o: Offer) => void }) {
  return <div className="mn-offer-grid">{rows.map((o) => <Card key={o.id} o={o} onOpen={onOpen} />)}</div>;
}

function OfferSheet({ offer, onClose }: { offer: Offer; onClose: () => void }) {
  const { status } = useAuth();
  const qc = useQueryClient();
  const toast = useToast();
  const live = useQuery({ queryKey: ['offers', 'item', offer.id], queryFn: () => api.money.offers.get(offer.id), initialData: offer });
  const o = live.data;
  const fail = (e: unknown) => toast(e instanceof ApiError ? e.message : 'Couldn’t update.', 'error');
  const done = () => { qc.invalidateQueries({ queryKey: ['offers'] }); };
  const save = useMutation({ mutationFn: async () => { if (o.saved) await api.money.offers.unsave(o.id); else await api.money.offers.save(o.id); }, onSuccess: () => { done(); toast(o.saved ? 'Removed from saved' : 'Saved'); }, onError: fail });
  const claim = useMutation({ mutationFn: () => api.money.offers.claim(o.id), onSuccess: (r) => { done(); toast(`${r.code} is on your account`); }, onError: fail });
  const copy = async () => { try { await navigator.clipboard.writeText(o.code ?? ''); toast('Code copied'); } catch { toast('Couldn’t copy. The code is shown above.', 'error'); } };
  return (
    <Sheet open onClose={onClose} label={o.title}>
      <div className="mn-sheet mn-form" data-theme={THEME[o.service]}>
        <span className="small mn-muted"><Icon name={iconFor(o.service)} size={14} /> {o.serviceLabel}{o.partner ? ` · ${o.partner.name}` : ''}</span>
        <h2>{o.benefit}</h2>
        <p>{o.title}</p>
        {o.description && o.description !== o.title && o.description.toLowerCase() !== o.kind && <p className="small mn-muted">{o.description}</p>}
        <Badges o={o} />
        <dl className="mn-dl">
          {o.minAmount && <div><dt>Minimum spend</dt><dd>{money(o.minAmount)}</dd></div>}
          {o.maxDiscount && <div><dt>Maximum discount</dt><dd>{money(o.maxDiscount)}</dd></div>}
          {o.startsAt && <div><dt>From</dt><dd>{dateOf(o.startsAt)}</dd></div>}
          <div><dt>Valid till</dt><dd>{o.endsAt ? dateOf(o.endsAt) : 'Until withdrawn'}</dd></div>
        </dl>
        {o.conditions.length > 0 && <ul className="mn-bullets small">{o.conditions.map((c) => <li key={c}>{c}</li>)}</ul>}
        {o.terms && <p className="small mn-muted">{o.terms}</p>}
        {o.code && (
          <div className="mn-code-box"><span className="mn-code mn-code--lg">{o.code}</span><button type="button" className="mn-link small" onClick={copy}><Icon name="copy" size={14} /> Copy</button></div>
        )}
        {status === 'authenticated' ? (
          <div className="mn-row2">
            <Button variant="secondary" loading={save.isPending} onClick={() => save.mutate()}><Icon name="heart" size={16} /> {o.saved ? 'Saved' : 'Save'}</Button>
            {o.code && !o.claimed ? <Button loading={claim.isPending} onClick={() => claim.mutate()}>Claim code</Button>
              : <Link to={o.link} className="btn btn--primary" onClick={onClose}>{o.kind === 'reward_boost' ? 'Start earning' : 'Use now'}</Link>}
          </div>
        ) : <Link to={o.link} className="btn btn--primary" onClick={onClose}>Use now</Link>}
        {o.claimed && <p className="small mn-ok">Claimed · it’s suggested at {o.serviceLabel} checkout.</p>}
      </div>
    </Sheet>
  );
}

function Mine({ onOpen }: { onOpen: (o: Offer) => void }) {
  const m = useQuery({ queryKey: ['offers', 'mine'], queryFn: api.money.offers.mine });
  if (m.isError) return <ErrorState error={m.error} onRetry={() => m.refetch()} />;
  if (!m.data) return <Skeleton height={300} />;
  const s = m.data.savings;
  const live = m.data.saved.filter((x): x is Offer => !('expired' in x));
  const ended = m.data.saved.filter((x) => 'expired' in x);
  return (
    <>
      <div className="mn-stats">
        <div><span className="small mn-muted">Saved this month</span><strong className="mn-ok">{money(s.savedThisMonth)}</strong></div>
        <div><span className="small mn-muted">Saved this year</span><strong>{money(s.savedThisYear)}</strong></div>
        <div><span className="small mn-muted">Offers used</span><strong>{s.offersUsed}</strong></div>
        <div><span className="small mn-muted">Cashback earned</span><strong>{money(s.cashbackEarned)}</strong></div>
      </div>
      <Section title="Saved offers" id="mn-saved">
        {live.length === 0 && ended.length === 0 ? <p className="small mn-muted">Tap the heart on an offer to keep it here.</p> : (
          <>
            {live.length > 0 && <Grid rows={live} onOpen={onOpen} />}
            {ended.length > 0 && <p className="small mn-muted">{ended.length} saved offer{ended.length > 1 ? 's have' : ' has'} ended.</p>}
          </>
        )}
      </Section>
      <Section title="Claimed codes" id="mn-claimed">
        {m.data.claimed.length === 0 ? <p className="small mn-muted">Codes you claim stay here and are suggested at checkout.</p> : (
          <ul className="mn-list">{m.data.claimed.map((c) => (
            <li key={c.offer} className="mn-row mn-row--static"><span className="mn-row__icon"><Icon name={iconFor(c.service)} size={18} /></span>
              <span className="mn-row__text"><strong>{c.title}</strong><span className="small mn-muted">{c.live ? 'Active' : 'Ended'}</span></span><span className="mn-code">{c.code}</span></li>
          ))}</ul>
        )}
      </Section>
      <Section title="Where you saved" id="mn-used">
        {s.history.length === 0 ? <p className="small mn-muted">Discounts you get at checkout appear here.</p> : (
          <ul className="mn-list">{s.history.map((x) => (
            <li key={`${x.reference}-${x.at}`} className="mn-row mn-row--static"><span className="mn-row__icon mn-row__icon--ok"><Icon name="tag" size={18} /></span>
              <span className="mn-row__text"><strong className="truncate">{x.title}</strong><span className="small mn-muted">{x.service} · {x.reference} · {dateOf(x.at)}</span></span>
              <strong className="mn-ok">−{money(x.saved)}</strong></li>
          ))}</ul>
        )}
      </Section>
    </>
  );
}
