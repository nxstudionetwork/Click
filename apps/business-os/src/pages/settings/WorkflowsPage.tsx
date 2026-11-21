import { useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Button, useToast } from '@click/ui';
import type { OSPolicy } from '@click/api';
import { api, apiMessage } from '../../lib/api';
import { fmtMoney } from '../../lib/format';
import { useAccess } from '../../session/access';
import { Alert, Card, Dialog, LoadingRows, QueryError, Status } from '../../components/ui';

export function WorkflowsPage() {
  const access = useAccess();
  const q = useQuery({ queryKey: ['os', 'admin', 'workflows'], queryFn: api.admin.policies });
  const [editing, setEditing] = useState<OSPolicy | null>(null);
  return (
    <div className="stack">
      <div><h2 style={{ fontSize: 'var(--fs-xl)' }}>Workflows & approvals</h2>
        <p className="muted small">Every module routes sign-off through these policies. Each level names the permission an approver needs; their scope and approval limit decide which requests reach them.</p></div>
      {q.isPending ? <Card><LoadingRows /></Card> : q.error ? <QueryError error={q.error} /> : q.data.results.map((p) => (
        <Card key={p.id} title={<div><h2>{p.name}</h2><span className="xs muted mono">{p.key}</span></div>}
          actions={<>{p.isActive ? <Status value="active" /> : <Status value="inactive" tone="neutral" label="Inactive" />}
            {access.can('workflows.policy.configure') && <Button size="sm" variant="outline" onClick={() => setEditing(p)}>Edit levels</Button>}</>}>
          <p className="small muted" style={{ marginBottom: 12 }}>{p.description} · Raised with <span className="mono">{p.submitPermission}</span> · Authority type: {q.data.approvalTypes[p.approvalType]} · {p.openRequests} open</p>
          <div className="steps">
            {p.levels.map((l) => (
              <div key={l.sequence} className="step">
                <strong>{l.sequence}. {l.name}</strong>
                <div className="xs muted mono">{l.approverPermission}</div>
                <div className="xs">{Number(l.minAmount) > 0 ? `From ${fmtMoney(l.minAmount, p.currency)}` : 'Always'}{l.enforceLimit ? ' · within approver limit' : ''}{l.escalateAfterHours ? ` · escalates after ${l.escalateAfterHours}h` : ''}</div>
              </div>
            ))}
          </div>
        </Card>
      ))}
      {editing && <LevelsDialog policy={editing} onClose={() => setEditing(null)} />}
    </div>
  );
}

function LevelsDialog({ policy, onClose }: { policy: OSPolicy; onClose: () => void }) {
  const qc = useQueryClient();
  const toast = useToast();
  const [levels, setLevels] = useState(policy.levels.map((l) => ({ ...l, minAmount: String(Number(l.minAmount)) })));
  const [active, setActive] = useState(policy.isActive);
  const save = useMutation({
    mutationFn: () => api.admin.updatePolicy(policy.id, { isActive: active, levels: levels.map((l, i) => ({ ...l, sequence: i + 1 })) }),
    onSuccess: () => { toast('Policy saved'); void qc.invalidateQueries({ queryKey: ['os', 'admin', 'workflows'] }); onClose(); },
  });
  const set = (i: number, patch: Partial<(typeof levels)[number]>) => setLevels((ls) => ls.map((l, j) => (j === i ? { ...l, ...patch } : l)));
  return (
    <Dialog title={`Edit ${policy.name}`} wide onClose={onClose} footer={<><Button variant="outline" onClick={onClose}>Cancel</Button><Button loading={save.isPending} onClick={() => save.mutate()}>Save</Button></>}>
      {save.error && <Alert tone="error">{apiMessage(save.error)}</Alert>}
      <Alert tone="info">Changes apply to new requests. Requests already in progress keep the levels they started with.</Alert>
      <label className="row small"><input type="checkbox" checked={active} onChange={(e) => setActive(e.target.checked)} />Policy active (people can raise requests)</label>
      {levels.map((l, i) => (
        <div key={i} className="card card__body stack" style={{ gap: 8 }}>
          <div className="row row--between"><strong>Level {i + 1}</strong>{levels.length > 1 && <Button size="sm" variant="ghost" onClick={() => setLevels((ls) => ls.filter((_, j) => j !== i))}>Remove</Button>}</div>
          <div className="grid grid--2">
            <div className="field"><label className="field__label">Name</label><input className="field__input" value={l.name} onChange={(e) => set(i, { name: e.target.value })} /></div>
            <div className="field"><label className="field__label">Approver permission</label><input className="field__input mono" value={l.approverPermission} onChange={(e) => set(i, { approverPermission: e.target.value })} /></div>
            <div className="field"><label className="field__label">Applies from amount</label><input className="field__input" type="number" min="0" value={l.minAmount} onChange={(e) => set(i, { minAmount: e.target.value })} /></div>
            <div className="field"><label className="field__label">Escalate after (hours)</label><input className="field__input" type="number" min="1" value={l.escalateAfterHours ?? ''} onChange={(e) => set(i, { escalateAfterHours: e.target.value ? Number(e.target.value) : null })} /></div>
          </div>
          <label className="row small"><input type="checkbox" checked={l.enforceLimit} onChange={(e) => set(i, { enforceLimit: e.target.checked })} />Approver’s approval limit must cover the amount</label>
        </div>
      ))}
      <div><Button variant="outline" size="sm" onClick={() => setLevels((ls) => [...ls, { sequence: ls.length + 1, name: `Level ${ls.length + 1}`, approverPermission: policy.levels[0]?.approverPermission ?? '', minAmount: '0', enforceLimit: true, escalateAfterHours: 48 }])}>Add level</Button></div>
    </Dialog>
  );
}
