/* eslint-disable @typescript-eslint/no-explicit-any */
/**
 * Home widget renderers. Data arrives already filtered by the server (permissions, scope, location); renderers only
 * present it. Actions call the same APIs as the full pages, so nothing here can bypass authorization.
 */
import { useState, type ReactElement } from 'react';
import { Link } from 'react-router-dom';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { Button, Icon, useToast, type IconName } from '@click/ui';
import type { OSAlert, OSPulseMetric } from '@click/api';
import { api, apiMessage, home } from '../../lib/api';
import { fmtDate, fmtDateTime, fmtMoney, fmtNumber, relative } from '../../lib/format';
import { Dialog, Status } from '../ui';

type D = any;
type R = (d: D, ctx: { refresh: () => void }) => ReactElement;

const Empty = ({ title, msg }: { title: string; msg?: string }) => (
  <div className="w-empty"><strong>{title}</strong>{msg && <span>{msg}</span>}</div>
);

const Row = ({ to, children, aside }: { to?: string; children: React.ReactNode; aside?: React.ReactNode }) =>
  to ? <Link to={to} className="list-row"><span className="list-row__main">{children}</span>{aside}</Link>
    : <div className="list-row"><span className="list-row__main">{children}</span>{aside}</div>;

const T = ({ title, sub, subTone }: { title: React.ReactNode; sub?: React.ReactNode; subTone?: 'danger' }) => (
  <>
    <span className="list-row__title" style={{ display: 'block' }}>{title}</span>
    {sub && <span className="list-row__sub" style={{ display: 'block', color: subTone === 'danger' ? 'var(--c-danger)' : undefined }}>{sub}</span>}
  </>
);

function useInvalidateHome() {
  const qc = useQueryClient();
  return () => { void qc.invalidateQueries({ queryKey: ['os', 'widget'] }); void qc.invalidateQueries({ queryKey: ['os', 'home'] }); };
}

function value(m: { format?: string; value: any }) {
  if (m.value === null || m.value === undefined) return '—';
  if (m.format === 'money') return fmtMoney(m.value);
  if (m.format === 'text') return String(m.value);
  return typeof m.value === 'number' || /^-?\d+(\.\d+)?$/.test(String(m.value)) ? fmtNumber(m.value) : String(m.value);
}

export function Sparkline({ series, down }: { series: { v: string }[]; down?: boolean }) {
  if (!series || series.length < 2) return null;
  const vs = series.map((s) => Number(s.v));
  const max = Math.max(...vs), min = Math.min(...vs);
  const pts = vs.map((v, i) => `${(i / (vs.length - 1)) * 100},${28 - ((v - min) / (max - min || 1)) * 24 - 2}`).join(' ');
  return (
    <svg className={`spark ${down ? 'spark--down' : ''}`} viewBox="0 0 100 28" preserveAspectRatio="none" aria-hidden="true">
      <polyline points={pts} fill="none" stroke="currentColor" strokeWidth="1.6" vectorEffect="non-scaling-stroke" />
    </svg>
  );
}

function MetricTiles({ metrics }: { metrics: any[] }) {
  return (
    <div className="metrics">
      {metrics.map((m) => {
        const tile = (
          <>
            <div className="metric__label">{m.label}{m.alert && <span className="flag flag--overdue" style={{ marginLeft: 6 }}>Check</span>}</div>
            <div className="metric__value">{value(m)}</div>
          </>
        );
        return m.path ? <Link key={m.key} to={m.path} className={`metric ${m.alert ? 'metric--alert' : ''}`} style={{ color: 'inherit', textDecoration: 'none' }}>{tile}</Link>
          : <div key={m.key} className={`metric ${m.alert ? 'metric--alert' : ''}`}>{tile}</div>;
      })}
    </div>
  );
}

