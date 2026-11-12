import { useEffect, useMemo, useState, type FormEvent } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { useMutation } from '@tanstack/react-query';
import type { BuddyAction, BuddyMessage } from '@click/api';
import { useAuth } from '../auth/AuthProvider';
import { Button, Icon } from '../components/ui';
import { useCapabilities } from '../features/assist/useCapabilities';
import { useRecorder } from '../features/assist/useRecorder';
import { ConfirmCard } from '../features/buddy/parts';
import { speak, stopSpeaking, useBuddyChat } from '../features/buddy/useBuddyChat';
import { api } from '../lib/api';

type GoState = 'ready' | 'listening' | 'thinking' | 'acting' | 'speaking' | 'completed' | 'error' | 'off';
const LABEL: Record<GoState, string> = { ready: 'Ready', listening: 'Listening', thinking: 'Thinking', acting: 'Acting', speaking: 'Speaking', completed: 'Done', error: 'Something went wrong', off: 'Voice is off' };
const EXAMPLES = ['Find me a plumber near my home', 'Show me my pending orders', 'Track my parcel', 'Find a hotel in Goa this weekend', 'Open my rewards'];

/**
 * Buddy GO — voice first. Tap, speak (recording stops by itself after a few seconds, never indefinitely), Buddy
 * transcribes on Click.'s own speech service, acts through the same server action layer as MAN, and answers aloud with
 * an on-device voice. Anything that needs a confirmation shows a summary and waits for a tap; payments always happen in
 * Click.'s checkout, never by voice.
 */
