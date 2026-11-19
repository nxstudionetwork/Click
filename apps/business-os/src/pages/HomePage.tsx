import { useEffect, useState, type ReactElement } from 'react';
import { Link } from 'react-router-dom';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Button, Icon, Skeleton, type IconName } from '@click/ui';
import type { OSMetric, OSWidget } from '@click/api';
import { api, apiMessage } from '../lib/api';
import { fmtDateTime, fmtMoney, fmtNumber, relative } from '../lib/format';
import { useOS, useOSSession } from '../session/OSSession';
import { Card, Dialog, QueryError, Status } from '../components/ui';

type Any = Record<string, any>; // eslint-disable-line @typescript-eslint/no-explicit-any

function greeting() {
  const h = new Date().getHours();
  return h < 12 ? 'Good morning' : h < 17 ? 'Good afternoon' : 'Good evening';
}

export function HomePage() {
  const ctx = useOS();
  const home = useQuery({ queryKey: ['os', 'home'], queryFn: api.home, refetchInterval: 120_000 });
  const [customize, setCustomize] = useState(false);
  const first = ctx.user.fullName.split(' ')[0];
  useEffect(() => { document.title = 'Home · Click Business OS'; }, []);

  return (
    <>
      <div className="greet">
        <div>
          <h1>{greeting()}, {first}</h1>
          <p className="muted">Here’s what needs you today at {ctx.organization.name}.</p>
          <div className="greet__meta">
            {ctx.employee?.designation && <span className="chip"><Icon name="briefcase" size={13} />{ctx.employee.designation}</span>}
            {ctx.orgContext.department && <span className="chip"><Icon name="team" size={13} />{ctx.orgContext.department.name}</span>}
            {ctx.orgContext.location && <span className="chip"><Icon name="pin" size={13} />{ctx.orgContext.location.name}</span>}
            {ctx.account.partner && <span className="chip"><Icon name="store" size={13} />{ctx.account.partner.name}</span>}
            {ctx.roles.map((r) => <span key={r.id} className="chip"><Icon name="key" size={13} />{r.name}</span>)}
          </div>
        </div>
        <Button variant="outline" size="sm" onClick={() => setCustomize(true)}><Icon name="settings" size={15} />Customize</Button>
      </div>

      {ctx.quickActions.length > 0 && (
        <div className="quick" style={{ marginBottom: 20 }} aria-label="Quick actions">
          {ctx.quickActions.map((a) => <Link key={a.key} to={a.path} className="quick__btn"><Icon name={a.icon as IconName} size={15} />{a.label}</Link>)}
        </div>
      )}

      {!ctx.account.mfaEnabled && (
        <div className="alert alert--warning" style={{ marginBottom: 16 }}>
          <Icon name="shield" size={16} />
          <div className="grow">Your account isn’t protected by two-step verification{ctx.mfaBlocked.length ? ' — some of your access stays off until it is' : ''}.</div>
          <Link to="/settings/security?setup=mfa" className="small">Turn it on</Link>
        </div>
      )}

      {home.isPending ? (
        <div className="grid grid--home">{[0, 1, 2, 3].map((i) => <div key={i} className="span-m card"><div className="loader"><Skeleton height={18} width="40%" /><Skeleton height={60} /><Skeleton height={14} width="70%" /></div></div>)}</div>
      ) : home.error ? (
        <QueryError error={home.error} onRetry={() => void home.refetch()} />
      ) : (
        <div className="grid grid--home">
          {home.data.widgets.map((w) => <div key={w.key} className={`span-${w.size}`}><WidgetCard widget={w} /></div>)}
        </div>
      )}
      {home.data && <p className="xs muted" style={{ marginTop: 16 }}>Updated {relative(home.data.generatedAt)} · Figures are limited to what your role and scope allow.</p>}
      {customize && home.data && <CustomizeDialog available={home.data.available} onClose={() => setCustomize(false)} />}
    </>
  );
}

const RENDERERS: Record<string, (d: Any) => ReactElement> = {
  my_work: MyWork, approvals: Approvals, notifications: Notifications, calendar: Calendar, security: Security,
  business_snapshot: Metrics, finance_overview: Metrics, people_overview: Metrics, operations_overview: Metrics,
  security_overview: Metrics, partner_pipeline: Pipeline,
};
const LINKS: Record<string, [string, string]> = {
  my_work: ['/tasks', 'All tasks'], approvals: ['/approvals', 'Open approvals'], notifications: ['/notifications', 'All notifications'],
  calendar: ['/calendar', 'Calendar'], security: ['/settings/security', 'Security settings'], finance_overview: ['/m/finance', 'Finance'],
  people_overview: ['/m/people', 'People & HR'], operations_overview: ['/m/operations', 'Operations'], partner_pipeline: ['/m/partners', 'Partners'],
  security_overview: ['/settings/users', 'Users'], business_snapshot: ['/m/analytics', 'Analytics'],
};

