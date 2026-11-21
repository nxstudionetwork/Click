import { useEffect, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import { useNavigate } from 'react-router-dom';
import { useQueryClient } from '@tanstack/react-query';
import type { BuzzItem, BuzzReportReason } from '@click/api';
import { useAuth } from '../../auth/AuthProvider';
import { Button, Icon, Sheet, useToast } from '../../components/ui';
import { api } from '../../lib/api';

const REASONS: { value: BuzzReportReason; label: string }[] = [
  { value: 'misleading', label: 'Misleading or false offer' }, { value: 'spam', label: 'Spam' },
  { value: 'offensive', label: 'Offensive or harassing' }, { value: 'illegal', label: 'Illegal or unsafe' }, { value: 'other', label: 'Something else' },
];

export const postId = (item: BuzzItem) => (item.kind === 'post' ? item.id.slice('post:'.length) : null);

/** Counts a view once the slide is mostly on screen (the server counts each viewer once a day). */
export function useBuzzView(item: BuzzItem) {
  const ref = useRef<HTMLElement>(null);
  useEffect(() => {
    const id = postId(item);
    const el = ref.current;
    if (!id || !el || typeof IntersectionObserver === 'undefined') return;
    const io = new IntersectionObserver(([e]) => {
      if (e?.isIntersecting) { void api.buzz.event(id, 'view').catch(() => undefined); io.disconnect(); }
    }, { threshold: 0.6 });
    io.observe(el);
    return () => io.disconnect();
  }, [item]);
  return ref;
}

/** Shares a Buzz item: the system share sheet where available, otherwise the link is copied. */
export async function shareBuzz(item: BuzzItem, toast: (m: string, t?: 'error') => void) {
  const url = `${window.location.origin}/buzz?item=${encodeURIComponent(item.id)}`;
  const text = `${item.title} on Click.`;
  try {
    if (navigator.share) { await navigator.share({ title: 'Click. Buzz', text, url }); return; }
    await navigator.clipboard.writeText(`${text} ${url}`);
    toast('Link copied');
  } catch (e) {
    if ((e as Error)?.name !== 'AbortError') toast('Couldn’t share right now.', 'error');
  }
}

/**
 * Like, save and share every Buzz instant; partner posts can also be reported. Counts are real reactions from the
 * server. Signed-out viewers are sent to sign in first (sharing works for everyone).
 */
export function PostEngage({ item, onSavedChange }: { item: BuzzItem; onSavedChange?: (saved: boolean) => void }) {
  const id = postId(item);
  const { status } = useAuth();
  const navigate = useNavigate();
  const toast = useToast();
  const qc = useQueryClient();
  const [liked, setLiked] = useState(item.engage?.liked ?? false);
  const [likes, setLikes] = useState(item.engage?.likes ?? 0);
  const [saved, setSaved] = useState(item.engage?.saved ?? false);
  const [pop, setPop] = useState(false);
  const [reporting, setReporting] = useState(false);
  const [reason, setReason] = useState<BuzzReportReason>('misleading');
  const [busy, setBusy] = useState(false);

  const signedIn = status === 'authenticated';
  const needAuth = () => navigate(`/login?next=${encodeURIComponent(`/buzz?item=${item.id}`)}`);

  async function toggle(kind: 'like' | 'save') {
    if (!signedIn) return needAuth();
    // Optimistic, then corrected by the server's answer.
    if (kind === 'like') { setLiked(!liked); setLikes(likes + (liked ? -1 : 1)); if (!liked) { setPop(true); setTimeout(() => setPop(false), 450); } }
    else setSaved(!saved);
    try {
      const r = id ? await (kind === 'like' ? api.buzz.like(id) : api.buzz.save(id)) : await api.buzz.itemReact(item.id, kind);
      if (kind === 'like') { setLiked(r.on); setLikes(r.count); } else { setSaved(r.on); onSavedChange?.(r.on); toast(r.on ? 'Saved to your Buzz' : 'Removed from saved'); }
      void qc.invalidateQueries({ queryKey: ['buzz'] });
    } catch {
      if (kind === 'like') { setLiked(liked); setLikes(likes); } else setSaved(saved);
      toast('Couldn’t update that. Try again.', 'error');
    }
  }

  async function report() {
    if (!id) return;
    setBusy(true);
    try {
      await api.buzz.report(id, reason);
      toast('Thanks. Click will review this post.');
      setReporting(false);
    } catch {
      toast('Couldn’t send the report. Try again.', 'error');
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="buzz-engage">
      <button type="button" className={`buzz-engage__btn ${liked ? 'is-on' : ''} ${pop ? 'is-pop' : ''}`} aria-pressed={liked} aria-label={`${liked ? "Unlike" : "Like"}, ${likes} ${likes === 1 ? "like" : "likes"}`} onClick={() => void toggle('like')}>
        <Icon name="heart" size={26} /><span>{likes > 0 ? likes.toLocaleString('en-IN') : 'Like'}</span>
      </button>
      <button type="button" className={`buzz-engage__btn ${saved ? 'is-on is-saved' : ''}`} aria-pressed={saved} aria-label={saved ? 'Remove from saved' : 'Save'} onClick={() => void toggle('save')}>
        <Icon name="bookmark" size={26} /><span>{saved ? 'Saved' : 'Save'}</span>
      </button>
      <button type="button" className="buzz-engage__btn" aria-label="Share" onClick={() => void shareBuzz(item, toast)}>
        <Icon name="share" size={26} /><span>Share</span>
      </button>
      {id && (
        <button type="button" className="buzz-engage__btn buzz-engage__btn--quiet" aria-label="Report this post" onClick={() => (signedIn ? setReporting(true) : needAuth())}>
          <Icon name="alert" size={22} /><span>Report</span>
        </button>
      )}
      {id && createPortal(<Sheet open={reporting} onClose={() => setReporting(false)} label="Report this post">
        <div className="buzz-report">
          <h2>Report this post</h2>
          <fieldset>
            <legend className="muted">What’s wrong with it?</legend>
            {REASONS.map((r) => (
              <label key={r.value} className="buzz-report__opt">
                <input type="radio" name="buzz-reason" value={r.value} checked={reason === r.value} onChange={() => setReason(r.value)} /> {r.label}
              </label>
            ))}
          </fieldset>
          <Button block loading={busy} onClick={() => void report()}>Send report</Button>
        </div>
      </Sheet>, document.body)}
    </div>
  );
}
