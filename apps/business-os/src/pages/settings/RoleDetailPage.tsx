import { useEffect, useMemo, useState } from 'react';
import { Link, useNavigate, useParams } from 'react-router-dom';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Button, TextField, useToast } from '@click/ui';
import { ApiError, type OSPermissionCatalog, type OSRoleDetail } from '@click/api';
import { api, apiMessage } from '../../lib/api';
import { fmtMoney } from '../../lib/format';
import { useAccess } from '../../session/access';
import { Alert, Card, ConfirmDialog, LoadingRows, QueryError, Status, Tabs } from '../../components/ui';

type Tab = 'permissions' | 'limits' | 'home' | 'holders';

export function RoleDetailPage() {
  const { id = '' } = useParams();
  const role = useQuery({ queryKey: ['os', 'admin', 'role', id], queryFn: () => api.admin.role(id) });
  const catalog = useQuery({ queryKey: ['os', 'admin', 'catalog'], queryFn: api.admin.permissions, staleTime: Infinity });
  if (role.isPending || catalog.isPending) return <Card><LoadingRows rows={8} /></Card>;
  if (role.error || catalog.error) return <QueryError error={role.error ?? catalog.error} />;
  return <RoleEditor key={role.data.id + role.dataUpdatedAt} role={role.data} catalog={catalog.data} />;
}

