import { useState } from 'react';
import { Link, useNavigate, useParams, useSearchParams } from 'react-router-dom';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { ApiError, type GiftDesign } from '@click/api';
import { useAuth } from '../auth/AuthProvider';
import { Button, EmptyState, ErrorState, Icon, Sheet, Skeleton, useToast } from '../components/ui';
import { MoneyHead, Pill, Section, dateOf, money, newKey } from '../features/money/parts';
import { PayOnline, useOnlineMethods } from '../features/payments/OnlinePay';
import { useWallet } from '../features/wallet/useWallet';
import { api } from '../lib/api';

export function GiftArt({ d, amount, small }: { d: GiftDesign; amount?: string; small?: boolean }) {
  const [a, b, c] = d.colors;
  return (
    <div className={`gc-art ${small ? 'gc-art--sm' : ''}`} style={{ background: `radial-gradient(120% 140% at 100% 0%, ${c ?? b}55 0%, transparent 55%), linear-gradient(140deg, ${a}, ${b ?? a})` }}>
      <span className="gc-art__brand">Click<b>.</b></span>
      <span className="gc-art__title">{d.title}</span>
      {amount && <strong className="gc-art__amt">{money(amount)}</strong>}
      <span className="gc-art__chip" aria-hidden="true" />
    </div>
  );
}

/** Gift Cards: designs from the backend, a buy flow (amount → recipient → message → delivery → review → pay), and
 *  your received / sent cards. Gift cards are their own balance — not Click. Wallet money. */
export function GiftCardsPage() {
  const { status } = useAuth();
  const q = useQuery({ queryKey: ['giftcards', 'designs'], queryFn: api.money.giftCards.designs });
  const [params] = useSearchParams();
  const [cat, setCat] = useState('');
  const [buying, setBuying] = useState<GiftDesign | null>(null);
  const all = q.data?.categories.flatMap((c) => c.designs) ?? [];
  const pre = params.get('design');
  if (pre && !buying && all.length) { const d = all.find((x) => x.id === pre); if (d) setTimeout(() => setBuying(d)); }
  return (
    <div className="mn-page gc-page">
      <MoneyHead title="Gift Cards" back="/" />
      <section className="gc-hero">
        <h2>Give something they’ll love.</h2><p>The Click. way — delivered to their Click. account or as a code you share.</p>
        <div className="mn-row2">
          {status === 'authenticated' && <Link to="/gift-cards/mine" className="btn btn--outline btn--sm"><Icon name="wallet" size={16} /> My gift cards</Link>}
          {status === 'authenticated' && <Link to="/gift-cards/mine?redeem=1" className="btn btn--outline btn--sm"><Icon name="key" size={16} /> Redeem a code</Link>}
        </div>
      </section>
      {q.isError ? <ErrorState error={q.error} onRetry={() => q.refetch()} /> : !q.data ? <Skeleton height={300} /> : q.data.categories.length === 0 ? (
        <EmptyState icon="gift" title="Gift cards are coming back soon" message="There are no gift cards on sale right now." />
      ) : (
        <>
          <div className="mn-chips" role="tablist" aria-label="Category">
            <button type="button" className="mn-chip" aria-pressed={!cat} onClick={() => setCat('')}>All</button>
            {q.data.categories.map((c) => <button key={c.code} type="button" className="mn-chip" aria-pressed={cat === c.code} onClick={() => setCat(c.code)}>{c.label}</button>)}
          </div>
          {q.data.categories.filter((c) => !cat || c.code === cat).map((c) => (
            <Section key={c.code} title={c.label} id={`gc-${c.code}`}>
              <div className="gc-grid">{c.designs.map((d) => (
                <button key={d.id} type="button" className="gc-tile" onClick={() => setBuying(d)}>
                  <GiftArt d={d} />
                  <span className="small">{d.tagline}</span>
                  <span className="small mn-muted">{money(d.minAmount)} – {money(d.maxAmount)} · {d.services.map((s) => s.label).join(', ')}</span>
                </button>
              ))}</div>
            </Section>
          ))}
          <Section title="How gift cards work" id="gc-how">
            <ul className="mn-bullets small">
              <li>Pay with Click. Wallet or online. The card is issued only after the payment is confirmed.</li>
              <li>Send it to their Click. account by phone number, or get a code to share yourself. You can schedule delivery up to 90 days ahead.</li>
              <li>They redeem it in Gift Cards and pay for Food, Groceries or Shop orders with it (the card must cover the whole order).</li>
              <li>Valid for 12 months. It isn’t cash, can’t be added to Click. Wallet, and refunds of orders paid with it go back to the card.</li>
            </ul>
          </Section>
        </>
      )}
      {buying && <BuySheet d={buying} onClose={() => setBuying(null)} />}
    </div>
  );
}

