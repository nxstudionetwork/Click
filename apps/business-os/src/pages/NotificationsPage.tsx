import { useState } from 'react';
import { Link } from 'react-router-dom';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Button, Icon, useToast } from '@click/ui';
import { api, apiMessage, home } from '../lib/api';
import { fmtDateTime, relative } from '../lib/format';
import { Card, Empty, LoadingRows, PageHeader, Pager, QueryError, Status, Tabs } from '../components/ui';

export function NotificationsPage() {
  const qc = useQueryClient();
  const toast = useToast();
  const [unread, setUnread] = useState(false);
  const [type, setType] = useState('');
  const [cat, setCat] = useState('');
  const [page, setPage] = useState(1);
  const q = useQuery({ queryKey: ['os', 'notifications', unread, type, cat, page], queryFn: () => api.notifications.list({ unread: unread ? 'true' : undefined, type: type || undefined, category: cat || undefined, page }) });
  const act = useMutation({ mutationFn: ({ id, a }: { id: string; a: 'unread' | 'archive' }) => home.notificationAction(id, a), onSuccess: refreshAll,
    onError: (e) => toast(apiMessage(e), 'error') });
  const clear = useMutation({ mutationFn: home.clearRead, onSuccess: (r) => { toast(`${r.cleared} cleared`); refreshAll(); } });
  const refresh = () => { void qc.invalidateQueries({ queryKey: ['os', 'notifications'] }); };
  function refreshAll() { refresh(); }
  const readAll = useMutation({ mutationFn: api.notifications.readAll, onSuccess: refresh });
  const readOne = useMutation({ mutationFn: api.notifications.read, onSuccess: refresh });

  return (
    <>
      <PageHeader title="Notifications" description="Approvals, tasks, security and business alerts. Choose what reaches you in Settings → Preferences."
        actions={<>
          <Link to="/settings/preferences" className="btn btn--ghost" style={{ textDecoration: 'none' }}>Preferences</Link>
          <Button variant="outline" loading={clear.isPending} onClick={() => clear.mutate()}>Clear read</Button>
          <Button variant="outline" loading={readAll.isPending} disabled={!q.data?.unread} onClick={() => readAll.mutate()}>Mark all as read</Button>
        </>} />
      <Tabs value={cat} onChange={(v) => { setCat(v); setPage(1); }} items={[{ value: '', label: 'All' }, { value: 'approvals', label: 'Approvals' },
        { value: 'tasks', label: 'Tasks' }, { value: 'security', label: 'Security' }, { value: 'business', label: 'Business' }, { value: 'system', label: 'System' }]
        .map((t) => ({ ...t, count: t.value ? (q.data as never as { categoryCounts?: Record<string, number> })?.categoryCounts?.[t.value] || undefined : q.data?.unread || undefined }))} />
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
                  {!n.read ? <Button size="sm" variant="ghost" onClick={() => readOne.mutate(n.id)}>Mark read</Button>
                    : <Button size="sm" variant="ghost" onClick={() => act.mutate({ id: n.id, a: 'unread' })}>Mark unread</Button>}
                  <button className="icon-btn" aria-label={`Clear ${n.title}`} title="Clear" onClick={() => act.mutate({ id: n.id, a: 'archive' })}><Icon name="close" size={15} /></button>
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
