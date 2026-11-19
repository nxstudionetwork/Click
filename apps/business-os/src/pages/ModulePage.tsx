import { Link, useParams } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { Icon, type IconName } from '@click/ui';
import { api } from '../lib/api';
import { SCOPE_LABEL } from '../lib/format';
import { Card, LoadingRows, PageHeader, QueryError, Status } from '../components/ui';

/**
 * Landing page for a business module that is registered in the OS but not built yet. It is honest about that and
 * shows what the person will be able to do there (from their real permissions), so access can be set up before the
 * module ships. When a module is built, its routes replace this page.
 */
export function ModulePage() {
  const { key = '' } = useParams();
  const q = useQuery({ queryKey: ['os', 'module', key], queryFn: () => api.module(key) });
  if (q.isPending) return <><PageHeader title="Loading…" /><Card><LoadingRows /></Card></>;
  if (q.error) return <><PageHeader title="Module" /><QueryError error={q.error} /></>;
  const m = q.data;
  const allowed = m.resources.flatMap((r) => r.actions.filter((a) => a.allowed));

  return (
    <>
      <PageHeader title={m.label} crumbs={[{ label: m.group[0]!.toUpperCase() + m.group.slice(1) }, { label: m.label }]} />
      <div className="stack stack--lg">
        <Card>
          <div className="module-hero">
            <span className="module-hero__icon"><Icon name={m.icon as IconName} /></span>
            <div className="grow stack" style={{ gap: 6 }}>
              <div className="row row--wrap"><h2>{m.label}</h2><Status value={m.status === 'foundation' ? 'info' : 'active'} tone="info" label={m.status === 'foundation' ? 'Coming in a later phase' : 'Live'} /></div>
              <p className="muted">{m.description}</p>
              <p className="small">This module is registered in Business OS: its permissions, navigation, search, approvals, notifications and audit are ready.
                Its screens arrive when the module is built. {allowed.length > 0 ? `Your role already grants ${allowed.length} of its permissions.` : ''}</p>
            </div>
          </div>
        </Card>
        <div className="grid grid--2">
          <Card title="Planned areas">
            <div className="pill-list">{m.submodules.map((s) => <span key={s} className="pill">{s}</span>)}</div>
            {m.includes.length > 0 && <p className="xs muted" style={{ marginTop: 12 }}>Brings together: {m.includes.join(' · ')}</p>}
          </Card>
          <Card title="Your access here" flush>
            <table className="table">
              <thead><tr><th>Resource</th><th>Actions you have</th></tr></thead>
              <tbody>
                {m.resources.map((r) => (
                  <tr key={r.key}>
                    <td>{r.label}{r.sensitive && <span className="xs muted"> · sensitive</span>}</td>
                    <td><div className="row row--wrap" style={{ gap: 4 }}>{r.actions.map((a) => (
                      <span key={a.action} className={`action-chip ${a.allowed ? 'on' : ''}`} title={a.allowed ? SCOPE_LABEL[a.scope] : 'Not granted'}>{a.action}</span>
                    ))}</div></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </Card>
        </div>
        {key === 'finance' && allowed.some((a) => a.action === 'create') && (
          <Card title="Available now"><p className="small">Expense claims already run on the shared approval engine. <Link to="/approvals/new?policy=finance.expense">Submit an expense →</Link></p></Card>
        )}
      </div>
    </>
  );
}
