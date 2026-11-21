import { useCallback, useEffect, useRef, useState } from 'react';

/**
 * Speech-to-text with the browser's own speech recogniser (Web Speech API: Chrome, Edge, Safari, Samsung Internet).
 * No API keys and nothing sent to Click.; the browser vendor's recogniser handles the audio, as it does for every site.
 * Used when Click.'s server-side speech provider isn't configured. Shows live words while the customer speaks.
 */
export type SpeechState = 'idle' | 'listening' | 'unsupported' | 'denied' | 'error' | 'nomatch';

interface Recognition extends EventTarget {
  lang: string; interimResults: boolean; continuous: boolean; maxAlternatives: number;
  start(): void; stop(): void; abort(): void;
  onresult: ((e: { resultIndex: number; results: ArrayLike<ArrayLike<{ transcript: string }> & { isFinal: boolean }> }) => void) | null;
  onerror: ((e: { error: string }) => void) | null;
  onend: (() => void) | null;
}
type RecognitionCtor = new () => Recognition;

const LOCALES: Record<string, string> = { en: 'en-IN', hi: 'hi-IN', te: 'te-IN' };

export const speechSupported = () =>
  typeof window !== 'undefined' && !!((window as unknown as { SpeechRecognition?: RecognitionCtor }).SpeechRecognition
    ?? (window as unknown as { webkitSpeechRecognition?: RecognitionCtor }).webkitSpeechRecognition);

export function useSpeech(onFinal: (text: string) => void) {
  const [state, setState] = useState<SpeechState>(() => (speechSupported() ? 'idle' : 'unsupported'));
  const [interim, setInterim] = useState('');
  const rec = useRef<Recognition | null>(null);
  const done = useRef(onFinal);
  done.current = onFinal;

  useEffect(() => () => rec.current?.abort(), []);

  const start = useCallback(() => {
    const Ctor = (window as unknown as { SpeechRecognition?: RecognitionCtor }).SpeechRecognition
      ?? (window as unknown as { webkitSpeechRecognition?: RecognitionCtor }).webkitSpeechRecognition;
    if (!Ctor) { setState('unsupported'); return; }
    rec.current?.abort();
    const r = new Ctor();
    r.lang = LOCALES[document.documentElement.lang] ?? 'en-IN';
    r.interimResults = true;
    r.continuous = false;
    r.maxAlternatives = 1;
    let finalText = '';
    r.onresult = (e) => {
      let live = '';
      for (let i = e.resultIndex; i < e.results.length; i++) {
        const res = e.results[i]!;
        if (res.isFinal) finalText += res[0]!.transcript; else live += res[0]!.transcript;
      }
      setInterim((finalText + live).trim());
    };
    r.onerror = (e) => setState(e.error === 'not-allowed' || e.error === 'service-not-allowed' ? 'denied' : e.error === 'no-speech' ? 'nomatch' : 'error');
    r.onend = () => {
      rec.current = null;
      const text = finalText.trim();
      setInterim('');
      if (text) { setState('idle'); done.current(text); } else setState((s) => (s === 'listening' ? 'nomatch' : s));
    };
    rec.current = r;
    setInterim('');
    setState('listening');
    try { r.start(); } catch { setState('error'); }
  }, []);

  const stop = useCallback(() => rec.current?.stop(), []);
  return { state, interim, start, stop };
}
