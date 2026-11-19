import { Link, useParams } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { api } from '../lib/api';
import { fmtDate, humanize } from '../lib/format';
import { Avatar, Card, LoadingRows, PageHeader, QueryError, Status } from '../components/ui';

export function EmployeePage() {
  const { id = '' } = useParams();
  const q = useQuery({ queryKey: ['os', 'employee', id], queryFn: () => api.people.get(id) });
  if (q.isPending) return <><PageHeader title="Employee" crumbs={[{ label: 'People' }]} /><Card><LoadingRows /></Card></>;
  if (q.error) return <><PageHeader title="Employee" crumbs={[{ label: 'People' }]} /><QueryError error={q.error} /></>;
  const e = q.data;
  return (
    <>
      <PageHeader title={e.fullName} crumbs={[{ label: 'People & HR', to: '/m/people' }, { label: e.employeeId }]} />
      <div style={{ maxWidth: 760 }}>
        <Card>
          <div className="row" style={{ gap: 16, marginBottom: 16 }}>
            <Avatar name={e.fullName} size="lg" />
            <div><h2>{e.fullName}</h2><div className="muted">{e.designation ?? '—'} · {e.location ?? '—'}</div><Status value={e.status === 'active' ? 'active' : 'warning'} label={humanize(e.status)} /></div>
          </div>
          <dl className="kv">
            <dt>Employee ID</dt><dd className="mono">{e.employeeId}</dd>
            <dt>Department</dt><dd>{e.department ?? '—'}</dd>
            <dt>Team</dt><dd>{e.team ?? '—'}</dd>
            <dt>Work email</dt><dd>{e.workEmail ? <a href={`mailto:${e.workEmail}`}>{e.workEmail}</a> : '—'}</dd>
            <dt>Manager</dt><dd>{e.manager ? <Link to={`/people/${e.manager.id}`}>{e.manager.fullName}</Link> : '—'}</dd>
            {e.fullRecord && <>
              <dt>Employment</dt><dd>{humanize(e.employmentType ?? '')}</dd>
              <dt>Joined</dt><dd>{fmtDate(e.joinedOn)}</dd>
              <dt>Business OS account</dt><dd>{e.hasAccount ? 'Yes' : 'Not yet'}</dd>
            </>}
          </dl>
          {!e.fullRecord && <p className="xs muted" style={{ marginTop: 12 }}>You’re seeing the company directory view. Full employee records are available to HR within their scope.</p>}
        </Card>
      </div>
    </>
  );
}
