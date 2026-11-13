import { useCallback, useEffect, useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useQueryClient } from '@tanstack/react-query';
import { ApiError, type BuddyActionRun, type BuddyAttachment, type BuddyMessage } from '@click/api';
import { api } from '../../lib/api';

export type PendingAction = { run: BuddyActionRun; label: string };
type Local = BuddyMessage & { failed?: boolean; local?: boolean };

/**
 * One conversation, shared by Buddy MAN and GO. Messages are stored on the server; restoring a chat only shows them
 * (actions are never re-run). Safe actions in a *fresh* reply (open a page, add to cart) already ran on the server —
 * the client only follows a navigation. Confirmation-tier actions return a server-built summary and wait here.
 */
export function useBuddyChat(mode: 'man' | 'go', initialId: string | null, onConversation?: (id: string) => void) {
  const navigate = useNavigate();
  const qc = useQueryClient();
  const [id, setId] = useState<string | null>(initialId);
  const [messages, setMessages] = useState<Local[]>([]);
  const [title, setTitle] = useState('');
  const [busy, setBusy] = useState(false);
  const [acting, setActing] = useState(false);
  const [error, setError] = useState<{ text: string; message: string } | null>(null);
  const [pending, setPending] = useState<PendingAction | null>(null);
  const [loading, setLoading] = useState(false);
  const abort = useRef<AbortController | null>(null);

  const load = useCallback(async (cid: string) => {
    setLoading(true);
    try {
      const c = await api.buddy.conversation(cid);
      setId(c.id); setMessages(c.messages); setTitle(c.title); setPending(null); setError(null);
    } catch (e) {
      setError({ text: '', message: e instanceof ApiError ? e.message : 'Couldn’t open that chat.' });
    } finally { setLoading(false); }
  }, []);

  useEffect(() => { if (initialId) load(initialId); }, [initialId, load]);

  const reset = useCallback(() => {
    abort.current?.abort();
    setId(null); setMessages([]); setTitle(''); setPending(null); setError(null); setBusy(false);
  }, []);

  const follow = useCallback((m: BuddyMessage) => {
    for (const c of m.cards) {
      if (c.type === 'action_result' && c.result.status === 'done' && c.result.result.navigate) {
        api.buddy.track('navigated', c.result.result.navigate.slice(0, 60));
        setTimeout(() => navigate(c.result.result.navigate!), 700);
        return true;
      }
    }
    return false;
  }, [navigate]);

  const send = useCallback(async (text: string, opts: { viaVoice?: boolean; attachment?: BuddyAttachment | null } = {}) => {
    const content = text.trim();
    if (!content || busy) return null;
    setError(null);
    const temp: Local = { id: `local-${Date.now()}`, role: 'user', content, cards: [], actions: [], attachment: {}, viaVoice: !!opts.viaVoice, createdAt: new Date().toISOString(), local: true };
    setMessages((m) => [...m, temp]);
    setBusy(true);
    const ctrl = new AbortController();
    abort.current = ctrl;
    try {
      let cid = id;
      if (!cid) {
        const c = await api.buddy.start(mode);
        cid = c.id; setId(cid); onConversation?.(cid);
      }
      const r = await api.buddy.say(cid, content, { ...opts, signal: ctrl.signal });
      setMessages((m) => [...m.filter((x) => x.id !== temp.id), { ...temp, local: false }, r.message]);
      setTitle(r.conversation.title);
      qc.invalidateQueries({ queryKey: ['buddy', 'conversations'] });
      if (r.message.cards.some((c) => c.type === 'action_result')) qc.invalidateQueries({ queryKey: ['customer', 'cart'] });
      follow(r.message);
      return r.message;
    } catch (e) {
      if (ctrl.signal.aborted) {
        setMessages((m) => m.map((x) => (x.id === temp.id ? { ...x, failed: true } : x)));
        setError({ text: content, message: 'Stopped. Your message is kept — send it again when you’re ready.' });
      } else {
        setMessages((m) => m.map((x) => (x.id === temp.id ? { ...x, failed: true } : x)));
        const offline = typeof navigator !== 'undefined' && navigator.onLine === false;
        setError({ text: content, message: offline ? 'You’re offline. Your message is kept — retry when you’re back online.'
          : e instanceof ApiError && e.code === 'ai_unavailable' ? 'Buddy isn’t available right now.' : e instanceof ApiError ? e.message : 'Buddy couldn’t answer. Try again.' });
      }
      return null;
    } finally { setBusy(false); abort.current = null; }
  }, [busy, id, mode, onConversation, qc, follow]);

  const stop = useCallback(() => abort.current?.abort(), []);

  const retry = useCallback(() => {
    if (!error?.text) return;
    const text = error.text;
    setMessages((m) => m.filter((x) => !(x.failed && x.content === text)));
    send(text);
  }, [error, send]);

  const runAction = useCallback(async (action: string, args: Record<string, unknown>, label: string) => {
    setActing(true);
    try {
      const run = await api.buddy.act(action, args, id);
      if (run.status === 'awaiting_confirmation') { setPending({ run, label }); return run; }
      if (run.result.navigate) navigate(run.result.navigate);
      if (action.startsWith('cart')) qc.invalidateQueries({ queryKey: ['customer', 'cart'] });
      return run;
    } catch (e) {
      setError({ text: '', message: e instanceof ApiError ? e.message : 'That didn’t work. Try again.' });
      return null;
    } finally { setActing(false); }
  }, [id, navigate, qc]);

  const decide = useCallback(async (decision: 'confirm' | 'cancel') => {
    if (!pending) return null;
    setActing(true);
    try {
      const run = await api.buddy.decide(pending.run.id, decision);
      setPending(null);
      const note: Local = { id: `act-${run.id}`, role: 'assistant', content: decision === 'cancel' ? 'Okay, I didn’t do it.' : run.result.message || run.summary,
        cards: [{ type: 'action_result', result: run }], actions: [], attachment: {}, viaVoice: false, createdAt: new Date().toISOString(), local: true };
      setMessages((m) => [...m, note]);
      if (decision === 'confirm' && run.result.navigate) setTimeout(() => navigate(run.result.navigate!), 900);
      return run;
    } catch (e) {
      setPending(null);
      setError({ text: '', message: e instanceof ApiError ? e.message : 'That didn’t work.' });
      return null;
    } finally { setActing(false); }
  }, [pending, navigate]);

  return { id, title, messages, busy, acting, loading, error, pending, send, stop, retry, reset, load, runAction, decide, setError };
}

/** Spoken replies use only on-device voices (no cloud speech service), and can be stopped at any time. */
export function speak(text: string, onEnd?: () => void): boolean {
  if (typeof window === 'undefined' || !('speechSynthesis' in window)) return false;
  const voices = window.speechSynthesis.getVoices().filter((v) => v.localService && v.lang.startsWith('en'));
  if (!voices.length) return false;
  window.speechSynthesis.cancel();
  const u = new SpeechSynthesisUtterance(text.slice(0, 400));
  u.voice = voices.find((v) => /IN/i.test(v.lang)) ?? voices[0]!;
  u.rate = 1.03;
  u.onend = () => onEnd?.();
  u.onerror = () => onEnd?.();
  window.speechSynthesis.speak(u);
  return true;
}
export const stopSpeaking = () => { if (typeof window !== 'undefined' && 'speechSynthesis' in window) window.speechSynthesis.cancel(); };
