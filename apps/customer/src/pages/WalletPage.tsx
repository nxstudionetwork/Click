import { useEffect, useMemo, useState } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import { useInfiniteQuery, useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { ApiError, type Wallet, type WalletFilter, type WalletTopUp } from '@click/api';
import { Button, EmptyState, ErrorState, Icon, Sheet, Skeleton, useToast } from '../components/ui';
import { walletKey } from '../features/wallet/useWallet';
import { MoneyHead, Section, dateOf, groupByDay, iconFor, money, newKey, signed, timeOf } from '../features/money/parts';
import { api } from '../lib/api';

const FILTERS: { id: WalletFilter; label: string }[] = [
  { id: '', label: 'All' }, { id: 'added', label: 'Added' }, { id: 'spent', label: 'Spent' }, { id: 'refunds', label: 'Refunds' },
  { id: 'cashback', label: 'Cashback' }, { id: 'rewards', label: 'Rewards' }, { id: 'promo', label: 'Promo credit' }, { id: 'expired', label: 'Expired' },
];
const KIND_ICON: Record<string, Parameters<typeof Icon>[0]['name']> = {
  topup: 'plus', refund: 'history', promo: 'gift', cashback: 'tag', reward: 'star', payment: 'card', expiry: 'clock', adjustment: 'settings',
};
const HIDE_KEY = 'click.wallet.hidden';

function readHidden() { try { return localStorage.getItem(HIDE_KEY) === '1'; } catch { return false; } }

/** Click. Wallet: a server-side ledger. The balance shown is the ledger's; money is added only after the payment
 *  provider's signed confirmation is verified on the server. No withdrawals or transfers. */
export function WalletPage() {
  const wq = useQuery({ queryKey: walletKey, queryFn: api.customer.wallet });
  const [hidden, setHidden] = useState(readHidden);
  const [params, setParams] = useSearchParams();
  const [adding, setAdding] = useState(params.get('add') === '1');
  const [showLimits, setShowLimits] = useState(false);
  const toggleHidden = () => { const v = !hidden; setHidden(v); try { localStorage.setItem(HIDE_KEY, v ? '1' : '0'); } catch { /* private mode */ } };

  if (wq.isError) return <div className="mn-page"><MoneyHead title="Click. Wallet" /><ErrorState error={wq.error} onRetry={() => wq.refetch()} /></div>;
  if (!wq.data) return <div className="mn-page"><MoneyHead title="Click. Wallet" /><Skeleton height={190} radius={24} /><Skeleton height={120} /><Skeleton height={260} /></div>;
  const w = wq.data;
  const mask = (v: string) => (hidden ? '₹ ••••' : money(v));
  const restricted = w.status !== 'active';

  return (
    <div className="mn-page">
      <MoneyHead title="Click. Wallet" />

      <section className="mn-wallet" aria-label="Wallet balance">
        <div className="mn-wallet__top">
          <span className="mn-wallet__label">Available balance</span>
          <button type="button" className="mn-wallet__eye" onClick={toggleHidden} aria-pressed={hidden} aria-label={hidden ? 'Show balance' : 'Hide balance'}>
            <Icon name={hidden ? 'eye' : 'eyeOff'} size={18} />
          </button>
        </div>
        <strong className="mn-wallet__value" aria-live="polite">{mask(w.balance)}</strong>
        <div className="mn-wallet__split">
          <span><span className="mn-dot mn-dot--cash" />Wallet balance <b>{mask(w.breakdown.cash)}</b></span>
          <span><span className="mn-dot mn-dot--promo" />Promo credit <b>{mask(w.breakdown.promo)}</b></span>
        </div>
        {w.lastUpdated && <span className="mn-wallet__meta">Updated {dateOf(w.lastUpdated)}, {timeOf(w.lastUpdated)} · {w.statusLabel}</span>}
        <div className="mn-wallet__actions">
          <button type="button" className="mn-wallet__btn mn-wallet__btn--main" onClick={() => setAdding(true)} disabled={!w.topUpAvailable}>
            <Icon name="plus" size={18} /> Add money
          </button>
          <Link to="/account/payments" className="mn-wallet__btn"><Icon name="card" size={18} /> Payments</Link>
          <Link to="/rewards" className="mn-wallet__btn"><Icon name="star" size={18} /> {w.rewardsPoints.toLocaleString('en-IN')} pts</Link>
        </div>
        {!w.topUpAvailable && !restricted && <p className="mn-wallet__note">Adding money needs a connected payment provider, which isn’t available right now. Refunds, cashback and rewards still arrive here.</p>}
      </section>

      {restricted && (
        <div className="mn-banner mn-banner--bad" role="status">
          <Icon name="shield" size={20} />
          <div><strong>Wallet {w.statusLabel.toLowerCase()}</strong><p className="small">{w.statusReason || 'Adding money and paying with the wallet are paused. Your balance is safe.'}</p>
            <Link to="/help/new?category=wallet" className="mn-link small">Contact support</Link></div>
        </div>
      )}

      {w.expiring.length > 0 && (
        <div className="mn-banner mn-banner--warn" role="status">
          <Icon name="clock" size={20} />
          <div><strong>{money(w.expiring.reduce((s, c) => s + Number(c.remaining), 0))} of promo credit expires soon</strong>
            <p className="small">{w.expiring.map((c) => `${money(c.remaining)} on ${dateOf(c.expiresAt!)}`).join(' · ')}. Promo credit is spent first at checkout.</p></div>
        </div>
      )}

      <Section title="This month" id="mn-month">
        <div className="mn-stats">
          <div><span className="small mn-muted">Spent</span><strong>{mask(w.summary.spent)}</strong></div>
          <div><span className="small mn-muted">Added</span><strong>{mask(w.summary.added)}</strong></div>
          <div><span className="small mn-muted">Refunds</span><strong>{mask(w.summary.refunds)}</strong></div>
          <div><span className="small mn-muted">Cashback & rewards</span><strong>{mask(String(Number(w.summary.cashback) + Number(w.summary.rewards)))}</strong></div>
        </div>
      </Section>

      {w.credits.length > 0 && (
        <Section title="Promo credit" id="mn-credits">
          <ul className="mn-list">
            {w.credits.map((c) => (
              <li key={c.id}><Link to={`/wallet/activity/${c.id}`} className="mn-row">
                <span className="mn-row__icon mn-row__icon--promo"><Icon name={KIND_ICON[c.kind] ?? 'gift'} size={18} /></span>
                <span className="mn-row__text"><strong className="truncate">{c.description}</strong>
                  <span className="small mn-muted">{c.kindLabel}{c.expiresAt ? ` · valid till ${dateOf(c.expiresAt)}` : ''}</span></span>
                <strong className="mn-row__amt">{money(c.remaining)}</strong>
              </Link></li>
            ))}
          </ul>
          <p className="small mn-muted">Promo credit is used before your wallet balance, soonest-expiring first, and can’t be withdrawn.</p>
        </Section>
      )}

      <Section title="Use your wallet" id="mn-use">
        <div className="mn-chips mn-chips--wrap">
          {w.eligibleServices.map((s) => <Link key={s.code} to={s.path} className="mn-chip"><Icon name={iconFor(s.code)} size={16} /> {s.label}</Link>)}
        </div>
        <p className="small mn-muted">Pay the full amount with Click. Wallet at checkout. Splitting one payment between the wallet and another method isn’t available.</p>
      </Section>

      <WalletActivity hidden={hidden} filter={(params.get('filter') ?? '') as WalletFilter} setFilter={(f) => setParams(f ? { filter: f } : {}, { replace: true })} />

      <Section title="Limits & security" id="mn-limits" action={<button type="button" className="mn-link small" onClick={() => setShowLimits((v) => !v)} aria-expanded={showLimits}>{showLimits ? 'Hide' : 'Show'}</button>}>
        {showLimits && <Limits w={w} />}
        <div className="mn-list">
          <Link to="/help/new?category=wallet" className="mn-row"><span className="mn-row__icon"><Icon name="alert" size={18} /></span>
            <span className="mn-row__text"><strong>Report a wallet problem</strong><span className="small mn-muted">A transaction you don’t recognise, a missing refund or a failed top-up</span></span><Icon name="right" size={16} /></Link>
          <Link to="/help/articles/wallet-credits" className="mn-row"><span className="mn-row__icon"><Icon name="book" size={18} /></span>
            <span className="mn-row__text"><strong>Promo credit, cashback and expiry</strong><span className="small mn-muted">How credits are used and when they expire</span></span><Icon name="right" size={16} /></Link>
        </div>
      </Section>

      {adding && <AddMoney w={w} onClose={() => { setAdding(false); if (params.get('add')) setParams({}, { replace: true }); }} />}
    </div>
  );
}

function Limits({ w }: { w: Wallet }) {
  const sec = useQuery({ queryKey: ['wallet', 'security'], queryFn: api.money.wallet.security });
  return (
    <div className="mn-card">
      <dl className="mn-dl">
        <div><dt>Add per top-up</dt><dd>{money(w.limits.minTopup)} – {money(w.limits.maxTopup)}</dd></div>
        <div><dt>Add per day</dt><dd>{money(w.limits.dailyTopup)}</dd></div>
        <div><dt>Add per month</dt><dd>{money(w.limits.monthlyTopup)}</dd></div>
        <div><dt>Maximum balance</dt><dd>{money(w.limits.maxBalance)}</dd></div>
      </dl>
      {sec.data && (
        <>
          <h3 className="mn-h3">Protection</h3>
          <ul className="mn-bullets small">{sec.data.protections.map((p) => <li key={p}>{p}</li>)}</ul>
          {sec.data.failedTopups > 0 && <p className="small mn-warn">{sec.data.failedTopups} failed attempt{sec.data.failedTopups > 1 ? 's' : ''} to add money in the last 30 days.</p>}
        </>
      )}
    </div>
  );
}

function WalletActivity({ hidden, filter, setFilter }: { hidden: boolean; filter: WalletFilter; setFilter: (f: WalletFilter) => void }) {
  const [q, setQ] = useState('');
  const [term, setTerm] = useState('');
  useEffect(() => { const t = setTimeout(() => setTerm(q.trim()), 300); return () => clearTimeout(t); }, [q]);
  const list = useInfiniteQuery({
    queryKey: ['wallet', 'transactions', filter, term],
    queryFn: ({ pageParam }) => api.money.wallet.transactions({ filter, q: term, page: pageParam }),
    initialPageParam: 1,
    getNextPageParam: (last) => (last.hasNext ? last.page + 1 : undefined),
  });
  const rows = useMemo(() => list.data?.pages.flatMap((p) => p.results) ?? [], [list.data]);
  return (
    <Section title="Wallet activity" id="mn-activity">
      <div className="mn-search">
        <Icon name="search" size={18} />
        <input type="search" value={q} onChange={(e) => setQ(e.target.value)} placeholder="Search by amount, order or reference" aria-label="Search wallet activity" />
      </div>
      <div className="mn-chips" role="group" aria-label="Filter wallet activity">
        {FILTERS.map((f) => <button key={f.id || 'all'} type="button" className="mn-chip" aria-pressed={filter === f.id} onClick={() => setFilter(f.id)}>{f.label}</button>)}
      </div>
      {list.isError ? <ErrorState error={list.error} onRetry={() => list.refetch()} /> : !list.data ? <Skeleton height={200} /> : rows.length === 0 ? (
        <EmptyState icon="wallet" title={term || filter ? 'Nothing matches' : 'No wallet activity yet'} message={term || filter ? 'Try another filter or search.' : 'Money you add, payments, refunds and credits will appear here.'} />
      ) : (
        <>
          {groupByDay(rows, (r) => r.createdAt).map((g) => (
            <div key={g.label} className="mn-group">
              <h3 className="mn-group__label">{g.label}</h3>
              <ul className="mn-list">
                {g.rows.map((t) => (
                  <li key={t.id}><Link to={`/wallet/activity/${t.id}`} className="mn-row">
                    <span className={`mn-row__icon ${t.bucket === 'promo' ? 'mn-row__icon--promo' : ''}`}><Icon name={KIND_ICON[t.kind] ?? 'receipt'} size={18} /></span>
                    <span className="mn-row__text"><strong className="truncate">{t.service?.label ? `${t.kindLabel} · ${t.service.label}` : t.kindLabel}</strong>
                      <span className="small mn-muted truncate">{t.description} · {timeOf(t.createdAt)}</span></span>
                    <strong className={`mn-row__amt ${t.direction === 'credit' ? 'mn-ok' : ''}`}>{hidden ? '••••' : signed(t.amount)}</strong>
                  </Link></li>
                ))}
              </ul>
            </div>
          ))}
          {list.hasNextPage && <Button variant="secondary" block loading={list.isFetchingNextPage} onClick={() => list.fetchNextPage()}>Load more</Button>}
        </>
      )}
    </Section>
  );
}

type Step = 'amount' | 'method' | 'review' | 'provider' | 'result';
const METHOD_LABEL: Record<string, string> = { upi: 'UPI', card: 'Debit / credit card', netbanking: 'Net banking' };

/** Amount → method → review → provider → server verification → result. The wallet changes only when the server
 *  has verified the provider's signed confirmation; this screen just shows that state. */
function AddMoney({ w, onClose }: { w: Wallet; onClose: () => void }) {
  const qc = useQueryClient();
  const toast = useToast();
  const [step, setStep] = useState<Step>('amount');
  const [amount, setAmount] = useState('');
  const [method, setMethod] = useState(w.topUp?.methods[0] ?? 'upi');
  const [key] = useState(newKey);
  const [topup, setTopup] = useState<WalletTopUp | null>(null);
  const [err, setErr] = useState('');
  const min = Number(w.limits.minTopup), max = Number(w.limits.maxTopup);
  const value = Number(amount);
  const after = Number(w.balance) + (value || 0);

  const start = useMutation({
    mutationFn: () => api.money.wallet.startTopUp({ amount: value.toFixed(2), method, idempotencyKey: key }),
    onSuccess: (t) => { setTopup(t); setStep('provider'); },
    onError: (e) => setErr(e instanceof ApiError ? e.message : 'Couldn’t start the payment. Nothing was charged.'),
  });
  const decide = useMutation({
    mutationFn: (outcome: 'succeeded' | 'failed') => api.money.wallet.sandbox(topup!.id, outcome),
    onSuccess: (t) => { setTopup(t); setStep('result'); },
    onError: (e) => setErr(e instanceof ApiError ? e.message : 'The payment provider didn’t respond. We’ll update this as soon as it does.'),
  });
  // While a top-up is waiting for the provider, read its status from the server (never assume success).
  const status = useQuery({
    queryKey: ['wallet', 'topup', topup?.id], queryFn: () => api.money.wallet.topUp(topup!.id),
    enabled: !!topup && step === 'result' && (topup.status === 'pending' || topup.status === 'created'), refetchInterval: 3000,
  });
  const current = status.data ?? topup;
  useEffect(() => {
    if (current?.status === 'succeeded') { qc.invalidateQueries({ queryKey: walletKey }); qc.invalidateQueries({ queryKey: ['wallet'] }); }
  }, [current?.status, qc]);

  const validAmount = () => {
    if (!value || Number.isNaN(value)) return 'Enter an amount.';
    if (value < min) return `The minimum is ${money(min)}.`;
    if (value > max) return `The maximum per top-up is ${money(max)}.`;
    if (after > Number(w.limits.maxBalance)) return `Your balance can’t go above ${money(w.limits.maxBalance)}.`;
    return '';
  };

  return (
    <Sheet open onClose={() => { if (current?.status === 'succeeded') toast('Money added'); onClose(); }} label="Add money to Click. Wallet">
      <div className="mn-sheet">
        <div className="mn-steps" aria-label="Progress">{(['amount', 'method', 'review', 'provider', 'result'] as Step[]).map((s, i) => <span key={s} className={`mn-steps__dot ${s === step ? 'is-on' : ''}`} aria-current={s === step ? 'step' : undefined}>{i + 1}</span>)}</div>

        {step === 'amount' && (
          <form className="mn-form" onSubmit={(e) => { e.preventDefault(); const m = validAmount(); setErr(m); if (!m) setStep('method'); }}>
            <h2>Add money</h2>
            <label className="mn-amount"><span>₹</span>
              <input inputMode="decimal" autoFocus value={amount} onChange={(e) => setAmount(e.target.value.replace(/[^\d.]/g, '').replace(/(\..{2}).*/, '$1'))} placeholder="0" aria-label="Amount in rupees" />
            </label>
            <div className="mn-chips">{(w.topUp?.presets ?? []).map((p) => <button key={p} type="button" className="mn-chip" aria-pressed={Number(p) === value} onClick={() => setAmount(String(Number(p)))}>{money(p)}</button>)}</div>
            <p className="small mn-muted">Current balance {money(w.balance)}{value ? ` · after adding ${money(after)}` : ''}. Between {money(min)} and {money(max)} per top-up.</p>
            {err && <p className="mn-error small" role="alert">{err}</p>}
            <Button type="submit" block>Continue</Button>
          </form>
        )}

        {step === 'method' && (
          <div className="mn-form">
            <h2>Pay with</h2>
            <div className="mn-options" role="radiogroup" aria-label="Payment method">
              {(w.topUp?.methods ?? []).map((m) => (
                <label key={m} className={`mn-option ${method === m ? 'is-on' : ''}`}>
                  <input type="radio" name="method" checked={method === m} onChange={() => setMethod(m)} />
                  <Icon name={m === 'upi' ? 'phone' : m === 'card' ? 'card' : 'store'} size={20} /><span>{METHOD_LABEL[m] ?? m}</span>
                </label>
              ))}
            </div>
            <p className="small mn-muted">You’ll complete the payment with the payment provider. Click. never sees or stores your UPI PIN, card number or bank password.</p>
            <div className="mn-row2"><Button variant="secondary" onClick={() => setStep('amount')}>Back</Button><Button onClick={() => setStep('review')}>Review</Button></div>
          </div>
        )}

        {step === 'review' && (
          <div className="mn-form">
            <h2>Review</h2>
            <dl className="mn-dl">
              <div><dt>Amount</dt><dd>{money(value)}</dd></div>
              <div><dt>Method</dt><dd>{METHOD_LABEL[method]}</dd></div>
              <div><dt>Fee</dt><dd>None</dd></div>
              <div><dt>Balance after</dt><dd>{money(after)}</dd></div>
            </dl>
            <p className="small mn-muted">Money added to Click. Wallet can be spent on Click. services. It can’t be withdrawn to a bank account or sent to someone else.</p>
            {err && <p className="mn-error small" role="alert">{err}</p>}
            <div className="mn-row2"><Button variant="secondary" onClick={() => setStep('method')}>Back</Button>
              <Button loading={start.isPending} onClick={() => { setErr(''); start.mutate(); }}>Pay {money(value)}</Button></div>
          </div>
        )}

        {step === 'provider' && topup && (
          <div className="mn-form">
            <h2>Payment provider</h2>
            {topup.client?.testMode ? (
              <>
                <div className="mn-banner mn-banner--warn"><Icon name="alert" size={20} /><div><strong>Test mode</strong><p className="small">{topup.client.instructions}</p></div></div>
                <dl className="mn-dl"><div><dt>Amount</dt><dd>{money(topup.amount)}</dd></div><div><dt>Reference</dt><dd className="mn-mono">{topup.providerReference}</dd></div></dl>
                {err && <p className="mn-error small" role="alert">{err}</p>}
                <div className="mn-row2">
                  <Button variant="secondary" loading={decide.isPending && decide.variables === 'failed'} onClick={() => decide.mutate('failed')}>Decline</Button>
                  <Button loading={decide.isPending && decide.variables === 'succeeded'} onClick={() => decide.mutate('succeeded')}>Approve test payment</Button>
                </div>
              </>
            ) : (
              <p>Complete the payment in the provider’s window. This screen updates once the provider confirms it.</p>
            )}
          </div>
        )}

        {step === 'result' && current && (
          <div className="mn-form mn-result">
            {current.status === 'succeeded' ? (
              <><span className="mn-result__icon mn-result__icon--ok"><Icon name="check" size={28} /></span><h2>{money(current.amount)} added</h2>
                <p className="mn-muted">Verified with the payment provider and credited to your wallet.</p>
                {current.transactionId && <Link to={`/wallet/activity/${current.transactionId}`} className="mn-link" onClick={onClose}>View transaction</Link>}</>
            ) : current.status === 'failed' || current.status === 'expired' ? (
              <><span className="mn-result__icon mn-result__icon--bad"><Icon name="close" size={28} /></span><h2>Money wasn’t added</h2>
                <p className="mn-muted">{current.failureReason || 'The payment didn’t go through.'} If money left your account, it’s returned by your bank or payment app as per their timelines.</p>
                <Link to="/help/new?category=wallet" className="mn-link" onClick={onClose}>Get help</Link></>
            ) : (
              <><span className="mn-result__icon"><Icon name="clock" size={28} /></span><h2>Waiting for confirmation</h2>
                <p className="mn-muted">We’ll credit your wallet only after the payment provider confirms. You can close this; we’ll notify you.</p></>
            )}
            <Button block onClick={() => { if (current.status === 'succeeded') toast('Money added'); onClose(); }}>Done</Button>
          </div>
        )}
      </div>
    </Sheet>
  );
}
