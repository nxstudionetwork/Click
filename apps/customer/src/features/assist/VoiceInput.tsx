import { useState, type FormEvent } from 'react';
import { Link } from 'react-router-dom';
import { useMutation } from '@tanstack/react-query';
import { useAuth } from '../../auth/AuthProvider';
import { Button, Icon } from '../../components/ui';
import { api } from '../../lib/api';
import { useCapabilities } from './useCapabilities';
import { useRecorder } from './useRecorder';

/**
 * Voice-first input with an honest text fallback. Records only when the server reports a configured speech
 * provider; otherwise it says voice isn't on yet and lets the customer type. It never pretends to have listened.
 */
export function VoiceInput({ onText, placeholder, listeningLabel = 'Listening…', busy = false }: {
  onText: (text: string) => void; placeholder: string; listeningLabel?: string; busy?: boolean;
}) {
  const { status } = useAuth();
  const caps = useCapabilities();
  const [draft, setDraft] = useState('');
  const transcribe = useMutation({
    mutationFn: (audio: Blob) => api.customer.assistant.transcribe(audio),
    onSuccess: (r) => { if (r.text) onText(r.text); },
  });
  const rec = useRecorder((audio) => transcribe.mutate(audio));
  const voiceOn = status === 'authenticated' && caps.data?.voice === true;
  const listening = rec.state === 'listening';

  const submit = (e: FormEvent) => {
    e.preventDefault();
    if (draft.trim()) { onText(draft.trim()); setDraft(''); }
  };

  let note: string | null = null;
  if (status !== 'authenticated') note = 'Sign in to talk to Buddy.';
  else if (caps.isPending) note = null;
  else if (!voiceOn) note = 'Voice isn’t switched on for Click. yet, so I can’t listen. Type what you need instead.';
  else if (rec.state === 'unsupported') note = 'This browser can’t record audio. Type what you need instead.';
  else if (rec.state === 'denied') note = 'Microphone access is blocked. Allow it in your browser settings, or type instead.';
  else if (rec.state === 'error' || transcribe.isError) note = 'Couldn’t hear that clearly. Try again or type instead.';

  return (
    <div className="voice">
      <button
        type="button" className={`voice__orb ${listening ? 'voice__orb--live' : ''} ${voiceOn ? '' : 'voice__orb--off'}`}
        style={{ ['--lvl' as string]: rec.level }}
        disabled={!voiceOn || transcribe.isPending || busy} aria-pressed={listening}
        aria-label={listening ? 'Stop listening' : voiceOn ? 'Start speaking' : 'Voice unavailable'}
        onClick={() => (listening ? rec.stop() : rec.start())}
      >
        <Icon name="mic" size={30} />
      </button>
      <p className="voice__status" role="status" aria-live="polite">
        {transcribe.isPending ? 'Understanding…' : listening ? listeningLabel : voiceOn ? 'Tap to speak' : ''}
      </p>
      {note && <p className="voice__note">{note}{status !== 'authenticated' && <> <Link to="/login">Sign in</Link></>}</p>}
      {status === 'authenticated' && (
        <form className="voice__type" onSubmit={submit}>
          <input value={draft} onChange={(e) => setDraft(e.target.value)} placeholder={placeholder} aria-label={placeholder} maxLength={500} />
          <Button type="submit" size="sm" disabled={!draft.trim() || busy} loading={busy} aria-label="Send"><Icon name="send" size={16} /></Button>
        </form>
      )}
    </div>
  );
}
