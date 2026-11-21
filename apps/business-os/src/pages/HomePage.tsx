import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Button, Icon, Skeleton, useToast } from '@click/ui';
import type { OSHomeV2, OSWidgetMeta } from '@click/api';
import { apiMessage, home } from '../lib/api';
import { relative } from '../lib/format';
import { useOS } from '../session/OSSession';
import { RENDERERS } from '../components/home/renderers';
import { Alert, Dialog, QueryError } from '../components/ui';

function greeting() {
  const h = new Date().getHours();
  return h < 12 ? 'Good morning' : h < 17 ? 'Good afternoon' : 'Good evening';
}

export function HomePage() {
  const ctx = useOS();
  const qc = useQueryClient();
  const toast = useToast();
  const q = useQuery({ queryKey: ['os', 'home'], queryFn: () => home.get(), refetchInterval: 120_000 });
  const [customize, setCustomize] = useState(false);
  useEffect(() => { document.title = 'Home · Click Business OS'; }, []);
  const view = useMutation({
    mutationFn: (id: string) => home.activateView(id),
    onSuccess: () => { void qc.invalidateQueries({ queryKey: ['os', 'home'] }); void qc.invalidateQueries({ queryKey: ['os', 'widget'] }); },
    onError: (e) => toast(apiMessage(e), 'error'),
  });

  if (q.isPending) return <HomeSkeleton />;
  if (q.error) return <QueryError error={q.error} onRetry={() => void q.refetch()} />;
  const h = q.data;
  const s = h.summary;
  const first = ctx.user.fullName.split(' ')[0];
  const date = new Date(s.date).toLocaleDateString('en-IN', { weekday: 'long', day: 'numeric', month: 'long', year: 'numeric' });
  const contextLabel = [ctx.organization.name, h.context.unit?.name ?? ctx.orgContext.location?.name].filter(Boolean).join(' · ');

  return (
    <>
      <div className="welcome">
        <div>
          <div className="welcome__date">{date} · {contextLabel}</div>
          <h1>{greeting()}, {first}</h1>
          <p className="muted">Here’s what needs your attention today.</p>
          <nav className="attention" aria-label="Today at a glance">
            <Link to="/approvals" className={s.approvalsOverdue ? 'hot' : ''}><strong>{s.approvalsWaiting}</strong> approvals{s.approvalsOverdue ? ` (${s.approvalsOverdue} overdue)` : ''}</Link>
            <Link to="/tasks" className={s.tasksOverdue ? 'hot' : ''}><strong>{s.tasksOpen}</strong> open tasks{s.tasksOverdue ? ` (${s.tasksOverdue} overdue)` : ''}</Link>
            <Link to="/tasks?view=upcoming"><strong>{s.tasksDueToday}</strong> due today</Link>
            <Link to="#w-alerts" className={s.alertsCritical ? 'hot' : ''}><strong>{s.alertsImportant}</strong> important alerts</Link>
            <Link to="/calendar"><strong>{s.deadlinesWeek}</strong> deadlines this week</Link>
          </nav>
        </div>
        <div className="home-toolbar" style={{ marginBottom: 0 }}>
          <label className="sr-only" htmlFor="home-view">Home view</label>
          <select id="home-view" className="field__input" value={h.views.active ?? 'default'} onChange={(e) => view.mutate(e.target.value)}>
            <option value="default">My default view</option>
            {h.views.saved.length > 0 && <optgroup label="Saved views">{h.views.saved.map((v) => <option key={v.id} value={v.id}>{v.name}</option>)}</optgroup>}
            {h.views.presets.length > 0 && <optgroup label="Views for your role">{h.views.presets.map((v) => <option key={v.id} value={v.id}>{v.name}</option>)}</optgroup>}
          </select>
          {h.canExecutive && h.views.active !== 'preset:executive' && <Button size="sm" variant="outline" onClick={() => view.mutate('preset:executive')}><Icon name="chart" size={15} />Executive view</Button>}
          <Button size="sm" variant="outline" onClick={() => setCustomize(true)}><Icon name="settings" size={15} />Customize</Button>
          <Button size="sm" variant="ghost" aria-label="Refresh Home" onClick={() => { void qc.invalidateQueries({ queryKey: ['os', 'widget'] }); void q.refetch(); }}>
            <Icon name="history" size={15} />
          </Button>
        </div>
      </div>
      {!ctx.account.mfaEnabled && (
        <div className="alert alert--warning" style={{ marginBottom: 16 }}>
          <Icon name="shield" size={16} /><div className="grow">Your account isn’t protected by two-step verification{ctx.mfaBlocked.length ? ' — some of your access stays off until it is' : ''}.</div>
          <Link to="/settings/security?setup=mfa" className="small">Turn it on</Link>
        </div>
      )}
      <div className="grid grid--home home-grid--mobile-first">
        {h.layout.map((w) => <div key={w.key} id={`w-${w.key}`} className={`span-${w.size} w-${w.key}`}><WidgetCard meta={w} periods={h.periods} unit={h.context.selected} /></div>)}
      </div>
      <p className="xs muted" style={{ marginTop: 16 }}>Layout loaded {relative(h.generatedAt)}. Each section shows when it was last updated and where its data comes from. Figures only include what your role and scope allow.</p>
      {customize && <CustomizeDialog h={h} onClose={() => setCustomize(false)} />}
    </>
  );
}

