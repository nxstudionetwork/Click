/* eslint-disable @typescript-eslint/no-explicit-any */
/** Module 3 — Identity & Access workspace. Every screen reads from /os/access/*, where the central engine decides. */
import { useState } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { Button, Icon } from '@click/ui';
import { access, api } from '../../lib/api';
import { fmtDate, fmtDateTime, humanize, relative } from '../../lib/format';
import { DataTable, FormDialog } from '../../components/forms';
import { Kpis, ModuleShell, ModuleTitle, useAction } from '../../components/ModuleShell';
import { Alert, Card, Empty, LoadingRows, QueryError, Status, Tabs } from '../../components/ui';

const K = ['os', 'access'];
const T = (title: string, desc?: string, actions?: React.ReactNode) => <ModuleTitle module="Identity & Access" root="/access" title={title} desc={desc} actions={actions} />;

export function AccessLayout() {
  return <ModuleShell api={access} label="Identity & Access" root="/access" icon="key" />;
}

function useQ<T = any>(path: string, query: Record<string, any> = {}, enabled = true) {
  return useQuery<T>({ queryKey: [...K, path, query], queryFn: () => access.get<T>(path, query), enabled });
}

function Loading({ q, children }: { q: any; children: () => React.ReactNode }) {
  if (q.isPending) return <Card><LoadingRows /></Card>;
  if (q.error) return <QueryError error={q.error} />;
  return <>{children()}</>;
}

/** Account picker over the Users directory (server-scoped). */
function AccountPicker({ value, onChange, label = 'Person' }: { value: string; onChange: (id: string) => void; label?: string }) {
  const [q, setQ] = useState('');
  const users = useQuery({ queryKey: [...K, 'picker', q], queryFn: () => api.admin.users({ q: q || undefined, page_size: 20 }) });
  return (
    <div className="row row--wrap">
      <div className="search-input"><Icon name="search" size={16} /><input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Name, email or EMP-…" aria-label={`Search ${label}`} /></div>
      <select className="field__input" aria-label={label} value={value} onChange={(e) => onChange(e.target.value)}>
        <option value="">Choose {label.toLowerCase()}…</option>
        {(users.data?.results ?? []).map((u) => <option key={u.id} value={u.id}>{u.fullName} · {u.email}</option>)}
      </select>
    </div>
  );
}

// ---------------------------------------------------------------------------------------------------------------------
export function AccessHome() {
  const q = useQ('home');
  return (
    <>
      {T('Identity & Access', 'Who can do what, where — and whether they still should.')}
      <Loading q={q}>{() => q.data.mode === 'self' ? <MySummary /> : (
        <div className="stack stack--lg">
          <Card title="Identities"><Kpis items={[
            { label: 'Total identities', value: q.data.identity.total, to: '/settings/users' }, { label: 'Active', value: q.data.identity.active },
            { label: 'Invited / pending', value: q.data.identity.invited }, { label: 'Suspended', value: q.data.identity.suspended, tone: q.data.identity.suspended ? 'alert' : undefined },
            { label: 'Expired / deactivated', value: q.data.identity.expired }, { label: 'External identities', value: q.data.identity.external },
            { label: 'Service accounts', value: q.data.identity.serviceAccounts }]} /></Card>
          <Card title="Access"><Kpis items={[
            { label: 'Roles', value: q.data.access.roles, hint: `${q.data.access.customRoles} custom`, to: '/settings/roles' },
            { label: 'Privileged users', value: q.data.access.privilegedUsers, to: '/access/privileged' },
            { label: 'Temporary access', value: q.data.access.temporary, hint: `${q.data.access.expiring7d} ending in 7 days` },
            { label: 'Pending access requests', value: q.data.access.pendingRequests, to: '/access/requests' },
            { label: 'Access packages', value: q.data.access.packages, to: '/access/packages' }]} /></Card>
          <Card title="Security"><Kpis items={[
            { label: 'Failed sign-ins (24h)', value: q.data.security.failedLogins24h ?? '—', tone: q.data.security.failedLogins24h > 10 ? 'alert' : undefined, to: '/access/security' },
            { label: 'Locked accounts', value: q.data.security.locked }, { label: 'Two-step coverage', value: `${q.data.security.mfaCoveragePct}%` },
            { label: 'Admins', value: q.data.security.admins },
            { label: 'Privileged without two-step', value: q.data.security.privilegedWithoutMfa, tone: q.data.security.privilegedWithoutMfa ? 'alert' : 'good' },
            { label: 'Emergency access active', value: q.data.security.emergencyActive, tone: q.data.security.emergencyActive ? 'alert' : undefined, to: '/access/emergency' },
            { label: 'Emergency use awaiting review', value: q.data.security.emergencyUnreviewed, to: '/access/emergency' }]} /></Card>
          <Card title="Governance"><Kpis items={[
            { label: 'Open access reviews', value: q.data.governance.reviewsOpen, to: '/access/reviews' },
            { label: 'Waiting on you', value: q.data.governance.reviewItemsMine, to: '/access/reviews' },
            { label: 'SoD conflicts', value: q.data.governance.sodViolations ?? '—', tone: q.data.governance.sodViolations ? 'alert' : undefined, to: '/access/sod' },
            { label: 'Orphaned accounts', value: q.data.governance.orphaned ?? '—', to: '/access/hygiene' },
            { label: 'Unused roles', value: q.data.governance.unusedRoles ?? '—', to: '/access/hygiene' }]} /></Card>
          <Card title="Quick actions"><div className="quick">
            <Link to="/settings/users?new=1" className="quick__btn">Create identity</Link><Link to="/settings/roles" className="quick__btn">Create role</Link>
            <Link to="/access/requests?new=1" className="quick__btn">Request access</Link><Link to="/access/reviews" className="quick__btn">Review access</Link>
            <Link to="/access/simulator" className="quick__btn">Run permission check</Link><Link to="/access/security" className="quick__btn">Security events</Link></div></Card>
        </div>)}</Loading>
    </>
  );
}