function PulseTile({ m }: { m: OSPulseMetric }) {
  const up = (m.deltaPct ?? 0) >= 0;
  const good = m.deltaPct === null ? null : (up && m.goodWhen === 'up') || (!up && m.goodWhen === 'down');
  return (
    <Link to={m.drill || '#'} className="metric" style={{ color: 'inherit', textDecoration: 'none' }} title={m.description || m.note || undefined}>
      <div className="metric__label">{m.label}</div>
      <div className="metric__value">{m.error ? '—' : value(m)}</div>
      {m.deltaPct !== null ? <div className={`metric__delta ${good ? 'up' : 'down'}`}>{up ? '▲' : '▼'} {Math.abs(m.deltaPct)}% vs previous period</div>
        : <div className="metric__delta">{m.error ?? (m.pointInTime ? 'Right now' : m.note || 'No comparison yet')}</div>}
      {m.deltaPct !== null && m.note && <div className="metric__delta">{m.note}</div>}
      <Sparkline series={m.series} down={good === false} />
    </Link>
  );
}

// =================================================================================================================
function Priorities(d: D) {
  if (!d.items.length) return <Empty title="Nothing urgent" msg="No overdue work, blocked approvals or critical alerts. Nice." />;
  return (
    <ul className="list">
      {d.items.map((p: any, i: number) => (
        <li key={i}><Row to={p.path} aside={<span className={`flag flag--${p.severity === 'critical' ? 'overdue' : 'due_soon'}`}>{p.kind}</span>}>
          <T title={p.title} sub={`${p.reason}${p.dueAt ? ` · ${relative(p.dueAt)}` : ''}`} subTone={p.severity === 'critical' ? 'danger' : undefined} />
        </Row></li>
      ))}
    </ul>
  );
}

function Approvals(d: D, { refresh }: { refresh: () => void }) {
  return <ApprovalCenter d={d} refresh={refresh} />;
}

