import { useEffect, useRef, useState, type FormEvent } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import { useMutation } from '@tanstack/react-query';
import { ApiError, type AssistantMessage, type BuddyCard, type BuddyReply } from '@click/api';
import { useAuth } from '../auth/AuthProvider';
import { Button, Icon, Sheet } from '../components/ui';
import { VoiceInput } from '../features/assist/VoiceInput';
import { BookingCard } from '../features/bookings/BookingCard';
import { EventCard } from '../features/bookings/EventCard';
import { useAddToCart } from '../features/menu/useAddToCart';
import { OfferCard } from '../features/offers/OfferCard';
import { OrderCard } from '../features/orders/OrderCard';
import { ProductCard } from '../features/stores/ProductCard';
import { StoreCard } from '../features/stores/StoreCard';
import { api } from '../lib/api';

type Turn = { role: 'user'; content: string } | { role: 'assistant'; reply: BuddyReply };

const historyOf = (turns: Turn[]): AssistantMessage[] =>
  turns.map((t): AssistantMessage => (t.role === 'user' ? t : { role: 'assistant', content: t.reply.message.content })).slice(-20);

const SUGGESTIONS = ['Find me a good biryani', 'Movies tonight', 'Where is my order?', 'Plan dinner and a movie tonight', 'Cheapest rice', 'What’s my wallet balance?'];

/**
 * Buddy MAN: the full conversation with Click.'s assistant. Own layout (no app header or bottom navigation).
 * Every answer comes from the backend (/customer/assistant/messages), which only uses real, customer-scoped
 * Click. data. Buddy prepares; the customer reviews and pays.
 */
