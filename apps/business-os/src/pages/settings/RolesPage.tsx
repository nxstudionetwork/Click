import { useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { useMutation, useQuery } from '@tanstack/react-query';
import { Button, Icon, TextArea, TextField } from '@click/ui';
import { api, apiMessage, fieldErrors } from '../../lib/api';
import { useAccess } from '../../session/access';
import { Alert, Card, Dialog, LoadingRows, QueryError, Status } from '../../components/ui';

export function RolesPage() {
  const access = useAccess();
  const navigate = useNavigate();
  const q = useQuery({ queryKey: ['os', 'admin', 'roles'], queryFn: api.admin.roles });
  const [creating, setCreating] = useState(false);
  return (
    <div className="stack">
      <div className="row row--between row--wrap">
        <div><h2 style={{ fontSize: 'var(--fs-xl)' }}>Roles & permissions</h2>
          <p className="muted small">A role is a set of permissions, each granted at a scope (own records → team → department → branch → … → organization). Assign roles to people in Users.</p></div>
        {access.can('access.role.create') && <Button onClick={() => setCreating(true)}><Icon name="plus" size={16} />New role</Button>}
      </div>
      <Card flush>
        {q.isPending ? <LoadingRows /> : q.error ? <QueryError error={q.error} /> : (
          <div className="table-wrap"><table className="table">
            <thead><tr><th>Role</th><th>For</th><th className="num">Permissions</th><th className="num">Holders</th><th>Notes</th></tr></thead>
            <tbody>{q.data.results.map((r) => (
              <tr key={r.id} className="clickable" onClick={() => navigate(`/settings/roles/${r.id}`)}>
                <td><Link to={`/settings/roles/${r.id}`} onClick={(e) => e.stopPropagation()}><strong>{r.name}</strong></Link><div className="xs muted">{r.description}</div></td>
                <td className="small">{r.audience}</td>
                <td className="num">{r.permissionCount}</td>
                <td className="num">{r.holderCount}</td>
                <td><div className="row row--wrap" style={{ gap: 4 }}>{r.isSystem && <Status value="system" tone="info" label="Template" />}{r.requiresMfa && <Status value="mfa" tone="warning" label="Needs 2-step" />}{r.parent && <span className="xs muted">inherits {r.parent.name}</span>}</div></td>
              </tr>
            ))}</tbody>
          </table></div>
        )}
      </Card>
      {creating && <NewRoleDialog onClose={() => setCreating(false)} />}
    </div>
  );
}

function NewRoleDialog({ onClose }: { onClose: () => void }) {
  const navigate = useNavigate();
  const [name, setName] = useState('');
  const [description, setDescription] = useState('');
  const create = useMutation({ mutationFn: () => api.admin.createRole({ name, description, grants: [] }), onSuccess: (r) => navigate(`/settings/roles/${r.id}`) });
  const errs = fieldErrors(create.error);
  return (
    <Dialog title="New role" onClose={onClose} footer={<><Button variant="outline" onClick={onClose}>Cancel</Button><Button loading={create.isPending} disabled={name.trim().length < 2} onClick={() => create.mutate()}>Create and edit permissions</Button></>}>
      {create.error && !Object.keys(errs).length && <Alert tone="error">{apiMessage(create.error)}</Alert>}
      <TextField label="Name" value={name} onChange={(e) => setName(e.target.value)} error={errs.name ?? errs.key} placeholder="e.g. Regional Finance Analyst" />
      <TextArea label="Description" value={description} onChange={(e) => setDescription(e.target.value)} maxLength={300} />
      <p className="xs muted">Tip: duplicating a built-in template is often faster than starting empty.</p>
    </Dialog>
  );
}
