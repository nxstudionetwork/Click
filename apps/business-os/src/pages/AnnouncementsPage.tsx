import { useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Button, Icon, useToast } from '@click/ui';
import { apiMessage, home, people } from '../lib/api';
import { fmtDate, fromLocalInput } from '../lib/format';
import { useAccess } from '../session/access';
import { FormDialog } from '../components/forms';
import { Card, LoadingRows, PageHeader, QueryError, Status, Tabs } from '../components/ui';

export function AnnouncementsPage() {
  const access = useAccess();
  const qc = useQueryClient();
  const toast = useToast();
  const [params, setParams] = useSearchParams();
  const [tab, setTab] = useState<'feed' | 'manage'>('feed');
  const manage = tab === 'manage';
  const q = useQuery({ queryKey: ['os', 'announcements', manage], queryFn: () => home.announcements(manage) });
  const lookups = useQuery({ queryKey: ['os', 'people', 'lookups'], queryFn: people.lookups, enabled: params.get('new') === '1' });
  const act = useMutation({
    mutationFn: ({ id, a }: { id: string; a: 'acknowledge' | 'dismiss' }) => home.announcementAction(id, a),
    onSuccess: () => void qc.invalidateQueries({ queryKey: ['os', 'announcements'] }), onError: (e) => toast(apiMessage(e), 'error'),
  });
  const end = useMutation({ mutationFn: (id: string) => home.updateAnnouncement(id, { isPublished: false }), onSuccess: () => void qc.invalidateQueries({ queryKey: ['os', 'announcements'] }) });
  const canCreate = access.can('communications.announcement.create');
  return (
    <>
      <PageHeader title="Announcements" description="Company notices, policy updates, maintenance and security announcements."
        actions={canCreate && <Button onClick={() => setParams({ new: '1' })}><Icon name="plus" size={16} />New announcement</Button>} />
      {access.can('communications.announcement.view') && <Tabs value={tab} onChange={setTab} items={[{ value: 'feed', label: 'For me' }, { value: 'manage', label: 'Manage' }]} />}
      <Card flush>
        {q.isPending ? <LoadingRows /> : q.error ? <QueryError error={q.error} /> : !q.data.results.length ? <p className="muted small" style={{ padding: 16 }}>No announcements.</p> : (
          <ul className="list">
            {q.data.results.map((a) => (
              <li key={a.id} className="list-row" style={{ alignItems: 'flex-start' }}>
                <span className={`sev sev--${a.priority === 'critical' ? 'critical' : a.priority === 'important' ? 'high' : 'low'}`} />
                <div className="list-row__main">
                  <div className="row row--wrap"><strong>{a.title}</strong><Status value={a.priority} tone={a.priority === 'critical' ? 'danger' : a.priority === 'important' ? 'warning' : 'neutral'} />
                    <span className="xs muted">{a.categoryLabel}</span></div>
                  <p className="small" style={{ whiteSpace: 'pre-wrap', margin: '4px 0' }}>{a.body}</p>
                  <span className="xs muted">{fmtDate(a.startsAt)}{a.endsAt ? ` – ${fmtDate(a.endsAt)}` : ''}{a.author ? ` · ${a.author}` : ''}
                    {manage && ` · ${a.acks ?? 0} acknowledged · ${a.isPublished ? 'published' : 'ended'}`}</span>
                </div>
                {!manage && <div className="stack" style={{ gap: 4 }}>
                  {a.requiresAck && !a.acknowledged && <Button size="sm" onClick={() => act.mutate({ id: a.id, a: 'acknowledge' })}>Acknowledge</Button>}
                  {a.acknowledged && <Status value="active" label="Acknowledged" />}
                  {a.canDismiss && !a.dismissed && <Button size="sm" variant="ghost" onClick={() => act.mutate({ id: a.id, a: 'dismiss' })}>Hide from Home</Button>}
                </div>}
                {manage && a.isPublished && access.can('communications.announcement.edit') && <Button size="sm" variant="outline" onClick={() => end.mutate(a.id)}>End now</Button>}
              </li>
            ))}
          </ul>
        )}
      </Card>
      {params.get('new') === '1' && canCreate && (
        <FormDialog title="New announcement" wide onClose={() => setParams({})} submitLabel="Publish"
          intro={<p className="small muted">Critical announcements can’t be dismissed and need approval authority. Leave the audience empty to reach everyone.</p>}
          fields={[
            { name: 'title', label: 'Title', required: true },
            { name: 'body', label: 'Message', type: 'textarea', required: true },
            { name: 'category', label: 'Category', type: 'select', required: true, half: true, options: (q.data?.categories ?? [
              { key: 'company', label: 'Company' }, { key: 'policy', label: 'Policy update' }, { key: 'maintenance', label: 'System maintenance' },
              { key: 'operational', label: 'Operational notice' }, { key: 'security', label: 'Security' }, { key: 'feature', label: 'New in Business OS' }])
              .map((c) => ({ value: c.key, label: c.label })) },
            { name: 'priority', label: 'Priority', type: 'select', required: true, half: true, options: [{ value: 'normal', label: 'Normal' },
              { value: 'important', label: 'Important' }, ...(access.can('communications.announcement.approve') ? [{ value: 'critical', label: 'Critical (can’t be dismissed)' }] : [])] },
            { name: 'starts_at', label: 'Starts', type: 'datetime-local', half: true },
            { name: 'ends_at', label: 'Ends', type: 'datetime-local', half: true },
            { name: 'departments', label: 'Only these departments', type: 'multiselect', options: (lookups.data?.departments ?? []).map((d) => ({ value: d.id, label: d.name })) },
            { name: 'requires_ack', label: 'People must acknowledge it', type: 'checkbox' },
          ]}
          initial={{ category: 'company', priority: 'normal' }}
          onSubmit={(v) => home.createAnnouncement({
            title: String(v.title), body: String(v.body), category: String(v.category), priority: String(v.priority), requiresAck: Boolean(v.requiresAck),
            startsAt: v.startsAt ? fromLocalInput(String(v.startsAt)) ?? undefined : undefined, endsAt: v.endsAt ? fromLocalInput(String(v.endsAt)) : null,
            audience: (v.departments as string[] | null)?.length ? { departments: v.departments as string[] } : {},
          })}
          onDone={() => { toast('Announcement published'); void qc.invalidateQueries({ queryKey: ['os', 'announcements'] }); }} />
      )}
    </>
  );
}