function MySummary() {
  return <Alert tone="info">This is where you see your own access and request more. <Link to="/access/me">Open My access</Link> · <Link to="/access/requests?new=1">Request access</Link></Alert>;
}

// ---------------------------------------------------------------------------------------------------------------------
function EffectiveView({ d }: { d: any }) {
  const [module, setModule] = useState('');
  const mods = [...new Set(d.permissions.map((p: any) => p.module))] as string[];
  return (
    <div className="stack stack--lg">
      <Card>
        <div className="row row--wrap" style={{ gap: 16 }}>
          <div className="grow"><h2 style={{ fontSize: 'var(--fs-lg)' }}>{d.account.name}</h2>
            <div className="small muted">{d.account.email} · {humanize(d.account.identityType)} · {humanize(d.account.kind)} account</div>
            <div className="row" style={{ marginTop: 6 }}><Status value={d.account.status} />{d.account.mfa ? <Status value="active" label="Two-step on" /> : <Status value="pending" label="No two-step" />}
              {d.account.expiresAt && <span className="chip">Access ends {fmtDate(d.account.expiresAt)}</span>}</div></div>
          <div className="stat" style={{ minWidth: 180 }}><span className="stat__label">Access risk (internal)</span>
            <strong className={`stat__value ${d.risk.level === 'high' ? 'stat__value--alert' : ''}`}>{d.risk.score}/100</strong>
            <span className="stat__hint">{d.risk.factors.join(' · ') || 'Nothing notable'}</span></div>
        </div>
      </Card>
      <Card title="Roles" flush><DataTable rows={d.assignments} empty="No roles" columns={[
        { key: 'r', label: 'Role', render: (a: any) => <><strong>{a.role.name}</strong>{a.inherits.length > 0 && <div className="xs muted">inherits {a.inherits.join(' → ')}</div>}</> },
        { key: 'a', label: 'Applies at', render: (a: any) => a.anchor },
        { key: 'v', label: 'Validity', render: (a: any) => <span className="small">{a.live ? (a.validUntil ? `until ${fmtDateTime(a.validUntil)}` : 'Permanent') : 'Not active now'}{a.emergency && <span className="flag flag--overdue" style={{ marginLeft: 6 }}>emergency</span>}</span> },
        { key: 'g', label: 'Granted by', render: (a: any) => <span className="small">{a.grantedBy ?? '—'}<div className="xs muted">{a.note}</div></span> }]} />
        {d.implicitRoles.map((r: any) => <p key={r.role.key} className="small" style={{ padding: '8px 16px' }}><strong>{r.role.name}</strong> — automatic: {r.why}</p>)}</Card>
      <div className="grid grid--2">
        <Card title="Approval authority" flush><DataTable rows={d.approvalAuthority.map((x: any) => ({ ...x, id: x.type }))} empty="No approval authority" columns={[
          { key: 't', label: 'Type', render: (x: any) => x.label }, { key: 'l', label: 'Limit', render: (x: any) => x.limit ?? 'No upper limit' }]} /></Card>
        <Card title="Delegations to this person" flush><DataTable rows={d.delegations.map((x: any, i: number) => ({ ...x, id: String(i) }))} empty="None active" columns={[
          { key: 'f', label: 'From', render: (x: any) => x.from }, { key: 'p', label: 'For', render: (x: any) => x.policy }, { key: 'u', label: 'Until', render: (x: any) => fmtDateTime(x.until) }]} /></Card>
      </div>
      {d.conflicts.length > 0 && <Alert tone="warning"><strong>Segregation of duties:</strong> {d.conflicts.map((c: any) => `${c.name} (${c.severity}${c.exception ? ', exception approved' : ''})`).join('; ')}</Alert>}
      {d.mfaBlocked.length > 0 && <Alert tone="info">{d.mfaBlocked.length} granted permissions are inactive until two-step verification is on.</Alert>}
      <Card title={`Effective permissions (${d.permissions.length})`} flush actions={
        <select className="field__input" aria-label="Module" value={module} onChange={(e) => setModule(e.target.value)}><option value="">All modules</option>{mods.map((m) => <option key={m} value={m}>{humanize(m)}</option>)}</select>}>
        <DataTable rows={d.permissions.filter((p: any) => !module || p.module === module).map((p: any) => ({ ...p, id: p.code }))} columns={[
          { key: 'c', label: 'Permission', render: (p: any) => <>{p.label}{p.sensitive && <span className="flag flag--high_value" style={{ marginLeft: 6 }}>sensitive</span>}<div className="xs muted mono">{p.code}</div></> },
          { key: 's', label: 'Scope', render: (p: any) => humanize(p.scope) }, { key: 'r', label: 'From', render: (p: any) => <span className="xs">{p.sources.join(', ')}</span> }]} /></Card>
    </div>
  );
}

