import { useState } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { ApiError, type PendingReview } from '@click/api';
import { Button, EmptyState, ErrorState, Icon, Sheet, Skeleton, useToast } from '../components/ui';
import { MoneyHead, THEME, dateOf, iconFor } from '../features/money/parts';
import { api } from '../lib/api';

function Stars({ value, onChange, size = 30, label }: { value: number; onChange?: (n: number) => void; size?: number; label: string }) {
  return (
    <div className="rv-stars" role={onChange ? 'radiogroup' : 'img'} aria-label={onChange ? label : `${label}: ${value} of 5`}>
      {[1, 2, 3, 4, 5].map((n) => onChange ? (
        <button key={n} type="button" role="radio" aria-checked={value === n} aria-label={`${n} star${n > 1 ? 's' : ''}`} className={n <= value ? 'is-on' : ''} onClick={() => onChange(n)}>
          <Icon name="star" size={size} />
        </button>
      ) : <span key={n} className={n <= value ? 'is-on' : ''}><Icon name="star" size={size} /></span>)}
    </div>
  );
}

/** Reviews & Ratings: completed orders and bookings waiting for a rating, and every review you've written. Only things
 *  you actually bought, rode, stayed at, visited or booked can be reviewed — the server decides. */
export function ReviewsPage() {
  const q = useQuery({ queryKey: ['reviews'], queryFn: api.money.reviews.get });
  const [params, setParams] = useSearchParams();
  const tab = params.get('tab') === 'mine' ? 'mine' : 'pending';
  const [open, setOpen] = useState<PendingReview | null>(null);
  if (q.isError) return <div className="mn-page"><MoneyHead title="Reviews" /><ErrorState error={q.error} onRetry={() => q.refetch()} /></div>;
  if (!q.data) return <div className="mn-page"><MoneyHead title="Reviews" /><Skeleton height={300} /></div>;
  const d = q.data;
  return (
    <div className="mn-page">
      <MoneyHead title="Reviews & ratings" />
      <div className="mn-tabs" role="tablist">
        <button type="button" role="tab" className="mn-tab" aria-selected={tab === 'pending'} onClick={() => setParams({})}>To review · {d.pending.length}</button>
        <button type="button" role="tab" className="mn-tab" aria-selected={tab === 'mine'} onClick={() => setParams({ tab: 'mine' })}>Your reviews · {d.mine.length}</button>
      </div>
      {tab === 'pending' ? (
        d.pending.length === 0 ? <EmptyState icon="star" title="All caught up" message="When an order, ride, stay, visit or booking is completed, you can rate it here." /> : (
          <ul className="mn-list">{d.pending.map((p) => (
            <li key={`${p.kind}:${p.targetId}`} className="mn-row mn-row--static rv-pending" data-theme={THEME[p.service]}>
              <span className="mn-row__icon mn-row__icon--theme"><Icon name={iconFor(p.service)} size={18} /></span>
              <span className="mn-row__text"><strong className="truncate">{p.title}</strong>
                <span className="small mn-muted truncate">{p.kindLabel} · {p.subtitle}{p.completedAt ? ` · ${dateOf(p.completedAt)}` : ''}</span></span>
              <Button size="sm" onClick={() => setOpen(p)}>Rate</Button>
            </li>
          ))}</ul>
        )
      ) : d.mine.length === 0 ? <EmptyState icon="star" title="No reviews yet" message="Reviews you write appear here with the order or booking they’re about." /> : (
        <ul className="mn-list">{d.mine.map((r) => (
          <li key={`${r.kind}:${r.id}`}><Link to={r.link} className="mn-row rv-mine">
            <span className="mn-row__icon"><Icon name={iconFor(r.service)} size={18} /></span>
            <span className="mn-row__text"><strong className="truncate">{r.title}</strong>
              <Stars value={r.rating} size={14} label="Your rating" />
              {r.comment && <span className="small rv-comment">{r.comment}</span>}
              <span className="small mn-muted">{r.kindLabel}{r.target ? ` · ${r.target}` : ''} · {dateOf(r.createdAt)}{r.status !== 'published' ? ' · under review' : ''}</span></span>
          </Link></li>
        ))}</ul>
      )}
      {open && <ReviewSheet item={open} onClose={() => setOpen(null)} />}
    </div>
  );
}

function ReviewSheet({ item, onClose }: { item: PendingReview; onClose: () => void }) {
  const qc = useQueryClient();
  const toast = useToast();
  const [rating, setRating] = useState(0);
  const [aspects, setAspects] = useState<Record<string, number>>({});
  const [liked, setLiked] = useState('');
  const [better, setBetter] = useState('');
  const send = useMutation({
    mutationFn: () => api.money.reviews.submit({ kind: item.kind, targetId: item.targetId, rating, liked, better, aspects }),
    onSuccess: (d) => { qc.setQueryData(['reviews'], d); toast('Thanks for your review'); onClose(); },
  });
  return (
    <Sheet open onClose={onClose} label={`Rate ${item.title}`}>
      <div className="mn-sheet mn-form">
        <span className="small mn-muted">{item.kindLabel} · {item.subtitle}</span>
        <h2>How was your experience?</h2>
        <p className="mn-muted">{item.title}</p>
        <Stars value={rating} onChange={setRating} label="Overall rating" />
        {rating > 0 && item.aspects.length > 0 && (
          <div className="rv-aspects">{item.aspects.map((a) => (
            <div key={a.code} className="rv-aspect"><span className="small">{a.label}</span><Stars value={aspects[a.code] ?? 0} size={18} label={a.label} onChange={(n) => setAspects({ ...aspects, [a.code]: n })} /></div>
          ))}</div>
        )}
        {rating > 0 && (
          <>
            <label className="mn-field"><span>What did you like? <span className="mn-muted small">(optional)</span></span>
              <textarea rows={2} maxLength={500} value={liked} onChange={(e) => setLiked(e.target.value)} /></label>
            <label className="mn-field"><span>What could be better? <span className="mn-muted small">(optional)</span></span>
              <textarea rows={2} maxLength={500} value={better} onChange={(e) => setBetter(e.target.value)} /></label>
          </>
        )}
        {send.isError && <p className="mn-error small" role="alert">{send.error instanceof ApiError ? send.error.message : 'Couldn’t send your review.'}</p>}
        <Button block disabled={!rating} loading={send.isPending} onClick={() => send.mutate()}>Submit review</Button>
        <p className="small mn-muted">Your review is shown with your first name and a verified badge. Don’t include phone numbers or other personal details.</p>
      </div>
    </Sheet>
  );
}
