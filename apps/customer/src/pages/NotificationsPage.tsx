import { Link, useNavigate } from 'react-router-dom';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import type { Notification, NotificationCategory } from '@click/api';
import { useState } from 'react';
import { Button, EmptyState, ErrorState, Icon, Skeleton, type IconName } from '../components/ui';
import { notificationKeys } from '../features/notifications/hooks';
import { api } from '../lib/api';
import { formatDateTime } from '../lib/format';

const ICON: Record<NotificationCategory, IconName> = {
  orders: 'receipt', rides: 'ride', deliveries: 'parcel', payments: 'card', offers: 'tag', rewards: 'gift', support: 'help', system: 'bell',
};
const FILTERS: { id: '' | NotificationCategory; label: string }[] = [
  { id: '', label: 'All' }, { id: 'orders', label: 'Orders' }, { id: 'rewards', label: 'Rewards' }, { id: 'support', label: 'Support' }, { id: 'offers', label: 'Offers' },
];

export function NotificationsPage() {
  const [category, setCategory] = useState<'' | NotificationCategory>('');
  const qc = useQueryClient();
  const navigate = useNavigate();
  const list = useQuery({
    queryKey: [...notificationKeys.all, 'list', category],
    queryFn: () => api.customer.notifications.list({ category: category || undefined }),
  });
  const refresh = () => qc.invalidateQueries({ queryKey: notificationKeys.all });
  const markRead = useMutation({ mutationFn: api.customer.notifications.markRead, onSuccess: refresh });
  const markAll = useMutation({ mutationFn: api.customer.notifications.markAllRead, onSuccess: refresh });

  const open = (n: Notification) => {
    if (!n.isRead) markRead.mutate(n.id);
    if (n.linkPath) navigate(n.linkPath);
  };

  return (
    <div className="stack">
      <div className="page-head">
        <h1>Notifications</h1>
        <Button variant="ghost" size="sm" onClick={() => markAll.mutate()} loading={markAll.isPending} disabled={!list.data?.results.some((n) => !n.isRead)}>Mark all as read</Button>
      </div>
      <div className="chips">{FILTERS.map((f) => <button key={f.id || 'all'} className="chip" aria-pressed={category === f.id} onClick={() => setCategory(f.id)}>{f.label}</button>)}</div>
      {list.isError ? <ErrorState error={list.error} onRetry={() => list.refetch()} />
        : list.isPending ? <Skeleton height={180} radius={16} />
        : list.data.results.length === 0 ? <EmptyState icon="bell" title="You’re all caught up" message="Updates about your orders, rewards and support requests appear here." action={<Link to="/explore" className="btn btn--outline">Explore</Link>} />
        : (
          <div className="card list">
            {list.data.results.map((n) => (
              <button key={n.id} className={`list-row ${n.isRead ? '' : 'list-row--unread'}`} onClick={() => open(n)}>
                <span className="list-row__icon"><Icon name={ICON[n.category]} size={18} /></span>
                <span style={{ flex: 1, minWidth: 0 }}>
                  <span className="list-row__title" style={{ fontWeight: n.isRead ? 500 : 700 }}>{n.title}</span>
                  {n.body && <span className="small muted" style={{ display: 'block' }}>{n.body}</span>}
                  <span className="small muted" style={{ display: 'block' }}>{formatDateTime(n.createdAt)}</span>
                </span>
                {n.linkPath && <Icon name="right" size={18} />}
              </button>
            ))}
          </div>
        )}
    </div>
  );
}