export function MyAccess() {
  const q = useQ('me');
  return <>{T('My access', 'What you can do in Business OS, where, and why.', <Link to="/access/requests?new=1" className="btn btn--primary" style={{ textDecoration: 'none' }}>Request access</Link>)}
    <Loading q={q}>{() => <EffectiveView d={q.data} />}</Loading></>;
}

export function EffectiveAccess() {
  const [params, setParams] = useSearchParams();
  const id = params.get('account') ?? '';
  const q = useQ(`effective/${id}`, {}, !!id);
  return <>{T('Effective access', 'Everything a person can actually do — direct, inherited, automatic, temporary and delegated.')}
    <Card><AccountPicker value={id} onChange={(v) => setParams(v ? { account: v } : {})} /></Card><div style={{ height: 16 }} />
    {id ? <Loading q={q}>{() => <EffectiveView d={q.data} />}</Loading> : <Empty icon="key" title="Choose a person" />}</>;
}

// ---------------------------------------------------------------------------------------------------------------------
function PermissionSelect({ value, onChange }: { value: string; onChange: (v: string) => void }) {
  const cat = useQuery({ queryKey: ['os', 'permissions'], queryFn: api.admin.permissions, staleTime: 600_000 });
  return (
    <select className="field__input" aria-label="Permission" value={value} onChange={(e) => onChange(e.target.value)}>
      <option value="">Choose a permission…</option>
      {cat.data?.modules.map((m) => <optgroup key={m.key} label={m.label}>{m.resources.flatMap((r) => r.actions.map((a) =>
        <option key={a.code} value={a.code}>{m.label} → {r.label} → {humanize(a.action)}</option>))}</optgroup>)}
    </select>
  );
}

export function Simulator() {
  const [v, setV] = useState({ account: '', code: '', type: '', amount: '' });
  const [res, setRes] = useState<any>(null);
  const run = useAction((b: any) => access.post('simulate', b).then(setRes), [], 'Checked');
  const types = useQuery({ queryKey: ['os', 'permissions'], queryFn: api.admin.permissions, staleTime: 600_000 });
  return <>{T('Permission simulator', 'Ask whether a person could perform an action — and see exactly why or why not.')}
    <Card><div className="stack">
      <AccountPicker value={v.account} onChange={(a) => setV({ ...v, account: a })} />
      <PermissionSelect value={v.code} onChange={(c) => setV({ ...v, code: c })} />
      <div className="row row--wrap">
        <select className="field__input" aria-label="Approval type" value={v.type} onChange={(e) => setV({ ...v, type: e.target.value })}>
          <option value="">No approval limit check</option>{types.data?.approvalTypes.map((t) => <option key={t.key} value={t.key}>{t.label}</option>)}</select>
        <input className="field__input" type="number" placeholder="Amount (₹)" aria-label="Amount" value={v.amount} onChange={(e) => setV({ ...v, amount: e.target.value })} />
        <Button disabled={!v.account || !v.code} loading={run.isPending} onClick={() => run.mutate({ accountId: v.account, code: v.code, approvalType: v.type, amount: v.amount || null })}>Check</Button>
      </div>
      {res && <Alert tone={res.allowed ? 'success' : 'error'}><strong>{res.allowed ? 'ALLOWED' : 'DENIED'}</strong><ul style={{ margin: '4px 0 0 18px' }}>{res.reasons.map((r: string) => <li key={r}>{r}</li>)}</ul></Alert>}
    </div></Card></>;
}

export function WhoHas() {
  const [params, setParams] = useSearchParams();
  const code = params.get('code') ?? '';
  const q = useQ('who-has', { code }, !!code);
  return <>{T('Who has access?', 'Everyone who can use a permission, through which role, at what scope.')}
    <Card><PermissionSelect value={code} onChange={(c) => setParams(c ? { code: c } : {})} /></Card><div style={{ height: 16 }} />
    {code ? <Loading q={q}>{() => <Card flush><DataTable rows={q.data.results.map((r: any) => ({ ...r, id: r.userId + r.role }))} empty="Nobody holds this permission" columns={[
      { key: 'n', label: 'Person', render: (r: any) => <Link to={`/access/effective?account=${r.accountId}`}>{r.name}</Link> },
      { key: 'r', label: 'Role', render: (r: any) => <>{r.role}{r.via && <div className="xs muted">inherited from {r.via}</div>}</> },
      { key: 's', label: 'Scope', render: (r: any) => `${humanize(r.effectiveScope)} · ${r.anchor}` },
      { key: 'v', label: 'Until', render: (r: any) => (r.validUntil ? fmtDate(r.validUntil) : 'Permanent') },
      { key: 'g', label: 'Granted by', render: (r: any) => r.grantedBy ?? '—' },
      { key: 'm', label: '', render: (r: any) => r.mfaBlocked && <span className="flag">needs two-step</span> }]} /></Card>}</Loading> : <Empty icon="key" title="Choose a permission" />}</>;
}