function WidgetCard({ widget }: { widget: OSWidget }) {
  const qc = useQueryClient();
  const R = RENDERERS[widget.key];
  const link = LINKS[widget.key];
  return (
    <Card title={widget.title} flush actions={link && <Link to={link[0]} className="small">{link[1]}</Link>}>
      {widget.error ? (
        <div className="card__body"><div className={`alert ${widget.error.code === 'not_at_scope' ? 'alert--info' : 'alert--warning'}`}>
          <Icon name={widget.error.code === 'not_at_scope' ? 'lock' : 'alert'} size={16} />
          <div className="grow">{widget.error.message}</div>
          {widget.error.code !== 'not_at_scope' && <button className="btn btn--ghost btn--sm" onClick={() => void qc.invalidateQueries({ queryKey: ['os', 'home'] })}>Retry</button>}
        </div></div>
      ) : R && widget.data ? R(widget.data as Any) : null}
    </Card>
  );
}

function MetricTile({ m }: { m: OSMetric }) {
  const fmt = (v: string | number | undefined) => (m.format === 'money' ? fmtMoney(v ?? null) : fmtNumber(v ?? null));
  let delta: ReactElement | null = null;
  if (m.previous !== undefined) {
    const cur = Number(m.value), prev = Number(m.previous);
    const pct = prev ? Math.round(((cur - prev) / prev) * 100) : null;
    delta = <div className={`metric__delta ${pct === null ? '' : pct >= 0 ? 'up' : 'down'}`}>{pct === null ? `Previous: ${fmt(m.previous)}` : `${pct >= 0 ? '▲' : '▼'} ${Math.abs(pct)}% vs previous`}</div>;
  }
  return (
    <div className={`metric ${m.alert ? 'metric--alert' : ''}`}>
      <div className="metric__label">{m.label}</div>
      <div className="metric__value">{fmt(m.value)}</div>
      {delta}
    </div>
  );
}

function Metrics(d: Any) {
  return (
    <>
      {d.period && <div className="xs muted" style={{ padding: '8px 16px 0' }}>{d.period}</div>}
      <div className="metrics">{(d.metrics as OSMetric[]).map((m) => <MetricTile key={m.key} m={m} />)}</div>
      {d.breakdown?.length > 0 && <div className="pill-list" style={{ padding: '10px 16px' }}>{d.breakdown.map((b: Any) => <span key={b.label} className="pill">{b.label}: <strong>{b.value}</strong></span>)}</div>}
      {d.note && <div className="note">{d.note}</div>}
    </>
  );
}

function Pipeline(d: Any) {
  const max = Math.max(1, ...d.stages.map((s: Any) => s.value));
  return (
    <div className="card__body funnel">
      {d.stages.map((s: Any) => (
        <div key={s.key} className="funnel__row">
          <span className="ellipsis">{s.label}</span>
          <span className="funnel__bar"><span style={{ width: `${(s.value / max) * 100}%` }} /></span>
          <strong className="num" style={{ textAlign: 'right' }}>{s.value}</strong>
        </div>
      ))}
      <span className="xs muted">{d.total} partners in total</span>
    </div>
  );
}

function Counts({ items }: { items: [string, number, boolean?][] }) {
  return <div className="counts" style={{ padding: 16 }}>{items.map(([label, n, alert]) => <div key={label} className={`count ${alert && n > 0 ? 'count--alert' : ''}`}><strong>{n}</strong><span>{label}</span></div>)}</div>;
}

function MyWork(d: Any) {
  return (
    <>
      <Counts items={[['Open', d.counts.open], ['Overdue', d.counts.overdue, true], ['Due this week', d.counts.dueWeek]]} />
      {d.items.length ? (
        <ul className="list" style={{ borderTop: '1px solid var(--c-line-2)' }}>
          {d.items.map((t: Any) => (
            <li key={t.id}><Link to={t.path} className="list-row">
              <span className="list-row__main"><span className="list-row__title" style={{ display: 'block' }}>{t.title}</span>
                <span className="list-row__sub" style={{ display: 'block', color: t.overdue ? 'var(--c-danger)' : undefined }}>{t.dueAt ? `${t.overdue ? 'Overdue · ' : 'Due '}${fmtDateTime(t.dueAt)}` : 'No due date'}</span></span>
              {t.priority !== 'normal' && <Status value={t.priority} />}
            </Link></li>
          ))}
        </ul>
      ) : <p className="muted small" style={{ padding: '0 16px 16px' }}>No open tasks. Nice.</p>}
    </>
  );
}

