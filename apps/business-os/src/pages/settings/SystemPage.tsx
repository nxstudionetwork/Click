import { useQuery } from '@tanstack/react-query';
import { Button } from '@click/ui';
import { api } from '../../lib/api';
import { fmtDateTime, humanize } from '../../lib/format';
import { useAccess } from '../../session/access';
import { Card, LoadingRows, QueryError, Status } from '../../components/ui';
import { ServiceAccountsCard } from './ServiceAccountsCard';

export function SystemPage() {
  const access = useAccess();
  const q = useQuery({ queryKey: ['os', 'system', 'health'], queryFn: api.system.health });
  return (
    <div className="stack stack--lg">
      <div className="row row--between"><div><h2 style={{ fontSize: 'var(--fs-xl)' }}>System</h2><p className="muted small">Live health checks and the security policy in force. Configuration is set on the server, not in the browser.</p></div>
        <Button variant="outline" size="sm" loading={q.isFetching} onClick={() => void q.refetch()}>Re-check</Button></div>
      {q.isPending ? <Card><LoadingRows /></Card> : q.error ? <QueryError error={q.error} /> : (
        <>
          <Card title="Health" flush foot={<span className="muted">Checked {fmtDateTime(q.data.checkedAt)} · {q.data.activeSessions} active sessions</span>}>
            <table className="table"><tbody>{q.data.checks.map((c) => (
              <tr key={c.key}><td><strong>{c.label}</strong></td><td className="small muted">{c.detail}</td><td className="num"><Status value={c.status} label={humanize(c.status)} /></td></tr>
            ))}</tbody></table>
          </Card>
          <Card title="Session & sign-in policy">
            <dl className="kv">
              <dt>Idle sign-out</dt><dd>{q.data.sessionPolicy.idleMinutes} minutes</dd>
              <dt>Maximum session</dt><dd>{q.data.sessionPolicy.maxHours} hours</dd>
              <dt>Lockout</dt><dd>After {q.data.sessionPolicy.maxFailedLogins} failed attempts, for {q.data.sessionPolicy.lockoutMinutes} minutes</dd>
            </dl>
          </Card>
        </>
      )}
      {(access.can('identity.service_account.view') || access.mfaBlocked('identity.service_account.view')) && <ServiceAccountsCard />}
    </div>
  );
}
