import { useState } from 'react';
import { Link, useLocation, useNavigate, useParams, useSearchParams } from 'react-router-dom';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { ApiError, type EventEnquiry, type EventPlanDetail } from '@click/api';
import { Button, EmptyState, ErrorState, Icon, Sheet, Skeleton, useConfirm, useToast } from '../components/ui';
import { useThemeOverride } from '../components/layout/AppShell';
import { fmtDate, ProviderCardView, ProviderMark } from '../features/events/parts';
import { api } from '../lib/api';
import { formatMoney } from '../lib/format';

type Tab = 'quotes' | 'teams' | 'checklist';

/** One event plan: quotes from teams (accept → book, ask for changes, decline, message), matching teams to ask, and a
 *  checklist built from the event type and the services needed (ticked automatically as bookings cover them). */
export function EventPlanPage() {
  useThemeOverride('events');
  const { id = '' } = useParams();
  const [sp, setSp] = useSearchParams();
  const navigate = useNavigate();
  const location = useLocation();
  const toast = useToast();
  const confirm = useConfirm();
  const qc = useQueryClient();
  const key = ['eventhub', 'plan', id];
  const q = useQuery({ queryKey: key, queryFn: () => api.eventHub.plan(id) });
  const plan = q.data;
  const tab: Tab = (sp.get('tab') as Tab) || (plan && plan.enquiries.length === 0 ? 'teams' : 'quotes');
  const [kind, setKind] = useState<string>('');
  const matches = useQuery({ queryKey: ['eventhub', 'matches', id, kind], queryFn: () => api.eventHub.matches(id, kind || undefined), enabled: tab === 'teams' && !!plan });
  const [picked, setPicked] = useState<string[]>([]);
  const [message, setMessage] = useState('');
  const [task, setTask] = useState('');
  const [changes, setChanges] = useState<EventEnquiry | null>(null);
  const [changeNote, setChangeNote] = useState('');
  const [thread, setThread] = useState<EventEnquiry | null>(null);
  const [reply, setReply] = useState('');
  const setPlan = (p: EventPlanDetail) => qc.setQueryData(key, p);
  const fail = (e: unknown) => toast(e instanceof ApiError ? e.message : 'Something went wrong.', 'error');

  const send = useMutation({
    mutationFn: () => api.eventHub.enquire(id, picked, message.trim()),
    onSuccess: (p) => { setPlan(p); setPicked([]); setMessage(''); qc.invalidateQueries({ queryKey: ['eventhub', 'matches', id] }); setSp({ tab: 'quotes' }, { replace: true }); toast('Quote requests sent'); },
    onError: fail,
  });
  const enquiryAct = useMutation({
    mutationFn: ({ e, action, note }: { e: EventEnquiry; action: 'reject' | 'changes' | 'message' | 'withdraw'; note?: string }) => api.eventHub.enquiry(e.id, action, note),
    onSuccess: (e, v) => {
      qc.setQueryData<EventPlanDetail>(key, (p) => (p ? { ...p, enquiries: p.enquiries.map((x) => (x.id === e.id ? e : x)) } : p));
      if (v.action === 'message') { setReply(''); setThread(e); } else { setChanges(null); setChangeNote(''); }
      toast({ reject: 'Quote declined', changes: 'Change request sent', message: 'Message sent', withdraw: 'Request withdrawn' }[v.action]);
    },
    onError: fail,
  });
  const taskAct = useMutation({
    mutationFn: (a: { kind: 'add' } | { kind: 'toggle'; item: string; done: boolean } | { kind: 'remove'; item: string }) =>
      a.kind === 'add' ? api.eventHub.addTask(id, task.trim()) : a.kind === 'toggle' ? api.eventHub.toggleTask(id, a.item, a.done) : api.eventHub.removeTask(id, a.item),
    onSuccess: (p, a) => { setPlan(p); if (a.kind === 'add') setTask(''); },
    onError: fail,
  });
  const cancelPlan = useMutation({ mutationFn: () => api.eventHub.cancelPlan(id), onSuccess: (p) => { setPlan(p); toast('Plan cancelled'); }, onError: fail });

  if (q.isError) return <div className="ev-page"><ErrorState error={q.error} onRetry={() => q.refetch()} /></div>;
  if (!plan) return <div className="ev-page"><Skeleton height={180} radius={24} /><Skeleton height={320} radius={22} /></div>;
  const closed = plan.status === 'cancelled' || plan.status === 'done';
  const quotesWaiting = plan.enquiries.filter((e) => e.quotes[0]?.status === 'pending').length;

  return (
    <div className="ev-page" data-theme="events" style={{ ['--ev-accent' as string]: plan.eventType.accent }}>
      <Link to="/events/mine" className="ev-back"><Icon name="back" size={18} /> My events</Link>
      {(location.state as { created?: boolean } | null)?.created && (
        <div className="ev-banner" role="status"><Icon name="check" size={18} /> Plan saved. {plan.enquiries.length ? 'Your request was sent — you’ll be notified when the quote arrives.' : 'Pick up to 5 teams below to ask for quotes.'}</div>
      )}
      <header className="ev-planhead">
        <span className="ev-kicker">{plan.number} · {plan.statusLabel}</span>
        <h1>{plan.title}</h1>
        <div className="ev-planfacts small">
          <span><Icon name="ticket" size={14} /> {plan.dateFlexible ? `Flexible${plan.dateNote ? ` · ${plan.dateNote}` : ''}` : `${fmtDate(plan.date)}${plan.startTime ? `, ${plan.startTime}` : ''}`}</span>
          <span><Icon name="team" size={14} /> {plan.guests} guests</span>
          <span><Icon name="pin" size={14} /> {plan.address.line2 || plan.address.line1}</span>
          <span><Icon name="wallet" size={14} /> {plan.budget.max ? `Up to ${formatMoney(plan.budget.max)}` : plan.budget.min ? `${formatMoney(plan.budget.min)}+` : 'Flexible budget'}</span>
        </div>
        <div className="ev-chips">{plan.services.map((s) => <span key={s.slug} className="ev-chip">{s.name}</span>)}</div>
        {plan.requirements && <p className="small ev-req">“{plan.requirements}”</p>}
        {plan.attachments.length > 0 && <div className="ev-photos">{plan.attachments.map((a) => <a key={a.id} className="ev-thumb" href={a.src} target="_blank" rel="noreferrer"><img src={a.thumb} alt="Reference" /></a>)}</div>}
        <div className="ev-progressline" aria-label={`Checklist ${plan.progress.done} of ${plan.progress.total} done`}>
          <span style={{ width: `${plan.progress.total ? (plan.progress.done / plan.progress.total) * 100 : 0}%` }} />
        </div>
        <span className="small ev-muted">{plan.progress.done} of {plan.progress.total} checklist items done</span>
      </header>

      {plan.bookingList.length > 0 && (
        <div className="ev-mine">{plan.bookingList.map((b) => (
          <Link key={b.id} to={`/events/bookings/${b.id}`} className="ev-minecard" style={{ ['--ev-accent' as string]: b.provider.accent }}>
            <span className="ev-kicker">{b.number} · {b.statusLabel}</span><strong>{b.title}</strong><span className="small ev-muted">{formatMoney(b.total)} · {b.paymentStatusLabel}</span>
          </Link>
        ))}</div>
      )}

      <div className="ev-seg ev-seg--wide" role="tablist" aria-label="Plan">
        <button type="button" role="tab" aria-selected={tab === 'quotes'} onClick={() => setSp({ tab: 'quotes' }, { replace: true })}>Quotes{quotesWaiting ? ` (${quotesWaiting})` : ''}</button>
        <button type="button" role="tab" aria-selected={tab === 'teams'} onClick={() => setSp({ tab: 'teams' }, { replace: true })}>Find teams</button>
        <button type="button" role="tab" aria-selected={tab === 'checklist'} onClick={() => setSp({ tab: 'checklist' }, { replace: true })}>Checklist</button>
      </div>

      {tab === 'quotes' && (plan.enquiries.length === 0 ? (
        <EmptyState icon="receipt" title="No quote requests yet" message="Choose teams that fit your event and ask them for a quote." action={<Button onClick={() => setSp({ tab: 'teams' })}>Find teams</Button>} />
      ) : (
        <div className="ev-enqs">{plan.enquiries.map((e) => {
          const qt = e.quotes[0];
          const optional = qt?.items.filter((i) => i.optional) ?? [];
          return (
            <article key={e.id} className="ev-enq" style={{ ['--ev-accent' as string]: e.provider.accent }}>
              <header>
                <ProviderMark p={e.provider} size={44} />
                <div><Link to={`/events/providers/${e.provider.id}`}><strong>{e.provider.name}</strong></Link><span className={`ev-status ev-status--${e.status} small`}>{e.statusLabel}</span></div>
              </header>
              {qt && qt.status !== 'superseded' ? (
                <div className="ev-quote">
                  <span className="ev-kicker">Quote v{qt.version}{qt.validUntil ? ` · valid until ${fmtDate(qt.validUntil, { day: 'numeric', month: 'short' })}` : ''}</span>
                  <ul>{qt.items.map((i, n) => <li key={n}><span>{i.label}{i.optional && <span className="ev-chip">Optional</span>}</span><span>{formatMoney(i.amount)}</span></li>)}</ul>
                  <div className="ev-quote__total"><span>Required items {formatMoney(qt.amount)} + tax {formatMoney(qt.tax)}</span><strong>{formatMoney(qt.total)}</strong></div>
                  {(qt.durationHours || qt.teamSize) && <p className="small ev-muted">{qt.durationHours ? `${qt.durationHours} hrs` : ''}{qt.durationHours && qt.teamSize ? ' · ' : ''}{qt.teamSize ? `team of ${qt.teamSize}` : ''}</p>}
                  {qt.notes && <p className="small">{qt.notes}</p>}
                  {qt.terms && <p className="small ev-muted">Terms: {qt.terms}</p>}
                  {qt.status === 'pending' && !qt.expired && !closed ? (
                    <div className="ev-row">
                      <Button onClick={() => navigate(`/events/book?plan=${plan.id}&quote=${qt.id}`)}>Accept & book{optional.length ? '…' : ''}</Button>
                      <Button variant="secondary" onClick={() => setChanges(e)}>Request changes</Button>
                      <Button variant="ghost" onClick={async () => { if (await confirm({ title: `Decline ${e.provider.name}’s quote?`, confirmLabel: 'Decline' })) enquiryAct.mutate({ e, action: 'reject' }); }}>Decline</Button>
                    </div>
                  ) : qt.expired && qt.status === 'pending' ? <p className="small">This quote has expired. Message the team for a new one.</p> : null}
                  {qt.customerNote && <p className="small ev-muted">You: {qt.customerNote}</p>}
                </div>
              ) : e.status === 'requested' ? <p className="small ev-muted">Waiting for {e.provider.name} to quote. You’ll get a notification.</p>
                : e.status === 'revision' ? <p className="small ev-muted">You asked for changes. Waiting for a revised quote.</p> : null}
              {e.bookingId && <Link to={`/events/bookings/${e.bookingId}`} className="ev-link small">View booking</Link>}
              <div className="ev-enq__foot">
                <button type="button" className="ev-link small" onClick={() => setThread(e)}><Icon name="send" size={13} /> Messages{e.messages.length ? ` (${e.messages.length})` : ''}</button>
                {['requested', 'quoted', 'revision'].includes(e.status) && !closed && (
                  <button type="button" className="ev-link small ev-muted" onClick={() => enquiryAct.mutate({ e, action: 'withdraw' })}>Withdraw request</button>
                )}
              </div>
            </article>
          );
        })}</div>
      ))}

      {tab === 'teams' && (closed ? <p className="ev-note">This plan is {plan.statusLabel.toLowerCase()}.</p> : (
        <>
          <div className="ev-toolbar">
            {[['', 'All'], ['team', 'Event teams'], ['vendor', 'Specialists'], ['venue', 'Venues']].map(([k, l]) => (
              <button key={k} type="button" className={`ev-chipbtn${kind === k ? ' is-on' : ''}`} aria-pressed={kind === k} onClick={() => setKind(k!)}>{l}</button>
            ))}
          </div>
          <p className="small ev-muted">Teams that serve your location, take {plan.guests} guests and your event type{plan.date ? `, and are free on ${fmtDate(plan.date)}` : ''}. Pick up to 5.</p>
          {matches.isError ? <ErrorState error={matches.error} onRetry={() => matches.refetch()} /> : matches.isPending ? <Skeleton height={300} radius={22} /> : matches.data.results.length === 0 ? (
            <EmptyState icon="team" title="No matching teams yet" message="Try another date or fewer services, or check back as more teams join Click." />
          ) : (
            <div className="ev-grid">{matches.data.results.map((m) => {
              const on = picked.includes(m.id);
              return (
                <div key={m.id} className="ev-match">
                  <p className="small ev-covers">Covers {m.covers.length} of {plan.services.length}: {m.covers.map((c) => plan.services.find((s) => s.slug === c)?.name).join(', ')}</p>
                  <ProviderCardView p={m} compact extra={m.contacted ? <span className="ev-chip">Asked</span> : (
                    <button type="button" className={`ev-btn ev-btn--sm${on ? '' : ' ev-btn--ghost'}`} aria-pressed={on} disabled={!on && picked.length >= 5}
                      onClick={() => setPicked((cur) => (cur.includes(m.id) ? cur.filter((x) => x !== m.id) : cur.length >= 5 ? cur : [...cur, m.id]))}>{on ? <><Icon name="check" size={14} /> Selected</> : 'Select'}</button>
                  )} />
                </div>
              );
            })}</div>
          )}
          {picked.length > 0 && (
            <div className="ev-sendbar">
              <input className="ev-input" value={message} maxLength={600} onChange={(e) => setMessage(e.target.value)} placeholder="Add a note for the teams (optional)" aria-label="Note for the teams" />
              <Button loading={send.isPending} onClick={() => send.mutate()}>Request {picked.length} quote{picked.length > 1 ? 's' : ''}</Button>
            </div>
          )}
        </>
      ))}

      {tab === 'checklist' && (
        <section className="ev-sec">
          <h2 className="ev-h2">Your Event Checklist</h2>
          <ul className="ev-checklist">{plan.checklist.map((c) => (
            <li key={c.id} className={c.done ? 'is-done' : ''}>
              <label><input type="checkbox" checked={c.done} disabled={taskAct.isPending} onChange={(e) => taskAct.mutate({ kind: 'toggle', item: c.id, done: e.target.checked })} />
                <span>{c.label}{c.auto && <span className="ev-chip">Covered by a booking</span>}</span></label>
              {c.custom && <button type="button" className="ev-x" aria-label={`Remove ${c.label}`} onClick={() => taskAct.mutate({ kind: 'remove', item: c.id })}><Icon name="close" size={14} /></button>}
            </li>
          ))}</ul>
          <form className="ev-addtask" onSubmit={(e) => { e.preventDefault(); if (task.trim().length > 1) taskAct.mutate({ kind: 'add' }); }}>
            <input className="ev-input" value={task} maxLength={120} onChange={(e) => setTask(e.target.value)} placeholder="Add your own task" aria-label="New checklist task" />
            <Button type="submit" variant="secondary" disabled={task.trim().length < 2}>Add</Button>
          </form>
        </section>
      )}

      {!closed && plan.bookingList.every((b) => !b.isActive) && (
        <button type="button" className="ev-link small ev-muted" style={{ alignSelf: 'center' }}
          onClick={async () => { if (await confirm({ title: 'Cancel this plan?', message: 'Open quote requests are withdrawn.', confirmLabel: 'Cancel plan' })) cancelPlan.mutate(); }}>Cancel this plan</button>
      )}

      <Sheet open={!!changes} onClose={() => setChanges(null)} label="Request changes">
        {changes && (
          <div className="ev-sheet">
            <h2>Ask {changes.provider.name} for changes</h2>
            <textarea className="ev-textarea" rows={4} maxLength={600} value={changeNote} onChange={(e) => setChangeNote(e.target.value)} placeholder="e.g. Can you add a cake and drop the photographer?" aria-label="What should change" />
            <Button block disabled={changeNote.trim().length < 3} loading={enquiryAct.isPending} onClick={() => enquiryAct.mutate({ e: changes, action: 'changes', note: changeNote })}>Send change request</Button>
          </div>
        )}
      </Sheet>
      <Sheet open={!!thread} onClose={() => setThread(null)} label="Messages">
        {thread && (
          <div className="ev-sheet">
            <h2>Messages with {thread.provider.name}</h2>
            <p className="small ev-muted">Kept on Click. — phone numbers aren’t shared.</p>
            <ul className="ev-thread">{thread.messages.length === 0 ? <li className="small ev-muted">No messages yet.</li> : thread.messages.map((m) => (
              <li key={m.id} className={m.fromCustomer ? 'is-me' : ''}><span>{m.body}</span><span className="small ev-muted">{new Date(m.at).toLocaleString('en-IN', { day: 'numeric', month: 'short', hour: 'numeric', minute: '2-digit' })}</span></li>
            ))}</ul>
            <form className="ev-addtask" onSubmit={(e) => { e.preventDefault(); if (reply.trim().length > 1) enquiryAct.mutate({ e: thread, action: 'message', note: reply }); }}>
              <input className="ev-input" value={reply} maxLength={1000} onChange={(e) => setReply(e.target.value)} placeholder="Ask a question" aria-label="Message" />
              <Button type="submit" loading={enquiryAct.isPending} disabled={reply.trim().length < 2}>Send</Button>
            </form>
          </div>
        )}
      </Sheet>
    </div>
  );
}
