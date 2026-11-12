import { useEffect, useRef, useState, type FormEvent, type KeyboardEvent } from 'react';
import { Link, useNavigate, useSearchParams } from 'react-router-dom';
import { useInfiniteQuery, useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { ApiError, type BuddyAttachment, type BuddyConversation } from '@click/api';
import { useAuth } from '../auth/AuthProvider';
import { Icon, Sheet, Skeleton, useConfirm } from '../components/ui';
import { useCapabilities } from '../features/assist/useCapabilities';
import { useRecorder } from '../features/assist/useRecorder';
import { ConfirmCard, MessageView, QUICK } from '../features/buddy/parts';
import { useBuddyChat } from '../features/buddy/useBuddyChat';
import { api } from '../lib/api';
import { useDeliveryLocation } from '../location/LocationProvider';

const desktopEnter = () => typeof window !== 'undefined' && window.matchMedia?.('(pointer: fine)').matches;

/**
 * Buddy MAN — Click.'s conversational workspace (its own layout: no Click header or bottom navigation; the Home icon
 * returns to Click). Conversations are stored on the server and only ever shown again, never re-run. Buddy answers
 * from real Click data, runs safe actions through the server's action layer, and asks before anything that needs a
 * confirmation. It never pays: payments happen in Click.'s normal checkout.
 */
export function BuddyPage() {
  const { status } = useAuth();
  const navigate = useNavigate();
  const confirm = useConfirm();
  const [sp, setSp] = useSearchParams();
  const cid = sp.get('c');
  const chat = useBuddyChat('man', cid, (id) => setSp({ c: id }, { replace: true }));
  const [draft, setDraft] = useState('');
  const [historyOpen, setHistoryOpen] = useState(false);
  const [attachOpen, setAttachOpen] = useState(false);
  const [attachment, setAttachment] = useState<(BuddyAttachment & { label: string }) | null>(null);
  const [online, setOnline] = useState(typeof navigator === 'undefined' ? true : navigator.onLine);
  const endRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);
  const caps = useCapabilities();
  const transcribe = useMutation({
    mutationFn: (audio: Blob) => api.customer.assistant.transcribe(audio),
    onSuccess: (r) => { if (r.text) { api.buddy.track('voice_success'); chat.send(r.text, { viaVoice: true }); } },
    onError: () => api.buddy.track('voice_failed'),
  });
  const rec = useRecorder((audio) => transcribe.mutate(audio));
  const voiceOn = caps.data?.voice === true;

  useEffect(() => { endRef.current?.scrollIntoView?.({ behavior: 'smooth', block: 'end' }); }, [chat.messages.length, chat.busy, chat.pending]);
  useEffect(() => {
    const on = () => setOnline(true), off = () => setOnline(false);
    window.addEventListener('online', on); window.addEventListener('offline', off);
    return () => { window.removeEventListener('online', on); window.removeEventListener('offline', off); };
  }, []);
  useEffect(() => { if (rec.state === 'denied') api.buddy.track('mic_denied'); }, [rec.state]);
  // A question handed over from search / GO ("?q=") is sent once.
  const q0 = sp.get('q');
  useEffect(() => {
    if (q0 && status === 'authenticated') { setSp(cid ? { c: cid } : {}, { replace: true }); chat.send(q0); }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [q0, status]);
  useEffect(() => { const t = inputRef.current; if (t) { t.style.height = 'auto'; t.style.height = `${Math.min(160, t.scrollHeight)}px`; } }, [draft]);

  const submit = (e?: FormEvent) => {
    e?.preventDefault();
    if (!draft.trim() || chat.busy) return;
    chat.send(draft, { attachment: attachment ? { kind: attachment.kind, id: attachment.id } : null });
    setDraft(''); setAttachment(null);
  };
  const onKey = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey && desktopEnter()) { e.preventDefault(); submit(); }
  };
  const newChat = async () => {
    if ((draft.trim() || chat.pending) && !(await confirm({ title: 'Start a new chat?', message: chat.pending ? 'The action waiting for your OK will be dropped.' : 'Your unsent message will be cleared.', confirmLabel: 'New chat' }))) return;
    chat.reset(); setDraft(''); setAttachment(null); setSp({}, { replace: true }); inputRef.current?.focus();
  };
  const open = (c: BuddyConversation) => { setHistoryOpen(false); setSp({ c: c.id }, { replace: true }); chat.load(c.id); };

  if (status !== 'authenticated') {
    return (
      <div className="bd-page" data-theme="buddy">
        <div className="bd-gate"><span className="bd-orb bd-orb--sm" aria-hidden="true" /><h1>Buddy</h1><p>Sign in so Buddy can use your addresses, orders and bookings — only yours.</p>
          <Link to="/login?next=/buddy" className="bd-btn">Sign in</Link><Link to="/" className="bd-link small">Back to Click.</Link></div>
      </div>
    );
  }

  return (
    <div className="bd-page" data-theme="buddy">
      <header className="bd-header">
        <div className="bd-brand"><span className="bd-orb bd-orb--sm" aria-hidden="true" /><span><strong>Buddy</strong>{chat.title && <span className="small bd-muted">{chat.title}</span>}</span></div>
        <nav className="bd-header__acts" aria-label="Buddy">
          <button type="button" className="bd-icon" onClick={newChat} aria-label="New chat" title="New chat"><Icon name="plus" size={20} /></button>
          <button type="button" className="bd-icon" onClick={() => navigate('/')} aria-label="Click. Home" title="Home"><Icon name="home" size={20} /></button>
          <button type="button" className="bd-icon" onClick={() => setHistoryOpen(true)} aria-label="Recent chats" title="Recent chats"><Icon name="history" size={20} /></button>
        </nav>
      </header>
      {!online && <div className="bd-banner" role="status"><Icon name="alert" size={14} /> You’re offline. Buddy will answer when you’re back.</div>}

      <main className="bd-main" aria-live="polite">
        {chat.loading ? <div className="bd-stream"><Skeleton height={60} /><Skeleton height={120} /></div> : chat.messages.length === 0 ? (
          <section className="bd-welcome">
            <span className="bd-orb" aria-hidden="true" />
            <h1>Hi, I’m Buddy.</h1>
            <p>What would you like to do with Click. today?</p>
            <div className="bd-quick">{QUICK.map((x) => (
              <button key={x.label} type="button" className="bd-quickbtn" onClick={() => chat.send(x.prompt)}><Icon name={x.icon} size={18} /> {x.label}</button>
            ))}</div>
            <p className="small bd-muted"><Icon name="shield" size={12} /> Buddy uses Click. data only, asks before anything important, and never pays for you.</p>
          </section>
        ) : (
          <div className="bd-stream">
            {chat.messages.map((m) => (
              <MessageView key={m.id} m={m} acting={chat.acting} onPrompt={(t) => chat.send(t)} onAction={(a) => chat.runAction(a.action, a.args, a.label)} />
            ))}
            {chat.busy && <div className="bd-msg bd-msg--buddy"><span className="bd-avatar bd-avatar--live" aria-hidden="true" /><div className="bd-thinking" aria-label="Buddy is thinking"><span /><span /><span /> <span className="small bd-muted">Checking Click…</span></div></div>}
            {chat.pending && <ConfirmCard p={chat.pending} busy={chat.acting} onDecide={(d) => chat.decide(d)} />}
            {chat.error && (
              <div className="bd-error" role="alert"><Icon name="alert" size={16} /><span>{chat.error.message}</span>
                {chat.error.text && <button type="button" className="bd-chip" onClick={chat.retry}>Retry</button>}
                <button type="button" className="bd-x" aria-label="Dismiss" onClick={() => chat.setError(null)}><Icon name="close" size={14} /></button></div>
            )}
            <div ref={endRef} />
          </div>
        )}
      </main>

      <form className="bd-input" onSubmit={submit}>
        {attachment && <div className="bd-attached small"><Icon name="pin" size={12} /> {attachment.label}<button type="button" aria-label="Remove attachment" onClick={() => setAttachment(null)}><Icon name="close" size={12} /></button></div>}
        {(rec.state === 'denied' || rec.state === 'unsupported' || transcribe.isError) && (
          <p className="bd-voicenote small" role="status">{rec.state === 'denied' ? 'Microphone access is blocked. Allow it in your browser, or type.' : rec.state === 'unsupported' ? 'This browser can’t record audio.' : 'Couldn’t hear that clearly. Try again.'}</p>
        )}
        <div className="bd-input__bar">
          <button type="button" className="bd-icon" aria-label="Attach Click. context" onClick={() => setAttachOpen(true)}><Icon name="pin" size={20} /></button>
          <textarea ref={inputRef} rows={1} value={draft} maxLength={2000} placeholder={rec.state === 'listening' ? 'Listening…' : transcribe.isPending ? 'Understanding…' : 'Ask Buddy anything…'}
            aria-label="Ask Buddy anything" onChange={(e) => setDraft(e.target.value)} onKeyDown={onKey} />
          <button type="button" className={`bd-icon bd-mic${rec.state === 'listening' ? ' is-live' : ''}`} style={{ ['--lvl' as string]: rec.level }}
            disabled={!voiceOn || transcribe.isPending || chat.busy} aria-pressed={rec.state === 'listening'}
            aria-label={!voiceOn ? 'Voice isn’t switched on yet' : rec.state === 'listening' ? 'Stop listening' : 'Speak to Buddy'}
            title={!voiceOn ? 'Voice isn’t switched on for Click. yet' : undefined}
            onClick={() => { if (rec.state === 'listening') rec.stop(); else { api.buddy.track('voice_started'); rec.start(); } }}>
            <Icon name="mic" size={20} />
          </button>
          {chat.busy ? <button type="button" className="bd-send bd-send--stop" onClick={chat.stop} aria-label="Stop"><span /></button>
            : <button type="submit" className="bd-send" disabled={!draft.trim()} aria-label="Send"><Icon name="send" size={18} /></button>}
        </div>
      </form>

      <AttachSheet open={attachOpen} onClose={() => setAttachOpen(false)} onPick={(a) => { setAttachment(a); setAttachOpen(false); inputRef.current?.focus(); }}
        imageOn={caps.data?.visualSearch === true} />
      <HistoryPanel open={historyOpen} onClose={() => setHistoryOpen(false)} onOpen={open} currentId={chat.id} onDeleted={(id) => { if (id === chat.id) { chat.reset(); setSp({}, { replace: true }); } }} />
    </div>
  );
}

