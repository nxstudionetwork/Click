import { useRef, useState, type FormEvent } from 'react';
import { Link } from 'react-router-dom';
import { useMutation } from '@tanstack/react-query';
import { ApiError, type AssistantMessage } from '@click/api';
import { useAuth } from '../auth/AuthProvider';
import { Button, Icon } from '../components/ui';
import { api } from '../lib/api';

/**
 * Click AI chat. All answers come from the shared backend AI layer
 * (/customer/assistant/messages) which builds a permission-scoped context.
 * No answers are generated or hardcoded in the frontend.
 */
export function AssistantPage() {
  const { status } = useAuth();
  const [messages, setMessages] = useState<AssistantMessage[]>([]);
  const [draft, setDraft] = useState('');
  const endRef = useRef<HTMLDivElement>(null);
  const send = useMutation({
    mutationFn: api.customer.assistant.send,
    onSuccess: (r) => { setMessages((m) => [...m, r.message]); setTimeout(() => endRef.current?.scrollIntoView?.({ behavior: 'smooth' }), 0); },
  });
  const unavailable = send.error instanceof ApiError && send.error.code === 'ai_unavailable';

  function submit(e: FormEvent) {
    e.preventDefault();
    const text = draft.trim();
    if (!text || send.isPending) return;
    const next = [...messages, { role: 'user' as const, content: text }];
    setMessages(next);
    setDraft('');
    send.mutate(next.slice(-20));
  }

  if (status === 'anonymous') {
    return (
      <div className="state">
        <div className="state__icon"><Icon name="sparkle" /></div>
        <h1>Click AI</h1>
        <p>Sign in to get help finding things and with your orders.</p>
        <Link to="/login?next=/assistant" className="btn btn--primary">Sign in</Link>
      </div>
    );
  }

  return (
    <div className="stack" style={{ maxWidth: 760 }}>
      <div className="page-head"><div><h1>Click AI</h1><p>Ask about stores, products or your orders.</p></div></div>
      <div className="chat" aria-live="polite">
        {messages.length === 0 && <p className="muted small">Try: “Where is my last order?” or “Find a grocery store with organic produce”.</p>}
        {messages.map((m, i) => <div key={i} className={`bubble bubble--${m.role}`}>{m.content}</div>)}
        {send.isPending && <div className="bubble bubble--assistant muted">Thinking…</div>}
        {send.isError && (
          <div className="card card--pad stack" role="alert" style={{ gap: 6 }}>
            <strong>{unavailable ? 'Click AI isn’t available yet' : 'Click AI couldn’t answer'}</strong>
            <span className="small muted">
              {unavailable ? 'The assistant is being set up. In the meantime, use Search or Help & Support.' : send.error.message}
            </span>
            <div className="row">
              {unavailable ? <><Link to="/search" className="btn btn--outline btn--sm">Search</Link><Link to="/help" className="btn btn--ghost btn--sm">Help & Support</Link></>
                : <Button size="sm" variant="outline" onClick={() => send.mutate(messages.slice(-20))}>Try again</Button>}
            </div>
          </div>
        )}
        <div ref={endRef} />
      </div>
      <form className="composer" onSubmit={submit}>
        <textarea className="field__input" value={draft} maxLength={2000} placeholder="Message Click AI" aria-label="Message Click AI"
          onChange={(e) => setDraft(e.target.value)}
          onKeyDown={(e) => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); submit(e); } }} />
        <Button type="submit" aria-label="Send" disabled={!draft.trim()} loading={send.isPending}><Icon name="send" size={18} /></Button>
      </form>
    </div>
  );
}