function RoleEditor({ role, catalog }: { role: OSRoleDetail; catalog: OSPermissionCatalog }) {
  const qc = useQueryClient();
  const toast = useToast();
  const navigate = useNavigate();
  const access = useAccess();
  const [tab, setTab] = useState<Tab>('permissions');
  const [name, setName] = useState(role.name);
  const [description, setDescription] = useState(role.description);
  const [requiresMfa, setRequiresMfa] = useState(role.requiresMfa);
  const [grants, setGrants] = useState<Record<string, string>>(() => Object.fromEntries(role.grants.map((g) => [g.code, g.scope])));
  const [limits, setLimits] = useState<Record<string, string | null>>(() => Object.fromEntries(role.approvalLimits.map((l) => [l.approvalType, l.maxAmount])));
  const [widgets, setWidgets] = useState<string[]>(role.homeWidgets);
  const [filter, setFilter] = useState('');
  const [confirmDelete, setConfirmDelete] = useState(false);
  const editable = role.canEdit;
  const inherited = useMemo(() => new Map(role.inherited.map((g) => [g.code, g])), [role.inherited]);

  useEffect(() => { document.title = `${role.name} · Roles · Click Business OS`; }, [role.name]);
  const invalidate = () => { void qc.invalidateQueries({ queryKey: ['os', 'admin'] }); void qc.invalidateQueries({ queryKey: ['os', 'context'] }); };

  const save = useMutation({
    mutationFn: () => api.admin.updateRole(role.id, {
      name, description, requiresMfa, homeWidgets: widgets,
      grants: Object.entries(grants).map(([code, scope]) => ({ code, scope })),
      approvalLimits: Object.entries(limits).map(([approvalType, maxAmount]) => ({ approvalType, maxAmount: maxAmount === '' ? null : maxAmount })),
    }),
    onSuccess: () => { toast('Role saved'); invalidate(); },
  });
  const duplicate = useMutation({ mutationFn: () => api.admin.duplicateRole(role.id), onSuccess: (r) => { invalidate(); navigate(`/settings/roles/${r.id}`); } });
  const remove = useMutation({ mutationFn: () => api.admin.deleteRole(role.id), onSuccess: () => { invalidate(); navigate('/settings/roles'); } });

  const dirty = editable && (name !== role.name || description !== role.description || requiresMfa !== role.requiresMfa ||
    JSON.stringify(grants) !== JSON.stringify(Object.fromEntries(role.grants.map((g) => [g.code, g.scope]))) ||
    JSON.stringify(limits) !== JSON.stringify(Object.fromEntries(role.approvalLimits.map((l) => [l.approvalType, l.maxAmount]))) ||
    JSON.stringify(widgets) !== JSON.stringify(role.homeWidgets));

  const blocked = save.error instanceof ApiError ? ((save.error.details?.permissions as string[] | undefined) ?? []) : [];
  const f = filter.toLowerCase();
  const modules = catalog.modules.filter((m) => !f || m.label.toLowerCase().includes(f) || m.resources.some((r) => r.label.toLowerCase().includes(f)));

  return (
    <div className="stack stack--lg">
      <div className="crumbs"><Link to="/settings/roles">Roles</Link><span>/</span><span>{role.name}</span></div>
      <div className="row row--between row--wrap">
        <div>
          <h2 style={{ fontSize: 'var(--fs-xl)' }}>{role.name}</h2>
          <div className="row row--wrap" style={{ marginTop: 4 }}>
            {role.isSystem && <Status value="system" tone="info" label="Built-in template · read-only" />}
            <span className="small muted">{Object.keys(grants).length} permissions · {role.holderCount} holders · for {role.audience}</span>
          </div>
        </div>
        <div className="row">
          {access.can('access.role.create') && <Button variant="outline" loading={duplicate.isPending} onClick={() => duplicate.mutate()}>Duplicate</Button>}
          {role.canDelete && <Button variant="danger" onClick={() => setConfirmDelete(true)}>Delete</Button>}
          {editable && <Button loading={save.isPending} disabled={!dirty} onClick={() => save.mutate()}>Save changes</Button>}
        </div>
      </div>
      {save.error && <Alert tone="error">{apiMessage(save.error)}{blocked.length > 0 && <div className="xs mono">{blocked.join(', ')}</div>}</Alert>}
      {duplicate.error && <Alert tone="error">{apiMessage(duplicate.error)}</Alert>}
      {role.isSystem && <Alert tone="info">Built-in templates can’t be changed so everyone knows what they mean. Duplicate it to make an editable version.</Alert>}

      {editable && (
        <Card title="Details">
          <div className="grid grid--2">
            <TextField label="Name" value={name} onChange={(e) => setName(e.target.value)} />
            <TextField label="Description" value={description} onChange={(e) => setDescription(e.target.value)} maxLength={300} />
          </div>
          <label className="row small" style={{ marginTop: 12 }}><input type="checkbox" checked={requiresMfa} onChange={(e) => setRequiresMfa(e.target.checked)} />
            Holders must have two-step verification for this role to take effect</label>
        </Card>
      )}

      <Tabs value={tab} onChange={setTab} items={[
        { value: 'permissions', label: 'Permissions', count: Object.keys(grants).length }, { value: 'limits', label: 'Approval authority' },
        { value: 'home', label: 'Home widgets' }, { value: 'holders', label: 'Holders', count: role.holders.length },
      ]} />

      {tab === 'permissions' && (
        <Card flush>
          <div className="toolbar">
            <div className="search-input"><input value={filter} onChange={(e) => setFilter(e.target.value)} placeholder="Filter modules" aria-label="Filter modules" /></div>
            <span className="xs muted">Choose a scope for each action. “—” means not granted. You can only grant what you hold yourself.</span>
          </div>
          <div className="table-wrap" style={{ maxHeight: '65vh', overflowY: 'auto' }}>
            <table className="matrix">
              <thead><tr><th style={{ minWidth: 200 }}>Resource</th><th>Actions and scope</th></tr></thead>
              <tbody>
                {modules.map((m) => (
                  <ModuleRows key={m.key} module={m} grants={grants} inherited={inherited} scopes={catalog.scopes} editable={editable}
                    onChange={(code, scope) => setGrants((g) => { const n = { ...g }; if (scope) n[code] = scope; else delete n[code]; return n; })} />
                ))}
              </tbody>
            </table>
          </div>
        </Card>
      )}

      {tab === 'limits' && (
        <Card title="Approval authority" flush>
          <table className="table">
            <thead><tr><th>Approval type</th><th>Can approve</th><th>Up to (₹)</th></tr></thead>
            <tbody>{catalog.approvalTypes.map((t) => {
              const has = t.key in limits;
              return (
                <tr key={t.key}>
                  <td>{t.label}</td>
                  <td><input type="checkbox" aria-label={`${t.label} authority`} disabled={!editable} checked={has}
                    onChange={(e) => setLimits((l) => { const n = { ...l }; if (e.target.checked) n[t.key] = '0'; else delete n[t.key]; return n; })} /></td>
                  <td>{has ? (editable ? (
                    <div className="row"><input className="field__input" style={{ maxWidth: 160 }} type="number" min="0" placeholder="No limit" value={limits[t.key] ?? ''}
                      onChange={(e) => setLimits((l) => ({ ...l, [t.key]: e.target.value === '' ? null : e.target.value }))} aria-label={`${t.label} limit`} />
                      <span className="xs muted">{limits[t.key] === null ? 'No upper limit' : fmtMoney(limits[t.key])}</span></div>
                  ) : (limits[t.key] === null ? 'No upper limit' : fmtMoney(limits[t.key]))) : <span className="muted">—</span>}</td>
                </tr>
              );
            })}</tbody>
          </table>
          <div className="note">Approval authority works together with the approver permission and its scope: an approver needs all three.</div>
        </Card>
      )}

      {tab === 'home' && (
        <Card title="Home widgets this role brings">
          <p className="small muted" style={{ marginBottom: 12 }}>People see a widget only if they also hold its permission. Order matters: earlier widgets appear first.</p>
          <div className="stack" style={{ gap: 6 }}>
            {catalog.widgets.map((w) => (
              <label key={w.key} className="row small">
                <input type="checkbox" disabled={!editable} checked={widgets.includes(w.key)} onChange={(e) => setWidgets((ws) => (e.target.checked ? [...ws, w.key] : ws.filter((x) => x !== w.key)))} />
                {w.title}{w.permission && <span className="xs muted mono">needs {w.permission}</span>}
              </label>
            ))}
          </div>
        </Card>
      )}

      {tab === 'holders' && (
        <Card flush>
          {!role.holders.length ? <p className="muted small" style={{ padding: 16 }}>Nobody holds this role.</p> : (
            <table className="table"><thead><tr><th>Person</th><th>Applies at</th></tr></thead>
              <tbody>{role.holders.map((h) => <tr key={h.userId}><td>{h.fullName}</td><td className="small muted">{[h.orgUnit, h.department].filter(Boolean).join(' · ') || 'Own location'}</td></tr>)}</tbody></table>
          )}
        </Card>
      )}

      {confirmDelete && <ConfirmDialog title="Delete this role?" message="This can’t be undone." confirmLabel="Delete role" danger busy={remove.isPending}
        onConfirm={() => remove.mutate()} onClose={() => setConfirmDelete(false)}>{remove.error && <Alert tone="error">{apiMessage(remove.error)}</Alert>}</ConfirmDialog>}
    </div>
  );
}

