import { useState } from 'react';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { ApiError, type OrderDetail } from '@click/api';
import { Button, Icon, TextArea, useToast } from '../../components/ui';
import { api } from '../../lib/api';

/** Rate a delivered order (once). The store's rating updates on the server. */
export function OrderReview({ order }: { order: OrderDetail }) {
  const qc = useQueryClient();
  const toast = useToast();
  const [rating, setRating] = useState(0);
  const [comment, setComment] = useState('');
  const send = useMutation({
    mutationFn: () => api.customer.orders.review(order.id, { rating, comment }),
    onSuccess: (o) => { qc.setQueryData(['customer', 'orders', 'detail', order.id], o); toast('Thanks for rating your order'); },
    onError: (e) => toast(e instanceof ApiError ? e.message : 'Couldn’t send your rating. Try again.', 'error'),
  });

  if (order.review) {
    return (
      <section className="card card--pad stack" aria-label="Your rating">
        <h3>Your rating</h3>
        <div className="stars" aria-label={`${order.review.rating} out of 5`}>{[1, 2, 3, 4, 5].map((n) => <Icon key={n} name="star" size={20} className={n <= order.review!.rating ? 'on' : ''} />)}</div>
        {order.review.comment && <p className="muted">“{order.review.comment}”</p>}
      </section>
    );
  }
  if (!order.canReview) return null;
  return (
    <section className="card card--pad stack" aria-labelledby="rate-h">
      <h3 id="rate-h">How was {order.store.name}?</h3>
      <div className="stars stars--input" role="radiogroup" aria-label="Rating">
        {[1, 2, 3, 4, 5].map((n) => (
          <button key={n} type="button" role="radio" aria-checked={rating === n} aria-label={`${n} star${n > 1 ? 's' : ''}`} onClick={() => setRating(n)}>
            <Icon name="star" size={28} className={n <= rating ? 'on' : ''} />
          </button>
        ))}
      </div>
      <TextArea label="Tell us more (optional)" maxLength={500} value={comment} onChange={(e) => setComment(e.target.value)} />
      <Button disabled={!rating} loading={send.isPending} onClick={() => send.mutate()} style={{ alignSelf: 'flex-start' }}>Submit rating</Button>
    </section>
  );
}
