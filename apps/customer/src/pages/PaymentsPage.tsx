import { useEffect, useMemo, useState } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import { useInfiniteQuery, useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { ApiError } from '@click/api';
import { Button, EmptyState, ErrorState, Icon, Skeleton, useToast } from '../components/ui';
import { MoneyHead, Pill, Section, dateOf, groupByDay, iconFor, money, timeOf, toneOfPayment } from '../features/money/parts';
import { api } from '../lib/api';

const TABS = [{ id: 'all', label: 'Payments' }, { id: 'refunds', label: 'Refunds' }, { id: 'methods', label: 'Methods' }] as const;
const STATUSES = [['', 'Any status'], ['successful', 'Successful'], ['pending', 'Pending'], ['pay_later', 'Pay later'], ['failed', 'Failed'], ['refunded', 'Refunded'], ['cancelled', 'Cancelled']];
const SERVICES = [['', 'All services'], ['food', 'Food'], ['groceries', 'Groceries'], ['shop', 'Shop'], ['ride', 'Ride'], ['parcel', 'Parcel'], ['services', 'Services'],
  ['shows', 'Shows'], ['events', 'Events'], ['hotels', 'Hotels'], ['travel', 'Travel'], ['bookings', 'Bookings'], ['wallet', 'Wallet top-ups']];
const PERIODS = [['', 'Any time'], ['today', 'Today'], ['7d', 'Last 7 days'], ['30d', 'Last 30 days']];

/** Payments: how each Click. order or booking was paid, from the payment records themselves. Wallet balance lives in
 *  Click. Wallet; this page is about payments. */
export function PaymentsPage() {
  const [params, setParams] = useSearchParams();
  const tab = (TABS.find((t) => t.id === params.get('tab'))?.id ?? 'all') as (typeof TABS)[number]['id'];
  const ov = useQuery({ queryKey: ['payments', 'overview'], queryFn: api.money.payments.overview });
  return (
    <div className="mn-page">
      <MoneyHead title="Payments" />
      {ov.data && (ov.data.counts.failed > 0 || ov.data.counts.pending > 0) && (
        <div className="mn-stats mn-stats--3">
          <button type="button" onClick={() => setParams({ status: 'failed' })}><span className="small mn-muted">Failed</span><strong className={ov.data.counts.failed ? 'mn-bad' : ''}>{ov.data.counts.failed}</strong></button>
          <button type="button" onClick={() => setParams({ status: 'pending' })}><span className="small mn-muted">Pending</span><strong>{ov.data.counts.pending}</strong></button>
          <button type="button" onClick={() => setParams({ tab: 'refunds' })}><span className="small mn-muted">Refunds</span><strong>{ov.data.counts.refunds}</strong></button>
        </div>
      )}
      <div className="mn-tabs" role="tablist">
        {TABS.map((t) => <button key={t.id} type="button" role="tab" aria-selected={tab === t.id} className="mn-tab" onClick={() => setParams(t.id === 'all' ? {} : { tab: t.id })}>{t.label}</button>)}
      </div>
      {tab === 'all' ? <PaymentList /> : tab === 'refunds' ? <Refunds /> : <Methods />}
    </div>
  );
}

function PaymentList() {
  const [params, setParams] = useSearchParams();
  const [q, setQ] = useState(params.get('q') ?? '');
  const service = params.get('service') ?? '', status = params.get('status') ?? '', period = params.get('period') ?? '';
  const set = (k: string, v: string) => { const n = new URLSearchParams(params); if (v) n.set(k, v); else n.delete(k); setParams(n, { replace: true }); };
  useEffect(() => { const t = setTimeout(() => { if ((params.get('q') ?? '') !== q.trim()) set('q', q.trim()); }, 350); return () => clearTimeout(t); }); // eslint-disable-line react-hooks/exhaustive-deps
  const list = useInfiniteQuery({
    queryKey: ['payments', 'list', service, status, period, params.get('q') ?? ''],
    queryFn: ({ pageParam }) => api.money.payments.list({ service: service || undefined, status: status || undefined, period: period || undefined, q: params.get('q') || undefined, page: pageParam }),
    initialPageParam: 1, getNextPageParam: (l) => (l.hasNext ? l.page + 1 : undefined),
  });
  const rows = useMemo(() => list.data?.pages.flatMap((p) => p.results) ?? [], [list.data]);
  const filtered = !!(service || status || period || params.get('q'));
  return (
    <>
      <div className="mn-search"><Icon name="search" size={18} />
        <input type="search" value={q} onChange={(e) => setQ(e.target.value)} placeholder="Order number, PNR, payment reference or amount" aria-label="Search payments" /></div>
      <div className="mn-selects">
        <select value={service} onChange={(e) => set('service', e.target.value)} aria-label="Service">{SERVICES.map(([v, l]) => <option key={v} value={v}>{l}</option>)}</select>
        <select value={status} onChange={(e) => set('status', e.target.value)} aria-label="Status">{STATUSES.map(([v, l]) => <option key={v} value={v}>{l}</option>)}</select>
        <select value={period} onChange={(e) => set('period', e.target.value)} aria-label="Period">{PERIODS.map(([v, l]) => <option key={v} value={v}>{l}</option>)}</select>
      </div>
      {list.isError ? <ErrorState error={list.error} onRetry={() => list.refetch()} /> : !list.data ? <Skeleton height={240} /> : rows.length === 0 ? (
        <EmptyState icon="card" title={filtered ? 'No payments match' : 'No payments yet'} message={filtered ? 'Try clearing a filter.' : 'Payments for your orders, rides and bookings appear here.'}
          action={filtered ? <button type="button" className="btn btn--outline" onClick={() => setParams({}, { replace: true })}>Clear filters</button> : undefined} />
      ) : (
        <>
          {groupByDay(rows, (r) => r.createdAt).map((g) => (
            <div key={g.label} className="mn-group"><h3 className="mn-group__label">{g.label}</h3>
              <ul className="mn-list">{g.rows.map((p) => (
                <li key={p.id}><Link to={`/account/payments/${p.id}`} className="mn-row">
                  <span className="mn-row__icon"><Icon name={iconFor(p.service)} size={18} /></span>
                  <span className="mn-row__text"><strong className="truncate">{p.label}</strong>
                    <span className="small mn-muted truncate">{p.orderReference} · {p.methodLabel} · {timeOf(p.createdAt)}</span></span>
                  <span className="mn-row__end"><strong>{money(p.amount)}</strong><Pill tone={toneOfPayment(p.status)}>{p.statusLabel}</Pill></span>
                </Link></li>
              ))}</ul>
            </div>
          ))}
          {list.hasNextPage && <Button variant="secondary" block loading={list.isFetchingNextPage} onClick={() => list.fetchNextPage()}>Load more</Button>}
        </>
      )}
    </>
  );
}

function Refunds() {
  const list = useInfiniteQuery({
    queryKey: ['payments', 'refunds'], queryFn: ({ pageParam }) => api.money.payments.refunds(pageParam),
    initialPageParam: 1, getNextPageParam: (l) => (l.hasNext ? l.page + 1 : undefined),
  });
  const rows = list.data?.pages.flatMap((p) => p.results) ?? [];
  if (list.isError) return <ErrorState error={list.error} onRetry={() => list.refetch()} />;
  if (!list.data) return <Skeleton height={200} />;
  if (!rows.length) return <EmptyState icon="history" title="No refunds" message="Refunds for cancelled or returned items appear here, with where the money went." />;
  return (
    <>
      <ul className="mn-list">{rows.map((r) => (
        <li key={r.id}><Link to={r.payment ? `/account/payments/${r.payment.id}` : '/wallet'} className="mn-row">
          <span className="mn-row__icon mn-row__icon--ok"><Icon name="history" size={18} /></span>
          <span className="mn-row__text"><strong className="truncate">{r.payment ? `${r.payment.label} · ${r.payment.orderReference}` : 'Refund'}</strong>
            <span className="small mn-muted truncate">To {r.to} · {dateOf(r.creditedAt)}{r.refundReference ? ` · ${r.refundReference}` : ''}</span></span>
          <span className="mn-row__end"><strong className="mn-ok">+{money(r.amount)}</strong><Pill tone="ok">{r.statusLabel}</Pill></span>
        </Link></li>
      ))}</ul>
      {list.hasNextPage && <Button variant="secondary" block loading={list.isFetchingNextPage} onClick={() => list.fetchNextPage()}>Load more</Button>}
    </>
  );
}

function Methods() {
  const qc = useQueryClient();
  const toast = useToast();
  const ov = useQuery({ queryKey: ['payments', 'overview'], queryFn: api.money.payments.overview });
  const setDefault = useMutation({
    mutationFn: api.money.payments.setDefault,
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['payments', 'overview'] }); toast('Default payment method saved'); },
    onError: (e) => toast(e instanceof ApiError ? e.message : 'Couldn’t save.', 'error'),
  });
  if (ov.isError) return <ErrorState error={ov.error} onRetry={() => ov.refetch()} />;
  if (!ov.data) return <Skeleton height={240} />;
  return (
    <>
      <Section title="Ways to pay on Click." id="mn-methods">
        <ul className="mn-list">{ov.data.methods.map((m) => (
          <li key={m.code} className="mn-row mn-row--static">
            <span className="mn-row__icon"><Icon name={m.code === 'wallet' ? 'wallet' : m.code === 'pay_at_venue' ? 'ticket' : 'receipt'} size={18} /></span>
            <span className="mn-row__text"><strong>{m.label}{m.default && <Pill tone="ok">Default</Pill>}</strong>
              <span className="small mn-muted">{m.description}</span>{m.where && <span className="small mn-muted">Where: {m.where}</span>}{m.detail && <span className="small">{m.detail}</span>}</span>
            {m.canDefault && !m.default && <Button size="sm" variant="secondary" loading={setDefault.isPending && setDefault.variables === m.code} onClick={() => setDefault.mutate(m.code)}>Make default</Button>}
          </li>
        ))}</ul>
      </Section>
      <div className="mn-banner"><Icon name="shield" size={20} /><div><strong>Cards and UPI at checkout</strong><p className="small">{ov.data.onlineMethods.note}</p></div></div>
      <Link to="/wallet" className="mn-row mn-row--card"><span className="mn-row__icon"><Icon name="wallet" size={18} /></span>
        <span className="mn-row__text"><strong>Click. Wallet</strong><span className="small mn-muted">Balance, adding money, promo credit</span></span><Icon name="right" size={16} /></Link>
    </>
  );
}
