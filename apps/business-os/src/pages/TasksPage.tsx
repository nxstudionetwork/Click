import { useEffect, useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Button, Icon, TextArea, TextField, useToast } from '@click/ui';
import type { OSTask, OSTaskPriority, OSTaskStatus } from '@click/api';
import { api, apiMessage, fieldErrors } from '../lib/api';
import { fmtDateTime, fromLocalInput } from '../lib/format';
import { useAccess } from '../session/access';
import { useOS } from '../session/OSSession';
import { PersonPicker } from '../components/PersonPicker';
import { Alert, Card, Dialog, Drawer, Empty, LoadingRows, PageHeader, Pager, QueryError, Status, Tabs } from '../components/ui';

type View = 'assigned' | 'overdue' | 'upcoming' | 'created' | 'done';

export function TasksPage() {
  const [params, setParams] = useSearchParams();
  const [view, setView] = useState<View>('assigned');
  const [page, setPage] = useState(1);
  const [creating, setCreating] = useState(params.get('new') === '1');
  const openId = params.get('open');
  const q = useQuery({ queryKey: ['os', 'tasks', view, page], queryFn: () => api.tasks.list(view, page) });
  useEffect(() => setPage(1), [view]);

  return (
    <>
      <PageHeader title="Tasks" description="Work assigned to you and by you."
        actions={<Button onClick={() => setCreating(true)}><Icon name="plus" size={16} />New task</Button>} />
      <Tabs value={view} onChange={setView} items={[
        { value: 'assigned', label: 'Assigned to me' }, { value: 'overdue', label: 'Overdue' }, { value: 'upcoming', label: 'Due this week' },
        { value: 'created', label: 'Assigned by me' }, { value: 'done', label: 'Completed' },
      ]} />
      <Card flush>
        {q.isPending ? <LoadingRows /> : q.error ? <QueryError error={q.error} onRetry={() => void q.refetch()} /> : !q.data.results.length ? (
          <Empty icon="list" title={view === 'overdue' ? 'Nothing overdue' : 'No tasks here'} />
        ) : (
          <>
            <ul className="list">
              {q.data.results.map((t) => <TaskRow key={t.id} task={t} onOpen={() => setParams({ open: t.id })} />)}
            </ul>
            <Pager page={q.data.page} hasNext={q.data.hasNext} count={q.data.count} onPage={setPage} />
          </>
        )}
      </Card>
      {creating && <NewTaskDialog onClose={() => { setCreating(false); params.delete('new'); setParams(params, { replace: true }); }} />}
      {openId && <TaskDrawer id={openId} rows={q.data?.results ?? []} onClose={() => { params.delete('open'); setParams(params, { replace: true }); }} />}
    </>
  );
}

function TaskRow({ task: t, onOpen }: { task: OSTask; onOpen: () => void }) {
  const qc = useQueryClient();
  const toggle = useMutation({
    mutationFn: () => api.tasks.update(t.id, { status: t.status === 'done' ? 'open' : 'done' }),
    onSuccess: () => { void qc.invalidateQueries({ queryKey: ['os', 'tasks'] }); void qc.invalidateQueries({ queryKey: ['os', 'home'] }); },
  });
  return (
    <li className="list-row">
      <input type="checkbox" aria-label={`Mark ${t.title} ${t.status === 'done' ? 'not done' : 'done'}`} checked={t.status === 'done'}
             disabled={!t.canEdit || toggle.isPending} onChange={() => toggle.mutate()} />
      <button className="list-row__main" style={{ border: 0, background: 'none', textAlign: 'left', cursor: 'pointer', padding: 0 }} onClick={onOpen}>
        <span className="list-row__title" style={{ display: 'block', textDecoration: t.status === 'done' ? 'line-through' : undefined }}>{t.title}</span>
        <span className="list-row__sub" style={{ display: 'block', color: t.overdue ? 'var(--c-danger)' : undefined }}>
          {t.dueAt ? `${t.overdue ? 'Overdue · ' : 'Due '}${fmtDateTime(t.dueAt)}` : 'No due date'} · {t.assignee.fullName}{t.createdBy.id !== t.assignee.id ? ` (from ${t.createdBy.fullName})` : ''}
        </span>
      </button>
      {t.priority !== 'normal' && <Status value={t.priority} />}
      {t.status === 'in_progress' && <Status value="in_progress" />}
    </li>
  );
}