function ApprovalCenter({ d, refresh }: { d: D; refresh: () => void }) {
  const toast = useToast();
  const inv = useInvalidateHome();
  const [ask, setAsk] = useState<{ id: string; action: 'reject' | 'request_changes'; title: string } | null>(null);
  const [comment, setComment] = useState('');
  const act = useMutation({
    mutationFn: ({ id, action, c }: { id: string; action: 'approve' | 'reject' | 'request_changes'; c?: string }) => api.approvals.act(id, action, c ?? ''),
    onSuccess: (r) => { toast(`${r.reference} ${r.status === 'pending' ? 'moved to the next level' : r.status.replace('_', ' ')}`); setAsk(null); setComment(''); inv(); refresh(); },
    onError: (e) => toast(apiMessage(e), 'error'),
  });
  const c = d.counts;
  return (
    <>
      <div className="counts" style={{ padding: 12 }}>
        {[['Waiting on you', c.waitingOnMe, '/approvals'], ['Overdue', c.overdue, '/approvals'], ['Due soon', c.dueSoon, '/approvals'],
          ['High value', c.highValue, '/approvals'], ['Blocking', c.blocking, '/approvals']].map(([l, n, to]) => (
          <Link key={l as string} to={to as string} className={`count ${(l === 'Overdue' || l === 'Blocking') && Number(n) > 0 ? 'count--alert' : ''}`} style={{ color: 'inherit', textDecoration: 'none' }}>
            <strong>{n as number}</strong><span>{l as string}</span>
          </Link>
        ))}
      </div>
      {!d.items.length ? <Empty title="No pending approvals" msg="You’re all caught up." /> : (
        <ul className="list" style={{ borderTop: '1px solid var(--c-line-2)' }}>
          {d.items.map((r: any) => (
            <li key={r.id} className="list-row" style={{ alignItems: 'flex-start' }}>
              <div className="list-row__main">
                <Link to={r.path} className="list-row__title" style={{ display: 'block', color: 'inherit' }}>{r.title}</Link>
                <span className="list-row__sub" style={{ display: 'block' }}>
                  {r.type} · {r.requestedBy} · level {r.stage}/{r.levels} {r.stageName && `(${r.stageName})`} · waiting {r.waitingHours < 48 ? `${r.waitingHours}h` : `${Math.round(r.waitingHours / 24)} days`}
                  {r.dueAt && ` · due ${fmtDateTime(r.dueAt)}`}
                </span>
                <div className="row row--wrap" style={{ gap: 4, marginTop: 4 }}>{r.flags.map((f: string) => <span key={f} className={`flag flag--${f}`}>{f.replace('_', ' ')}</span>)}</div>
              </div>
              <div className="stack" style={{ gap: 6, alignItems: 'flex-end' }}>
                {r.amount && <strong className="small">{r.amountUnit === 'days' ? `${Number(r.amount)} day${Number(r.amount) === 1 ? '' : 's'}` : r.amountUnit === 'count' ? r.amount : fmtMoney(r.amount, r.currency)}</strong>}
                {r.quick ? (
                  <div className="row" style={{ gap: 4 }}>
                    <Button size="sm" loading={act.isPending && act.variables?.id === r.id && act.variables.action === 'approve'} onClick={() => act.mutate({ id: r.id, action: 'approve' })}>Approve</Button>
                    <Button size="sm" variant="outline" onClick={() => setAsk({ id: r.id, action: 'reject', title: r.title })}>Reject</Button>
                    {r.allowRequestChanges && <Button size="sm" variant="ghost" onClick={() => setAsk({ id: r.id, action: 'request_changes', title: r.title })}>Changes</Button>}
                  </div>
                ) : <Link to={r.path} className="btn btn--outline btn--sm" style={{ textDecoration: 'none' }}>Review</Link>}
              </div>
            </li>
          ))}
        </ul>
      )}
      {ask && (
        <Dialog title={ask.action === 'reject' ? `Reject: ${ask.title}` : `Request changes: ${ask.title}`} onClose={() => setAsk(null)} footer={<>
          <Button variant="outline" onClick={() => setAsk(null)}>Cancel</Button>
          <Button variant={ask.action === 'reject' ? 'danger' : 'primary'} disabled={!comment.trim()} loading={act.isPending}
                  onClick={() => act.mutate({ id: ask.id, action: ask.action, c: comment })}>{ask.action === 'reject' ? 'Reject' : 'Send back'}</Button>
        </>}>
          <label className="field"><span className="field__label">{ask.action === 'reject' ? 'Reason (shared with the requester)' : 'What needs to change?'}</span>
            <textarea className="field__input" rows={3} value={comment} onChange={(e) => setComment(e.target.value)} autoFocus /></label>
        </Dialog>
      )}
    </>
  );
}

function MyWork(d: D) {
  return <MyWorkList d={d} />;
}

function MyWorkList({ d }: { d: D }) {
  const inv = useInvalidateHome();
  const toast = useToast();
  const upd = useMutation({
    mutationFn: ({ id, body }: { id: string; body: Record<string, unknown> }) => api.tasks.update(id, body as never),
    onSuccess: () => inv(), onError: (e) => toast(apiMessage(e), 'error'),
  });
  const c = d.counts;
  const prio: Record<string, string> = { urgent: 'Critical', high: 'High', normal: 'Medium', low: 'Low' };
  return (
    <>
      <div className="counts" style={{ padding: 12 }}>
        {[['Open', c.open], ['Overdue', c.overdue, true], ['Due today', c.dueToday], ['This week', c.dueWeek], ['Follow-ups', c.followUps], ['Approvals', c.approvals]]
          .map(([l, n, alert]) => <div key={l as string} className={`count ${alert && Number(n) > 0 ? 'count--alert' : ''}`}><strong>{n as number}</strong><span>{l as string}</span></div>)}
      </div>
      {d.assigned?.length > 0 && (
        <div className="pill-list" style={{ padding: '0 12px 10px' }}>
          {d.assigned.map((a: any) => <Link key={a.kind} to={a.path} className="pill">{a.label}: <strong>{a.count}</strong></Link>)}
        </div>
      )}
      {!d.items.length ? <Empty title="No open tasks" msg="Work assigned to you appears here." /> : (
        <ul className="list" style={{ borderTop: '1px solid var(--c-line-2)' }}>
          {d.items.map((t: any) => (
            <li key={t.id} className="list-row">
              <input type="checkbox" aria-label={`Complete ${t.title}`} onChange={() => upd.mutate({ id: t.id, body: { status: 'done' } })} />
              <Link to={t.path} className="list-row__main" style={{ color: 'inherit' }}>
                <T title={t.title} subTone={t.overdue ? 'danger' : undefined}
                   sub={`${t.dueAt ? `${t.overdue ? 'Overdue · ' : 'Due '}${fmtDateTime(t.dueAt)}` : 'No due date'}${t.from ? ` · from ${t.from}` : ''}`} />
              </Link>
              <span className={`flag ${t.priority === 'urgent' ? 'flag--overdue' : t.priority === 'high' ? 'flag--due_soon' : ''}`}>{prio[t.priority]}</span>
              <button className="icon-btn" title="Snooze until tomorrow" aria-label={`Snooze ${t.title}`} onClick={() => upd.mutate({ id: t.id, body: { snoozeHours: 24 } as never })}><Icon name="clock" size={15} /></button>
            </li>
          ))}
        </ul>
      )}
    </>
  );
}