export function BuddyGoPage() {
  const { status } = useAuth();
  const navigate = useNavigate();
  const caps = useCapabilities();
  const chat = useBuddyChat('go', null);
  const [speakingNow, setSpeakingNow] = useState(false);
  const [last, setLast] = useState<BuddyMessage | null>(null);
  const [heard, setHeard] = useState('');
  const [typed, setTyped] = useState('');
  const voiceOn = caps.data?.voice === true;
  const transcribe = useMutation({
    mutationFn: (audio: Blob) => api.customer.assistant.transcribe(audio),
    onSuccess: async (r) => {
      if (!r.text) return;
      api.buddy.track('voice_success');
      setHeard(r.text);
      const m = await chat.send(r.text, { viaVoice: true });
      if (m) reply(m);
    },
    onError: () => api.buddy.track('voice_failed'),
  });
  const rec = useRecorder((audio) => transcribe.mutate(audio));
  useEffect(() => { if (rec.state === 'denied') api.buddy.track('mic_denied'); }, [rec.state]);
  useEffect(() => () => stopSpeaking(), []);

  const reply = (m: BuddyMessage) => {
    setLast(m);
    if (m.content && speak(m.content, () => setSpeakingNow(false))) setSpeakingNow(true);
  };
  const state: GoState = useMemo(() => {
    if (!voiceOn && caps.isSuccess) return 'off';
    if (rec.state === 'listening') return 'listening';
    if (transcribe.isPending || chat.busy) return 'thinking';
    if (chat.acting) return 'acting';
    if (speakingNow) return 'speaking';
    if (chat.error || transcribe.isError || rec.state === 'error' || rec.state === 'denied') return 'error';
    if (last) return 'completed';
    return 'ready';
  }, [voiceOn, caps.isSuccess, rec.state, transcribe.isPending, transcribe.isError, chat.busy, chat.acting, speakingNow, chat.error, last]);

  const tap = () => {
    if (rec.state === 'listening') return rec.stop();
    if (speakingNow) { stopSpeaking(); setSpeakingNow(false); return; }
    if (chat.busy) return chat.stop();
    chat.setError(null);
    api.buddy.track('voice_started');
    rec.start();
  };
  const sendTyped = async (e: FormEvent) => {
    e.preventDefault();
    if (!typed.trim()) return;
    setHeard(typed.trim());
    const m = await chat.send(typed.trim());
    setTyped('');
    if (m) reply(m);
  };
  const doAction = (a: BuddyAction) => {
    if ('path' in a) return navigate(a.path);
    if ('prompt' in a) { setHeard(a.prompt); chat.send(a.prompt).then((m) => m && reply(m)); return; }
    chat.runAction(a.action, a.args, a.label).then((run) => { if (run?.status === 'awaiting_confirmation') speak(`${run.summary} Tap confirm to go ahead.`); });
  };

  if (status !== 'authenticated') {
    return <div className="go-page" data-theme="buddy"><div className="bd-gate"><h1>Buddy GO</h1><p>Sign in to talk to Buddy.</p><Link to="/login?next=/buddy/go" className="bd-btn">Sign in</Link></div></div>;
  }

  return (
    <div className="go-page" data-theme="buddy" data-state={state}>
      <header className="go-head">
        <Link to="/" className="bd-icon" aria-label="Back to Click."><Icon name="close" size={20} /></Link>
        <span className="go-brand"><span className="bd-orb bd-orb--sm" aria-hidden="true" /> Buddy <strong>GO</strong></span>
        <Link to={chat.id ? `/buddy?c=${chat.id}` : '/buddy'} className="bd-icon" aria-label="Open this in Buddy MAN"><Icon name="menu" size={20} /></Link>
      </header>

      <main className="go-main">
        <p className="go-prompt">{state === 'off' ? 'Voice isn’t switched on for Click. yet.' : last ? '' : 'What can I do for you?'}</p>
        <button type="button" className="go-orb" onClick={tap} disabled={state === 'off' || transcribe.isPending} style={{ ['--lvl' as string]: rec.level }}
          aria-label={state === 'listening' ? 'Stop listening' : state === 'speaking' ? 'Stop speaking' : state === 'thinking' ? 'Stop' : 'Tap and speak'}>
          <span className="go-orb__ring" /><span className="go-orb__ring go-orb__ring--2" /><span className="go-orb__core"><Icon name={state === 'speaking' ? 'play' : 'mic'} size={34} /></span>
        </button>
        <p className="go-state" role="status" aria-live="assertive">{LABEL[state]}</p>
        {heard && <p className="go-heard">“{heard}”</p>}
        {state === 'error' && (
          <p className="go-note">{rec.state === 'denied' ? 'Microphone access is blocked. Allow it in your browser settings and try again.'
            : rec.state === 'unsupported' ? 'This browser can’t record audio.' : transcribe.isError ? 'I couldn’t hear that clearly. Tap and try again.'
              : chat.error?.message ?? 'Try again.'}
            {chat.error?.text && <button type="button" className="bd-chip" onClick={() => chat.retry()}>Retry</button>}</p>
        )}
        {last && (
          <section className="go-answer" aria-label="Buddy’s answer">
            <p>{last.content}</p>
            {last.actions.length > 0 && <div className="go-actions">{last.actions.slice(0, 3).map((a, i) => (
              <Button key={i} variant={i === 0 ? 'primary' : 'secondary'} disabled={chat.acting} onClick={() => doAction(a)}>{a.label}</Button>
            ))}</div>}
          </section>
        )}
        {chat.pending && <ConfirmCard p={chat.pending} busy={chat.acting} onDecide={(d) => chat.decide(d).then((r) => r && speak(d === 'confirm' ? (r.result.message || 'Done.') : 'Okay, I didn’t do it.'))} />}
        {!last && state !== 'off' && <ul className="go-examples" aria-label="Try saying">{EXAMPLES.map((x) => <li key={x}>“{x}”</li>)}</ul>}
        {state === 'off' && (
          <form className="go-type" onSubmit={sendTyped}>
            <input value={typed} onChange={(e) => setTyped(e.target.value)} placeholder="Type instead, e.g. Track my parcel" aria-label="Type a request" maxLength={500} />
            <Button type="submit" disabled={!typed.trim() || chat.busy} loading={chat.busy}>Go</Button>
          </form>
        )}
      </main>
      <footer className="go-foot small"><Icon name="shield" size={12} /> Recording stops on its own. Voice never pays — payments happen in checkout.</footer>
    </div>
  );
}
