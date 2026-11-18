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

/** Like, save and report a partner's Buzz post. Signed-out viewers are sent to sign in first. */
export function PostEngage({ item }: { item: BuzzItem }) {
  const id = postId(item);
  const { status } = useAuth();
  const navigate = useNavigate();
  const toast = useToast();
  const qc = useQueryClient();
  const [liked, setLiked] = useState(item.post?.liked ?? false);
  const [likes, setLikes] = useState(item.post?.likes ?? 0);
  const [saved, setSaved] = useState(item.post?.saved ?? false);
  const [reporting, setReporting] = useState(false);
  const [reason, setReason] = useState<BuzzReportReason>('misleading');
  const [busy, setBusy] = useState(false);
  if (!id || !item.post) return null;

  const signedIn = status === 'authenticated';
  const needAuth = () => navigate(`/login?next=${encodeURIComponent(`/buzz?item=${item.id}`)}`);

  async function toggle(kind: 'like' | 'save') {
    if (!signedIn) return needAuth();
    try {
      const r = await (kind === 'like' ? api.buzz.like(id!) : api.buzz.save(id!));
      if (kind === 'like') { setLiked(r.on); setLikes(r.count); } else { setSaved(r.on); toast(r.on ? 'Saved' : 'Removed from saved'); }
      void qc.invalidateQueries({ queryKey: ['buzz'] });
    } catch {
      toast('Couldn’t update that. Try again.', 'error');
    }
  }

  async function report() {
    setBusy(true);
    try {
      await api.buzz.report(id!, reason);
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
      <button type="button" className={`buzz-engage__btn ${liked ? 'is-on' : ''}`} aria-pressed={liked} aria-label={liked ? 'Unlike' : 'Like'} onClick={() => void toggle('like')}>
        <Icon name="heart" size={22} /><span>{likes}</span>
      </button>
      <button type="button" className={`buzz-engage__btn ${saved ? 'is-on' : ''}`} aria-pressed={saved} aria-label={saved ? 'Unsave' : 'Save'} onClick={() => void toggle('save')}>
        <Icon name="book" size={22} /><span>{saved ? 'Saved' : 'Save'}</span>
      </button>
      <button type="button" className="buzz-engage__btn" aria-label="Report this post" onClick={() => (signedIn ? setReporting(true) : needAuth())}>
        <Icon name="alert" size={22} /><span>Report</span>
      </button>
      {createPortal(<Sheet open={reporting} onClose={() => setReporting(false)} label="Report this post">
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
