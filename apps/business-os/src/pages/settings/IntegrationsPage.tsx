import { useQuery } from '@tanstack/react-query';
import { api } from '../../lib/api';
import { Card, LoadingRows, QueryError, Status } from '../../components/ui';

export function IntegrationsPage() {
  const q = useQuery({ queryKey: ['os', 'system', 'integrations'], queryFn: api.system.integrations });
  return (
    <div className="stack">
      <div><h2 style={{ fontSize: 'var(--fs-xl)' }}>Integrations</h2><p className="muted small">Connectors Business OS and the Click platform rely on.</p></div>
      {q.isPending ? <Card><LoadingRows /></Card> : q.error ? <QueryError error={q.error} /> : (
        <>
          <Card flush>
            <table className="table"><thead><tr><th>Integration</th><th>Used by</th><th>Provider</th><th>Status</th></tr></thead>
              <tbody>{q.data.results.map((i) => (
                <tr key={i.key}><td><strong>{i.label}</strong></td><td className="small muted">{i.area}</td><td className="small mono">{i.provider ?? '—'}</td>
                  <td><Status value={i.status} label={i.status === 'connected' ? 'Connected' : 'Not configured'} /></td></tr>
              ))}</tbody></table>
          </Card>
          <p className="xs muted">{q.data.note}</p>
        </>
      )}
    </div>
  );
}