export function BuddyPage() {
  const { status } = useAuth();
  const [params, setParams] = useSearchParams();
  const [turns, setTurns] = useState<Turn[]>([]);
  const [draft, setDraft] = useState('');
  const [voiceOpen, setVoiceOpen] = useState(false);
  const endRef = useRef<HTMLDivElement>(null);
  const { addToCart, isAdding } = useAddToCart();

  const send = useMutation({
    mutationFn: api.customer.assistant.send,
    onSuccess: (reply) => setTurns((t) => [...t, { role: 'assistant', reply }]),
  });

  useEffect(() => { endRef.current?.scrollIntoView?.({ behavior: 'smooth', block: 'end' }); }, [turns, send.isPending]);

  function ask(text: string) {
    const content = text.trim();
    if (!content || send.isPending) return;
    const next: Turn[] = [...turns, { role: 'user', content }];
    setTurns(next);
    setDraft('');
    send.mutate(historyOf(next));
  }

  // A query handed over from global search ("Ask Buddy") is sent once.
  const initial = params.get('q');
  useEffect(() => {
    if (initial && status === 'authenticated') { ask(initial); setParams({}, { replace: true }); }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [initial, status]);

  const submit = (e: FormEvent) => { e.preventDefault(); ask(draft); };
  const newChat = () => { setTurns([]); setDraft(''); send.reset(); };
  const mode = [...turns].reverse().find((t): t is Extract<Turn, { role: 'assistant' }> => t.role === 'assistant')?.reply.mode;

  const renderCard = (c: BuddyCard, i: number) => {
    switch (c.type) {
      case 'store': return <StoreCard key={i} store={c.store} />;
      case 'product': return <ProductCard key={i} product={c.product} currency={c.product.store.currency} canOrder={c.product.store.isOpen} busy={isAdding} onAdd={() => addToCart(c.product)} showStore />;
      case 'event': return <EventCard key={i} event={c.event} />;
      case 'order': return <div key={i} className="card"><OrderCard order={c.order} /></div>;
      case 'booking': return <div key={i} className="card"><BookingCard booking={c.booking} /></div>;
      case 'offer': return <OfferCard key={i} offer={c.offer} />;
    }
  };

  return (
    <div className="buddy buddy--page" data-theme="buddy">
      <header className="buddy__head">
        <div className="buddy__title"><span className="buddy__orb" aria-hidden="true"><Icon name="sparkle" size={18} /></span><div><strong>Buddy</strong><span className="small muted" style={{ display: 'block' }}>{mode === 'basic' ? 'Basic mode' : 'Your Click. assistant'}</span></div></div>
        <div className="row" style={{ gap: 6 }}>
          <button className="btn btn--secondary btn--sm" onClick={newChat} disabled={!turns.length && !send.isError}><Icon name="plus" size={16} /> New chat</button>
          <Link to="/" className="icon-btn" aria-label="Click. home"><Icon name="home" /></Link>
        </div>
      </header>

      {status === 'anonymous' ? (
        <div className="state">
          <div className="state__icon"><Icon name="sparkle" /></div>
          <h2>Sign in to use Buddy</h2>
          <p>Buddy uses your orders, bookings and location to help.</p>
          <Link to="/login?next=/buddy" className="btn btn--primary">Sign in</Link>
        </div>
      ) : (
        <>
          <div className="buddy__chat" aria-live="polite">
            {turns.length === 0 && (
              <div className="buddy__welcome">
                <span className="buddy__orb buddy__orb--lg" aria-hidden="true"><Icon name="sparkle" size={28} /></span>
                <h2>How can I help?</h2>
                <p className="muted">I can find food, groceries, products and shows, check your orders and bookings, and help you plan. I only use Click. data and your own account, and I never pay for you: you review and confirm.</p>
                <div className="chips" style={{ flexWrap: 'wrap', justifyContent: 'center' }}>{SUGGESTIONS.map((s) => <button key={s} className="chip" onClick={() => ask(s)}>{s}</button>)}</div>
              </div>
            )}
            {turns.map((t, i) => t.role === 'user' ? (
              <div key={i} className="bubble bubble--user">{t.content}</div>
            ) : (
              <div key={i} className="buddy__reply">
                <div className="bubble bubble--assistant">{t.reply.message.content}</div>
                {t.reply.cards.length > 0 && <div className="buddy__cards">{t.reply.cards.map(renderCard)}</div>}
                {t.reply.actions.length > 0 && (
                  <div className="chips" style={{ flexWrap: 'wrap' }}>
                    {t.reply.actions.map((a, j) => 'path' in a
                      ? <Link key={j} to={a.path} className="chip chip--link">{a.label} <Icon name="right" size={14} /></Link>
                      : <button key={j} className="chip" onClick={() => ask(a.prompt)}>{a.label}</button>)}
                  </div>
                )}
              </div>
            ))}
            {send.isPending && <div className="bubble bubble--assistant buddy__typing" aria-label="Buddy is thinking"><span /><span /><span /></div>}
            {send.isError && (
              <div className="card card--pad stack" role="alert" style={{ gap: 6 }}>
                <strong>{send.error instanceof ApiError && send.error.code === 'ai_unavailable' ? 'Buddy isn’t available right now' : 'Buddy couldn’t answer'}</strong>
                <span className="small muted">{send.error.message}</span>
                <div className="row">
                  <button className="btn btn--primary btn--sm" onClick={() => send.mutate(historyOf(turns))}>Retry</button>
                  <Link to="/search" className="btn btn--outline btn--sm">Search instead</Link>
                </div>
              </div>
            )}
            <div ref={endRef} />
          </div>
          <form className="composer" onSubmit={submit}>
            <textarea className="field__input" value={draft} maxLength={2000} placeholder="Ask Buddy…" aria-label="Message Buddy"
              onChange={(e) => setDraft(e.target.value)}
              onKeyDown={(e) => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); ask(draft); } }} />
            <button type="button" className="icon-btn composer__mic" aria-label="Talk to Buddy" onClick={() => setVoiceOpen(true)}><Icon name="mic" /></button>
            <Button type="submit" aria-label="Send" disabled={!draft.trim()} loading={send.isPending}><Icon name="send" size={18} /></Button>
          </form>
        </>
      )}

      <Sheet open={voiceOpen} onClose={() => setVoiceOpen(false)} label="Talk to Buddy">
        <div className="stack" style={{ padding: 'var(--s-5)' }}>
          <div className="spread"><h2>Talk to Buddy</h2><button className="icon-btn" aria-label="Close" onClick={() => setVoiceOpen(false)}><Icon name="close" /></button></div>
          <VoiceInput onText={(t) => { setVoiceOpen(false); ask(t); }} placeholder="Or type here" listeningLabel="Buddy is listening…" />
        </div>
      </Sheet>
    </div>
  );
}