export function Compare() {
  const roles = useQuery({ queryKey: ['os', 'roles'], queryFn: api.admin.roles });
  const [sel, setSel] = useState<string[]>([]);
  const [tab, setTab] = useState<'compare' | 'matrix'>('compare');
  const [module, setModule] = useState('finance');
  const [onlyDiff, setOnlyDiff] = useState(true);
  const cmp = useQ('compare', { roles: sel.join(',') }, sel.length >= 2 && tab === 'compare');
  const mx = useQ('matrix', { module }, tab === 'matrix');
  return <>{T('Role comparison & matrix', 'See how roles differ, and which role holds what in each module.')}
    <Tabs value={tab} onChange={setTab} items={[{ value: 'compare', label: 'Compare roles' }, { value: 'matrix', label: 'Access matrix' }]} />
    {tab === 'compare' ? <>
      <Card><div className="pill-list">{roles.data?.results.map((r) => <label key={r.id} className={`pill ${sel.includes(r.id) ? 'pill--on' : ''}`}>
        <input type="checkbox" className="sr-only" checked={sel.includes(r.id)} onChange={(e) => setSel(e.target.checked ? [...sel, r.id] : sel.filter((x) => x !== r.id))} />{r.name}</label>)}</div>
        <label className="row small" style={{ marginTop: 8 }}><input type="checkbox" checked={onlyDiff} onChange={(e) => setOnlyDiff(e.target.checked)} />Only differences</label></Card>
      <div style={{ height: 16 }} />
      {sel.length < 2 ? <Empty title="Choose two or more roles" /> : <Loading q={cmp}>{() => <Card flush><div className="table-wrap"><table className="table">
        <thead><tr><th>Permission</th>{cmp.data.roles.map((r: any) => <th key={r.id}>{r.name} <span className="xs muted">v{r.version}</span></th>)}</tr></thead>
        <tbody>{cmp.data.rows.filter((r: any) => !onlyDiff || r.differs).map((r: any) => <tr key={r.code}><td className="mono xs">{r.code}</td>
          {r.values.map((v: any, i: number) => <td key={i} className="small" style={{ background: r.differs ? 'var(--c-surface-2)' : undefined }}>{v ? humanize(v) : '—'}</td>)}</tr>)}
          {cmp.data.limits.map((l: any) => <tr key={l.type}><td className="small"><strong>Approval limit · {humanize(l.type)}</strong></td>{l.values.map((v: any, i: number) => <td key={i} className="small">{v ?? '—'}</td>)}</tr>)}</tbody>
      </table></div></Card>}</Loading>}
    </> : <Loading q={mx}>{() => <Card flush actions={<select className="field__input" aria-label="Module" value={module} onChange={(e) => setModule(e.target.value)}>
      {mx.data.modules.map((m: any) => <option key={m.key} value={m.key}>{m.label}</option>)}</select>}>
      {mx.data.rows.map((row: any) => <div key={row.resource} style={{ padding: '8px 16px', borderTop: '1px solid var(--c-line)' }}>
        <strong className="small">{row.resource}</strong>{row.sensitive && <span className="flag" style={{ marginLeft: 6 }}>sensitive</span>}
        <div className="table-wrap"><table className="table"><thead><tr><th>Role</th>{Object.keys(row.actions).map((a) => <th key={a}>{humanize(a)}</th>)}</tr></thead>
          <tbody>{mx.data.roles.filter((r: any) => Object.values(row.actions).some((m: any) => m[r.id])).map((r: any) => <tr key={r.id}><td className="small">{r.name}</td>
            {Object.values(row.actions).map((m: any, i) => <td key={i} className="xs">{m[r.id] ? `✓ ${humanize(m[r.id])}` : '—'}</td>)}</tr>)}</tbody></table></div></div>)}
    </Card>}</Loading>}</>;
}

// ---------------------------------------------------------------------------------------------------------------------
export function Packages() {
  const q = useQ('packages');
  const roles = useQuery({ queryKey: ['os', 'roles'], queryFn: api.admin.roles });
  const [create, setCreate] = useState(false);
  const [assign, setAssign] = useState<any>(null);
  const [acct, setAcct] = useState('');
  const doAssign = useAction((b: any) => access.post(`packages/${assign.id}/assign`, b), [[...K]], 'Package assigned');
  return <>{T('Access packages', 'Reusable bundles of roles: assign or request access in one step.', <Button onClick={() => setCreate(true)}><Icon name="plus" size={16} />New package</Button>)}
    <Loading q={q}>{() => <Card flush><DataTable rows={q.data.results} empty="No packages yet" columns={[
      { key: 'n', label: 'Package', render: (p: any) => <><strong>{p.name}</strong><div className="xs muted">{p.description}</div></> },
      { key: 'r', label: 'Roles', render: (p: any) => <span className="small">{p.roles.map((r: any) => r.name).join(', ')}</span> },
      { key: 'x', label: 'Duration', render: (p: any) => (p.maxDays ? `${p.maxDays} days max` : 'Permanent') },
      { key: 'q', label: 'Requestable', render: (p: any) => (p.requestable ? 'Yes' : 'No') },
      { key: 'a', label: '', render: (p: any) => <Button size="sm" variant="outline" onClick={() => setAssign(p)}>Assign</Button> }]} /></Card>}</Loading>
    {create && <FormDialog title="New access package" onClose={() => setCreate(false)} initial={{ requestable: true }}
      fields={[{ name: 'name', label: 'Name', required: true }, { name: 'description', label: 'Description' },
        { name: 'role_ids', label: 'Roles', type: 'multiselect', options: (roles.data?.results ?? []).map((r) => ({ value: r.id, label: r.name })) },
        { name: 'max_days', label: 'Grants expire after (days, optional)', type: 'number', half: true }, { name: 'requestable', label: 'Employees can request it', type: 'checkbox' }]}
      onSubmit={(v) => access.post('packages', v)} onDone={() => void q.refetch()} />}
    {assign && <FormDialog title={`Assign ${assign.name}`} onClose={() => setAssign(null)} submitLabel="Assign"
      intro={<><p className="small muted">Grants every role in the package. You can only grant what you hold; segregation-of-duties rules apply.</p><AccountPicker value={acct} onChange={setAcct} /></>}
      fields={[{ name: 'valid_until', label: 'Ends (optional)', type: 'date', half: true }, { name: 'sod_exception_reason', label: 'SoD exception reason (only if asked)' }]}
      onSubmit={(v) => doAssign.mutateAsync({ ...v, accountId: acct })} />}</>;
}