export function AlertList({ items, compact }: { items: OSAlert[]; compact?: boolean }) {
  const inv = useInvalidateHome();
  const toast = useToast();
  const act = useMutation({ mutationFn: ({ id, a }: { id: string; a: 'acknowledge' | 'resolve' }) => home.alertAction(id, a), onSuccess: () => inv(),
    onError: (e) => toast(apiMessage(e), 'error') });
  if (!items.length) return <Empty title="No open alerts" msg="Exceptions from payments, operations, partners, people, security and systems appear here." />;
  return (
    <ul className="list">
      {items.map((a) => (
        <li key={a.id} className="list-row" style={{ alignItems: 'stretch' }}>
          <span className={`sev sev--${a.severity}`} aria-label={a.severity} />
          <div className="list-row__main">
            <Link to={a.path || '#'} className="list-row__title" style={{ display: 'block', color: 'inherit', whiteSpace: 'normal' }}>{a.title}</Link>
            <span className="list-row__sub" style={{ display: 'block', whiteSpace: 'normal' }}>
              {a.severity.toUpperCase()} · {a.source} · {relative(a.lastSeenAt)}{a.location ? ` · ${a.location}` : ''} · {a.owner ? `Owner: ${a.owner.fullName}` : 'No owner'} · {a.status}
            </span>
            {!compact && a.recommendedAction && <span className="xs" style={{ display: 'block' }}>→ {a.recommendedAction}</span>}
          </div>
          {!a.personal && a.status === 'open' && <Button size="sm" variant="ghost" onClick={() => act.mutate({ id: a.id, a: 'acknowledge' })}>Take it</Button>}
          {a.status !== 'resolved' && !compact && <Button size="sm" variant="ghost" onClick={() => act.mutate({ id: a.id, a: 'resolve' })}>Resolve</Button>}
        </li>
      ))}
    </ul>
  );
}

function Alerts(d: D) {
  const c = d.counts;
  return (
    <>
      <div className="row row--wrap" style={{ padding: '10px 16px', gap: 6 }}>
        {(['critical', 'high', 'medium', 'low'] as const).map((s) => <span key={s} className="chip"><span className={`sev sev--${s}`} style={{ width: 8, height: 8, borderRadius: 4 }} />{c[s]} {s}</span>)}
      </div>
      <AlertList items={d.items} />
    </>
  );
}

function PriorityInbox(d: D) {
  if (!d.items.length) return <Empty title="Nothing critical or important" msg="Only events that need attention appear here — not every notification." />;
  return (
    <ul className="list">
      {d.items.map((x: any) => (
        <li key={x.id}><Row to={x.path || '/notifications'} aside={<span className={`flag ${x.level === 'critical' ? 'flag--overdue' : 'flag--due_soon'}`}>{x.level}</span>}>
          <T title={x.title} sub={`${x.source} · ${relative(x.at)}${x.read ? ' · seen' : ''}`} />
        </Row></li>
      ))}
    </ul>
  );
}

