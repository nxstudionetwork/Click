import { useCallback, useEffect, useRef, useState } from 'react';

export type RecorderState = 'idle' | 'requesting' | 'listening' | 'denied' | 'unsupported' | 'error';

const MAX_MS = 8000;

/**
 * Microphone capture for voice input. Audio stays on the device until the caller sends the recording to Click.'s
 * own transcription endpoint. Exposes a live input level so the UI shows that it is genuinely listening.
 */
export function useRecorder(onRecorded: (audio: Blob) => void) {
  const [state, setState] = useState<RecorderState>('idle');
  const [level, setLevel] = useState(0);
  const rec = useRef<MediaRecorder | null>(null);
  const stream = useRef<MediaStream | null>(null);
  const raf = useRef(0);
  const timer = useRef<ReturnType<typeof setTimeout> | undefined>(undefined);
  const ctx = useRef<AudioContext | null>(null);

  const cleanup = useCallback(() => {
    cancelAnimationFrame(raf.current);
    clearTimeout(timer.current);
    stream.current?.getTracks().forEach((t) => t.stop());
    stream.current = null;
    ctx.current?.close().catch(() => {});
    ctx.current = null;
    setLevel(0);
  }, []);

  useEffect(() => cleanup, [cleanup]);

  const supported = typeof navigator !== 'undefined' && !!navigator.mediaDevices?.getUserMedia && typeof MediaRecorder !== 'undefined';

  const start = useCallback(async () => {
    if (!supported) { setState('unsupported'); return; }
    setState('requesting');
    try {
      const s = await navigator.mediaDevices.getUserMedia({ audio: true });
      stream.current = s;
      const chunks: Blob[] = [];
      const r = new MediaRecorder(s);
      r.ondataavailable = (e) => { if (e.data.size) chunks.push(e.data); };
      r.onstop = () => {
        cleanup();
        setState('idle');
        if (chunks.length) onRecorded(new Blob(chunks, { type: r.mimeType || 'audio/webm' }));
      };
      rec.current = r;
      r.start();
      setState('listening');
      // Live input level (local Web Audio analysis only).
      if (typeof AudioContext !== 'undefined') {
        const ac = new AudioContext();
        ctx.current = ac;
        const an = ac.createAnalyser();
        an.fftSize = 256;
        ac.createMediaStreamSource(s).connect(an);
        const buf = new Uint8Array(an.frequencyBinCount);
        const tick = () => {
          an.getByteTimeDomainData(buf);
          let peak = 0;
          for (const v of buf) peak = Math.max(peak, Math.abs(v - 128));
          setLevel(Math.min(1, peak / 64));
          raf.current = requestAnimationFrame(tick);
        };
        tick();
      }
      timer.current = setTimeout(() => { if (r.state === 'recording') r.stop(); }, MAX_MS);
    } catch (e) {
      cleanup();
      setState(e instanceof DOMException && (e.name === 'NotAllowedError' || e.name === 'SecurityError') ? 'denied' : 'error');
    }
  }, [supported, cleanup, onRecorded]);

  const stop = useCallback(() => { if (rec.current?.state === 'recording') rec.current.stop(); }, []);

  return { state, level, start, stop, supported };
}
