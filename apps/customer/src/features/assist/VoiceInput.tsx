import { useEffect, useState, type FormEvent } from 'react';
import { useMutation } from '@tanstack/react-query';
import { Button, Icon } from '../../components/ui';
import { api } from '../../lib/api';
import { useAuth } from '../../auth/AuthProvider';
import { useCapabilities } from './useCapabilities';
import { useRecorder } from './useRecorder';
import { speechSupported, useSpeech } from './useSpeech';

/**
 * Voice input. Uses Click.'s server speech provider when it is configured; otherwise the browser's own speech
 * recogniser (no keys, works signed in or out). Live words appear as the customer speaks; typing always works too.
 * It never pretends to have listened: unsupported browsers and blocked microphones say so plainly.
 */
export function VoiceInput({ onText, placeholder, listeningLabel = 'Listening…', busy = false, autoStart = true }: {
  onText: (text: string) => void; placeholder: string; listeningLabel?: string; busy?: boolean; autoStart?: boolean;
}) {
  const { status } = useAuth();
  const caps = useCapabilities();
  const [draft, setDraft] = useState('');
  const serverVoice = status === 'authenticated' && caps.data?.voice === true;

  const transcribe = useMutation({
    mutationFn: (audio: Blob) => api.customer.assistant.transcribe(audio),
    onSuccess: (r) => { if (r.text) onText(r.text); },
  });
  const rec = useRecorder((audio) => transcribe.mutate(audio));
  const speech = useSpeech(onText);

  const useServer = serverVoice;
  const listening = useServer ? rec.state === 'listening' : speech.state === 'listening';
  const available = useServer || speechSupported();

  // Opening the voice panel starts listening straight away (one tap, like any voice search).
  useEffect(() => {
    if (!autoStart || caps.isPending && status === 'authenticated') return;
    if (useServer) rec.start(); else if (speechSupported()) speech.start();
  }, [caps.isPending]); // eslint-disable-line react-hooks/exhaustive-deps

  const toggle = () => {
    if (useServer) { if (listening) rec.stop(); else rec.start(); return; }
    if (listening) speech.stop(); else speech.start();
  };
  const submit = (e: FormEvent) => {
    e.preventDefault();
    if (draft.trim()) { onText(draft.trim()); setDraft(''); }
  };

  let note: string | null = null;
  const st = useServer ? rec.state : speech.state;
  if (!available) note = 'This browser can’t take voice input. Type instead, or try Chrome, Edge or Safari.';
  else if (st === 'denied') note = 'Microphone access is blocked. Allow it in your browser settings, or type instead.';
  else if (st === 'nomatch') note = 'Didn’t catch that. Tap the mic and try again.';
  else if (st === 'error' || transcribe.isError) note = 'Couldn’t hear that clearly. Try again or type instead.';

  return (
    <div className="voice">
      <button
        type="button" className={`voice__orb ${listening ? 'voice__orb--live' : ''} ${available ? '' : 'voice__orb--off'}`}
        style={{ ['--lvl' as string]: useServer ? rec.level : listening ? 0.35 : 0 }}
        disabled={!available || transcribe.isPending || busy} aria-pressed={listening}
        aria-label={listening ? 'Stop listening' : available ? 'Start speaking' : 'Voice unavailable'}
        onClick={toggle}
      >
        <Icon name="mic" size={30} />
      </button>
      <p className="voice__status" role="status" aria-live="polite">
        {transcribe.isPending ? 'Understanding…' : listening ? (speech.interim ? `“${speech.interim}”` : listeningLabel) : available ? 'Tap to speak' : ''}
      </p>
      {note && <p className="voice__note">{note}</p>}
      <form className="voice__type" onSubmit={submit}>
        <input value={draft} onChange={(e) => setDraft(e.target.value)} placeholder={placeholder} aria-label={placeholder} maxLength={500} />
        <Button type="submit" size="sm" disabled={!draft.trim() || busy} loading={busy} aria-label="Send"><Icon name="send" size={16} /></Button>
      </form>
    </div>
  );
}
