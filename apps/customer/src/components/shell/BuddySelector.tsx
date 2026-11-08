import { useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { useMutation } from '@tanstack/react-query';
import { ApiError, type BuddyReply } from '@click/api';
import { useAuth } from '../../auth/AuthProvider';
import { VoiceInput } from '../../features/assist/VoiceInput';
import { api } from '../../lib/api';
import { Icon, Sheet } from '../ui';

type Step = 'choose' | 'go';

const GO_PROMPTS = ['Find me a good biryani nearby', 'Movies tonight', 'Where is my order?', 'Show me groceries nearby'];

/**
 * Header Buddy entry. Opens a choice between:
 *   GO  — voice-first action mode: say (or type) what you need, Buddy finds it and offers the next step.
 *   MAN — the full Buddy conversation page.
 * Buddy prepares and navigates; it never places orders or payments.
 */
export function BuddySelector() {
  const [open, setOpen] = useState(false);
  const [step, setStep] = useState<Step>('choose');
  const close = () => { setOpen(false); setStep('choose'); };
  return (
    <>
      <button className="icon-btn buddy-btn" aria-label="Buddy, your Click. assistant" aria-haspopup="dialog" onClick={() => setOpen(true)}>
        <Icon name="sparkle" />
      </button>
      <Sheet open={open} onClose={close} label="Buddy">
        <div className="buddy-sheet" data-theme="buddy">
          <div className="spread">
            <div className="row" style={{ gap: 10 }}>
              {step === 'go' && <button className="icon-btn" aria-label="Back to Buddy modes" onClick={() => setStep('choose')}><Icon name="back" /></button>}
              <span className="buddy-mark" aria-hidden="true"><Icon name="sparkle" size={18} /></span>
              <div><h2>Buddy</h2><span className="small muted">{step === 'go' ? 'GO · action mode' : 'Your Click. assistant'}</span></div>
            </div>
            <button className="icon-btn" aria-label="Close" onClick={close}><Icon name="close" /></button>
          </div>
          {step === 'choose' ? <Choose onGo={() => setStep('go')} onClose={close} /> : <GoMode onClose={close} />}
        </div>
      </Sheet>
    </>
  );
}

function Choose({ onGo, onClose }: { onGo: () => void; onClose: () => void }) {
  const navigate = useNavigate();
  return (
    <div className="buddy-modes">
      <button className="buddy-mode buddy-mode--go" onClick={onGo}>
        <span className="buddy-mode__icon"><Icon name="mic" size={26} /></span>
        <span className="buddy-mode__name">GO</span>
        <span className="buddy-mode__desc">Say what you need. Buddy finds it and takes you there.</span>
      </button>
      <button className="buddy-mode buddy-mode--man" onClick={() => { onClose(); navigate('/buddy'); }}>
        <span className="buddy-mode__icon"><Icon name="sparkle" size={26} /></span>
        <span className="buddy-mode__name">MAN</span>
        <span className="buddy-mode__desc">Full conversation. Plan, compare and ask follow-ups.</span>
      </button>
      <p className="small muted buddy-modes__note"><Icon name="shield" size={14} /> Buddy prepares; you review and pay. It never pays for you.</p>
    </div>
  );
}

function GoMode({ onClose }: { onClose: () => void }) {
  const { status } = useAuth();
  const navigate = useNavigate();
  const [asked, setAsked] = useState('');
  const send = useMutation({ mutationFn: (text: string) => api.customer.assistant.send([{ role: 'user', content: text }]) });
  const ask = (text: string) => { setAsked(text); send.mutate(text); };
  const go = (path: string) => { onClose(); navigate(path); };
  const reply: BuddyReply | undefined = send.data;

  if (status !== 'authenticated') {
    return (
      <div className="state" style={{ padding: 'var(--s-6) 0' }}>
        <p>Sign in so Buddy can use your location, orders and bookings.</p>
        <Link to="/login" className="btn btn--primary" onClick={onClose}>Sign in</Link>
      </div>
    );
  }

  return (
    <div className="buddy-go">
      <VoiceInput onText={ask} placeholder="Tell Buddy what you need" listeningLabel="Buddy is listening…" busy={send.isPending} />
      {!asked && (
        <div className="chips buddy-go__prompts">{GO_PROMPTS.map((p) => <button key={p} className="chip" onClick={() => ask(p)}>{p}</button>)}</div>
      )}
      {asked && (
        <div className="buddy-go__result" aria-live="polite">
          <div className="bubble bubble--user">{asked}</div>
          {send.isPending && <div className="bubble bubble--assistant buddy__typing" aria-label="Buddy is thinking"><span /><span /><span /></div>}
          {send.isError && (
            <div className="bubble bubble--assistant" role="alert">
              {send.error instanceof ApiError && send.error.code === 'ai_unavailable' ? 'Buddy isn’t available right now.' : 'Buddy couldn’t answer. Please try again.'}
              <div className="row" style={{ marginTop: 8 }}><button className="btn btn--outline btn--sm" onClick={() => ask(asked)}>Try again</button></div>
            </div>
          )}
          {reply && (
            <>
              <div className="bubble bubble--assistant">{reply.message.content}</div>
              <div className="buddy-go__actions">
                {reply.actions.map((a, i) => 'path' in a
                  ? <button key={i} className={`btn btn--sm ${i === 0 ? 'btn--primary' : 'btn--outline'}`} onClick={() => go(a.path)}>{a.label} <Icon name="right" size={14} /></button>
                  : <button key={i} className="btn btn--sm btn--outline" onClick={() => ask(a.prompt)}>{a.label}</button>)}
                {reply.cards.length > 0 && (
                  <button className="btn btn--sm btn--ghost" onClick={() => go(`/buddy?q=${encodeURIComponent(asked)}`)}>
                    See {reply.cards.length} result{reply.cards.length === 1 ? '' : 's'} in Buddy
                  </button>
                )}
              </div>
            </>
          )}
        </div>
      )}
    </div>
  );
}
