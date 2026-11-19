import { useEffect, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { Button, Icon } from '@click/ui';
import type { OSAuditEvent } from '@click/api';
import { api, http } from '../../lib/api';
import { fmtDateTime, humanize } from '../../lib/format';
import { Card, Drawer, Empty, LoadingRows, Pager, QueryError, Status } from '../../components/ui';

export function AuditPage() {
  const [category, setCategory] = useState('');
  const [outcome, setOutcome] = useState('');
  const [actorText, setActorText] = useState('');
  const [actor, setActor] = useState('');
  const [from, setFrom] = useState('');
  const [to, setTo] = useState('');
  const [page, setPage] = useState(1);
  const [open, setOpen] = useState<OSAuditEvent | null>(null);
  const [exporting, setExporting] = useState(false);
  useEffect(() => { const t = setTimeout(() => { setActor(actorText); setPage(1); }, 300); return () => clearTimeout(t); }, [actorText]);
  const filters = { category: category || undefined, outcome: outcome || undefined, actor: actor || undefined, from: from || undefined, to: to || undefined };
  const q = useQuery({ queryKey: ['os', 'audit', filters, page], queryFn: () => api.audit({ ...filters, page }) });

  const exportCsv = async () => {
    setExporting(true);
    try {
      const qs = new URLSearchParams(Object.entries({ ...filters, export: 'csv' }).filter(([, v]) => v) as [string, string][]);
      const blob = await http.blob!(`/os/audit?${qs}`);
      const a = document.createElement('a');
      a.href = URL.createObjectURL(blob);
      a.download = 'click-audit.csv';
      a.click();
      URL.revokeObjectURL(a.href);
    } finally { setExporting(false); }
  };

  return (
    <div className="stack">
      <div className="row row--between row--wrap">
        <div><h2 style={{ fontSize: 'var(--fs-xl)' }}>Audit trail</h2><p className="muted small">Append-only record of sign-ins, security, access, approval, configuration and data changes. Exports are audited too.</p></div>
        {q.data?.canExport && <Button variant="outline" loading={exporting} onClick={() => void exportCsv()}><Icon name="download" size={16} />Export CSV</Button>}
      </div>
      <Card flush>
        <div className="toolbar">
          <div className="search-input"><Icon name="user" size={15} /><input value={actorText} onChange={(e) => setActorText(e.target.value)} placeholder="Who" aria-label="Filter by person" /></div>
          <select className="field__input" aria-label="Category" value={category} onChange={(e) => { setCategory(e.target.value); setPage(1); }}>
            <option value="">All categories</option>{q.data?.categories.map((c) => <option key={c.key} value={c.key}>{c.label}</option>)}
          </select>
          <select className="field__input" aria-label="Outcome" value={outcome} onChange={(e) => { setOutcome(e.target.value); setPage(1); }}>
            <option value="">Any outcome</option><option value="success">Success</option><option value="failure">Failure</option><option value="denied">Denied</option>
          </select>
          <input className="field__input" type="date" aria-label="From" value={from} onChange={(e) => { setFrom(e.target.value); setPage(1); }} />
          <input className="field__input" type="date" aria-label="To" value={to} onChange={(e) => { setTo(e.target.value); setPage(1); }} />
        </div>
        {q.isPending ? <LoadingRows rows={8} /> : q.error ? <QueryError error={q.error} /> : !q.data.results.length ? <Empty icon="history" title="No events match" /> : (
          <>
            <div className="table-wrap"><table className="table">
              <thead><tr><th>When</th><th>Who</th><th>Action</th><th>Resource</th><th>Result</th><th>IP</th></tr></thead>
              <tbody>{q.data.results.map((e) => (
                <tr key={e.id} className="clickable" onClick={() => setOpen(e)}>
                  <td className="small muted" style={{ whiteSpace: 'nowrap' }}>{fmtDateTime(e.at)}</td>
                  <td className="small">{e.actor}{e.actorKind !== 'user' && <span className="xs muted"> · {e.actorKind}</span>}</td>
                  <td><span className="mono xs">{e.action}</span>{e.sensitive && <> <Status value="sensitive" tone="warning" label="Sensitive" /></>}</td>
                  <td className="small ellipsis" style={{ maxWidth: 240 }}>{e.resourceLabel || '—'}</td>
                  <td><Status value={e.outcome} /></td>
                  <td className="mono xs muted">{e.ip ?? '—'}</td>
                </tr>
              ))}</tbody>
            </table></div>
            <Pager page={q.data.page} hasNext={q.data.hasNext} count={q.data.count} onPage={setPage} />
          </>
        )}
      </Card>
      {open && (
        <Drawer title={humanize(open.action)} onClose={() => setOpen(null)}>
          <dl className="kv" style={{ gridTemplateColumns: '110px minmax(0,1fr)' }}>
            <dt>When</dt><dd>{fmtDateTime(open.at)}</dd>
            <dt>Who</dt><dd>{open.actor} ({open.actorKind})</dd>
            <dt>Action</dt><dd className="mono">{open.action}</dd>
            <dt>Category</dt><dd>{open.category}</dd>
            <dt>Resource</dt><dd>{open.resourceLabel || '—'}<div className="xs muted mono">{open.resourceType} {open.resourceId}</div></dd>
            <dt>Result</dt><dd><Status value={open.outcome} /></dd>
            <dt>IP</dt><dd className="mono">{open.ip ?? '—'}</dd>
          </dl>
          {open.oldValue && <div><h3>Before</h3><pre className="diff">{JSON.stringify(open.oldValue, null, 2)}</pre></div>}
          {open.newValue && <div><h3>After</h3><pre className="diff">{JSON.stringify(open.newValue, null, 2)}</pre></div>}
          {Object.keys(open.metadata).length > 0 && <div><h3>Context</h3><pre className="diff">{JSON.stringify(open.metadata, null, 2)}</pre></div>}
        </Drawer>
      )}
    </div>
  );
}
