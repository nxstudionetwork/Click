import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useNavigate } from 'react-router-dom';
import { Button, Icon, Skeleton, type IconName } from '@click/ui';
import { AppShell } from '../components/AppShell';
import { HOME_KEY, LIVE_POLL_MS, NOTIFICATIONS_KEY } from '../features/home/queries';
import { Empty } from '../features/home/sections';
import { api } from '../lib/api';
import { apiMessage } from '../lib/format';
import { timeAgo } from '../lib/money';

const ICON: Record<string, IconName> = { work: 'bell', update: 'history', account: 'shield', payment: 'wallet', system: 'alert' };

export function NotificationsPage() {
  const qc = useQueryClient();
  const navigate = useNavigate();
  const q = useQuery({ queryKey: NOTIFICATIONS_KEY, queryFn: api.partner.notifications, refetchInterval: LIVE_POLL_MS * 3 });
  const refresh = () => { void qc.invalidateQueries({ queryKey: NOTIFICATIONS_KEY }); void qc.invalidateQueries({ queryKey: HOME_KEY }); };
  const readOne = useMutation({ mutationFn: api.partner.readNotification, onSettled: refresh });
  const readAll = useMutation({ mutationFn: api.partner.readAllNotifications, onSettled: refresh });

  return (
    <AppShell>
      <div className="page">
        <div className="page__head spread">
          <h1>Notifications</h1>
          {!!q.data?.unread && <Button size="sm" variant="outline" loading={readAll.isPending} onClick={() => readAll.mutate()}>Mark all read</Button>}
        </div>
        {q.isPending ? <Skeleton height={220} radius={20} /> : q.isError ? (
          <div className="dash__error" role="alert"><h2>Couldn’t load notifications</h2><p className="muted">{apiMessage(q.error)}</p>
            <Button onClick={() => void q.refetch()}>Try again</Button></div>
        ) : q.data!.results.length === 0 ? (
          <Empty icon="bell" title="No notifications yet." message="New work, cancellations and account updates appear here." />
        ) : (
          <ul className="notes">
            {q.data!.results.map((n) => (
              <li key={n.id}>
                <button type="button" className={`note ${n.read ? '' : 'is-unread'}`}
                  onClick={() => { if (!n.read) readOne.mutate(n.id); if (n.linkPath) navigate(n.linkPath); }}>
                  <span className="note__icon" aria-hidden="true"><Icon name={ICON[n.category] ?? 'bell'} size={18} /></span>
                  <span className="note__text">
                    <span className="note__title">{n.title}{!n.read && <span className="visually-hidden"> (unread)</span>}</span>
                    {n.body && <span className="small muted">{n.body}</span>}
                  </span>
                  <time className="small muted" dateTime={n.createdAt}>{timeAgo(n.createdAt)}</time>
                </button>
              </li>
            ))}
          </ul>
        )}
      </div>
    </AppShell>
  );
}
