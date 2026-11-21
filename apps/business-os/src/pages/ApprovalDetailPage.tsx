import { useState } from 'react';
import { useParams } from 'react-router-dom';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Button, TextArea, useToast } from '@click/ui';
import { api, apiMessage } from '../lib/api';
import { fmtDateTime, fmtMoney } from '../lib/format';
import { Alert, Card, LoadingRows, PageHeader, QueryError, Status } from '../components/ui';

export function ApprovalDetailPage() {
  const { id = '' } = useParams();
  const qc = useQueryClient();
  const toast = useToast();
  const q = useQuery({ queryKey: ['os', 'approval', id], queryFn: () => api.approvals.get(id) });
  const [comment, setComment] = useState('');
  const [amount, setAmount] = useState('');
  const act = useMutation({
    mutationFn: (action: 'approve' | 'reject' | 'cancel' | 'comment' | 'request_changes' | 'resubmit') =>
      action === 'resubmit' ? api.approvals.resubmit(id, { comment, amount: amount || undefined }) : api.approvals.act(id, action, comment),
    onSuccess: (data, action) => {
      qc.setQueryData(['os', 'approval', id], data);
      void qc.invalidateQueries({ queryKey: ['os', 'approvals'] });
      void qc.invalidateQueries({ queryKey: ['os', 'home'] });
      setComment('');
      toast(action === 'comment' ? 'Comment added' : action === 'cancel' ? 'Request withdrawn' : `Request ${data.status === 'pending' ? 'moved to the next level' : data.status}`);
    },
  });

  if (q.isPending) return <><PageHeader title="Approval" crumbs={[{ label: 'Approvals', to: '/approvals' }]} /><Card><LoadingRows /></Card></>;
  if (q.error) return <><PageHeader title="Approval" crumbs={[{ label: 'Approvals', to: '/approvals' }]} /><QueryError error={q.error} /></>;
  const r = q.data;

  return (
    <>
      <PageHeader title={r.title} crumbs={[{ label: 'Approvals', to: '/approvals' }, { label: r.reference }]}
        description={<span className="row row--wrap"><Status value={r.status} /><span>{r.policy.name}</span>{r.amount && <strong>{fmtMoney(r.amount, r.currency)}</strong>}</span>} />
      <div className="detail-grid">
        <div className="stack stack--lg">
          <Card title="Approval levels">
            <div className="steps">
              {r.steps.map((s) => (
                <div key={s.sequence} className={`step step--${s.status}`}>
                  <div className="row row--between"><strong>{s.sequence}. {s.name}</strong><Status value={s.status} /></div>
                  {s.decidedBy && <div className="xs muted">{s.decidedBy.fullName}{s.onBehalfOf ? ` for ${s.onBehalfOf.fullName}` : ''} · {fmtDateTime(s.decidedAt)}</div>}
                  {s.status === 'pending' && s.dueAt && <div className="xs muted">Due {fmtDateTime(s.dueAt)}</div>}
                  {s.comment && <div className="small" style={{ marginTop: 4 }}>“{s.comment}”</div>}
                </div>
              ))}
            </div>
          </Card>
          {r.description && <Card title="Details"><p style={{ whiteSpace: 'pre-wrap' }}>{r.description}</p></Card>}
          <Card title="History">
            <ul className="timeline">
              {r.history.map((h, i) => (
                <li key={i} className={h.kind === 'approved' ? 'ok' : h.kind === 'rejected' ? 'bad' : ''}>
                  <strong>{h.author?.fullName ?? 'System'}</strong> <span className="muted">{h.kind}</span> · <span className="xs muted">{fmtDateTime(h.at)}</span>
                  {h.body && <div className="small">{h.body}</div>}
                </li>
              ))}
            </ul>
          </Card>
        </div>
        <div className="stack stack--lg">
          <Card title="Request">
            <dl className="kv" style={{ gridTemplateColumns: '110px minmax(0,1fr)' }}>
              <dt>Reference</dt><dd className="mono">{r.reference}</dd>
              <dt>Requested by</dt><dd>{r.requestedBy.fullName}</dd>
              <dt>Location</dt><dd>{r.orgUnit ?? '—'}</dd>
              <dt>Department</dt><dd>{r.department ?? '—'}</dd>
              <dt>Raised</dt><dd>{fmtDateTime(r.createdAt)}</dd>
              {r.decidedAt && <><dt>Decided</dt><dd>{fmtDateTime(r.decidedAt)}</dd></>}
            </dl>
          </Card>
          {(r.canDecide || r.canCancel || r.status === 'pending' || r.status === 'changes_requested') && (
            <Card title={r.canDecide ? 'Your decision' : 'Comment'}>
              <div className="stack">
                {r.decidingOnBehalfOf && <Alert tone="info">You’re deciding on behalf of {r.decidingOnBehalfOf.fullName}.</Alert>}
                {act.error && <Alert tone="error">{apiMessage(act.error)}</Alert>}
                <TextArea label={r.canDecide ? 'Comment (required to reject)' : 'Comment'} value={comment} onChange={(e) => setComment(e.target.value)} maxLength={2000} />
                {r.status === 'changes_requested' && <Alert tone="warning">Sent back for changes. {r.canResubmit ? 'Update and resubmit when ready.' : 'Waiting for the requester.'}</Alert>}
                {r.canResubmit && (
                  <div className="stack" style={{ gap: 8 }}>
                    {r.amount && <label className="field"><span className="field__label">Amount (optional change)</span>
                      <input className="field__input" type="number" min="1" value={amount} placeholder={r.amount} onChange={(e) => setAmount(e.target.value)} /></label>}
                    <Button loading={act.isPending && act.variables === 'resubmit'} onClick={() => act.mutate('resubmit')}>Resubmit</Button>
                  </div>
                )}
                {r.canDecide && (
                  <div className="row">
                    <Button className="grow" loading={act.isPending && act.variables === 'approve'} disabled={act.isPending} onClick={() => act.mutate('approve')}>Approve</Button>
                    <Button className="grow" variant="danger" loading={act.isPending && act.variables === 'reject'} disabled={act.isPending || !comment.trim()} onClick={() => act.mutate('reject')}>Reject</Button>
                  </div>
                )}
                {r.canRequestChanges && (
                  <Button variant="outline" size="sm" disabled={act.isPending || !comment.trim()} onClick={() => act.mutate('request_changes')}>Request changes (uses your comment)</Button>
                )}
                <div className="row">
                  {r.status === 'pending' && <Button variant="outline" size="sm" disabled={!comment.trim() || act.isPending} onClick={() => act.mutate('comment')}>Add comment</Button>}
                  {r.canCancel && <Button variant="ghost" size="sm" disabled={act.isPending} onClick={() => act.mutate('cancel')}>Withdraw request</Button>}
                </div>
                {!r.canDecide && r.status === 'pending' && <p className="xs muted">You can follow this request but it’s not waiting on your decision.</p>}
              </div>
            </Card>
          )}
        </div>
      </div>
    </>
  );
}
