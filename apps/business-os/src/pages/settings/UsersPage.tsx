import { useEffect, useState } from 'react';
import { Link, useNavigate, useSearchParams } from 'react-router-dom';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Button, Icon, TextField } from '@click/ui';
import type { OSAccountKind } from '@click/api';
import { api, apiMessage, fieldErrors } from '../../lib/api';
import { relative } from '../../lib/format';
import { useAccess } from '../../session/access';
import { Alert, Avatar, Card, Dialog, Empty, LoadingRows, Pager, QueryError, Status, Tabs } from '../../components/ui';

export function UsersPage() {
  const access = useAccess();
  const navigate = useNavigate();
  const [params, setParams] = useSearchParams();
  const [status, setStatus] = useState<string>('');
  const [text, setText] = useState('');
  const [q, setQ] = useState('');
  const [page, setPage] = useState(1);
  useEffect(() => { const t = setTimeout(() => { setQ(text); setPage(1); }, 250); return () => clearTimeout(t); }, [text]);
  const users = useQuery({ queryKey: ['os', 'admin', 'users', status, q, page], queryFn: () => api.admin.users({ status: status || undefined, q: q || undefined, page }) });
  const inviting = params.get('invite') === '1';
  const counts = users.data?.counts ?? {};

  return (
    <div className="stack">
      <div className="row row--between row--wrap">
        <div><h2 style={{ fontSize: 'var(--fs-xl)' }}>Users</h2><p className="muted small">Business OS accounts in your scope. Employee records themselves live in People & HR.</p></div>
        {access.can('identity.user.create') && <Button onClick={() => setParams({ invite: '1' })}><Icon name="plus" size={16} />Invite user</Button>}
      </div>
      <Tabs value={status} onChange={(v) => { setStatus(v); setPage(1); }} items={[
        { value: '', label: 'All' }, { value: 'active', label: 'Active', count: counts.active }, { value: 'invited', label: 'Invited', count: counts.invited },
        { value: 'suspended', label: 'Suspended', count: counts.suspended },
      ]} />
      <Card flush>
        <div className="toolbar"><div className="search-input"><Icon name="search" size={16} /><input value={text} onChange={(e) => setText(e.target.value)} placeholder="Name, email or employee ID" aria-label="Search users" /></div></div>
        {users.isPending ? <LoadingRows /> : users.error ? <QueryError error={users.error} onRetry={() => void users.refetch()} /> : !users.data.results.length ? <Empty icon="team" title="No users found" /> : (
          <>
            <div className="table-wrap"><table className="table">
              <thead><tr><th>Name</th><th>Type</th><th>Location / department</th><th>Roles</th><th>Status</th><th>2-step</th><th>Last sign-in</th></tr></thead>
              <tbody>{users.data.results.map((u) => (
                <tr key={u.id} className="clickable" onClick={() => navigate(`/settings/users/${u.id}`)}>
                  <td><div className="row"><Avatar name={u.fullName} src={u.avatarUrl} size="sm" /><div><Link to={`/settings/users/${u.id}`} onClick={(e) => e.stopPropagation()}><strong>{u.fullName}</strong></Link><div className="xs muted">{u.email}</div></div></div></td>
                  <td className="muted">{u.kind}</td>
                  <td className="small">{u.employee?.orgUnit?.name ?? '—'}<div className="xs muted">{u.employee?.department?.name ?? ''}</div></td>
                  <td className="small">{u.roles.map((r) => r.name).join(', ') || <span className="muted">None</span>}</td>
                  <td><Status value={u.status} />{u.isLocked && <> <Status value="locked" tone="danger" /></>}</td>
                  <td>{u.mfaEnabled ? <Status value="active" label="On" /> : <span className="muted small">Off</span>}</td>
                  <td className="muted small">{u.lastLoginAt ? relative(u.lastLoginAt) : 'Never'}</td>
                </tr>
              ))}</tbody>
            </table></div>
            <Pager page={users.data.page} hasNext={users.data.hasNext} count={users.data.count} onPage={setPage} />
          </>
        )}
      </Card>
      {inviting && <InviteDialog onClose={() => setParams({})} />}
    </div>
  );
}

function InviteDialog({ onClose }: { onClose: () => void }) {
  const qc = useQueryClient();
  const [email, setEmail] = useState('');
  const [fullName, setFullName] = useState('');
  const [kind, setKind] = useState<OSAccountKind>('employee');
  const [partnerId, setPartnerId] = useState('');
  const [link, setLink] = useState<string | null>(null);
  const invite = useMutation({
    mutationFn: () => api.admin.invite({ email, fullName, kind, partnerId: kind === 'partner' ? partnerId : undefined }),
    onSuccess: (r) => { setLink(`${window.location.origin}${r.inviteUrl}`); void qc.invalidateQueries({ queryKey: ['os', 'admin', 'users'] }); },
  });
  const errs = fieldErrors(invite.error);
  if (link) {
    return (
      <Dialog title="Invitation created" onClose={onClose} footer={<><Button variant="outline" onClick={() => void navigator.clipboard?.writeText(link)}>Copy link</Button><Button onClick={onClose}>Done</Button></>}>
        <p className="small">Send this link to {fullName}. It works once and expires in 7 days. They’ll set their own password; you never see it.</p>
        <div className="secret">{link}</div>
        <Alert tone="info">The account has no access until you assign roles. Open the user to assign them.</Alert>
      </Dialog>
    );
  }
  return (
    <Dialog title="Invite user" onClose={onClose} footer={<><Button variant="outline" onClick={onClose}>Cancel</Button><Button loading={invite.isPending} onClick={() => invite.mutate()} disabled={!email || !fullName}>Create invitation</Button></>}>
      {invite.error && !Object.keys(errs).length && <Alert tone="error">{apiMessage(invite.error)}</Alert>}
      <TextField label="Full name" value={fullName} onChange={(e) => setFullName(e.target.value)} error={errs.fullName} />
      <TextField label="Work email" type="email" value={email} onChange={(e) => setEmail(e.target.value)} error={errs.email} />
      <div className="field"><label className="field__label" htmlFor="kind">Account type</label>
        <select id="kind" className="field__input" value={kind} onChange={(e) => setKind(e.target.value as OSAccountKind)}>
          <option value="employee">Employee</option><option value="partner">Partner / business</option><option value="external">Other authorized account</option>
        </select>
        <span className="field__hint">Partner and external accounts never get employee access by default.</span></div>
      {kind === 'partner' && <TextField label="Partner ID (internal)" value={partnerId} onChange={(e) => setPartnerId(e.target.value)} error={errs.partnerId} />}
    </Dialog>
  );
}
