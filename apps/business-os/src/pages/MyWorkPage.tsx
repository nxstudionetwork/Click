import { Link } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { api } from '../lib/api';
import { fmtDateTime } from '../lib/format';
import { ApprovalTable } from './ApprovalsPage';
import { Card, Empty, LoadingRows, PageHeader, QueryError, Status } from '../components/ui';

/** Everything that needs the signed-in person, in one place: decisions, tasks and their own open requests. */
export function MyWorkPage() {
  const inbox = useQuery({ queryKey: ['os', 'approvals', 'inbox'], queryFn: () => api.approvals.list('inbox') });
  const tasks = useQuery({ queryKey: ['os', 'tasks', 'assigned', 1], queryFn: () => api.tasks.list('assigned') });
  const mine = useQuery({ queryKey: ['os', 'approvals', 'mine'], queryFn: () => api.approvals.list('mine') });
  return (
    <>
      <PageHeader title="My Work" description="Decisions waiting on you, your tasks, and the requests you’ve raised." />
      <div className="stack stack--lg">
        <Card title="Waiting for your decision" flush actions={<Link to="/approvals" className="small">All approvals</Link>}>
          {inbox.isPending ? <LoadingRows /> : inbox.error ? <QueryError error={inbox.error} /> :
            <ApprovalTable rows={inbox.data.results} empty="Nothing is waiting for your decision" />}
        </Card>
        <div className="grid grid--2">
          <Card title="My tasks" flush actions={<Link to="/tasks" className="small">All tasks</Link>}>
            {tasks.isPending ? <LoadingRows /> : tasks.error ? <QueryError error={tasks.error} /> : !tasks.data.results.length ? <Empty icon="list" title="No open tasks" /> : (
              <ul className="list">{tasks.data.results.slice(0, 8).map((t) => (
                <li key={t.id}><Link to={`/tasks?open=${t.id}`} className="list-row">
                  <span className="list-row__main"><span className="list-row__title" style={{ display: 'block' }}>{t.title}</span>
                    <span className="list-row__sub" style={{ display: 'block', color: t.overdue ? 'var(--c-danger)' : undefined }}>{t.dueAt ? `${t.overdue ? 'Overdue · ' : 'Due '}${fmtDateTime(t.dueAt)}` : 'No due date'}</span></span>
                  {t.priority !== 'normal' && <Status value={t.priority} />}
                </Link></li>))}</ul>
            )}
          </Card>
          <Card title="My open requests" flush actions={<Link to="/approvals/new" className="small">New request</Link>}>
            {mine.isPending ? <LoadingRows /> : mine.error ? <QueryError error={mine.error} /> : (() => {
              const open = mine.data.results.filter((r) => r.status === 'pending');
              return !open.length ? <Empty icon="check" title="No requests in progress" /> : (
                <ul className="list">{open.map((r) => (
                  <li key={r.id}><Link to={`/approvals/${r.id}`} className="list-row">
                    <span className="list-row__main"><span className="list-row__title" style={{ display: 'block' }}>{r.title}</span><span className="list-row__sub" style={{ display: 'block' }}>{r.reference} · level {r.currentSequence}</span></span>
                    <Status value={r.status} />
                  </Link></li>))}</ul>
              );
            })()}
          </Card>
        </div>
      </div>
    </>
  );
}