function ModuleRows({ module: m, grants, inherited, scopes, editable, onChange }: {
  module: OSPermissionCatalog['modules'][number]; grants: Record<string, string>; inherited: Map<string, { from: string; scope: string }>;
  scopes: { key: string; label: string }[]; editable: boolean; onChange: (code: string, scope: string) => void;
}) {
  const granted = m.resources.flatMap((r) => r.actions).filter((a) => grants[a.code]).length;
  return (
    <>
      <tr className="module-row"><td colSpan={2}>{m.label} <span className="xs muted">{granted ? `· ${granted} granted` : ''}{m.status !== 'live' ? ' · module not built yet' : ''}</span></td></tr>
      {m.resources.map((r) => (
        <tr key={r.key}>
          <td>{r.label}{r.sensitive && <div className="xs" style={{ color: 'var(--c-warning)' }}>Sensitive · needs 2-step</div>}</td>
          <td><div className="row row--wrap" style={{ gap: 6 }}>
            {r.actions.map((a) => {
              const inh = inherited.get(a.code);
              return (
                <label key={a.code} className="row" style={{ gap: 4 }} title={inh ? `Inherited from ${inh.from} (${inh.scope})` : a.code}>
                  <span className="xs">{a.action}</span>
                  <select className={grants[a.code] ? 'on' : ''} value={grants[a.code] ?? ''} disabled={!editable} onChange={(e) => onChange(a.code, e.target.value)} aria-label={`${r.label} ${a.action} scope`}>
                    <option value="">{inh ? `↑ ${inh.scope}` : '—'}</option>
                    {scopes.map((s) => <option key={s.key} value={s.key}>{s.label}</option>)}
                  </select>
                </label>
              );
            })}
          </div></td>
        </tr>
      ))}
    </>
  );
}