function QuickActions(d: D) {
  return <QuickActionGrid d={d} />;
}

function QuickActionGrid({ d }: { d: D }) {
  const inv = useInvalidateHome();
  const pins: string[] = d.items.filter((a: any) => a.pinned).map((a: any) => a.key);
  const pin = useMutation({ mutationFn: (keys: string[]) => home.pinQuickActions(keys), onSuccess: () => inv() });
  if (!d.items.length) return <Empty title="No quick actions" />;
  return (
    <div className="quick" style={{ padding: 12 }}>
      {d.items.map((a: any) => (
        <span key={a.key} className="row" style={{ gap: 0 }}>
          <Link to={a.path} className="quick__btn" onClick={() => void home.quickActionUsed(a.key).catch(() => undefined)} style={{ borderTopRightRadius: 0, borderBottomRightRadius: 0 }}>
            <Icon name={a.icon as IconName} size={15} />{a.label}
          </Link>
          <button className="quick__btn" aria-label={a.pinned ? `Unpin ${a.label}` : `Pin ${a.label}`} title={a.pinned ? 'Unpin' : 'Pin'}
                  style={{ borderLeft: 0, borderTopLeftRadius: 0, borderBottomLeftRadius: 0, padding: '0 8px', color: a.pinned ? 'var(--c-brand)' : 'var(--c-ink-4)' }}
                  onClick={() => pin.mutate(a.pinned ? pins.filter((k) => k !== a.key) : [...pins, a.key])}>★</button>
        </span>
      ))}
    </div>
  );
}

function Upcoming(d: D) {
  if (!d.total) return <Empty title="Nothing scheduled this week" msg="Deadlines, approvals, leave, holidays, reviews and interviews show here." />;
  return (
    <div>
      {d.groups.map((g: any) => g.items.length > 0 && (
        <div key={g.key}>
          <div className="palette__group" style={{ padding: '10px 16px 2px' }}>{g.label}</div>
          <ul className="list">{g.items.map((i: any) => (
            <li key={i.id}><Row to={i.path} aside={<span className="list-row__aside">{fmtDateTime(i.at)}</span>}><T title={i.title} sub={i.kind.replace('_', ' ')} /></Row></li>
          ))}</ul>
        </div>
      ))}
    </div>
  );
}

function Announcements(d: D) {
  return <AnnouncementList d={d} />;
}

function AnnouncementList({ d }: { d: D }) {
  const inv = useInvalidateHome();
  const toast = useToast();
  const act = useMutation({ mutationFn: ({ id, a }: { id: string; a: 'acknowledge' | 'dismiss' }) => home.announcementAction(id, a), onSuccess: () => inv(),
    onError: (e) => toast(apiMessage(e), 'error') });
  if (!d.items.length) return <Empty title="No announcements" msg={d.canCreate ? 'Post one from Announcements.' : undefined} />;
  return (
    <ul className="list">
      {d.items.map((a: any) => (
        <li key={a.id} className="list-row" style={{ alignItems: 'flex-start' }}>
          <span className={`sev sev--${a.priority === 'critical' ? 'critical' : a.priority === 'important' ? 'high' : 'low'}`} />
          <div className="list-row__main">
            <span className="list-row__title" style={{ display: 'block' }}>{a.title}</span>
            <span className="small" style={{ display: 'block', whiteSpace: 'pre-wrap' }}>{a.body}</span>
            <span className="xs muted">{a.categoryLabel} · {fmtDate(a.startsAt)}{a.endsAt ? ` – ${fmtDate(a.endsAt)}` : ''}{a.author ? ` · ${a.author}` : ''}</span>
          </div>
          <div className="stack" style={{ gap: 4 }}>
            {a.requiresAck && !a.acknowledged && <Button size="sm" onClick={() => act.mutate({ id: a.id, a: 'acknowledge' })}>Acknowledge</Button>}
            {a.acknowledged && <Status value="active" label="Acknowledged" />}
            {a.canDismiss && <Button size="sm" variant="ghost" onClick={() => act.mutate({ id: a.id, a: 'dismiss' })}>Dismiss</Button>}
          </div>
        </li>
      ))}
    </ul>
  );
}

