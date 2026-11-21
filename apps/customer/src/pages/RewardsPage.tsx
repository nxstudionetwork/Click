import { useMemo, useState } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import { useInfiniteQuery, useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { ApiError, type RewardItem, type Rewards } from '@click/api';
import { Button, EmptyState, ErrorState, Icon, Sheet, Skeleton, useToast } from '../components/ui';
import { walletKey } from '../features/wallet/useWallet';
import { MoneyHead, Section, dateOf, groupByDay, iconFor, money, newKey, timeOf } from '../features/money/parts';
import { api } from '../lib/api';

const TABS = [['', 'Overview'], ['earn', 'Ways to earn'], ['redeem', 'Redeem'], ['history', 'History']] as const;
const HISTORY = [['', 'All'], ['earn', 'Earned'], ['redeem', 'Redeemed'], ['expire', 'Expired'], ['adjust', 'Adjustments']];
const pts = (n: number) => n.toLocaleString('en-IN');

/** Click. Rewards: points from the rewards ledger, tiers from configuration, missions measured from real orders and
 *  bookings, and redemption that converts points into Click. Wallet credit in one server transaction. */
export function RewardsPage() {
  const rq = useQuery({ queryKey: ['customer', 'rewards'], queryFn: api.money.rewards.get });
  const [params, setParams] = useSearchParams();
  const tab = params.get('tab') ?? '';
  if (rq.isError) return <div className="mn-page"><MoneyHead title="Click. Rewards" /><ErrorState error={rq.error} onRetry={() => rq.refetch()} /></div>;
  if (!rq.data) return <div className="mn-page"><MoneyHead title="Click. Rewards" /><Skeleton height={200} radius={24} /><Skeleton height={240} /></div>;
  const r = rq.data;
  const t = r.tier;
  const pct = t.next ? Math.min(100, Math.round((t.qualifyingPoints / t.next.minPoints) * 100)) : 100;
  return (
    <div className="mn-page">
      <MoneyHead title="Click. Rewards" />
      <section className="mn-rewards" aria-label="Your points">
        <span className="mn-rewards__tier"><Icon name="star" size={16} /> {t.name} · {t.multiplier}× points</span>
        <strong className="mn-rewards__value">{pts(r.balance)} <span>points</span></strong>
        <div className="mn-progress" role="progressbar" aria-valuemin={0} aria-valuemax={100} aria-valuenow={pct} aria-label={t.next ? `Progress to ${t.next.name}` : 'Top tier'}><span style={{ width: `${pct}%` }} /></div>
        <span className="small">{t.next ? `${pts(t.toNext)} more points in 12 months to reach ${t.next.name}` : 'You’re at the top tier.'}</span>
        <div className="mn-rewards__row">
          <span><b>{pts(r.earnedThisMonth)}</b> earned this month</span><span><b>{pts(r.redeemed)}</b> redeemed</span><span><b>{pts(r.expired)}</b> expired</span>
        </div>
      </section>

      {r.expiring.length > 0 && (
        <div className="mn-banner mn-banner--warn"><Icon name="clock" size={20} /><div>
          <strong>{pts(r.expiring.reduce((s, e) => s + e.points, 0))} points expire soon</strong>
          <p className="small">{r.expiring.map((e) => `${pts(e.points)} on ${dateOf(e.expiresAt)}`).join(' · ')}</p>
          <button type="button" className="mn-link small" onClick={() => setParams({ tab: 'redeem' })}>Redeem now</button></div></div>
      )}

      <div className="mn-tabs" role="tablist">
        {TABS.map(([id, label]) => <button key={id || 'o'} type="button" role="tab" className="mn-tab" aria-selected={tab === id} onClick={() => setParams(id ? { tab: id } : {})}>{label}</button>)}
      </div>

      {tab === '' && <Overview r={r} go={(x) => setParams({ tab: x })} />}
      {tab === 'earn' && <Earn r={r} />}
      {tab === 'redeem' && <Redeem r={r} />}
      {tab === 'history' && <History />}
    </div>
  );
}

function Overview({ r, go }: { r: Rewards; go: (t: string) => void }) {
  const next = r.catalog.filter((c) => c.available).sort((a, b) => a.pointsCost - b.pointsCost)[0];
  const active = r.missions.filter((m) => !m.completed && !m.expired).slice(0, 3);
  return (
    <>
      {next && (
        <div className="mn-card mn-next">
          <div><span className="small mn-muted">{next.affordable ? 'You can redeem' : 'Next reward'}</span><strong>{next.title}</strong>
            <span className="small mn-muted">{pts(next.pointsCost)} points{!next.affordable ? ` · ${pts(next.pointsCost - r.balance)} to go` : ''}</span></div>
          <Button size="sm" variant={next.affordable ? 'primary' : 'secondary'} onClick={() => go('redeem')}>{next.affordable ? 'Redeem' : 'See rewards'}</Button>
        </div>
      )}
      {r.campaigns.length > 0 && (
        <Section title="Boosts" id="mn-boosts">
          <ul className="mn-list">{r.campaigns.map((c) => (
            <li key={c.id} className="mn-row mn-row--static"><span className="mn-row__icon mn-row__icon--promo"><Icon name={iconFor(c.service)} size={18} /></span>
              <span className="mn-row__text"><strong>{c.title}</strong><span className="small mn-muted">{c.description} · until {dateOf(c.endsAt)}</span></span>
              <strong>{Number(c.multiplier)}×</strong></li>
          ))}</ul>
        </Section>
      )}
      {active.length > 0 && <Section title="Missions" id="mn-missions" action={<button type="button" className="mn-link small" onClick={() => go('earn')}>All</button>}><Missions r={{ ...r, missions: active }} /></Section>}
      <Section title="Achievements" id="mn-ach">
        <div className="mn-badges">{r.achievements.map((a) => (
          <div key={a.code} className={`mn-badge ${a.unlocked ? 'is-on' : ''}`} title={a.description}>
            <span className="mn-badge__icon"><Icon name={a.unlocked ? 'star' : 'clock'} size={20} /></span>
            <strong>{a.title}</strong><span className="small mn-muted">{a.unlocked ? 'Unlocked' : `${a.progress}/${a.target}`}</span>
          </div>
        ))}</div>
      </Section>
      <Section title="Tiers" id="mn-tiers">
        <ul className="mn-tiers">{r.tiers.map((t) => (
          <li key={t.code} className={t.code === r.tier.code ? 'is-on' : ''}><strong>{t.name}</strong><span className="small mn-muted">{pts(t.minPoints)}+ points in 12 months · {t.multiplier}×</span>
            <ul className="mn-bullets small">{t.benefits.map((b) => <li key={b}>{b}</li>)}</ul></li>
        ))}</ul>
      </Section>
    </>
  );
}

function Missions({ r }: { r: Rewards }) {
  return (
    <ul className="mn-list">{r.missions.map((m) => (
      <li key={m.code}><Link to={m.link} className="mn-row">
        <span className={`mn-row__icon ${m.completed ? 'mn-row__icon--ok' : ''}`}><Icon name={m.completed ? 'check' : 'compass'} size={18} /></span>
        <span className="mn-row__text"><strong>{m.title} <span className="mn-muted small">+{pts(m.points)} pts</span></strong>
          <span className="small mn-muted">{m.description}{m.endsAt && !m.completed ? ` · ends ${dateOf(m.endsAt)}` : ''}</span>
          {!m.completed && <span className="mn-progress mn-progress--thin"><span style={{ width: `${Math.round((m.progress / m.target) * 100)}%` }} /></span>}</span>
        <span className="small">{m.completed ? 'Done' : m.expired ? 'Ended' : `${m.progress}/${m.target}`}</span>
      </Link></li>
    ))}</ul>
  );
}

function Earn({ r }: { r: Rewards }) {
  return (
    <>
      <Section title="How you earn" id="mn-how">
        <div className="mn-card">
          <p><strong>{r.rules.pointsPer100} points for every ₹100</strong> on {r.rules.earnOn.join(', ').toLowerCase()}, multiplied by your tier.</p>
          <p className="small mn-muted">Points are added once an order is delivered or a booking is completed, and expire {r.rules.expiryDays} days after they’re earned. Points on refunded purchases are reversed.</p>
        </div>
      </Section>
      <Section title="Missions" id="mn-all-m"><Missions r={r} /></Section>
    </>
  );
}

function Redeem({ r }: { r: Rewards }) {
  const [item, setItem] = useState<RewardItem | null>(null);
  return (
    <>
      <p className="small mn-muted">{r.rules.conversionNote}</p>
      {r.catalog.length === 0 ? <EmptyState icon="gift" title="Nothing to redeem right now" message="New rewards appear here." /> : (
        <ul className="mn-catalog">{r.catalog.map((c) => (
          <li key={c.id} className={`mn-reward ${c.available ? '' : 'is-off'}`}>
            <span className="mn-reward__icon"><Icon name="wallet" size={22} /></span>
            <strong>{c.title}</strong>
            <span className="small mn-muted">{pts(c.pointsCost)} points · valid {c.creditValidDays} days</span>
            {!c.available && <span className="small mn-warn">{c.reason}</span>}
            <Button size="sm" variant={c.available ? 'primary' : 'secondary'} disabled={!c.available} onClick={() => setItem(c)}>Redeem</Button>
          </li>
        ))}</ul>
      )}
      {item && <RedeemSheet item={item} balance={r.balance} onClose={() => setItem(null)} />}
    </>
  );
}

function RedeemSheet({ item, balance, onClose }: { item: RewardItem; balance: number; onClose: () => void }) {
  const qc = useQueryClient();
  const toast = useToast();
  const [key] = useState(newKey);
  const redeem = useMutation({
    mutationFn: () => api.money.rewards.redeem(item.id, key),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['customer', 'rewards'] }); qc.invalidateQueries({ queryKey: walletKey }); qc.invalidateQueries({ queryKey: ['rewards'] }); },
  });
  const done = redeem.data;
  return (
    <Sheet open onClose={onClose} label={`Redeem ${item.title}`}>
      <div className="mn-sheet mn-form">
        {done ? (
          <div className="mn-result"><span className="mn-result__icon mn-result__icon--ok"><Icon name="check" size={28} /></span>
            <h2>{money(done.value)} added to your wallet</h2><p className="mn-muted">{pts(done.points)} points used · {pts(done.balance)} points left.</p>
            {done.walletTransactionId && <Link to={`/wallet/activity/${done.walletTransactionId}`} className="mn-link" onClick={() => toast('Reward redeemed')}>View in Click. Wallet</Link>}
            <Button block onClick={onClose}>Done</Button></div>
        ) : (
          <>
            <h2>Redeem {item.title}?</h2>
            <dl className="mn-dl">
              <div><dt>Points used</dt><dd>{pts(item.pointsCost)}</dd></div>
              <div><dt>Points left</dt><dd>{pts(balance - item.pointsCost)}</dd></div>
              <div><dt>You get</dt><dd>{money(item.value)} Click. Wallet promo credit</dd></div>
              <div><dt>Valid for</dt><dd>{item.creditValidDays} days</dd></div>
            </dl>
            <p className="small mn-muted">{item.terms}</p>
            {redeem.isError && <p className="mn-error small" role="alert">{redeem.error instanceof ApiError ? redeem.error.message : 'Couldn’t redeem. No points were used.'}</p>}
            <div className="mn-row2"><Button variant="secondary" onClick={onClose}>Cancel</Button><Button loading={redeem.isPending} onClick={() => redeem.mutate()}>Redeem</Button></div>
          </>
        )}
      </div>
    </Sheet>
  );
}

