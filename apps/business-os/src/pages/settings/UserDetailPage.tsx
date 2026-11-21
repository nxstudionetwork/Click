import { useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Button, Icon, TextField, useToast } from '@click/ui';
import { access, api, apiMessage } from '../../lib/api';
import { fmtDateTime, fromLocalInput, humanize, relative } from '../../lib/format';
import { Alert, Avatar, Card, ConfirmDialog, Dialog, LoadingRows, QueryError, Status } from '../../components/ui';

type Action = 'suspend' | 'reactivate' | 'unlock' | 'sign_out_everywhere' | 'resend_invite';

export function UserDetailPage() {
  const { id = '' } = useParams();
  const qc = useQueryClient();
  const toast = useToast();
  const q = useQuery({ queryKey: ['os', 'admin', 'user', id], queryFn: () => api.admin.user(id) });
  const [confirm, setConfirm] = useState<Action | null>(null);
  const [assigning, setAssigning] = useState(false);
  const [inviteLink, setInviteLink] = useState<string | null>(null);
  const refresh = () => { void qc.invalidateQueries({ queryKey: ['os', 'admin'] }); };
  const status = useMutation({
    mutationFn: (a: Action) => api.admin.userStatus(id, a),
    onSuccess: (r, a) => { setConfirm(null); refresh(); if (r.inviteUrl) setInviteLink(`${window.location.origin}${r.inviteUrl}`); else toast(`${humanize(a)} done`); },
  });
  const removeRole = useMutation({ mutationFn: (assignmentId: string) => api.admin.removeRole(id, assignmentId), onSuccess: () => { toast('Role removed'); refresh(); } });

  if (q.isPending) return <Card><LoadingRows /></Card>;
  if (q.error) return <QueryError error={q.error} />;
  const u = q.data;
  const CONFIRM: Record<Action, [string, string, boolean]> = {
    suspend: ['Suspend this account?', `${u.fullName} is signed out everywhere immediately and can’t sign in until reactivated.`, true],
    reactivate: ['Reactivate this account?', 'They can sign in again with their existing password and roles.', false],
    unlock: ['Unlock this account?', 'Clears the lock from failed sign-in attempts.', false],
    sign_out_everywhere: ['Sign out every device?', 'All their Business OS sessions end now.', true],
    resend_invite: ['Create a new invitation link?', 'Earlier links stop working.', false],
  };

  return (
    <div className="stack stack--lg">
      <div className="crumbs"><Link to="/settings/users">Users</Link><span>/</span><span>{u.fullName}</span></div>
      <Card>
        <div className="row row--wrap" style={{ gap: 16 }}>
          <Avatar name={u.fullName} src={u.avatarUrl} size="lg" />
          <div className="grow">
            <h2 style={{ fontSize: 'var(--fs-xl)' }}>{u.fullName}</h2>
            <div className="muted small">{u.email} · {humanize(u.kind)}{u.employee ? ` · ${u.employee.employeeId}` : ''}</div>
            <div className="row row--wrap" style={{ marginTop: 6 }}><Status value={u.status} />{u.isLocked && <Status value="locked" tone="danger" label={`Locked until ${fmtDateTime(u.lockedUntil)}`} />}
              {u.mfaEnabled ? <Status value="active" label="2-step on" /> : <Status value="warning" label="2-step off" />}
              {u.identityType && <span className="chip">{humanize(u.identityType)}</span>}
              {u.expiresAt && <span className="chip">Access ends {fmtDateTime(u.expiresAt)}</span>}
              <Link to={`/access/effective?account=${u.id}`} className="small">Effective access →</Link></div>
            {u.canManage && <IdentityLifecycle id={u.id} type={u.identityType} expires={u.expiresAt} onDone={refresh} />}
          </div>
          {u.canManage && (
            <div className="row row--wrap">
              {u.status === 'active' && <Button variant="danger" size="sm" onClick={() => setConfirm('suspend')}>Suspend</Button>}
              {u.status === 'suspended' && <Button size="sm" onClick={() => setConfirm('reactivate')}>Reactivate</Button>}
              {u.status === 'invited' && <Button variant="outline" size="sm" onClick={() => setConfirm('resend_invite')}>New invitation link</Button>}
              {u.isLocked && <Button variant="outline" size="sm" onClick={() => setConfirm('unlock')}>Unlock</Button>}
              {u.sessions > 0 && <Button variant="outline" size="sm" onClick={() => setConfirm('sign_out_everywhere')}>Sign out {u.sessions} device{u.sessions > 1 ? 's' : ''}</Button>}
            </div>
          )}
        </div>
        {u.isSelf && <p className="xs muted" style={{ marginTop: 12 }}>This is your own account. Another administrator must change your status or roles.</p>}
      </Card>

      <Card title="Roles & scope" flush actions={u.canAssign && <Button size="sm" onClick={() => setAssigning(true)}><Icon name="plus" size={15} />Assign role</Button>}>
        {!u.assignments.length ? <p className="muted small" style={{ padding: 16 }}>No roles. This account can sign in but has no access beyond its own workspace.</p> : (
          <div className="table-wrap"><table className="table">
            <thead><tr><th>Role</th><th>Applies at</th><th>Valid until</th><th>Granted by</th><th /></tr></thead>
            <tbody>{u.assignments.map((a) => (
              <tr key={a.id}>
                <td><Link to={`/settings/roles/${a.role.id}`}>{a.role.name}</Link></td>
                <td className="small">{[a.orgUnit?.name, a.department?.name, a.team?.name].filter(Boolean).join(' · ') || <span className="muted">Their own location</span>}</td>
                <td className="small muted">{a.validUntil ? fmtDateTime(a.validUntil) : 'No end date'}</td>
                <td className="small muted">{a.grantedBy ?? 'System'}</td>
                <td className="num">{u.canAssign && <Button size="sm" variant="ghost" loading={removeRole.isPending && removeRole.variables === a.id} onClick={() => removeRole.mutate(a.id)}>Remove</Button>}</td>
              </tr>
            ))}</tbody>
          </table></div>
        )}
        {removeRole.error && <div className="card__body"><Alert tone="error">{apiMessage(removeRole.error)}</Alert></div>}
      </Card>

      {u.recentActivity && (
        <Card title="Recent activity" flush>
          {!u.recentActivity.length ? <p className="muted small" style={{ padding: 16 }}>No activity.</p> : (
            <ul className="list">{u.recentActivity.map((a, i) => (
              <li key={i} className="list-row"><span className="list-row__main">{humanize(a.action)}</span><Status value={a.outcome} /><span className="list-row__aside">{relative(a.at)}<br />{a.ip}</span></li>
            ))}</ul>
          )}
        </Card>
      )}

      {confirm && <ConfirmDialog title={CONFIRM[confirm][0]} message={CONFIRM[confirm][1]} danger={CONFIRM[confirm][2]} confirmLabel="Confirm"
        busy={status.isPending} onConfirm={() => status.mutate(confirm)} onClose={() => setConfirm(null)}>
        {status.error && <Alert tone="error">{apiMessage(status.error)}</Alert>}
      </ConfirmDialog>}
      {assigning && <AssignRoleDialog userId={id} onClose={() => { setAssigning(false); refresh(); }} />}
      {inviteLink && <Dialog title="New invitation link" onClose={() => setInviteLink(null)}><div className="secret">{inviteLink}</div></Dialog>}
    </div>
  );
}