function HomeSkeleton() {
  return (
    <div aria-busy="true" aria-label="Loading Home">
      <Skeleton height={28} width="40%" /><div style={{ height: 8 }} /><Skeleton height={16} width="60%" /><div style={{ height: 20 }} />
      <div className="grid grid--home">{[0, 1, 2, 3].map((i) => <div key={i} className="span-m card"><div className="loader"><Skeleton height={18} width="40%" /><Skeleton height={60} /><Skeleton height={14} width="70%" /></div></div>)}</div>
    </div>
  );
}

const LINKS: Record<string, [string, string]> = {
  approvals: ['/approvals', 'Approval center'], my_work: ['/my-work', 'My work'], priority_inbox: ['/notifications', 'Notifications'], upcoming: ['/calendar', 'Calendar'],
  announcements: ['/announcements', 'All'], alerts: ['/alerts', 'All alerts'], risk_watch: ['/alerts?risk=true', 'All risks'], business_pulse: ['/m/analytics', 'Analytics'],
  finance_snapshot: ['/m/finance', 'Finance'], partner_snapshot: ['/m/partners', 'Partners'], services_snapshot: ['/m/services', 'Click Services'],
  operations_overview: ['/m/operations', 'Operations'], security_overview: ['/settings/users', 'Users'], system_status: ['/settings/system', 'System'],
  team: ['/people/directory?manager=me', 'Team'], people_overview: ['/people', 'People & HR'], new_joiners: ['/people/onboarding', 'Onboarding'],
  pending_leave: ['/approvals', 'Approvals'], open_positions: ['/people/positions', 'Positions'], upcoming_reviews: ['/people/performance', 'Performance'],
  document_expiries: ['/people/directory', 'People'], attendance_exceptions: ['/people/attendance?tab=exceptions', 'Attendance'],
  probation_ending: ['/people/lifecycle', 'Lifecycle'], training_due: ['/people/learning', 'Learning'], recent_activity: ['/settings/security', 'Account activity'],
};

