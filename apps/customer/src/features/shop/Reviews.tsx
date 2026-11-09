import { useState } from 'react';
import { useInfiniteQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { ApiError, type ShopProductDetail, type ShopReview } from '@click/api';
import { Button, Icon, TextArea, TextField, useConfirm, useToast } from '../../components/ui';
import { api } from '../../lib/api';
import { formatDateTime } from '../../lib/format';

/** Ratings and reviews. Only verified purchases can be reviewed (the server decides, the UI just follows). */
export function Reviews({ product }: { product: ShopProductDetail }) {
  const s = product.ratingSummary;
  const [filter, setFilter] = useState<number | null>(null);
  const [editing, setEditing] = useState(false);
  const list = useInfiniteQuery({
    queryKey: ['shop', 'reviews', product.id, filter],
    queryFn: ({ pageParam }) => api.shop.reviews(product.id, { page: pageParam, rating: filter ?? undefined }),
    initialPageParam: 1,
    getNextPageParam: (last) => (last.hasMore ? last.page + 1 : undefined),
  });
  const reviews = list.data?.pages.flatMap((p) => p.results) ?? product.reviews;
  const max = Math.max(1, ...Object.values(s.distribution));

  return (
    <section className="spdp__panel" aria-labelledby="reviews-h" id="reviews">
      <h3 id="reviews-h">Ratings & reviews</h3>
      {s.count > 0 ? (
        <div className="rsum">
          <div className="rsum__big"><strong>{s.average?.toFixed(1)}</strong><span className="small muted">{s.count} verified rating{s.count === 1 ? '' : 's'}</span></div>
          <div className="rsum__bars">
            {['5', '4', '3', '2', '1'].map((k) => (
              <button key={k} type="button" className="rsum__bar" style={{ background: 'none', border: 0, padding: 0, cursor: 'pointer' }} aria-pressed={filter === Number(k)}
                onClick={() => setFilter(filter === Number(k) ? null : Number(k))} aria-label={`${k} stars: ${s.distribution[k]} reviews${filter === Number(k) ? ' (showing)' : ''}`}>
                <span>{k}★</span><span className="rsum__track"><span className="rsum__fill" style={{ width: `${(s.distribution[k]! / max) * 100}%` }} /></span><span>{s.distribution[k]}</span>
              </button>
            ))}
          </div>
        </div>
      ) : <p className="small muted">No ratings yet. Reviews come only from customers who bought and received this product on Click.</p>}

      {product.myReview && !editing && (
        <div className="ret"><strong>Your review</strong><ReviewBody r={product.myReview} />
          <MyReviewActions product={product} onEdit={() => setEditing(true)} /></div>
      )}
      {(product.canReview || editing) && <ReviewForm product={product} existing={editing ? product.myReview : null} onDone={() => setEditing(false)} />}

      {filter && <p className="small">Showing {filter}★ reviews · <button type="button" className="btn btn--ghost btn--sm" onClick={() => setFilter(null)}>Show all</button></p>}
      <div>{reviews.map((r) => <div key={r.id} className="review"><ReviewBody r={r} /></div>)}</div>
      {list.hasNextPage && <Button variant="outline" size="sm" onClick={() => list.fetchNextPage()} loading={list.isFetchingNextPage}>More reviews</Button>}
    </section>
  );
}

function ReviewBody({ r }: { r: ShopReview }) {
  return (
    <>
      <div className="review__head"><span className="pcard__stars">{r.rating} <Icon name="star" size={10} /></span>{r.title && <strong>{r.title}</strong>}</div>
      {r.body && <p className="small">{r.body}</p>}
      <span className="review__meta">{r.author}{r.verifiedPurchase ? ' · Verified purchase' : ''}{r.variantLabel ? ` · ${r.variantLabel}` : ''} · {formatDateTime(r.createdAt)}{r.edited ? ' · edited' : ''}</span>
    </>
  );
}

function useRefresh(productId: string) {
  const qc = useQueryClient();
  return () => { qc.invalidateQueries({ queryKey: ['shop', 'product', productId] }); qc.invalidateQueries({ queryKey: ['shop', 'reviews', productId] }); };
}

function MyReviewActions({ product, onEdit }: { product: ShopProductDetail; onEdit: () => void }) {
  const confirm = useConfirm();
  const toast = useToast();
  const refresh = useRefresh(product.id);
  const remove = useMutation({ mutationFn: () => api.shop.review.remove(product.id), onSuccess: () => { toast('Review deleted'); refresh(); },
    onError: (e) => toast(e instanceof ApiError ? e.message : 'Couldn’t delete the review.', 'error') });
  return (
    <div className="row">
      <Button variant="ghost" size="sm" onClick={onEdit}>Edit</Button>
      <Button variant="ghost" size="sm" loading={remove.isPending}
        onClick={async () => { if (await confirm({ title: 'Delete your review?', message: 'Your rating will be removed from this product.', confirmLabel: 'Delete', danger: true })) remove.mutate(); }}>Delete</Button>
    </div>
  );
}

function ReviewForm({ product, existing, onDone }: { product: ShopProductDetail; existing: ShopReview | null; onDone: () => void }) {
  const [rating, setRating] = useState(existing?.rating ?? 0);
  const [title, setTitle] = useState(existing?.title ?? '');
  const [body, setBody] = useState(existing?.body ?? '');
  const toast = useToast();
  const refresh = useRefresh(product.id);
  const save = useMutation({
    mutationFn: () => (existing ? api.shop.review.update : api.shop.review.create)(product.id, { rating, title, body }),
    onSuccess: () => { toast(existing ? 'Review updated' : 'Thanks for your review'); refresh(); onDone(); },
    onError: (e) => toast(e instanceof ApiError ? e.message : 'Couldn’t save your review.', 'error'),
  });
  return (
    <form className="stack" style={{ gap: 'var(--s-2)' }} onSubmit={(e) => { e.preventDefault(); if (rating) save.mutate(); }}>
      <strong className="small">{existing ? 'Edit your review' : 'You bought this. How is it?'}</strong>
      <div className="stars-input" role="radiogroup" aria-label="Your rating">
        {[1, 2, 3, 4, 5].map((n) => (
          <button key={n} type="button" role="radio" aria-checked={rating === n} aria-label={`${n} star${n > 1 ? 's' : ''}`} className={n <= rating ? 'is-lit' : ''} onClick={() => setRating(n)}>
            <Icon name="star" size={26} />
          </button>
        ))}
      </div>
      <TextField label="Title (optional)" maxLength={100} value={title} onChange={(e) => setTitle(e.target.value)} />
      <TextArea label="Review (optional)" maxLength={2000} value={body} onChange={(e) => setBody(e.target.value)} />
      <div className="row">
        <Button type="submit" size="sm" disabled={!rating} loading={save.isPending}>{existing ? 'Save changes' : 'Submit review'}</Button>
        {existing && <Button type="button" variant="ghost" size="sm" onClick={onDone}>Cancel</Button>}
      </div>
    </form>
  );
}
