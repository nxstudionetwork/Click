import { useRef } from 'react';
import { Link } from 'react-router-dom';
import { useMutation } from '@tanstack/react-query';
import { Button, useToast } from '@click/ui';
import { api, apiMessage } from '../lib/api';
import { fmtDate, fmtDateTime, fmtMoney, humanize, SCOPE_LABEL } from '../lib/format';
import { useOS, useOSSession } from '../session/OSSession';
import { Avatar, Card, PageHeader, Status } from '../components/ui';

export function ProfilePage() {
  const ctx = useOS();
  const { setContext } = useOSSession();
  const toast = useToast();
  const file = useRef<HTMLInputElement>(null);
  const upload = useMutation({ mutationFn: api.me.uploadAvatar, onSuccess: (c) => { setContext(c); toast('Photo updated'); }, onError: (e) => toast(apiMessage(e), 'error') });
  const remove = useMutation({ mutationFn: api.me.removeAvatar, onSuccess: (c) => setContext(c) });
  const emp = ctx.employee;
  const byModule = new Map<string, { code: string; scope: string }[]>();
  for (const p of ctx.permissions) byModule.set(p.code.split('.')[0]!, [...(byModule.get(p.code.split('.')[0]!) ?? []), p]);

  return (
    <>
      <PageHeader title="Profile" description="Who you are in the organization, and what you can access." />
      <div className="stack stack--lg">
        <Card>
          <div className="row row--wrap" style={{ gap: 20 }}>
            <Avatar name={ctx.user.fullName} src={ctx.user.avatarUrl} size="lg" />
            <div className="grow">
              <h2 style={{ fontSize: 'var(--fs-xl)' }}>{ctx.user.fullName}</h2>
              <div className="muted">{emp?.designation ?? humanize(ctx.account.kind)}{ctx.orgContext.department ? ` · ${ctx.orgContext.department.name}` : ''}</div>
              <div className="row row--wrap" style={{ marginTop: 8 }}><Status value={ctx.account.status} />{ctx.account.mfaEnabled ? <Status value="active" label="2-step on" /> : <Status value="warning" label="2-step off" />}</div>
            </div>
            <div className="row">
              <input ref={file} type="file" accept="image/jpeg,image/png,image/webp" hidden onChange={(e) => { const f = e.target.files?.[0]; if (f) upload.mutate(f); e.target.value = ''; }} />
              <Button variant="outline" size="sm" loading={upload.isPending} onClick={() => file.current?.click()}>Change photo</Button>
              {ctx.user.avatarUrl && <Button variant="ghost" size="sm" loading={remove.isPending} onClick={() => remove.mutate()}>Remove</Button>}
              <Link to="/settings/preferences" className="btn btn--outline btn--sm" style={{ textDecoration: 'none' }}>Edit details</Link>
            </div>
          </div>
        </Card>
        <div className="grid grid--2">
          <Card title="Work information">
            <dl className="kv">
              <dt>Employee ID</dt><dd className="mono">{emp?.employeeId ?? '—'}</dd>
              <dt>Work email</dt><dd>{ctx.user.email ?? '—'}</dd>
              <dt>Designation</dt><dd>{emp?.designation ?? '—'}</dd>
              <dt>Department</dt><dd>{ctx.orgContext.department?.name ?? '—'}</dd>
              <dt>Team</dt><dd>{ctx.orgContext.team?.name ?? '—'}</dd>
              <dt>Location</dt><dd>{ctx.orgContext.units.length ? ctx.orgContext.units.map((u) => u.name).join(' › ') : '—'}</dd>
              <dt>Manager</dt><dd>{emp?.manager ? <Link to={`/people/${emp.manager.id}`}>{emp.manager.fullName}</Link> : '—'}</dd>
              <dt>Employment</dt><dd>{emp ? `${humanize(emp.employmentType)} · since ${fmtDate(emp.joinedOn)}` : '—'}</dd>
              {ctx.account.partner && <><dt>Partner business</dt><dd>{ctx.account.partner.name} <span className="mono xs">{ctx.account.partner.code}</span></dd></>}
            </dl>
            <p className="xs muted" style={{ marginTop: 12 }}>Work information is maintained by People & HR.</p>
          </Card>
          <Card title="Account & security">
            <dl className="kv">
              <dt>Organization</dt><dd>{ctx.organization.name}</dd>
              <dt>Account type</dt><dd>{humanize(ctx.account.kind)}</dd>
              <dt>Roles</dt><dd>{ctx.roles.map((r) => r.name).join(', ') || '—'}</dd>
              <dt>Last sign-in</dt><dd>{fmtDateTime(ctx.account.lastLoginAt)}</dd>
              <dt>Time zone</dt><dd>{ctx.account.timezone}</dd>
              <dt>Session ends</dt><dd>{fmtDateTime(ctx.session?.expiresAt)} (or after {ctx.security.idleMinutes} min idle)</dd>
            </dl>
            <Link to="/settings/security" className="small" style={{ display: 'inline-block', marginTop: 12 }}>Security & sessions →</Link>
            <div className="row" style={{ gap: 12, marginTop: 8 }}><Link to="/access/me" className="small">My access →</Link><Link to="/access/requests?new=1" className="small">Request access →</Link></div>
          </Card>
        </div>
        {ctx.approvalAuthority.length > 0 && (
          <Card title="Approval authority" flush>
            <table className="table"><thead><tr><th>Type</th><th className="num">Up to</th></tr></thead>
              <tbody>{ctx.approvalAuthority.map((a) => <tr key={a.type}><td>{a.label}</td><td className="num">{a.maxAmount ? fmtMoney(a.maxAmount, a.currency) : 'No upper limit'}</td></tr>)}</tbody></table>
          </Card>
        )}
        <Card title={`Access (${ctx.permissions.length} permissions)`}>
          {ctx.mfaBlocked.length > 0 && <div className="alert alert--warning small" style={{ marginBottom: 12 }}>{ctx.mfaBlocked.length} more permissions turn on once you enable two-step verification.</div>}
          <div className="stack">
            {[...byModule.entries()].map(([m, perms]) => (
              <div key={m}><strong className="small">{humanize(m)}</strong>
                <div>{perms.map((p) => <span key={p.code} className="perm-tag" title={SCOPE_LABEL[p.scope]}>{p.code.split('.').slice(1).join('.')} · {SCOPE_LABEL[p.scope]?.toLowerCase()}</span>)}</div>
              </div>
            ))}
            {!ctx.permissions.length && <p className="muted small">No permissions yet. Ask your administrator.</p>}
          </div>
        </Card>
      </div>
    </>
  );
}