function WidgetCard({ meta, periods, unit }: { meta: OSWidgetMeta; periods: { key: string; label: string }[]; unit: string | null }) {
  const [period, setPeriod] = useState<string>(meta.period ?? (meta.periods ? 'last_30_days' : ''));
  const q = useQuery({
    queryKey: ['os', 'widget', meta.key, unit, period],
    queryFn: ({ signal }) => home.widget(meta.key, { period: meta.periods ? period : undefined, unit: meta.unitAware ? unit ?? undefined : undefined }, signal),
    refetchInterval: meta.refreshSeconds * 1000,
  });
  const R = RENDERERS[meta.key];
  const link = LINKS[meta.key];
  return (
    <section className="card" aria-labelledby={`wt-${meta.key}`} aria-busy={q.isPending}>
      <header className="card__head">
        <div className="row" style={{ minWidth: 0 }}>
          <h2 id={`wt-${meta.key}`} className="ellipsis">{meta.title}</h2>
          {meta.pinned && <span title="Pinned" className="xs" style={{ color: 'var(--c-brand)' }}>★</span>}
          {meta.mandatory && <span className="xs muted" title="Always shown">•</span>}
        </div>
        <div className="widget-tools">
          {meta.periods && (
            <select aria-label={`${meta.title} period`} value={period} onChange={(e) => setPeriod(e.target.value)}>
              {periods.filter((p) => p.key !== 'custom').map((p) => <option key={p.key} value={p.key}>{p.label}</option>)}
            </select>
          )}
          {link && <Link to={link[0]} className="xs">{link[1]}</Link>}
        </div>
      </header>
      {q.isPending ? <div className="loader"><Skeleton height={16} width="50%" /><Skeleton height={44} /><Skeleton height={14} width="70%" /></div>
        : q.error ? <div className="card__body"><QueryError error={q.error} onRetry={() => void q.refetch()} /></div>
          : q.data.error ? (
            <div className="card__body">
              <div className={`alert ${q.data.error.code === 'not_at_scope' ? 'alert--info' : 'alert--warning'}`}>
                <Icon name={q.data.error.code === 'not_at_scope' ? 'lock' : 'alert'} size={16} /><div className="grow">{q.data.error.message}</div>
                {q.data.error.code !== 'not_at_scope' && <Button size="sm" variant="ghost" onClick={() => void q.refetch()}>Retry</Button>}
              </div>
            </div>
          ) : R && q.data.data ? R(q.data.data, { refresh: () => void q.refetch() }) : <div className="card__body muted small">Nothing to show.</div>}
      {q.data && !q.data.error && (
        <div className="fresh">
          <span>{q.data.live ? 'Live' : 'Cached'} · updated {relative(q.data.generatedAt)}{q.isFetching ? ' · refreshing…' : ''}</span>
          <span>{q.data.source}{q.data.location ? ` · ${q.data.location}` : ''}</span>
        </div>
      )}
    </section>
  );
}

