import { useState } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { useMutation, useQuery } from '@tanstack/react-query';
import { Button, TextArea, TextField, useToast } from '@click/ui';
import { api, apiMessage, fieldErrors } from '../lib/api';
import { fmtMoney } from '../lib/format';
import { useOS } from '../session/OSSession';
import { Alert, Card, Empty, LoadingRows, PageHeader, QueryError } from '../components/ui';

export function NewApprovalPage() {
  const ctx = useOS();
  const [params] = useSearchParams();
  const navigate = useNavigate();
  const toast = useToast();
  const policies = useQuery({ queryKey: ['os', 'policies'], queryFn: api.approvals.policies });
  const [key, setKey] = useState(params.get('policy') ?? '');
  const [title, setTitle] = useState('');
  const [amount, setAmount] = useState('');
  const [description, setDescription] = useState('');
  const policy = policies.data?.results.find((p) => p.key === key) ?? (policies.data?.results.length === 1 ? policies.data.results[0] : undefined);
  const submit = useMutation({
    mutationFn: () => api.approvals.submit({ policyKey: policy!.key, title, amount: amount || undefined, description }),
    onSuccess: (r) => { toast(`Request ${r.reference} submitted`); navigate(`/approvals/${r.id}`, { replace: true }); },
  });
  const errs = fieldErrors(submit.error);
  const levels = policy?.levels.filter((l) => !amount || Number(amount) >= Number(l.minAmount)) ?? [];

  return (
    <>
      <PageHeader title="New request" crumbs={[{ label: 'Approvals', to: '/approvals' }, { label: 'New' }]}
        description="Requests go to approvers with the right permission, scope and approval limit for your location." />
      <div style={{ maxWidth: 680 }}>
        <Card>
          {policies.isPending ? <LoadingRows /> : policies.error ? <QueryError error={policies.error} /> : !policies.data.results.length ? (
            <Empty title="No request types available" message="Your role can’t raise approval requests yet." />
          ) : (
            <form className="stack" onSubmit={(e) => { e.preventDefault(); submit.mutate(); }}>
              {submit.error && !Object.keys(errs).length && <Alert tone="error">{apiMessage(submit.error)}</Alert>}
              <div className="field"><label className="field__label" htmlFor="pol">Request type</label>
                <select id="pol" className="field__input" value={policy?.key ?? ''} onChange={(e) => setKey(e.target.value)} required>
                  <option value="" disabled>Choose…</option>
                  {policies.data.results.map((p) => <option key={p.key} value={p.key}>{p.name}</option>)}
                </select>
                {policy && <span className="field__hint">{policy.description}</span>}
              </div>
              <TextField label="Title" value={title} onChange={(e) => setTitle(e.target.value)} error={errs.title} maxLength={160} required placeholder="e.g. Client visit travel" />
              {policy?.requiresAmount !== false && (
                <TextField label={`Amount (${policy?.currency ?? ctx.organization.currency})`} type="number" min="1" step="0.01" inputMode="decimal"
                           value={amount} onChange={(e) => setAmount(e.target.value)} error={errs.amount} required={policy?.requiresAmount} />
              )}
              <TextArea label="Details" value={description} onChange={(e) => setDescription(e.target.value)} maxLength={4000} placeholder="Purpose, vendor, dates…" />
              {policy && (
                <div className="alert alert--info small">
                  <div>Approval path: {levels.length ? levels.map((l, i) => <span key={l.name}>{i > 0 && ' → '}<strong>{l.name}</strong>{Number(l.minAmount) > 0 ? ` (from ${fmtMoney(l.minAmount)})` : ''}</span>) : 'set once you enter the amount'}.
                    {ctx.orgContext.location && <> Routed for <strong>{ctx.orgContext.location.name}</strong>.</>}</div>
                </div>
              )}
              <div className="row" style={{ justifyContent: 'flex-end' }}>
                <Button variant="outline" onClick={() => navigate(-1)}>Cancel</Button>
                <Button type="submit" loading={submit.isPending} disabled={!policy || title.trim().length < 3}>Submit for approval</Button>
              </div>
            </form>
          )}
        </Card>
      </div>
    </>
  );
}