type Step = 'amount' | 'recipient' | 'review' | 'pay';

function BuySheet({ d, onClose }: { d: GiftDesign; onClose: () => void }) {
  const { status } = useAuth();
  const nav = useNavigate();
  const qc = useQueryClient();
  const wallet = useWallet();
  const online = useOnlineMethods();
  const [step, setStep] = useState<Step>('amount');
  const [amount, setAmount] = useState(d.presets[0] ?? d.minAmount);
  const [name, setName] = useState('');
  const [phone, setPhone] = useState('');
  const [message, setMessage] = useState('');
  const [delivery, setDelivery] = useState<'click' | 'share'>('click');
  const [later, setLater] = useState('');
  const [method, setMethod] = useState('wallet');
  const [err, setErr] = useState('');
  const [key] = useState(newKey);
  const buy = useMutation({
    mutationFn: () => api.money.giftCards.buy({ designId: d.id, amount: Number(amount).toFixed(2), recipientName: name.trim(), recipientPhone: delivery === 'click' ? phone.replace(/\s/g, '') : '',
      message: message.trim(), delivery, deliverOn: later || null, paymentMethod: method, idempotencyKey: key }),
    onSuccess: (card) => { qc.invalidateQueries({ queryKey: ['giftcards'] }); qc.invalidateQueries({ queryKey: ['customer', 'wallet'] }); if (card.paymentIntent) setStep('pay'); else nav(`/gift-cards/mine/${card.id}`, { state: { bought: true } }); },
    onError: (e) => setErr(e instanceof ApiError ? e.message : 'Couldn’t buy the gift card. Nothing was charged.'),
  });
  const v = Number(amount);
  const amountErr = !v || v < Number(d.minAmount) || v > Number(d.maxAmount) ? `Choose between ${money(d.minAmount)} and ${money(d.maxAmount)}.` : '';
  const today = new Date().toISOString().slice(0, 10);
  const maxDate = new Date(Date.now() + 90 * 86_400_000).toISOString().slice(0, 10);
  if (status !== 'authenticated') {
    return <Sheet open onClose={onClose} label="Sign in"><div className="mn-sheet mn-form"><h2>Sign in to buy a gift card</h2><Link to="/login?next=/gift-cards" className="btn btn--primary">Sign in</Link></div></Sheet>;
  }
  return (
    <Sheet open onClose={onClose} label={`Buy ${d.title}`}>
      <div className="mn-sheet mn-form">
        <GiftArt d={d} amount={String(v || 0)} small />
        {step === 'amount' && (
          <>
            <h2>Choose an amount</h2>
            <div className="mn-chips mn-chips--wrap">{d.presets.map((p) => <button key={p} type="button" className="mn-chip" aria-pressed={Number(p) === v} onClick={() => setAmount(p)}>{money(p)}</button>)}</div>
            <label className="mn-amount"><span>₹</span><input inputMode="numeric" value={amount} onChange={(e) => setAmount(e.target.value.replace(/\D/g, '').slice(0, 5))} aria-label="Custom amount" /></label>
            {amountErr && <p className="small mn-muted">{amountErr}</p>}
            <Button block disabled={!!amountErr} onClick={() => setStep('recipient')}>Continue</Button>
          </>
        )}
        {step === 'recipient' && (
          <form className="mn-form" onSubmit={(e) => { e.preventDefault(); if (!name.trim()) return setErr('Add the recipient’s name.'); if (delivery === 'click' && !/^\+[1-9]\d{7,14}$/.test(phone.replace(/\s/g, ''))) return setErr('Add their mobile number with the country code, e.g. +91 98765 43210.'); setErr(''); setStep('review'); }}>
            <h2>Who is it for?</h2>
            <label className="mn-field"><span>Their name</span><input value={name} maxLength={80} onChange={(e) => setName(e.target.value)} /></label>
            <fieldset className="mn-field"><legend>Delivery</legend>
              <label className="mn-option"><input type="radio" checked={delivery === 'click'} onChange={() => setDelivery('click')} /><span>To their Click. account (by mobile number)</span></label>
              <label className="mn-option"><input type="radio" checked={delivery === 'share'} onChange={() => setDelivery('share')} /><span>I’ll share the code myself</span></label>
            </fieldset>
            {delivery === 'click' && <label className="mn-field"><span>Their mobile number</span><input inputMode="tel" placeholder="+91 98765 43210" value={phone} onChange={(e) => setPhone(e.target.value)} /></label>}
            <label className="mn-field"><span>Message <span className="mn-muted small">(optional)</span></span><textarea rows={2} maxLength={300} value={message} onChange={(e) => setMessage(e.target.value)} /></label>
            <label className="mn-field"><span>Deliver later <span className="mn-muted small">(optional)</span></span><input type="date" min={today} max={maxDate} value={later} onChange={(e) => setLater(e.target.value)} /></label>
            {err && <p className="mn-error small" role="alert">{err}</p>}
            <div className="mn-row2"><Button variant="secondary" onClick={() => setStep('amount')}>Back</Button><Button type="submit">Review</Button></div>
          </form>
        )}
        {step === 'review' && (
          <>
            <h2>Review</h2>
            <dl className="mn-dl">
              <div><dt>Gift card</dt><dd>{d.title}</dd></div><div><dt>Value</dt><dd>{money(v)}</dd></div>
              <div><dt>For</dt><dd>{name}{delivery === 'click' ? ` · ${phone}` : ''}</dd></div>
              <div><dt>Delivery</dt><dd>{delivery === 'click' ? 'Their Click. account' : 'Code for you to share'}{later ? ` on ${dateOf(later)}` : ', right away'}</dd></div>
              <div><dt>Usable on</dt><dd>{d.services.map((s) => s.label).join(', ')}</dd></div><div><dt>Valid for</dt><dd>{Math.round(d.validityDays / 30)} months</dd></div>
            </dl>
            <fieldset className="mn-field"><legend>Pay with</legend>
              <label className="mn-option"><input type="radio" checked={method === 'wallet'} onChange={() => setMethod('wallet')} /><Icon name="wallet" size={18} /><span>Click. Wallet{wallet.data ? ` · ${money(wallet.data.balance)}` : ''}</span></label>
              {online?.available && online.methods.map((m) => <label key={m.code} className="mn-option"><input type="radio" checked={method === m.code} onChange={() => setMethod(m.code)} /><Icon name="card" size={18} /><span>{m.label}</span></label>)}
            </fieldset>
            <p className="small mn-muted">{d.terms}</p>
            {err && <p className="mn-error small" role="alert">{err}</p>}
            <div className="mn-row2"><Button variant="secondary" onClick={() => setStep('recipient')}>Back</Button><Button loading={buy.isPending} onClick={() => { setErr(''); buy.mutate(); }}>Pay {money(v)}</Button></div>
          </>
        )}
        {step === 'pay' && buy.data?.paymentIntent && (
          <>
            <PayOnline intent={buy.data.paymentIntent} onSettled={(s) => { if (s === 'succeeded') nav(`/gift-cards/mine/${buy.data!.id}`, { state: { bought: true } }); }} />
          </>
        )}
      </div>
    </Sheet>
  );
}

