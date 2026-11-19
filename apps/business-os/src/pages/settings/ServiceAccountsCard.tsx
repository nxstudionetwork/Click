import { useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Button, TextField } from '@click/ui';
import { api, apiMessage } from '../../lib/api';
import { relative } from '../../lib/format';
import { useAccess } from '../../session/access';
import { Alert, Card, Dialog, LoadingRows, QueryError, Status } from '../../components/ui';

/** Machine identities for integrations. Keys are shown once, stored hashed, and act only through roles assigned to them. */
export function ServiceAccountsCard() {
  const access = useAccess();
  const qc = useQueryClient();
  const q = useQuery({ queryKey: ['os', 'admin', 'service-accounts'], queryFn: api.admin.serviceAccounts });
  const [creating, setCreating] = useState(false);
  const [name, setName] = useState('');
  const [key, setKey] = useState<string | null>(null);
  const create = useMutation({ mutationFn: () => api.admin.createServiceAccount({ name }), onSuccess: (r) => { setKey(r.key); setName(''); void qc.invalidateQueries({ queryKey: ['os', 'admin', 'service-accounts'] }); } });
  const revoke = useMutation({ mutationFn: api.admin.revokeServiceAccount, onSuccess: () => void qc.invalidateQueries({ queryKey: ['os', 'admin', 'service-accounts'] }) });
  const manage = access.can('identity.service_account.manage');
  return (
    <Card title="Service accounts" flush actions={manage && <Button size="sm" onClick={() => setCreating(true)}>New key</Button>}>
      {q.isPending ? <LoadingRows /> : q.error ? <QueryError error={q.error} /> : !q.data.results.length ? <p className="muted small" style={{ padding: 16 }}>No service accounts. Integrations and automation will use these instead of people’s logins.</p> : (
        <table className="table"><thead><tr><th>Name</th><th>Key</th><th>Last used</th><th>Status</th><th /></tr></thead>
          <tbody>{q.data.results.map((s) => (
            <tr key={s.id}><td>{s.name}</td><td className="mono xs">{s.keyPrefix}.••••</td><td className="small muted">{s.lastUsedAt ? relative(s.lastUsedAt) : 'Never'}</td>
              <td><Status value={s.usable ? 'active' : 'deactivated'} label={s.usable ? 'Active' : 'Revoked'} /></td>
              <td className="num">{manage && s.usable && <Button size="sm" variant="ghost" onClick={() => revoke.mutate(s.id)}>Revoke</Button>}</td></tr>
          ))}</tbody></table>
      )}
      {creating && (
        <Dialog title={key ? 'Copy this key now' : 'New service account'} onClose={() => { setCreating(false); setKey(null); }}
          footer={key ? <Button onClick={() => { setCreating(false); setKey(null); }}>Done</Button> : <Button loading={create.isPending} disabled={name.trim().length < 3} onClick={() => create.mutate()}>Create</Button>}>
          {key ? <><Alert tone="warning">This key is shown once and can’t be recovered. Store it in the integration’s secret store.</Alert><div className="secret">{key}</div>
            <p className="xs muted">Use it as <span className="mono">Authorization: ClickKey &lt;key&gt;</span>. It has no permissions until roles are assigned.</p></> : <>
            {create.error && <Alert tone="error">{apiMessage(create.error)}</Alert>}
            <TextField label="What will use this key?" value={name} onChange={(e) => setName(e.target.value)} placeholder="e.g. Accounting export" />
          </>}
        </Dialog>
      )}
    </Card>
  );
}