function AttachSheet({ open, onClose, onPick, imageOn }: { open: boolean; onClose: () => void; onPick: (a: BuddyAttachment & { label: string }) => void; imageOn: boolean }) {
  const { addresses } = useDeliveryLocation();
  const orders = useQuery({ queryKey: ['buddy', 'attach', 'orders'], queryFn: () => api.customer.orders.list(), enabled: open });
  const stays = useQuery({ queryKey: ['buddy', 'attach', 'hotels'], queryFn: () => api.hotels.bookings('upcoming'), enabled: open });
  const services = useQuery({ queryKey: ['buddy', 'attach', 'services'], queryFn: () => api.services.bookings('active'), enabled: open });
  const events = useQuery({ queryKey: ['buddy', 'attach', 'events'], queryFn: () => api.eventHub.bookings('active'), enabled: open });
  const items: (BuddyAttachment & { label: string; detail: string; icon: string })[] = [
    ...(orders.data?.results ?? []).slice(0, 4).map((o) => ({ kind: 'order' as const, id: o.id, label: `Order ${o.number}`, detail: o.store.name, icon: 'receipt' })),
    ...(stays.data?.results ?? []).slice(0, 3).map((b) => ({ kind: 'hotel_booking' as const, id: b.id, label: `Stay ${b.number}`, detail: b.property.name, icon: 'hotel' })),
    ...(services.data?.results ?? []).slice(0, 3).map((b) => ({ kind: 'service_booking' as const, id: b.id, label: `Service ${b.number}`, detail: b.job.name, icon: 'wrench' })),
    ...(events.data?.results ?? []).slice(0, 3).map((b) => ({ kind: 'event_booking' as const, id: b.id, label: `Event ${b.number}`, detail: b.title, icon: 'gift' })),
    ...addresses.slice(0, 3).map((a) => ({ kind: 'address' as const, id: a.id, label: `Address: ${a.label}`, detail: a.line1, icon: 'pin' })),
  ];
  return (
    <Sheet open={open} onClose={onClose} label="Attach">
      <div className="bd-sheet">
        <h2>Attach to your message</h2>
        <p className="small bd-muted">Point Buddy at one of your Click. items. Only your own items are listed, and only its reference is shared.</p>
        {orders.isPending ? <Skeleton height={120} /> : items.length === 0 ? <p className="small">Nothing to attach yet.</p> : (
          <ul className="bd-attachlist">{items.map((it) => (
            <li key={`${it.kind}-${it.id}`}><button type="button" onClick={() => onPick({ kind: it.kind, id: it.id, label: it.label })}>
              <Icon name={it.icon as never} size={18} /><span><strong>{it.label}</strong><span className="small bd-muted">{it.detail}</span></span></button></li>
          ))}</ul>
        )}
        <div className="bd-attach-off small"><Icon name="camera" size={16} /> {imageOn ? 'Photo search lives in Click. search.' : 'Photos and documents: image understanding isn’t switched on for Click. yet.'}</div>
      </div>
    </Sheet>
  );
}