export function MyGiftCardsPage() {
  const qc = useQueryClient();
  const toast = useToast();
  const [params] = useSearchParams();
  const q = useQuery({ queryKey: ['giftcards', 'mine'], queryFn: api.money.giftCards.mine });
  const [code, setCode] = useState('');
  const redeem = useMutation({
    mutationFn: () => api.money.giftCards.redeem(code),
    onSuccess: (c) => { setCode(''); qc.invalidateQueries({ queryKey: ['giftcards'] }); toast(`${money(c.balance)} gift card added`); },
  });
  return (
    <div className="mn-page gc-page">
      <MoneyHead title="My gift cards" back="/gift-cards" />
      <form className="mn-card gc-redeem" onSubmit={(e) => { e.preventDefault(); if (code.trim()) redeem.mutate(); }}>
        <label className="mn-field"><span>Redeem a gift card</span><input value={code} autoFocus={params.get('redeem') === '1'} placeholder="XXXX-XXXX-XXXX-XXXX" maxLength={19} autoCapitalize="characters"
          onChange={(e) => setCode(e.target.value.toUpperCase())} aria-label="Gift card code" /></label>
        {redeem.isError && <p className="mn-error small" role="alert">{redeem.error instanceof ApiError ? redeem.error.message : 'Couldn’t redeem.'}</p>}
        <Button type="submit" loading={redeem.isPending} disabled={code.replace(/[^A-Z0-9]/g, '').length < 16}>Redeem</Button>
      </form>
      {q.isError ? <ErrorState error={q.error} onRetry={() => q.refetch()} /> : !q.data ? <Skeleton height={240} /> : (
        <>
          <Section title="Yours to spend" id="gc-held">
            {q.data.held.length === 0 ? <p className="small mn-muted">Gift cards sent to you or redeemed by you appear here.</p> : (
              <div className="gc-grid">{q.data.held.map((c) => (
                <Link key={c.id} to={`/gift-cards/mine/${c.id}`} className="gc-tile"><GiftArt d={c.design} amount={c.balance} />
                  <span className="small">{c.fromName ? `From ${c.fromName}` : c.design.title} · <Pill tone={c.status === 'active' ? 'ok' : 'info'}>{c.statusLabel}</Pill></span>
                  {c.expiresAt && <span className="small mn-muted">Valid till {dateOf(c.expiresAt)}</span>}</Link>
              ))}</div>
            )}
          </Section>
          <Section title="Sent by you" id="gc-sent">
            {q.data.sent.length === 0 ? <p className="small mn-muted">Gift cards you buy for others appear here. <Link to="/gift-cards" className="mn-link">Buy one</Link></p> : (
              <ul className="mn-list">{q.data.sent.map((c) => (
                <li key={c.id}><Link to={`/gift-cards/mine/${c.id}`} className="mn-row"><span className="mn-row__icon"><Icon name="gift" size={18} /></span>
                  <span className="mn-row__text"><strong className="truncate">{c.design.title} for {c.recipientName}</strong>
                    <span className="small mn-muted">{money(c.amount)} · {c.redeemed ? 'Redeemed' : c.statusLabel}{c.deliverOn && !c.deliveredAt ? ` · delivers ${dateOf(c.deliverOn)}` : ''}</span></span>
                  <Icon name="right" size={16} /></Link></li>
              ))}</ul>
            )}
          </Section>
        </>
      )}
    </div>
  );
}