function RecentActivity(d: D) {
  if (!d.items.length) return <Empty title="No recent activity" />;
  return <ul className="list">{d.items.map((e: any) => <li key={e.id}><Row aside={<span className="list-row__aside">{relative(e.at)}</span>}><T title={e.label} sub={e.resource || (e.outcome !== 'success' ? e.outcome : undefined)} /></Row></li>)}</ul>;
}

function Team(d: D) {
  const c = d.counts;
  return (
    <>
      <div className="counts" style={{ padding: 12 }}>
        {[['Direct reports', c.members], ['All reports', c.allReports], ['Open tasks', c.openTasks], ['Overdue', c.overdue, true], ['Done · 7d', c.doneWeek],
          ['Requests pending', c.requestsPending], ['Escalations', c.escalations, true], ['Away today', c.awayToday]].map(([l, n, a]) => (
          <div key={l as string} className={`count ${a && Number(n) > 0 ? 'count--alert' : ''}`}><strong>{n as number}</strong><span>{l as string}</span></div>))}
      </div>
      <ul className="list" style={{ borderTop: '1px solid var(--c-line-2)' }}>
        {d.members.map((m: any) => (
          <li key={m.id}><Row to={m.path} aside={<span className="row" style={{ gap: 6 }}>{m.away && <Status value="away" tone="info" label="Away" />}
            <span className="list-row__aside">{m.openTasks} open{m.overdue ? ` · ${m.overdue} overdue` : ''}</span></span>}>
            <T title={m.fullName} sub={m.designation} />
          </Row></li>
        ))}
      </ul>
    </>
  );
}

function Briefing(d: D) {
  return (
    <div className="card__body stack" style={{ gap: 8 }}>
      {d.lines.length ? d.lines.map((l: any, i: number) => (
        <Link key={i} to={l.path || '#'} className="row" style={{ alignItems: 'flex-start', color: 'inherit', textDecoration: 'none' }}>
          <Icon name="sparkle" size={14} /><span className="small grow">{l.text} <span className="xs muted">· {l.source}</span></span>
        </Link>
      )) : <p className="small muted">{d.empty}</p>}
      <span className="xs muted"><span className="badge-observed">Observed data</span> · {d.generatedFrom}</span>
    </div>
  );
}

function Pulse(d: D) {
  if (!d.metrics.length) return <Empty title="No business figures for your role" />;
  return (
    <>
      <div className="metrics">{d.metrics.map((m: OSPulseMetric) => <PulseTile key={m.key} m={m} />)}</div>
      <div className="note">{d.period.label}{d.location ? ` · ${d.location}` : ''} · {d.note}</div>
    </>
  );
}

function Insights(d: D) {
  if (!d.items.length) return <Empty title="No notable changes" msg={d.emptyReason} />;
  return (
    <ul className="list">
      {d.items.map((x: any, i: number) => (
        <li key={i}><Row to={x.path} aside={<span className={`flag ${x.good ? 'flag--high_value' : 'flag--overdue'}`}>{x.direction === 'up' ? '▲' : '▼'}</span>}>
          <span className="badge-observed">Observed</span>
          <T title={x.title} sub={`${x.what} ${x.why}. ${x.period} · ${x.source}`} />
          {x.nextStep && <span className="xs" style={{ display: 'block' }}><span className="badge-suggestion">Suggested next step</span> {x.nextStep}</span>}
        </Row></li>
      ))}
    </ul>
  );
}