function NewTaskDialog({ onClose }: { onClose: () => void }) {
  const ctx = useOS();
  const access = useAccess();
  const qc = useQueryClient();
  const toast = useToast();
  const [title, setTitle] = useState('');
  const [description, setDescription] = useState('');
  const [due, setDue] = useState('');
  const [priority, setPriority] = useState<OSTaskPriority>('normal');
  const [assignee, setAssignee] = useState<{ id: string; fullName: string } | null>(null);
  const create = useMutation({
    mutationFn: () => api.tasks.create({ title, description, dueAt: fromLocalInput(due), priority, assigneeId: assignee?.id }),
    onSuccess: () => { toast('Task created'); void qc.invalidateQueries({ queryKey: ['os', 'tasks'] }); void qc.invalidateQueries({ queryKey: ['os', 'home'] }); onClose(); },
  });
  const errs = fieldErrors(create.error);
  return (
    <Dialog title="New task" onClose={onClose} footer={<>
      <Button variant="outline" onClick={onClose}>Cancel</Button>
      <Button loading={create.isPending} disabled={title.trim().length < 2} onClick={() => create.mutate()}>Create task</Button>
    </>}>
      {create.error && !Object.keys(errs).length && <Alert tone="error">{apiMessage(create.error)}</Alert>}
      <TextField label="Title" value={title} onChange={(e) => setTitle(e.target.value)} error={errs.title} maxLength={160} autoFocus />
      <TextArea label="Description" value={description} onChange={(e) => setDescription(e.target.value)} maxLength={4000} />
      <div className="grid grid--2">
        <TextField label="Due" type="datetime-local" value={due} onChange={(e) => setDue(e.target.value)} />
        <div className="field"><label className="field__label" htmlFor="prio">Priority</label>
          <select id="prio" className="field__input" value={priority} onChange={(e) => setPriority(e.target.value as OSTaskPriority)}>
            {['low', 'normal', 'high', 'urgent'].map((p) => <option key={p} value={p}>{p[0]!.toUpperCase() + p.slice(1)}</option>)}
          </select></div>
      </div>
      {access.can('workflows.task.assign') ? (
        <>
          <PersonPicker label="Assign to (leave empty for yourself)" value={assignee} onChange={setAssignee} />
          <span className="xs muted">You can assign to people within your scope ({access.scopeOf('workflows.task.assign')}).</span>
        </>
      ) : <p className="xs muted">This task will be assigned to you, {ctx.user.fullName}.</p>}
    </Dialog>
  );
}

function TaskDrawer({ id, rows, onClose }: { id: string; rows: OSTask[]; onClose: () => void }) {
  const qc = useQueryClient();
  const task = rows.find((t) => t.id === id);
  const update = useMutation({
    mutationFn: (input: { status: OSTaskStatus }) => api.tasks.update(id, input),
    onSuccess: () => { void qc.invalidateQueries({ queryKey: ['os', 'tasks'] }); void qc.invalidateQueries({ queryKey: ['os', 'home'] }); },
  });
  if (!task) {
    return <Drawer title="Task" onClose={onClose}><p className="muted small">This task isn’t in the current list. Switch tabs to find it.</p></Drawer>;
  }
  return (
    <Drawer title={task.title} onClose={onClose} footer={task.canEdit && (
      <div className="row grow">
        {task.status !== 'in_progress' && task.status !== 'done' && <Button variant="outline" loading={update.isPending} onClick={() => update.mutate({ status: 'in_progress' })}>Start</Button>}
        {task.status !== 'done' ? <Button loading={update.isPending} onClick={() => update.mutate({ status: 'done' })}>Mark done</Button>
          : <Button variant="outline" loading={update.isPending} onClick={() => update.mutate({ status: 'open' })}>Reopen</Button>}
        {task.status !== 'cancelled' && task.status !== 'done' && <Button variant="ghost" onClick={() => update.mutate({ status: 'cancelled' })}>Cancel task</Button>}
      </div>
    )}>
      {update.error && <Alert tone="error">{apiMessage(update.error)}</Alert>}
      <div className="row"><Status value={task.status} />{task.priority !== 'normal' && <Status value={task.priority} />}{task.overdue && <Status value="overdue" tone="danger" />}</div>
      <dl className="kv" style={{ gridTemplateColumns: '110px minmax(0,1fr)' }}>
        <dt>Assignee</dt><dd>{task.assignee.fullName}</dd>
        <dt>Created by</dt><dd>{task.createdBy.fullName}</dd>
        <dt>Due</dt><dd>{fmtDateTime(task.dueAt)}</dd>
        <dt>Created</dt><dd>{fmtDateTime(task.createdAt)}</dd>
        {task.completedAt && <><dt>Completed</dt><dd>{fmtDateTime(task.completedAt)}</dd></>}
      </dl>
      {task.description ? <p style={{ whiteSpace: 'pre-wrap' }}>{task.description}</p> : <p className="muted small">No description.</p>}
    </Drawer>
  );
}