function CustomizeDialog({ h, onClose }: { h: OSHomeV2; onClose: () => void }) {
  const qc = useQueryClient();
  const toast = useToast();
  const titles = Object.fromEntries(h.available.map((a) => [a.key, a]));
  const [rows, setRows] = useState(h.layout.map((w) => ({ key: w.key, size: w.size, period: w.period, pinned: w.pinned })));
  const [pulse, setPulse] = useState<string[]>(h.pulse.selected);
  const [viewName, setViewName] = useState('');
  const hidden = h.available.filter((a) => !rows.some((r) => r.key === a.key));
  const done = () => { void qc.invalidateQueries({ queryKey: ['os', 'home'] }); void qc.invalidateQueries({ queryKey: ['os', 'widget'] }); };
  const save = useMutation({
    mutationFn: async () => {
      const r = await home.saveLayout(rows);
      if (h.pulse.available.length) await home.setPulse(pulse);
      if (viewName.trim()) await home.saveView(viewName.trim());
      return r;
    },
    onSuccess: (r) => { done(); toast(r.keptMandatory.length ? 'Saved. Mandatory sections stay on Home.' : 'Home saved'); onClose(); },
    onError: (e) => toast(apiMessage(e), 'error'),
  });
  const reset = useMutation({ mutationFn: home.resetLayout, onSuccess: () => { done(); toast('Home reset to your role’s default'); onClose(); } });
  const move = (i: number, d: number) => setRows((o) => { const n = [...o]; const j = i + d; if (j < 0 || j >= n.length) return o; [n[i], n[j]] = [n[j]!, n[i]!]; return n; });
  const set = (i: number, patch: Partial<(typeof rows)[number]>) => setRows((o) => o.map((r, j) => (j === i ? { ...r, ...patch } : r)));

  return (
    <Dialog title="Customize Home" wide onClose={onClose} footer={<>
      <Button variant="ghost" loading={reset.isPending} onClick={() => reset.mutate()}>Reset to default</Button>
      <span className="grow" />
      <Button variant="outline" onClick={onClose}>Cancel</Button>
      <Button loading={save.isPending} onClick={() => save.mutate()}>Save</Button>
    </>}>
      <p className="small muted">Only sections your role allows are listed. Security alerts and critical announcements always stay on Home.</p>
      <div className="table-wrap card">
        <table className="table">
          <thead><tr><th>Section</th><th>Size</th><th>Period</th><th>Pin</th><th className="num">Order</th></tr></thead>
          <tbody>
            {rows.map((r, i) => {
              const m = titles[r.key];
              return (
                <tr key={r.key}>
                  <td><div className="row">
                    <input type="checkbox" checked aria-label={`Show ${m?.title}`} disabled={m?.mandatory} onChange={() => setRows((o) => o.filter((_, j) => j !== i))} />
                    <span>{m?.title}{m?.mandatory && <span className="xs muted"> · always shown</span>}</span></div></td>
                  <td><select className="field__input" style={{ minHeight: 30 }} value={r.size} aria-label="Size" onChange={(e) => set(i, { size: e.target.value as 's' })}>
                    <option value="s">Small</option><option value="m">Medium</option><option value="l">Wide</option></select></td>
                  <td>{m?.periods ? <select className="field__input" style={{ minHeight: 30 }} value={r.period ?? ''} aria-label="Period" onChange={(e) => set(i, { period: e.target.value || null })}>
                    <option value="">Default</option>{h.periods.filter((p) => p.key !== 'custom').map((p) => <option key={p.key} value={p.key}>{p.label}</option>)}</select> : <span className="muted">—</span>}</td>
                  <td><input type="checkbox" aria-label="Pin to top" checked={r.pinned} onChange={(e) => set(i, { pinned: e.target.checked })} /></td>
                  <td className="num"><button className="icon-btn" aria-label="Move up" disabled={i === 0} onClick={() => move(i, -1)}><Icon name="chevron" size={15} className="rot180" /></button>
                    <button className="icon-btn" aria-label="Move down" disabled={i === rows.length - 1} onClick={() => move(i, 1)}><Icon name="chevron" size={15} /></button></td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
      {hidden.length > 0 && (
        <div className="stack" style={{ gap: 6 }}><h3>Add sections</h3>
          <div className="pill-list">{hidden.map((a) => <button key={a.key} className="pill" onClick={() => setRows((o) => [...o, { key: a.key, size: a.size, period: null, pinned: false }])}>+ {a.title}</button>)}</div>
        </div>
      )}
      {h.pulse.available.length > 0 && (
        <div className="stack" style={{ gap: 6 }}><h3>Business pulse metrics</h3>
          <div className="pill-list">{h.pulse.available.map((m) => (
            <label key={m.key} className={`pill ${pulse.includes(m.key) ? 'pill--on' : ''}`}>
              <input type="checkbox" className="sr-only" checked={pulse.includes(m.key)} onChange={(e) => setPulse((p) => (e.target.checked ? [...p, m.key] : p.filter((k) => k !== m.key)))} />{m.label}
            </label>))}</div>
        </div>
      )}
      <label className="field"><span className="field__label">Save this layout as a view (optional)</span>
        <input className="field__input" value={viewName} onChange={(e) => setViewName(e.target.value)} placeholder="e.g. Month-end close" maxLength={60} /></label>
      {save.error && <Alert tone="error">{apiMessage(save.error)}</Alert>}
    </Dialog>
  );
}