// ---------------------------------------------------------------------------------------------------------------------
export function Requests() {
  const [params, setParams] = useSearchParams();
  const [view, setView] = useState<'mine' | 'all'>('mine');
  const q = useQ('requests', { view });
  const opts = useQ('requestable', {}, params.get('new') === '1');
  const home = useQ('home');
  const canAll = home.data?.mode === 'admin';
  return <>{T('Access requests', 'Ask for a role or package. Your manager reviews it first, then an access administrator grants it.',
    <Button onClick={() => setParams({ new: '1' })}><Icon name="plus" size={16} />Request access</Button>)}
    {canAll && <Tabs value={view} onChange={setView} items={[{ value: 'mine', label: 'My requests' }, { value: 'all', label: 'All I can see' }]} />}
    <Loading q={q}>{() => <Card flush><DataTable rows={q.data.results} empty="No access requests" columns={[
      { key: 'c', label: 'Request', render: (r: any) => <><strong>{r.for}</strong> <span className="xs muted">({r.kind})</span><div className="xs muted mono">{r.code} · {r.requester}</div></> },
      { key: 'r', label: 'Reason', render: (r: any) => <span className="small">{r.reason}</span> },
      { key: 'u', label: 'Until', render: (r: any) => (r.validUntil ? fmtDate(r.validUntil) : 'Permanent') },
      { key: 's', label: 'Status', render: (r: any) => <><Status value={r.status === 'provisioned' ? 'approved' : r.status} label={r.statusLabel} />{r.outcomeNote && <div className="xs" style={{ color: 'var(--c-danger)' }}>{r.outcomeNote}</div>}</> },
      { key: 'a', label: '', render: (r: any) => r.approvalId && <Link to={`/approvals/${r.approvalId}`} className="small">Approval</Link> }]} /></Card>}</Loading>
    {params.get('new') === '1' && <FormDialog title="Request access" onClose={() => setParams({})} submitLabel="Submit request"
      intro={<p className="small muted">Explain the business need. Temporary access is preferred: set an end date when you can.</p>}
      fields={[{ name: 'role_id', label: 'Role', type: 'select', options: (opts.data?.roles ?? []).map((r: any) => ({ value: r.id, label: r.name })) },
        { name: 'package_id', label: '…or an access package', type: 'select', options: (opts.data?.packages ?? []).map((p: any) => ({ value: p.id, label: p.name })) },
        { name: 'valid_until', label: 'Needed until', type: 'date', half: true }, { name: 'reason', label: 'Why do you need it?', type: 'textarea', required: true }]}
      onSubmit={(v) => access.post('requests', v)} onDone={() => void q.refetch()} />}</>;
}

