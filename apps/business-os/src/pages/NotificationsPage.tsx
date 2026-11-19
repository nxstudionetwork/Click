import { useState } from 'react';
import { Link } from 'react-router-dom';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Button } from '@click/ui';
import { api } from '../lib/api';
import { fmtDateTime, relative } from '../lib/format';
import { Card, Empty, LoadingRows, PageHeader, Pager, QueryError, Status } from '../components/ui';

export function NotificationsPage() {
  const qc = useQueryClient();
  const [unread, setUnread] = useState(false);
  const [type, setType] = useState('');
  const [page, setPage] = useState(1);
  const q = useQuery({ queryKey: ['os', 'notifications', unread, type, page], queryFn: () => api.notifications.list({ unread: unread ? 'true' : undefined, type: type || undefined, page }) });
  const refresh = () => { void qc.invalidateQueries({ queryKey: ['os', 'notifications'] }); };
  const readAll = useMutation({ mutationFn: api.notifications.readAll, onSuccess: refresh });
  const readOne = useMutation({ mutationFn: api.notifications.read, onSuccess: refresh });

  return (
    <>
      <PageHeader title="Notifications" description="Approvals, tasks, security and business alerts. Choose what reaches you in Settings → Preferences."
        actions={<Button variant="outline" loading={readAll.isPending} disabled={!q.data?.unread} onClick={() => readAll.mutate()}>Mark all as read</Button>} />
      <Card flush>
        <div className="toolbar">
          <label className="row small"><input type="checkbox" checked={unread} onChange={(e) => { setUnread(e.target.checked); setPage(1); }} />Unread only</label>
          <select className="field__input" aria-label="Type" value={type} onChange={(e) => { setType(e.target.value); setPage(1); }}>
            <option value="">All types</option>
            {q.data?.types.map((t) => <option key={t.value} value={t.value}>{t.label}</option>)}
          </select>
          <span className="small muted" style={{ marginLeft: 'auto' }}>{q.data ? `${q.data.unread} unread` : ''}</span>
        </div>
        {q.isPending ? <LoadingRows /> : q.error ? <QueryError error={q.error} onRetry={() => void q.refetch()} /> : !q.data.results.length ? (
          <Empty icon="bell" title={unread ? 'You’re all caught up' : 'No notifications yet'} />
        ) : (
          <>
            <ul className="list">
              {q.data.results.map((n) => (
                <li key={n.id} className={`list-row ${n.read ? '' : 'list-row--unread'}`}>
                  <span className={`dot ${n.read ? 'dot--off' : n.priority !== 'normal' ? `dot--${n.priority}` : ''}`} />
                  <div className="list-row__main">
                    {n.path ? <Link to={n.path} className="list-row__title" style={{ display: 'block', color: 'inherit' }} onClick={() => !n.read && readOne.mutate(n.id)}>{n.title}</Link>
                      : <span className="list-row__title" style={{ display: 'block' }}>{n.title}</span>}
                    {n.body && <span className="list-row__sub" style={{ display: 'block', whiteSpace: 'normal' }}>{n.body}</span>}
                    <span className="xs muted" title={fmtDateTime(n.createdAt)}>{n.typeLabel} · {relative(n.createdAt)}</span>
                  </div>
                  {n.priority !== 'normal' && <Status value={n.priority} tone={n.priority === 'critical' ? 'danger' : 'warning'} />}
                  {!n.read && <Button size="sm" variant="ghost" onClick={() => readOne.mutate(n.id)}>Mark read</Button>}
                </li>
              ))}
            </ul>
            <Pager page={q.data.page} hasNext={q.data.hasNext} count={q.data.count} onPage={setPage} />
          </>
        )}
      </Card>
    </>
  );
}
