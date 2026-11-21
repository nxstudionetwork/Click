import { useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Button, Icon, TextField, useToast } from '@click/ui';
import type { OSApprovalBrief } from '@click/api';
import { api, apiMessage } from '../lib/api';
import { fmtDate, fmtMoney, fromLocalInput, relative } from '../lib/format';
import { useAccess } from '../session/access';
import { Alert, Card, Dialog, Empty, LoadingRows, PageHeader, QueryError, Status, Tabs } from '../components/ui';
import { PersonPicker } from '../components/PersonPicker';

type Box = 'inbox' | 'mine' | 'decided' | 'all';

export function ApprovalTable({ rows, empty }: { rows: OSApprovalBrief[]; empty: string }) {
  const navigate = useNavigate();
  if (!rows.length) return <Empty icon="check" title={empty} />;
  return (
    <div className="table-wrap">
      <table className="table">
        <thead><tr><th>Request</th><th>Type</th><th>Requested by</th><th>Location</th><th className="num">Amount</th><th>Status</th><th>Raised</th></tr></thead>
        <tbody>
          {rows.map((r) => (
            <tr key={r.id} className="clickable" onClick={() => navigate(`/approvals/${r.id}`)}>
              <td><Link to={`/approvals/${r.id}`} onClick={(e) => e.stopPropagation()}><strong>{r.title}</strong></Link><div className="xs muted mono">{r.reference}</div></td>
              <td>{r.policy.name}</td>
              <td>{r.requestedBy.fullName}</td>
              <td className="muted">{r.orgUnit ?? '—'}</td>
              <td className="num">{fmtMoney(r.amount, r.currency)}</td>
              <td><Status value={r.status} />{r.dueAt && r.status === 'pending' && <div className="xs muted">Due {fmtDate(r.dueAt)}</div>}</td>
              <td className="muted">{relative(r.createdAt)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export function ApprovalsPage() {
  const access = useAccess();
  const [box, setBox] = useState<Box>('inbox');
  const [delegating, setDelegating] = useState(false);
  const q = useQuery({ queryKey: ['os', 'approvals', box], queryFn: () => api.approvals.list(box) });
  const tabs: { value: Box; label: string; count?: number }[] = [
    { value: 'inbox', label: 'Waiting on me', count: box === 'inbox' ? q.data?.results.length : q.data?.counts.inbox },
    { value: 'mine', label: 'My requests' },
    { value: 'decided', label: 'Decided by me' },
  ];
  if (access.can('workflows.request.view')) tabs.push({ value: 'all', label: 'All in my scope' });

  return (
    <>
      <PageHeader title="Approvals" description="Decide requests that need you, follow your own, and delegate while you’re away."
        actions={<>
          <Button variant="outline" onClick={() => setDelegating(true)}><Icon name="team" size={16} />Delegation</Button>
          <Link to="/approvals/new" className="btn btn--primary" style={{ textDecoration: 'none' }}><Icon name="plus" size={16} />New request</Link>
        </>} />
      <Tabs value={box} onChange={setBox} items={tabs} />
      <Card flush>
        {q.isPending ? <LoadingRows /> : q.error ? <QueryError error={q.error} onRetry={() => void q.refetch()} /> :
          <ApprovalTable rows={q.data.results} empty={box === 'inbox' ? 'Nothing is waiting for your decision' : 'No requests here yet'} />}
      </Card>
      {delegating && <DelegationDialog onClose={() => setDelegating(false)} />}
    </>
  );
}

function DelegationDialog({ onClose }: { onClose: () => void }) {
  const qc = useQueryClient();
  const toast = useToast();
  const q = useQuery({ queryKey: ['os', 'delegations'], queryFn: api.approvals.delegations });
  const [person, setPerson] = useState<{ id: string; fullName: string } | null>(null);
  const [ends, setEnds] = useState('');
  const [reason, setReason] = useState('');
  const create = useMutation({
    mutationFn: () => api.approvals.delegate({ delegateId: person!.id, endsAt: fromLocalInput(ends)!, reason }),
    onSuccess: () => { toast(`Approvals delegated to ${person!.fullName}`); setPerson(null); setEnds(''); setReason(''); void qc.invalidateQueries({ queryKey: ['os', 'delegations'] }); },
  });
  const revoke = useMutation({ mutationFn: api.approvals.revokeDelegation, onSuccess: () => void qc.invalidateQueries({ queryKey: ['os', 'delegations'] }) });
  return (
    <Dialog title="Approval delegation" onClose={onClose} wide>
      <p className="small muted">While delegated, your colleague can decide requests you’re allowed to decide, within your scope and limits. Every decision records that it was made on your behalf.</p>
      {q.data && q.data.given.length > 0 && (
        <div className="stack"><h3>You’ve delegated to</h3>
          {q.data.given.map((d) => <div key={d.id} className="row row--between card card__body"><span><strong>{d.person.fullName}</strong> <span className="xs muted">until {fmtDate(d.endsAt)} · {d.policy}</span></span>
            <Button size="sm" variant="danger" loading={revoke.isPending} onClick={() => revoke.mutate(d.id)}>End</Button></div>)}
        </div>
      )}
      {q.data && q.data.received.length > 0 && (
        <Alert tone="info">You’re deciding on behalf of {q.data.received.map((d) => `${d.person.fullName} (until ${fmtDate(d.endsAt)})`).join(', ')}.</Alert>
      )}
      <h3>Delegate my approvals</h3>
      {create.error && <Alert tone="error">{apiMessage(create.error)}</Alert>}
      <PersonPicker label="Colleague" value={person} onChange={setPerson} />
      <TextField label="Until" type="datetime-local" value={ends} onChange={(e) => setEnds(e.target.value)} />
      <TextField label="Reason (optional)" value={reason} onChange={(e) => setReason(e.target.value)} placeholder="e.g. On leave" maxLength={200} />
      <div className="row" style={{ justifyContent: 'flex-end' }}><Button loading={create.isPending} disabled={!person || !ends} onClick={() => create.mutate()}>Delegate</Button></div>
    </Dialog>
  );
}
