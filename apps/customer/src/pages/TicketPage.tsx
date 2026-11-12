import { useRef, useState } from 'react';
import { Link, useLocation, useParams } from 'react-router-dom';
import { useInfiniteQuery, useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { ApiError, type SupportMessage } from '@click/api';
import { Button, EmptyState, ErrorState, Icon, Skeleton, useConfirm, useToast } from '../components/ui';
import { MoneyHead, Pill, dateOf, dateTimeOf, iconFor, timeOf } from '../features/money/parts';
import { api } from '../lib/api';
import { statusTone } from './HelpPage';

const MAX = 5 * 1024 * 1024;
const TYPES = ['image/jpeg', 'image/png', 'image/webp', 'application/pdf'];

/** One support request: what was asked, the related order or booking, and the conversation with Click. Support. */
export function TicketPage() {
  const { id = '' } = useParams();
  const location = useLocation();
  const qc = useQueryClient();
  const toast = useToast();
  const confirm = useConfirm();
  const t = useQuery({ queryKey: ['customer', 'support', id], queryFn: () => api.money.support.get(id) });
  const msgs = useQuery({ queryKey: ['customer', 'support', id, 'messages'], queryFn: () => api.money.support.messages(id), refetchInterval: 30_000 });
  const [body, setBody] = useState('');
  const [file, setFile] = useState<File | null>(null);
  const [err, setErr] = useState('');
  const fileRef = useRef<HTMLInputElement>(null);
  const refresh = () => qc.invalidateQueries({ queryKey: ['customer', 'support'] });
  const send = useMutation({
    mutationFn: () => api.money.support.send(id, body.trim(), file),
    onSuccess: () => { setBody(''); setFile(null); if (fileRef.current) fileRef.current.value = ''; refresh(); },
    onError: (e) => setErr(e instanceof ApiError ? e.message : 'Couldn’t send. Try again.'),
  });
  const act = useMutation({
    mutationFn: (a: 'close' | 'reopen') => api.money.support.action(id, a),
    onSuccess: (_, a) => { refresh(); toast(a === 'close' ? 'Request closed' : 'Request reopened'); },
    onError: (e) => toast(e instanceof ApiError ? e.message : 'Couldn’t update.', 'error'),
  });

  if (t.isError) {
    return <div className="mn-page"><MoneyHead title="Support request" back="/help" />{t.error instanceof ApiError && t.error.status === 404
      ? <EmptyState icon="help" title="Request not found" action={<Link to="/help" className="btn btn--outline">Help & Support</Link>} />
      : <ErrorState error={t.error} onRetry={() => t.refetch()} />}</div>;
  }
  if (!t.data) return <div className="mn-page"><MoneyHead title="Support request" back="/help" /><Skeleton height={300} /></div>;
  const x = t.data;
  const closed = x.status === 'closed';
  const done = x.status === 'resolved' || closed;
  const pickFile = (f: File | null) => {
    setErr('');
    if (!f) return setFile(null);
    if (!TYPES.includes(f.type)) return setErr('Attach a JPEG, PNG or WebP image, or a PDF.');
    if (f.size > MAX) return setErr('Attachments can be up to 5 MB.');
    setFile(f);
  };

  return (
    <div className="mn-page">
      <MoneyHead title={x.reference} back="/help/tickets" />
      {(location.state as { created?: boolean } | null)?.created && (
        <div className="mn-banner mn-banner--ok" role="status"><Icon name="check" size={20} /><div><strong>Request sent</strong>
          <p className="small">Replies from Click. Support appear here, and you’ll get a notification.</p></div></div>
      )}
      <section className="mn-card mn-ticket">
        <div className="mn-ticket__top"><Pill tone={statusTone(x.status)}>{x.statusLabel}</Pill>{x.priority !== 'normal' && <Pill tone="pending">{x.priorityLabel}</Pill>}</div>
        <h2>{x.subject}</h2>
        <span className="small mn-muted"><Icon name={iconFor(x.category)} size={14} /> {x.categoryLabel}{x.issueType ? ` · ${x.issueType}` : ''} · opened {dateTimeOf(x.createdAt)}</span>
        {x.related && <Link to={x.related.link} className="mn-row mn-row--card"><span className="mn-row__icon"><Icon name="receipt" size={18} /></span>
          <span className="mn-row__text"><strong>{x.related.label}</strong><span className="small mn-muted">Attached to this request</span></span><Icon name="right" size={16} /></Link>}
      </section>

      <ol className="mn-chat" aria-label="Conversation">
        <li className="mn-msg mn-msg--me"><p>{x.message}</p><span className="small mn-muted">You · {timeOf(x.createdAt)}</span></li>
        {msgs.data?.results.map((m) => <Message key={m.id} m={m} />)}
      </ol>

      {closed ? (
        <div className="mn-card mn-center"><p className="mn-muted">This request is closed.</p>
          <Button variant="secondary" loading={act.isPending} onClick={() => act.mutate('reopen')}>Reopen request</Button></div>
      ) : (
        <form className="mn-compose" onSubmit={(e) => { e.preventDefault(); if (!body.trim() && !file) return setErr('Write a message or attach a file.'); send.mutate(); }}>
          {x.status === 'awaiting_customer' && <p className="small mn-warn">Click. Support is waiting for your reply.</p>}
          <textarea rows={2} value={body} onChange={(e) => setBody(e.target.value.slice(0, 4000))} placeholder="Write a reply" aria-label="Reply" />
          <input ref={fileRef} type="file" accept="image/jpeg,image/png,image/webp,application/pdf" hidden onChange={(e) => pickFile(e.target.files?.[0] ?? null)} />
          {file && <div className="mn-file"><Icon name="receipt" size={18} /><span className="truncate">{file.name}</span><button type="button" className="mn-link small" onClick={() => setFile(null)}>Remove</button></div>}
          {err && <p className="mn-error small" role="alert">{err}</p>}
          <div className="mn-row2">
            <button type="button" className="btn btn--outline btn--sm" onClick={() => fileRef.current?.click()} aria-label="Attach a file"><Icon name="camera" size={16} /> Attach</button>
            <Button type="submit" size="sm" loading={send.isPending}><Icon name="send" size={16} /> Send</Button>
          </div>
        </form>
      )}
      <div className="mn-row2">
        {done && !closed && <Button variant="secondary" loading={act.isPending && act.variables === 'reopen'} onClick={() => act.mutate('reopen')}>Still a problem? Reopen</Button>}
        {!closed && <button type="button" className="mn-link small" onClick={async () => { if (await confirm({ title: 'Close this request?', message: 'You can reopen it later if you need to.', confirmLabel: 'Close request' })) act.mutate('close'); }}>Close request</button>}
      </div>
    </div>
  );
}

function Message({ m }: { m: SupportMessage }) {
  const [busy, setBusy] = useState(false);
  const open = async () => {
    setBusy(true);
    try {
      const b = await api.money.support.attachment(m.id);
      const url = URL.createObjectURL(b);
      const a = document.createElement('a'); // a download link works after an await (a new window would be blocked)
      a.href = url;
      a.download = m.attachment?.name ?? 'attachment';
      document.body.appendChild(a);
      a.click();
      a.remove();
      setTimeout(() => URL.revokeObjectURL(url), 60_000);
    } finally { setBusy(false); }
  };
  return (
    <li className={`mn-msg ${m.sender === 'customer' ? 'mn-msg--me' : ''}`}>
      {m.body && <p>{m.body}</p>}
      {m.attachment && <button type="button" className="mn-file" onClick={open} disabled={busy}><Icon name={m.attachment.type === 'application/pdf' ? 'receipt' : 'camera'} size={16} />
        <span className="truncate">{m.attachment.name}</span><span className="small mn-muted">{Math.ceil(m.attachment.size / 1024)} KB</span></button>}
      <span className="small mn-muted">{m.sender === 'customer' ? 'You' : m.senderLabel} · {timeOf(m.createdAt)}</span>
    </li>
  );
}

/** My support requests: every request, newest first, with its status. */
export function TicketsPage() {
  const list = useInfiniteQuery({
    queryKey: ['customer', 'support', 'all'], queryFn: ({ pageParam }) => api.money.support.list(pageParam),
    initialPageParam: 1, getNextPageParam: (l) => (l.hasNext ? l.page + 1 : undefined),
  });
  const rows = list.data?.pages.flatMap((p) => p.results) ?? [];
  return (
    <div className="mn-page">
      <MoneyHead title="My support requests" back="/help" action={<Link to="/help/new" className="mn-head__home" aria-label="New request"><Icon name="plus" size={20} /></Link>} />
      {list.isError ? <ErrorState error={list.error} onRetry={() => list.refetch()} /> : !list.data ? <Skeleton height={260} /> : rows.length === 0 ? (
        <EmptyState icon="help" title="No requests yet" message="When you contact Click. Support, your requests and replies appear here." action={<Link to="/help/new" className="btn btn--primary">Contact support</Link>} />
      ) : (
        <>
          <ul className="mn-list">{rows.map((t) => (
            <li key={t.id}><Link to={`/help/tickets/${t.id}`} className="mn-row"><span className="mn-row__icon"><Icon name={iconFor(t.category)} size={18} /></span>
              <span className="mn-row__text"><strong className="truncate">{t.subject}</strong>
                <span className="small mn-muted truncate">{t.reference}{t.related ? ` · ${t.related.label}` : ''} · {dateOf(t.lastUpdate)}</span></span>
              <Pill tone={statusTone(t.status)}>{t.statusLabel}</Pill></Link></li>
          ))}</ul>
          {list.hasNextPage && <Button variant="secondary" block loading={list.isFetchingNextPage} onClick={() => list.fetchNextPage()}>Load more</Button>}
        </>
      )}
    </div>
  );
}