function Opportunities(d: D) {
  return (
    <>
      {!d.items.length ? <Empty title="No opportunities spotted" msg="Not enough change in the data for this period." /> : (
        <ul className="list">
          {d.items.map((x: any, i: number) => (
            <li key={i}><Row to={x.path}>
              <span className="xs" style={{ display: 'block' }}><span className="badge-observed">Observed data</span> · {x.source} · {x.period}</span>
              <span className="small" style={{ display: 'block' }}>{x.observed}</span>
              <span className="xs" style={{ display: 'block' }}><span className="badge-suggestion">Rule-based suggestion</span> {x.suggestion}</span>
            </Row></li>
          ))}
        </ul>
      )}
      <div className="note">{d.disclaimer}</div>
    </>
  );
}

function Ecosystem(d: D) {
  return (
    <>
      <div className="xs muted" style={{ padding: '8px 16px 0' }}>Participants</div>
      <MetricTiles metrics={d.participants.map((x: any) => ({ ...x, format: 'number' }))} />
      <div className="xs muted" style={{ padding: '8px 16px 0' }}>Activity · {d.period}</div>
      <MetricTiles metrics={d.activity.map((x: any) => ({ ...x, format: 'number' }))} />
      <div className="note"><strong>Platform transactions (gross): {fmtMoney(d.transactions.platformGmv)}</strong>. {d.transactions.note}</div>
    </>
  );
}

function Finance(d: D) {
  return (
    <>
      <div className="table-wrap"><table className="table"><tbody>
        {d.lines.map((l: any) => (
          <tr key={l.key}><td>{l.label}{l.explain && <div className="xs muted">{l.explain}</div>}</td>
            <td className="num">{l.available ? (l.format === 'number' ? fmtNumber(l.value) : fmtMoney(l.value)) : <span className="muted small">Not available yet</span>}</td></tr>
        ))}
      </tbody></table></div>
      <div className="note">{d.period} · {d.note}</div>
    </>
  );
}

function Metrics(d: D) {
  return (
    <>
      <MetricTiles metrics={d.metrics} />
      {d.breakdown?.length > 0 && <div className="pill-list" style={{ padding: '10px 16px' }}>{d.breakdown.map((b: any) => <span key={b.label} className="pill">{b.label}: <strong>{b.value}</strong></span>)}</div>}
      {d.note && <div className="note">{d.period ? `${d.period} · ` : ''}{d.note}</div>}
    </>
  );
}

function Partners(d: D) {
  const max = Math.max(1, ...d.stages.map((s: any) => s.value));
  return (
    <div className="card__body stack">
      <div className="bars">{d.stages.map((s: any) => (
        <div key={s.key} className="bars__row"><span className="ellipsis">{s.label}</span><span className="bars__track"><span style={{ width: `${(s.value / max) * 100}%` }} /></span><strong className="num">{s.value}</strong></div>
      ))}</div>
      <div className="row row--wrap small"><span className="chip">New this week: {d.newWeek}</span><span className="chip">Documents expiring · 30d: {d.documentsExpiring}</span>
        <span className="chip">Documents to review: {d.documentsPending}</span></div>
    </div>
  );
}

function System(d: D) {
  return (
    <div className="card__body stack" style={{ gap: 6 }}>
      <Status value={d.overall} label={d.overall === 'ok' ? 'All systems normal' : d.overall === 'warning' ? 'Needs attention' : 'Problem detected'} />
      {d.checks.map((c: any) => <div key={c.key} className="row row--between small"><span>{c.label}</span><Status value={c.status} label={c.status.replace('_', ' ')} /></div>)}
      {d.jobs.map((j: any) => <div key={j.key} className="row row--between xs muted"><span>{j.label}</span><span>{j.lastRun ? relative(j.lastRun) : 'not run yet'}</span></div>)}
    </div>
  );
}