// ---------------------------------------------------------------------------------------------------------------------
export function Reviews() {
  const q = useQ('reviews');
  const roles = useQuery({ queryKey: ['os', 'roles'], queryFn: api.admin.roles });
  const [launch, setLaunch] = useState(false);
  const [decide, setDecide] = useState<{ item: any; decision: string } | null>(null);
  const [open, setOpen] = useState<string | null>(null);
  const detail = useQ(`reviews/${open}`, {}, !!open);
  const act = useAction((b: any) => access.post(`review-items/${b.id}/decide`, b), [[...K]], 'Recorded');
  return <>{T('Access reviews', 'Certify that people still need the access they have. Removing access takes effect immediately.',
    q.data?.canLaunch && <Button onClick={() => setLaunch(true)}><Icon name="plus" size={16} />Launch review</Button>)}
    <Loading q={q}>{() => <div className="stack stack--lg">
      <Card title={`Waiting on you (${q.data.mine.length})`} flush><DataTable rows={q.data.mine} empty="Nothing to review" columns={[
        { key: 'u', label: 'Person', render: (i: any) => <><strong>{i.user}</strong><div className="xs muted">{i.review}{i.reason ? ` · ${i.reason}` : ''}</div></> },
        { key: 'r', label: 'Role', render: (i: any) => <>{i.role}<div className="xs muted">{i.anchor}</div></> },
        { key: 'l', label: 'Last sign-in', render: (i: any) => relative(i.lastLoginAt) }, { key: 'd', label: 'Due', render: (i: any) => fmtDate(i.dueOn) },
        { key: 'a', label: '', render: (i: any) => <span className="row" style={{ gap: 4 }}>
          <Button size="sm" onClick={() => act.mutate({ id: i.id, decision: 'keep' })}>Keep</Button>
          {['remove', 'suspend', 'escalate'].map((d) => <Button key={d} size="sm" variant="ghost" onClick={() => setDecide({ item: i, decision: d })}>{humanize(d)}</Button>)}</span> }]} /></Card>
      {q.data.reviews.length > 0 && <Card title="Review campaigns" flush><DataTable rows={q.data.reviews} onRow={(r: any) => setOpen(r.id)} columns={[
        { key: 'n', label: 'Review', render: (r: any) => <><strong>{r.name}</strong><div className="xs muted">{humanize(r.kind)}</div></> },
        { key: 'p', label: 'Progress', render: (r: any) => <span className="row" style={{ gap: 8 }}><span className="progress" style={{ width: 120 }}><span style={{ width: `${((r.total - r.pending) / Math.max(1, r.total)) * 100}%` }} /></span><span className="xs">{r.total - r.pending}/{r.total}</span></span> },
        { key: 'x', label: 'Removed', num: true, render: (r: any) => r.removed }, { key: 'd', label: 'Due', render: (r: any) => fmtDate(r.dueOn) },
        { key: 's', label: 'Status', render: (r: any) => <Status value={r.status} /> }]} /></Card>}
      {open && <Loading q={detail}>{() => <Card title={detail.data.name} flush actions={<Button size="sm" variant="ghost" onClick={() => setOpen(null)}>Close</Button>}>
        <DataTable rows={detail.data.items} columns={[{ key: 'u', label: 'Person', render: (i: any) => i.user }, { key: 'r', label: 'Role', render: (i: any) => i.role },
          { key: 'v', label: 'Reviewer', render: (i: any) => i.reviewer ?? '—' }, { key: 'd', label: 'Decision', render: (i: any) => <><Status value={i.decision === 'keep' ? 'approved' : i.decision === 'pending' ? 'pending' : 'rejected'} label={humanize(i.decision)} />{i.comment && <div className="xs muted">{i.comment}</div>}</> }]} /></Card>}</Loading>}
    </div>}</Loading>
    {decide && <FormDialog title={`${humanize(decide.decision)} · ${decide.item.user} · ${decide.item.role}`} onClose={() => setDecide(null)} submitLabel={humanize(decide.decision)}
      fields={[{ name: 'comment', label: 'Reason (recorded in the audit trail)', type: 'textarea', required: true }]}
      onSubmit={(v) => act.mutateAsync({ id: decide.item.id, decision: decide.decision, comment: v.comment })} />}
    {launch && <FormDialog title="Launch access review" onClose={() => setLaunch(false)} initial={{ kind: 'periodic' }} submitLabel="Launch"
      intro={<p className="small muted">Each person's manager reviews their access; nobody certifies their own.</p>}
      fields={[{ name: 'name', label: 'Name', required: true, placeholder: 'e.g. Q4 2026 certification' },
        { name: 'kind', label: 'Type', type: 'select', half: true, options: [{ value: 'periodic', label: 'Periodic' }, { value: 'privileged', label: 'Privileged access' }] },
        { name: 'due_on', label: 'Due', type: 'date', half: true }, { name: 'privileged_only', label: 'Only privileged / sensitive roles', type: 'checkbox' },
        { name: 'role_ids', label: 'Only these roles (optional)', type: 'multiselect', options: (roles.data?.results ?? []).map((r) => ({ value: r.id, label: r.name })) }]}
      onSubmit={(v) => access.post('reviews', v)} onDone={() => void q.refetch()} />}</>;
}

// ---------------------------------------------------------------------------------------------------------------------
export function SoD() {
  const q = useQ('sod');
  const [create, setCreate] = useState(false);
  const setSev = useAction((b: any) => access.patch(`sod/rules/${b.id}`, b), [[...K]], 'Rule updated');
  const revoke = useAction((id: string) => access.post(`sod/exceptions/${id}/revoke`), [[...K]], 'Exception revoked');
  const home = useQ('home');
  return <>{T('Segregation of duties', 'Combinations of permissions that should not sit with one person, and the controlled exceptions.',
    <Button onClick={() => setCreate(true)}><Icon name="plus" size={16} />New rule</Button>)}
    <Loading q={q}>{() => <div className="stack stack--lg">
      <Card title={`Current conflicts (${q.data.violations.length})`} flush><DataTable rows={q.data.violations.map((v: any, i: number) => ({ ...v, id: String(i) }))} empty="No conflicts" columns={[
        { key: 'u', label: 'Person', render: (v: any) => <Link to={`/access/effective?account=${v.accountId}`}>{v.user}</Link> },
        { key: 'r', label: 'Conflict', render: (v: any) => <>{v.name}<div className="xs muted mono">{v.first.join(', ')} + {v.second.join(', ')}</div></> },
        { key: 's', label: 'Severity', render: (v: any) => <Status value={v.severity === 'block' ? 'rejected' : v.severity === 'exception' ? 'pending' : 'neutral'} label={humanize(v.severity)} /> },
        { key: 'e', label: 'Exception', render: (v: any) => (v.exception ? `Approved: ${v.exception.reason}` : '—') }]} /></Card>
      <Card title="Rules" flush><DataTable rows={q.data.rules} columns={[
        { key: 'n', label: 'Rule', render: (r: any) => <><strong>{r.name}</strong><div className="xs muted mono">{r.first.join(', ')} ⟷ {r.second.join(', ')}</div></> },
        { key: 's', label: 'When it happens', render: (r: any) => <select className="field__input" aria-label={`Severity for ${r.name}`} value={r.severity}
          onChange={(e) => setSev.mutate({ id: r.id, severity: e.target.value })}><option value="warning">Warn</option><option value="exception">Needs exception</option><option value="block">Block</option></select> },
        { key: 'a', label: 'Active', render: (r: any) => <input type="checkbox" checked={r.isActive} aria-label="Active" onChange={(e) => setSev.mutate({ id: r.id, isActive: e.target.checked })} /> }]} /></Card>
      <Card title="Exceptions" flush><DataTable rows={q.data.exceptions} empty="No exceptions" columns={[
        { key: 'u', label: 'Person', render: (e: any) => e.user }, { key: 'r', label: 'Rule', render: (e: any) => e.rule }, { key: 'w', label: 'Reason', render: (e: any) => <span className="small">{e.reason}</span> },
        { key: 'b', label: 'Approved by', render: (e: any) => e.approvedBy ?? '—' }, { key: 'v', label: 'Until', render: (e: any) => fmtDate(e.validUntil) },
        { key: 'a', label: '', render: (e: any) => e.live && <Button size="sm" variant="ghost" onClick={() => revoke.mutate(e.id)}>Revoke</Button> }]} /></Card>
    </div>}</Loading>
    {create && <FormDialog title="New SoD rule" onClose={() => setCreate(false)} initial={{ severity: 'warning' }}
      intro={<p className="small muted">List permission codes on each side (one per line; * wildcards allowed, e.g. finance.payment.*). {home.data ? '' : ''}</p>}
      fields={[{ name: 'name', label: 'Name', required: true }, { name: 'first', label: 'Side A permissions', type: 'textarea', required: true },
        { name: 'second', label: 'Side B permissions', type: 'textarea', required: true },
        { name: 'severity', label: 'Severity', type: 'select', options: [{ value: 'warning', label: 'Warn' }, { value: 'exception', label: 'Needs exception' }, { value: 'block', label: 'Block' }] }]}
      onSubmit={(v) => access.post('sod', { ...v, first: String(v.first).split(/\s+/).filter(Boolean), second: String(v.second).split(/\s+/).filter(Boolean) })}
      onDone={() => void q.refetch()} />}</>;
}

// ---------------------------------------------------------------------------------------------------------------------
export function Emergency() {
  const q = useQ('emergency');
  const [activate, setActivate] = useState(false);
  const [review, setReview] = useState<any>(null);
  const end = useAction((id: string) => access.post(`emergency/${id}/end`), [[...K]], 'Emergency access ended');
  return <>{T('Emergency access', 'Break-glass: time-limited, announced to security, fully audited and reviewed afterwards. Never a permanent bypass.',
    q.data?.canActivate && <Button variant="danger" onClick={() => setActivate(true)}>Activate emergency access</Button>)}
    <Loading q={q}>{() => <Card flush><DataTable rows={q.data.results} empty="No emergency access used" columns={[
      { key: 'u', label: 'Person', render: (e: any) => <><strong>{e.user}</strong><div className="xs muted">{e.role}</div></> },
      { key: 'r', label: 'Reason', render: (e: any) => <span className="small">{e.reason}</span> },
      { key: 'w', label: 'Window', render: (e: any) => <span className="small">{fmtDateTime(e.startsAt)} → {fmtDateTime(e.endedAt ?? e.endsAt)}</span> },
      { key: 'n', label: 'Actions logged', num: true, render: (e: any) => e.actions },
      { key: 's', label: 'Status', render: (e: any) => <><Status value={e.status === 'active' ? 'overdue' : e.status === 'reviewed' ? 'approved' : 'pending'} label={humanize(e.status)} />
        {e.reviewNote && <div className="xs muted">Reviewed by {e.reviewedBy}: {e.reviewNote}</div>}</> },
      { key: 'a', label: '', render: (e: any) => <>{e.status === 'active' && <Button size="sm" variant="outline" onClick={() => end.mutate(e.id)}>End now</Button>}
        {e.status === 'ended' && q.data.canReview && <Button size="sm" variant="outline" onClick={() => setReview(e)}>Review</Button>}</> }]} /></Card>}</Loading>
    {activate && <FormDialog title="Activate emergency access" onClose={() => setActivate(false)} submitLabel="Activate" initial={{ hours: 1 }}
      intro={<Alert tone="warning">Security administrators are notified immediately. Everything you do is audited and reviewed by someone else afterwards.</Alert>}
      fields={[{ name: 'role_id', label: 'Role', type: 'select', required: true, options: (q.data?.eligibleRoles ?? []).map((r: any) => ({ value: r.id, label: r.name })) },
        { name: 'hours', label: `Hours (max ${q.data?.maxHours ?? 8})`, type: 'number', min: 1, max: q.data?.maxHours ?? 8, half: true },
        { name: 'reason', label: 'Incident and why normal access is not enough', type: 'textarea', required: true }]}
      onSubmit={(v) => access.post('emergency', v)} onDone={() => void q.refetch()} />}
    {review && <FormDialog title={`Post-event review · ${review.user}`} onClose={() => setReview(null)} submitLabel="Complete review"
      fields={[{ name: 'note', label: 'What you checked and concluded', type: 'textarea', required: true }]}
      onSubmit={(v) => access.post(`emergency/${review.id}/review`, v)} onDone={() => void q.refetch()} />}</>;
}

// ---------------------------------------------------------------------------------------------------------------------
export function Privileged() {
  const q = useQ('privileged');
  return <>{T('Privileged access', 'Everyone with administrative or sensitive permissions, with two-step status and last review.')}
    <Loading q={q}>{() => <Card flush><DataTable rows={q.data.results.map((r: any) => ({ ...r, id: r.accountId }))} empty="No privileged access" columns={[
      { key: 'n', label: 'Person', render: (r: any) => <Link to={`/access/effective?account=${r.accountId}`}>{r.name}</Link> },
      { key: 'r', label: 'Roles', render: (r: any) => <span className="small">{r.roles.join(', ')}</span> },
      { key: 'a', label: 'Admin areas', render: (r: any) => <span className="small">{r.adminAreas.map(humanize).join(', ') || '—'}</span> },
      { key: 's', label: 'Sensitive', num: true, render: (r: any) => r.sensitive },
      { key: 'm', label: 'Two-step', render: (r: any) => (r.mfa ? <Status value="active" label="On" /> : <Status value="rejected" label="Off" />) },
      { key: 'l', label: 'Last sign-in', render: (r: any) => relative(r.lastLoginAt) }, { key: 'v', label: 'Last reviewed', render: (r: any) => fmtDate(r.lastReviewed) }]} /></Card>}</Loading></>;
}

export function Hygiene() {
  const q = useQ('hygiene');
  return <>{T('Orphaned & unused access', 'Flagged for review — nothing is removed automatically.')}
    <Loading q={q}>{() => <div className="stack stack--lg">
      <Card title={`Accounts needing attention (${q.data.orphaned.length})`} flush><DataTable rows={q.data.orphaned.map((r: any) => ({ ...r, id: r.accountId }))} empty="None" columns={[
        { key: 'n', label: 'Account', render: (r: any) => <Link to={`/settings/users/${r.accountId}`}>{r.name}</Link> }, { key: 's', label: 'Status', render: (r: any) => <Status value={r.status} /> },
        { key: 'i', label: 'Issues', render: (r: any) => <span className="small">{r.issues.join(' · ')}</span> }]} /></Card>
      <div className="grid grid--2">
        <Card title="Roles nobody holds" flush><DataTable rows={q.data.unusedRoles} empty="None" columns={[{ key: 'n', label: 'Role', render: (r: any) => <Link to={`/settings/roles/${r.id}`}>{r.name}</Link> }, { key: 's', label: 'Type', render: (r: any) => (r.system ? 'Template' : 'Custom') }]} /></Card>
        <Card title="Unused service accounts (90 days)" flush><DataTable rows={q.data.unusedServiceAccounts} empty="None" columns={[{ key: 'n', label: 'Service account', render: (r: any) => r.name }, { key: 'l', label: 'Last used', render: (r: any) => relative(r.lastUsedAt) }]} /></Card>
      </div>
      {q.data.expiredTemporary.length > 0 && <Alert tone="warning">{q.data.expiredTemporary.length} temporary grants are past their end date and will be removed by the next access job run.</Alert>}
    </div>}</Loading></>;
}

export function SecurityEvents() {
  const [failures, setFailures] = useState(false);
  const q = useQ('security', { failures: failures ? 'true' : undefined, days: 7 });
  return <>{T('Security events', 'Sign-ins, failures, lockouts, MFA and session events from the last 7 days.')}
    <Loading q={q}>{() => <div className="stack stack--lg">
      <Kpis items={[{ label: 'Failed sign-ins (7 days)', value: q.data.failures, tone: q.data.failures > 20 ? 'alert' : undefined },
        { label: 'Locked accounts', value: q.data.locked.length }, { label: 'Suspicious sources', value: q.data.suspiciousIps.length, tone: q.data.suspiciousIps.length ? 'alert' : undefined }]} />
      {q.data.suspiciousIps.length > 0 && <Alert tone="warning">Repeated failures from: {q.data.suspiciousIps.map((s: any) => `${s.ip} (${s.failures})`).join(', ')}</Alert>}
      <Card flush actions={<label className="row small"><input type="checkbox" checked={failures} onChange={(e) => setFailures(e.target.checked)} />Failures only</label>}>
        <DataTable rows={q.data.results} empty="No events" columns={[{ key: 'a', label: 'Event', render: (e: any) => <><span className="mono xs">{e.action}</span>{e.label && <div className="xs muted">{e.label}</div>}</> },
          { key: 'o', label: 'Outcome', render: (e: any) => <Status value={e.outcome === 'success' ? 'approved' : 'rejected'} label={e.outcome} /> },
          { key: 'u', label: 'Who', render: (e: any) => e.actor ?? '—' }, { key: 'i', label: 'IP', render: (e: any) => <span className="mono xs">{e.ip ?? '—'}</span> },
          { key: 't', label: 'When', render: (e: any) => fmtDateTime(e.at) }]} /></Card>
    </div>}</Loading></>;
}