function AssignRoleDialog({ userId, onClose }: { userId: string; onClose: () => void }) {
  const toast = useToast();
  const roles = useQuery({ queryKey: ['os', 'admin', 'roles'], queryFn: api.admin.roles });
  const tree = useQuery({ queryKey: ['os', 'org', 'tree'], queryFn: api.org.tree, retry: false });
  const [roleId, setRoleId] = useState('');
  const [unitId, setUnitId] = useState('');
  const [deptId, setDeptId] = useState('');
  const [until, setUntil] = useState('');
  const [note, setNote] = useState('');
  const assign = useMutation({
    mutationFn: () => api.admin.assignRole(userId, { roleId, orgUnitId: unitId || undefined, departmentId: deptId || undefined, validUntil: fromLocalInput(until) ?? undefined, note }),
    onSuccess: () => { toast('Role assigned'); onClose(); },
  });
  return (
    <Dialog title="Assign role" onClose={onClose} footer={<><Button variant="outline" onClick={onClose}>Cancel</Button><Button loading={assign.isPending} disabled={!roleId} onClick={() => assign.mutate()}>Assign</Button></>}>
      {assign.error && <Alert tone="error">{apiMessage(assign.error)}</Alert>}
      <div className="field"><label className="field__label" htmlFor="role">Role</label>
        <select id="role" className="field__input" value={roleId} onChange={(e) => setRoleId(e.target.value)}>
          <option value="">Choose…</option>
          {roles.data?.results.filter((r) => r.isActive).map((r) => <option key={r.id} value={r.id}>{r.name}{r.audience !== 'employee' ? ` (${r.audience})` : ''}</option>)}
        </select>
        <span className="field__hint">You can only assign roles whose permissions you hold yourself.</span></div>
      <div className="field"><label className="field__label" htmlFor="unit">Anchor location (optional)</label>
        <select id="unit" className="field__input" value={unitId} onChange={(e) => setUnitId(e.target.value)} disabled={!tree.data}>
          <option value="">Their own work location</option>
          {tree.data?.units.map((u) => <option key={u.id} value={u.id}>{'  '.repeat(u.depth)}{u.name} · {u.typeLabel}</option>)}
        </select>
        <span className="field__hint">Scopes in the role (branch, city, region…) are measured from here.</span></div>
      {tree.data && tree.data.departments.length > 0 && (
        <div className="field"><label className="field__label" htmlFor="dept">Anchor department (optional)</label>
          <select id="dept" className="field__input" value={deptId} onChange={(e) => setDeptId(e.target.value)}>
            <option value="">Their own department</option>
            {tree.data.departments.map((d) => <option key={d.id} value={d.id}>{d.name}</option>)}
          </select></div>
      )}
      <TextField label="Valid until (optional)" type="datetime-local" value={until} onChange={(e) => setUntil(e.target.value)} />
      <TextField label="Reason" value={note} onChange={(e) => setNote(e.target.value)} maxLength={200} />
    </Dialog>
  );
}

function IdentityLifecycle({ id, type, expires, onDone }: { id: string; type?: string; expires?: string | null; onDone: () => void }) {
  const toast = useToast();
  const [t, setT] = useState(type ?? 'employee');
  const [e, setE] = useState(expires ? expires.slice(0, 10) : '');
  const save = useMutation({
    mutationFn: () => access.patch(`identities/${id}`, { identityType: t, expiresAt: e || null }),
    onSuccess: () => { toast('Identity updated'); onDone(); }, onError: (err) => toast(apiMessage(err), 'error'),
  });
  return (
    <div className="row row--wrap" style={{ marginTop: 8 }}>
      <select className="field__input" aria-label="Identity type" value={t} onChange={(x) => setT(x.target.value)}>
        {['employee', 'contractor', 'consultant', 'intern', 'temporary', 'partner_user', 'support', 'external'].map((v) => <option key={v} value={v}>{humanize(v)}</option>)}
      </select>
      <label className="row small">Access ends <input type="date" className="field__input" value={e} onChange={(x) => setE(x.target.value)} /></label>
      <Button size="sm" variant="outline" loading={save.isPending} onClick={() => save.mutate()}>Save</Button>
    </div>
  );
}