function Security(d: D) {
  return (
    <div className="card__body stack" style={{ gap: 8 }}>
      <div className="row row--between small"><span>Two-step verification</span><Status value={d.mfaEnabled ? 'active' : 'warning'} label={d.mfaEnabled ? 'On' : 'Off'} /></div>
      <div className="row row--between small"><span>Signed-in devices</span><strong>{d.activeSessions}</strong></div>
      <div className="row row--between small"><span>Last sign-in</span><span className="muted">{fmtDateTime(d.lastLoginAt)}</span></div>
      {d.mfaBlocked > 0 && <Link to="/settings/security?setup=mfa" className="small">{d.mfaBlocked} permissions waiting for two-step verification →</Link>}
    </div>
  );
}

const peopleList = (title: string, emptyMsg: string, line: (x: any) => [string, string, boolean?]) => (d: D) =>
  !d.items.length ? <Empty title={title} msg={emptyMsg} /> : (
    <ul className="list">{d.items.map((x: any, i: number) => { const [t, s, hot] = line(x); return <li key={x.id ?? i}><Row to={x.path}><T title={t} sub={s} subTone={hot ? 'danger' : undefined} /></Row></li>; })}</ul>
  );

export const RENDERERS: Record<string, R> = {
  priorities: Priorities, approvals: Approvals, my_work: MyWork, alerts: Alerts, priority_inbox: PriorityInbox, quick_actions: QuickActions,
  upcoming: Upcoming, announcements: Announcements, recent_activity: RecentActivity, team: Team, ai_briefing: Briefing, business_pulse: Pulse,
  insights: Insights, opportunities: Opportunities, risk_watch: (d) => <AlertList items={d.items} />, ecosystem: Ecosystem,
  services_snapshot: (d) => <><MetricTiles metrics={d.metrics} /><div className="note">{d.period} · {d.note}</div></>, partner_snapshot: Partners,
  finance_snapshot: Finance, operations_overview: Metrics, security_overview: Metrics, system_status: System, security: Security,
  people_overview: Metrics,
  new_joiners: peopleList('No recent or upcoming joiners', 'People joining in the last or next 30 days.', (x) => [x.fullName, `${x.designation ?? ''} · ${x.department ?? ''} · ${x.upcoming ? 'joins' : 'joined'} ${fmtDate(x.joinedOn)}`]),
  pending_leave: (d) => !d.items.length ? <Empty title="No leave waiting for you" msg={d.pendingInScope != null ? `${d.pendingInScope} pending in your scope.` : undefined} />
    : <ul className="list">{d.items.map((x: any) => <li key={x.id}><Row to={x.path} aside={x.startsSoon && <span className="flag flag--due_soon">soon</span>}>
      <T title={`${x.employee} · ${x.type}`} sub={`${fmtDate(x.start)} – ${fmtDate(x.end)} · ${x.days} days`} /></Row></li>)}</ul>,
  open_positions: peopleList('No open positions', 'Approved positions that still need people.', (x) => [`${x.title} (${x.open} open)`, `${x.code} · ${x.department} · ${x.candidates} candidates`]),
  upcoming_reviews: peopleList('No reviews to write', 'Self, manager and peer reviews assigned to you.', (x) => [x.employee, `${x.kind} · ${x.cycle}${x.dueOn ? ` · due ${fmtDate(x.dueOn)}` : ''}`, x.overdue]),
  document_expiries: peopleList('No expiring documents', 'Employee documents and certifications expiring in 60 days.', (x) => [`${x.employee}: ${x.title}`, `${x.expired ? 'Expired' : 'Expires'} ${fmtDate(x.expiresOn)}`, x.expired]),
  attendance_exceptions: peopleList('No attendance exceptions', 'Missing check-outs, late arrivals and unrecorded working days.', (x) => [x.fullName, x.label, x.kind === 'absent']),
  probation_ending: peopleList('No probations ending', 'Probation periods ending in the next 30 days.', (x) => [x.fullName, `Probation ${x.overdue ? 'ended' : 'ends'} ${fmtDate(x.endsOn)}`, x.overdue]),
  training_due: peopleList('No training due', 'Courses due in the next two weeks.', (x) => [x.course, `${x.mine ? 'You' : x.employee} · due ${fmtDate(x.dueOn)}${x.mandatory ? ' · mandatory' : ''}`, x.overdue]),
};
