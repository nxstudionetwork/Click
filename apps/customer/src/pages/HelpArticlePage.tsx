import { useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import { useMutation, useQuery } from '@tanstack/react-query';
import { useAuth } from '../auth/AuthProvider';
import { ErrorState, Icon, Skeleton } from '../components/ui';
import { MoneyHead, Section, iconFor } from '../features/money/parts';
import { api } from '../lib/api';

/** A help article, its next step (when there is one), "was this helpful?" and related articles. */
export function HelpArticlePage() {
  const { slug = '' } = useParams();
  const { status } = useAuth();
  const q = useQuery({ queryKey: ['help', 'article', slug], queryFn: () => api.money.support.article(slug) });
  const [voted, setVoted] = useState<boolean | null>(null);
  const vote = useMutation({ mutationFn: (helpful: boolean) => api.money.support.feedback(slug, helpful), onSuccess: (r) => setVoted(r.helpful) });
  if (q.isError) return <div className="mn-page"><MoneyHead title="Help" back="/help" /><ErrorState error={q.error} onRetry={() => q.refetch()} /></div>;
  if (!q.data) return <div className="mn-page"><MoneyHead title="Help" back="/help" /><Skeleton height={300} /></div>;
  const a = q.data;
  return (
    <div className="mn-page">
      <MoneyHead title={a.categoryLabel} back="/help" />
      <article className="mn-article">
        <h2>{a.title}</h2>
        <p className="mn-muted">{a.summary}</p>
        {a.body.map((p, i) => <p key={i}>{p}</p>)}
        {a.steps.length > 0 && <ol className="mn-steps-list">{a.steps.map((s) => <li key={s}>{s}</li>)}</ol>}
        {a.action && <Link to={a.action.path} className="btn btn--primary">{a.action.label}</Link>}
      </article>

      <div className="mn-card mn-feedback">
        {voted === null ? (
          <>
            <strong>Was this helpful?</strong>
            {status === 'authenticated' ? (
              <div className="mn-row2">
                <button type="button" className="btn btn--outline btn--sm" disabled={vote.isPending} onClick={() => vote.mutate(true)}>Yes</button>
                <button type="button" className="btn btn--outline btn--sm" disabled={vote.isPending} onClick={() => vote.mutate(false)}>No</button>
              </div>
            ) : <span className="small mn-muted">Sign in to rate this article.</span>}
          </>
        ) : voted ? <span>Thanks for letting us know.</span> : (
          <span>Sorry it didn’t help. <Link to={`/help/new?category=${a.category}&subject=${encodeURIComponent(a.title)}`} className="mn-link">Raise a request</Link> and we’ll sort it out.</span>
        )}
      </div>

      {a.related.length > 0 && (
        <Section title="Related" id="mn-related">
          <ul className="mn-list">{a.related.map((r) => (
            <li key={r.slug}><Link to={`/help/articles/${r.slug}`} className="mn-row"><span className="mn-row__icon"><Icon name={iconFor(r.category)} size={18} /></span>
              <span className="mn-row__text"><strong>{r.title}</strong><span className="small mn-muted">{r.summary}</span></span><Icon name="right" size={16} /></Link></li>
          ))}</ul>
        </Section>
      )}
      <Link to={`/help/new?category=${a.category}`} className="mn-row mn-row--card"><span className="mn-row__icon"><Icon name="send" size={18} /></span>
        <span className="mn-row__text"><strong>Contact support</strong><span className="small mn-muted">Your recent order or booking can be attached</span></span><Icon name="right" size={16} /></Link>
    </div>
  );
}