function HistoryPanel({ open, onClose, onOpen, currentId, onDeleted }: {
  open: boolean; onClose: () => void; onOpen: (c: BuddyConversation) => void; currentId: string | null; onDeleted: (id: string) => void;
}) {
  const qc = useQueryClient();
  const confirm = useConfirm();
  const [archived, setArchived] = useState(false);
  const [renaming, setRenaming] = useState<{ id: string; title: string } | null>(null);
  const list = useInfiniteQuery({
    queryKey: ['buddy', 'conversations', archived], initialPageParam: 1, enabled: open,
    queryFn: ({ pageParam }) => api.buddy.conversations(archived, pageParam), getNextPageParam: (l, all) => (l.hasMore ? all.length + 1 : undefined),
  });
  const edit = useMutation({
    mutationFn: ({ id, body }: { id: string; body: { title?: string; archived?: boolean } }) => api.buddy.edit(id, body),
    onSuccess: () => { setRenaming(null); qc.invalidateQueries({ queryKey: ['buddy', 'conversations'] }); },
  });
  const del = useMutation({ mutationFn: (id: string) => api.buddy.remove(id), onSuccess: (_, id) => { onDeleted(id); qc.invalidateQueries({ queryKey: ['buddy', 'conversations'] }); } });
  const rows = list.data?.pages.flatMap((p) => p.results) ?? [];
  return (
    <Sheet open={open} onClose={onClose} label="Recent chats" variant="full">
      <div className="bd-sheet bd-history">
        <div className="bd-history__head"><h2>Recent chats</h2>
          <button type="button" className="bd-chip" aria-pressed={archived} onClick={() => setArchived(!archived)}>{archived ? 'Show recent' : 'Show archived'}</button></div>
        {list.isError ? <p className="small">{list.error instanceof ApiError ? list.error.message : 'Couldn’t load chats.'} <button type="button" className="bd-link" onClick={() => list.refetch()}>Retry</button></p>
          : list.isPending ? <Skeleton height={200} /> : rows.length === 0 ? <p className="small bd-muted">{archived ? 'No archived chats.' : 'Your chats will appear here.'}</p> : (
            <ul className="bd-convs">{rows.map((c) => (
              <li key={c.id} className={c.id === currentId ? 'is-current' : ''}>
                {renaming?.id === c.id ? (
                  <form className="bd-rename" onSubmit={(e) => { e.preventDefault(); if (renaming.title.trim()) edit.mutate({ id: c.id, body: { title: renaming.title } }); }}>
                    <input value={renaming.title} maxLength={80} autoFocus aria-label="Chat name" onChange={(e) => setRenaming({ id: c.id, title: e.target.value })} />
                    <button type="submit" className="bd-chip bd-chip--primary">Save</button><button type="button" className="bd-chip" onClick={() => setRenaming(null)}>Cancel</button>
                  </form>
                ) : (
                  <button type="button" className="bd-conv" onClick={() => onOpen(c)}>
                    <strong>{c.title}</strong><span className="small bd-muted">{c.preview}</span>
                    <span className="bd-conv__meta small">{c.topic && <span className="bd-tag">{c.topic}</span>}{new Date(c.updatedAt).toLocaleString('en-IN', { day: 'numeric', month: 'short', hour: 'numeric', minute: '2-digit' })}</span>
                  </button>
                )}
                {renaming?.id !== c.id && (
                  <div className="bd-conv__acts">
                    <button type="button" className="bd-x" aria-label={`Rename ${c.title}`} onClick={() => setRenaming({ id: c.id, title: c.title })}><Icon name="edit" size={14} /></button>
                    <button type="button" className="bd-x" aria-label={`${archived ? 'Unarchive' : 'Archive'} ${c.title}`} onClick={() => edit.mutate({ id: c.id, body: { archived: !archived } })}><Icon name="download" size={14} /></button>
                    <button type="button" className="bd-x" aria-label={`Delete ${c.title}`} onClick={async () => { if (await confirm({ title: 'Delete this chat?', message: 'It can’t be restored.', confirmLabel: 'Delete', danger: true })) del.mutate(c.id); }}><Icon name="close" size={14} /></button>
                  </div>
                )}
              </li>
            ))}</ul>
          )}
        {list.hasNextPage && <button type="button" className="bd-chip" onClick={() => list.fetchNextPage()}>Load more</button>}
      </div>
    </Sheet>
  );
}
