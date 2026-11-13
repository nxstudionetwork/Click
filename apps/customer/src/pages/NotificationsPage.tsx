import { useMemo, useState } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { useInfiniteQuery, useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { ApiError, type InboxNotification, type NotificationGroup } from '@click/api';
import { Button, EmptyState, ErrorState, Icon, Sheet, Skeleton, useToast } from '../components/ui';
import { notificationKeys } from '../features/notifications/hooks';
import { MoneyHead, groupByDay, iconFor, timeOf } from '../features/money/parts';
import { api } from '../lib/api';

const GROUPS: { id: '' | NotificationGroup; label: string }[] = [
  { id: '', label: 'All' }, { id: 'orders', label: 'Orders' }, { id: 'rides', label: 'Rides' }, { id: 'bookings', label: 'Bookings' },
  { id: 'payments', label: 'Payments' }, { id: 'wallet', label: 'Wallet' }, { id: 'offers', label: 'Offers' }, { id: 'rewards', label: 'Rewards' }, { id: 'account', label: 'Account' },
];

/** Notifications: things Click. told you (separate from Activity, which is what you did). Opening one marks it read
 *  and goes to the record it’s about. */
export function NotificationsPage() {
  const qc = useQueryClient();
  const toast = useToast();
  const nav = useNavigate();
  const [params, setParams] = useSearchParams();
  const group = (params.get('group') ?? '') as '' | NotificationGroup;
  const [unreadOnly, setUnreadOnly] = useState(false);
  const [prefs, setPrefs] = useState(false);
  const summary = useQuery({ queryKey: notificationKeys.summary, queryFn: api.money.notifications.summary });
  const list = useInfiniteQuery({
    queryKey: [...notificationKeys.all, 'list', group, unreadOnly],
    queryFn: ({ pageParam }) => api.money.notifications.list({ group, unread: unreadOnly, page: pageParam }),
    initialPageParam: 1, getNextPageParam: (l) => (l.hasNext ? l.page + 1 : undefined),
  });
  const rows = useMemo(() => list.data?.pages.flatMap((p) => p.results) ?? [], [list.data]);
  const refresh = () => qc.invalidateQueries({ queryKey: notificationKeys.all });
  const read = useMutation({ mutationFn: api.money.notifications.read, onSuccess: refresh });
  const unread = useMutation({ mutationFn: api.money.notifications.unread, onSuccess: refresh });
  const readAll = useMutation({
    mutationFn: () => api.money.notifications.readAll(group || undefined),
    onSuccess: (r) => { refresh(); toast(r.updated ? `Marked ${r.updated} as read` : 'Nothing unread'); },
    onError: (e) => toast(e instanceof ApiError ? e.message : 'Couldn’t update.', 'error'),
  });
  const open = (n: InboxNotification) => {
    if (!n.isRead) read.mutate(n.id);
    if (n.linkPath) nav(n.linkPath);
  };
  const s = summary.data;
  const groupUnread = group ? s?.byGroup[group] ?? 0 : s?.unread ?? 0;

  return (
    <div className="mn-page">
      <MoneyHead title="Notifications" sub={s ? (s.unread ? `${s.unread > 99 ? '99+' : s.unread} unread` : 'All caught up') : undefined}
        action={<button type="button" className="mn-head__home" onClick={() => setPrefs(true)} aria-label="Notification settings"><Icon name="settings" size={20} /></button>} />
      <div className="mn-chips" role="tablist" aria-label="Notification types">
        {GROUPS.map((g) => {
          const n = g.id ? s?.byGroup[g.id] ?? 0 : s?.unread ?? 0;
          return (
            <button key={g.id || 'all'} type="button" role="tab" className="mn-chip" aria-selected={group === g.id} aria-pressed={group === g.id}
              onClick={() => setParams(g.id ? { group: g.id } : {}, { replace: true })}>
              {g.id && <Icon name={iconFor(g.id)} size={15} />}{g.label}{n > 0 && <span className="mn-chip__count">{n > 99 ? '99+' : n}</span>}
            </button>
          );
        })}
      </div>
      <div className="mn-toolbar">
        <label className="mn-toggle"><input type="checkbox" checked={unreadOnly} onChange={(e) => setUnreadOnly(e.target.checked)} /> Unread only</label>
        <button type="button" className="mn-link small" disabled={!groupUnread || readAll.isPending} onClick={() => readAll.mutate()}>Mark all as read</button>
      </div>

      {list.isError ? <ErrorState error={list.error} onRetry={() => list.refetch()} /> : !list.data ? <Skeleton height={260} /> : rows.length === 0 ? (
        <EmptyState icon="bell" title={unreadOnly ? 'No unread notifications' : 'No notifications yet'} message="Updates about your orders, rides, bookings, payments and offers appear here." />
      ) : (
        <>
          {groupByDay(rows, (n) => n.createdAt).map((g) => (
            <div key={g.label} className="mn-group"><h3 className="mn-group__label">{g.label}</h3>
              <ul className="mn-list">{g.rows.map((n) => (
                <li key={n.id} className={`mn-note ${n.isRead ? '' : 'is-unread'} ${n.priority === 'urgent' || n.priority === 'important' ? 'is-important' : ''}`}>
                  <button type="button" className="mn-row" onClick={() => open(n)}>
                    <span className="mn-row__icon"><Icon name={iconFor(n.category)} size={18} /></span>
                    <span className="mn-row__text"><strong>{n.title}</strong>{n.body && <span className="small mn-muted">{n.body}</span>}
                      <span className="small mn-muted">{timeOf(n.createdAt)}</span></span>
                    {!n.isRead && <span className="mn-unread-dot" aria-label="Unread" />}
                  </button>
                  {n.isRead && <button type="button" className="mn-note__mark small" onClick={() => unread.mutate(n.id)} aria-label={`Mark “${n.title}” as unread`}>Mark unread</button>}
                </li>
              ))}</ul>
            </div>
          ))}
          {list.hasNextPage && <Button variant="secondary" block loading={list.isFetchingNextPage} onClick={() => list.fetchNextPage()}>Load more</Button>}
        </>
      )}
      {prefs && <Preferences onClose={() => setPrefs(false)} />}
    </div>
  );
}

function Preferences({ onClose }: { onClose: () => void }) {
  const qc = useQueryClient();
  const toast = useToast();
  const p = useQuery({ queryKey: ['notifications', 'prefs'], queryFn: api.money.notifications.prefs });
  const save = useMutation({
    mutationFn: api.money.notifications.setPrefs,
    onSuccess: (d) => { qc.setQueryData(['notifications', 'prefs'], d); toast('Saved'); },
    onError: (e) => toast(e instanceof ApiError ? e.message : 'Couldn’t save.', 'error'),
  });
  return (
    <Sheet open onClose={onClose} label="Notification settings">
      <div className="mn-sheet mn-form">
        <h2>Notification settings</h2>
        {!p.data ? <Skeleton height={200} /> : (
          <>
            <ul className="mn-list">{p.data.categories.map((c) => {
              const on = !p.data.muted.includes(c.code);
              return (
                <li key={c.code} className="mn-row mn-row--static">
                  <span className="mn-row__icon"><Icon name={iconFor(c.code)} size={18} /></span>
                  <span className="mn-row__text"><strong>{c.label}</strong>{!c.mutable && <span className="small mn-muted">Always on</span>}</span>
                  <input type="checkbox" role="switch" aria-label={c.label} checked={on} disabled={!c.mutable || save.isPending}
                    onChange={() => save.mutate(on ? [...p.data.muted, c.code] : p.data.muted.filter((m) => m !== c.code))} />
                </li>
              );
            })}</ul>
            <p className="small mn-muted">{p.data.note}</p>
          </>
        )}
      </div>
    </Sheet>
  );
}