function History() {
  const [kind, setKind] = useState('');
  const list = useInfiniteQuery({
    queryKey: ['rewards', 'history', kind], queryFn: ({ pageParam }) => api.money.rewards.history({ kind, page: pageParam }),
    initialPageParam: 1, getNextPageParam: (l) => (l.hasNext ? l.page + 1 : undefined),
  });
  const rows = useMemo(() => list.data?.pages.flatMap((p) => p.results) ?? [], [list.data]);
  return (
    <>
      <div className="mn-chips" role="group" aria-label="Filter history">{HISTORY.map(([v, l]) => <button key={v || 'all'} type="button" className="mn-chip" aria-pressed={kind === v} onClick={() => setKind(v!)}>{l}</button>)}</div>
      {list.isError ? <ErrorState error={list.error} onRetry={() => list.refetch()} /> : !list.data ? <Skeleton height={200} /> : rows.length === 0 ? <EmptyState icon="star" title="No points activity yet" message="Points from delivered orders and completed bookings appear here." /> : (
        <>
          {groupByDay(rows, (x) => x.createdAt).map((g) => (
            <div key={g.label} className="mn-group"><h3 className="mn-group__label">{g.label}</h3>
              <ul className="mn-list">{g.rows.map((h) => {
                const body = (<>
                  <span className={`mn-row__icon ${h.points > 0 ? 'mn-row__icon--ok' : ''}`}><Icon name={h.kind === 'earn' ? 'plus' : h.kind === 'redeem' ? 'gift' : h.kind === 'expire' ? 'clock' : 'settings'} size={18} /></span>
                  <span className="mn-row__text"><strong className="truncate">{h.description}</strong>
                    <span className="small mn-muted">{h.kindLabel} · {timeOf(h.createdAt)}{h.reversed ? ' · reversed' : ''}{h.expiresAt && h.points > 0 ? ` · expires ${dateOf(h.expiresAt)}` : ''}</span></span>
                  <strong className={h.points > 0 ? 'mn-ok' : ''}>{h.points > 0 ? '+' : '−'}{pts(Math.abs(h.points))}</strong></>);
                return <li key={h.id}>{h.source ? <Link to={h.source.link} className="mn-row">{body}</Link> : <div className="mn-row mn-row--static">{body}</div>}</li>;
              })}</ul>
            </div>
          ))}
          {list.hasNextPage && <Button variant="secondary" block loading={list.isFetchingNextPage} onClick={() => list.fetchNextPage()}>Load more</Button>}
        </>
      )}
    </>
  );
}