function Approvals(d: Any) {
  return (
    <>
      <Counts items={[['Waiting on you', d.counts.waitingOnMe, true], ['Your pending', d.counts.myPending], ['Approved · 7d', d.counts.approvedWeek], ['Rejected · 7d', d.counts.rejectedWeek]]} />
      {d.items.length ? (
        <ul className="list" style={{ borderTop: '1px solid var(--c-line-2)' }}>
          {d.items.map((r: Any) => (
            <li key={r.id}><Link to={r.path} className="list-row">
              <span className="list-row__main"><span className="list-row__title" style={{ display: 'block' }}>{r.title}</span>
                <span className="list-row__sub" style={{ display: 'block' }}>{r.reference} · {r.requestedBy} · {relative(r.createdAt)}</span></span>
              {r.amount && <strong className="small">{fmtMoney(r.amount, r.currency)}</strong>}
            </Link></li>
          ))}
        </ul>
      ) : <p className="muted small" style={{ padding: '0 16px 16px' }}>Nothing is waiting for your decision.</p>}
    </>
  );
}

function Notifications(d: Any) {
  if (!d.items.length) return <p className="muted small" style={{ padding: 16 }}>No notifications yet.</p>;
  return (
    <ul className="list">
      {d.items.map((n: Any) => (
        <li key={n.id}><Link to={n.path || '/notifications'} className={`list-row ${n.read ? '' : 'list-row--unread'}`}>
          <span className={`dot ${n.read ? 'dot--off' : n.priority !== 'normal' ? `dot--${n.priority}` : ''}`} />
          <span className="list-row__main"><span className="list-row__title" style={{ display: 'block' }}>{n.title}</span><span className="list-row__sub" style={{ display: 'block' }}>{n.body}</span></span>
          <span className="list-row__aside">{relative(n.createdAt)}</span>
        </Link></li>
      ))}
    </ul>
  );
}

function Calendar(d: Any) {
  if (!d.items.length) return <p className="muted small" style={{ padding: 16 }}>No deadlines in the next two weeks.</p>;
  return (
    <ul className="list">
      {d.items.map((i: Any) => (
        <li key={i.id}><Link to={i.path} className="list-row">
          <span className="chip" style={{ minWidth: 92, justifyContent: 'center' }}>{fmtDateTime(i.at)}</span>
          <span className="list-row__main"><span className="list-row__title" style={{ display: 'block' }}>{i.title}</span></span>
          <Status value={i.kind} label={i.kind === 'task' ? 'Task' : 'Approval'} tone={i.kind === 'task' ? 'brand' : 'warning'} />
        </Link></li>
      ))}
    </ul>
  );
}

function Security(d: Any) {
  return (
    <div className="card__body stack">
      <div className="row row--between small"><span>Two-step verification</span><Status value={d.mfaEnabled ? 'active' : 'warning'} label={d.mfaEnabled ? 'On' : 'Off'} /></div>
      <div className="row row--between small"><span>Signed-in devices</span><strong>{d.activeSessions}</strong></div>
      <div className="row row--between small"><span>Last sign-in</span><span className="muted">{fmtDateTime(d.lastLoginAt)}</span></div>
      {d.mfaEnabled && d.recoveryCodesLeft < 3 && <div className="alert alert--warning small">Only {d.recoveryCodesLeft} recovery codes left.</div>}
    </div>
  );
}

function CustomizeDialog({ available, onClose }: { available: { key: string; title: string; visible: boolean }[]; onClose: () => void }) {
  const qc = useQueryClient();
  const { setContext } = useOSSession();
  const [order, setOrder] = useState(available.map((a) => a.key));
  const [hidden, setHidden] = useState(available.filter((a) => !a.visible).map((a) => a.key));
  const title = (k: string) => available.find((a) => a.key === k)?.title ?? k;
  const save = useMutation({
    mutationFn: () => api.me.updatePreferences({ home: { hidden, order } }),
    onSuccess: (ctx) => { setContext(ctx); void qc.invalidateQueries({ queryKey: ['os', 'home'] }); onClose(); },
  });
  const move = (i: number, d: number) => setOrder((o) => { const n = [...o]; const j = i + d; if (j < 0 || j >= n.length) return o; [n[i], n[j]] = [n[j]!, n[i]!]; return n; });
  return (
    <Dialog title="Customize Home" onClose={onClose} footer={<>
      <Button variant="outline" onClick={onClose}>Cancel</Button>
      <Button loading={save.isPending} onClick={() => save.mutate()}>Save</Button>
    </>}>
      <p className="small muted">Only sections your role allows are listed. Your choice applies to you, not to others with the same role.</p>
      {save.error && <div className="alert alert--error">{apiMessage(save.error)}</div>}
      <ul className="list card">
        {order.map((k, i) => (
          <li key={k} className="list-row">
            <input type="checkbox" aria-label={`Show ${title(k)}`} checked={!hidden.includes(k)} onChange={(e) => setHidden((h) => (e.target.checked ? h.filter((x) => x !== k) : [...h, k]))} />
            <span className="grow">{title(k)}</span>
            <button className="icon-btn" aria-label="Move up" onClick={() => move(i, -1)} disabled={i === 0}><Icon name="chevron" size={16} className="rot180" /></button>
            <button className="icon-btn" aria-label="Move down" onClick={() => move(i, 1)} disabled={i === order.length - 1}><Icon name="chevron" size={16} /></button>
          </li>
        ))}
      </ul>
    </Dialog>
  );
}