export function GiftCardDetailPage() {
  const { id = '' } = useParams();
  const toast = useToast();
  const q = useQuery({ queryKey: ['giftcards', 'card', id], queryFn: () => api.money.giftCards.get(id) });
  if (q.isError) return <div className="mn-page"><MoneyHead title="Gift card" back="/gift-cards/mine" /><ErrorState error={q.error} onRetry={() => q.refetch()} /></div>;
  if (!q.data) return <div className="mn-page"><MoneyHead title="Gift card" back="/gift-cards/mine" /><Skeleton height={300} /></div>;
  const c = q.data;
  const share = async () => {
    const text = `${c.fromName ? '' : ''}A Click. gift card for you: ${money(c.amount)}. Redeem code ${c.code} in Click. → Gift Cards.${c.message ? ` “${c.message}”` : ''}`;
    try { if (navigator.share) await navigator.share({ title: 'Click. gift card', text }); else { await navigator.clipboard.writeText(text); toast('Copied — paste it to them'); } } catch { /* cancelled */ }
  };
  const canShare = c.role === 'buyer' && !c.redeemed && !c.code.startsWith('••••');
  return (
    <div className="mn-page gc-page">
      <MoneyHead title={c.design.title} back="/gift-cards/mine" />
      {c.paymentIntent && c.status === 'awaiting_payment' && <PayOnline intent={c.paymentIntent} onSettled={() => q.refetch()} />}
      <GiftArt d={c.design} amount={c.role === 'holder' ? c.balance : c.amount} />
      <section className="mn-card">
        <dl className="mn-dl">
          <div><dt>Status</dt><dd><Pill tone={c.status === 'active' ? 'ok' : c.status === 'awaiting_payment' ? 'pending' : 'info'}>{c.statusLabel}</Pill></dd></div>
          {c.role === 'holder' && <div><dt>Balance</dt><dd><strong>{money(c.balance)}</strong> of {money(c.amount)}</dd></div>}
          <div><dt>{c.role === 'holder' ? 'From' : 'For'}</dt><dd>{c.role === 'holder' ? c.fromName || 'A friend' : c.recipientName}</dd></div>
          <div><dt>Code</dt><dd className="mn-mono">{c.code}</dd></div>
          <div><dt>Delivery</dt><dd>{c.deliveryLabel}{c.deliverOn ? ` · ${dateOf(c.deliverOn)}` : ''}</dd></div>
          {c.expiresAt && <div><dt>Valid till</dt><dd>{dateOf(c.expiresAt)}</dd></div>}
          <div><dt>Use on</dt><dd>{c.design.services.map((s) => s.label).join(', ')}</dd></div>
        </dl>
        {c.message && <p className="gc-msg">“{c.message}”</p>}
      </section>
      {canShare && <Button onClick={share}><Icon name="share" size={16} /> Share the code with {c.recipientName}</Button>}
      {c.role === 'holder' && c.status === 'active' && (
        <div className="mn-chips mn-chips--wrap">{c.design.services.map((s) => <Link key={s.code} to={s.code === 'shop' ? '/shopping' : `/${s.code}`} className="mn-chip">Use on {s.label}</Link>)}</div>
      )}
      {c.entries && c.entries.length > 0 && (
        <Section title="Transactions" id="gc-tx">
          <ul className="mn-list">{c.entries.map((e) => (
            <li key={e.id} className="mn-row mn-row--static"><span className="mn-row__icon"><Icon name={e.kind === 'spend' ? 'bag' : e.kind === 'refund' ? 'history' : e.kind === 'expire' ? 'clock' : 'gift'} size={18} /></span>
              <span className="mn-row__text"><strong>{e.kindLabel}</strong><span className="small mn-muted">{e.description} · {dateOf(e.at)}</span></span>
              <strong className={Number(e.amount) > 0 ? 'mn-ok' : ''}>{Number(e.amount) > 0 ? '+' : '−'}{money(Math.abs(Number(e.amount)))}</strong></li>
          ))}</ul>
        </Section>
      )}
      <details className="mn-card small"><summary>Terms</summary><p>{c.design.terms}</p></details>
      <Link to={`/help/new?category=payment&subject=${encodeURIComponent(`Gift card ${c.code.slice(-4)}`)}`} className="mn-row mn-row--card"><span className="mn-row__icon"><Icon name="help" size={18} /></span>
        <span className="mn-row__text"><strong>Get help with this gift card</strong></span><Icon name="right" size={16} /></Link>
    </div>
  );
}

/** Pay with a gift card at Food / Groceries / Shop checkout (the card must cover the whole order). */
export function GiftCardOption({ service, total, value, onSelect }: { service: string; total: string | number; value: { method: string; card: string }; onSelect: (cardId: string) => void }) {
  const { status } = useAuth();
  const q = useQuery({ queryKey: ['giftcards', 'usable', service], queryFn: () => api.money.giftCards.usable(service), enabled: status === 'authenticated' });
  if (!q.data?.results.length) return null;
  return (
    <>
      {q.data.results.map((g) => {
        const enough = Number(g.balance) >= Number(total);
        return (
          <label key={g.id} className="option" style={!enough ? { opacity: 0.6 } : undefined}>
            <input type="radio" name="payment" disabled={!enough} checked={value.method === 'gift_card' && value.card === g.id} onChange={() => onSelect(g.id)} />
            <div><strong>{g.title} ••••{g.codeEnd}</strong><div className="muted small">{money(g.balance)} left{enough ? '' : ' — not enough for this order'}</div></div>
          </label>
        );
      })}
    </>
  );
}
