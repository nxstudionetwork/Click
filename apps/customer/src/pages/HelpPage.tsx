import { useMemo, useState } from 'react';
import { Link } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { useAuth } from '../auth/AuthProvider';
import { EmptyState, ErrorState, Icon, Skeleton } from '../components/ui';
import { FAQ, HELP_TOPICS } from '../features/support/faq';
import { TICKET_STATUS_LABEL } from '../features/support/status';
import { api } from '../lib/api';
import { formatDateTime } from '../lib/format';

export function HelpPage() {
  const { status } = useAuth();
  const [query, setQuery] = useState('');
  const [topic, setTopic] = useState<string>('');
  const tickets = useQuery({ queryKey: ['customer', 'support'], queryFn: api.customer.support.list, enabled: status === 'authenticated' });
  const faqs = useMemo(() => {
    const t = query.trim().toLowerCase();
    return FAQ.filter((f) => (!topic || f.topic === topic) && (!t || `${f.q} ${f.a}`.toLowerCase().includes(t)));
  }, [query, topic]);

  return (
    <div className="stack">
      <div className="page-head"><div><h1>Help & Support</h1><p>Find answers or contact the Click support team.</p></div>
        <Link to="/help/new" className="btn btn--primary">Contact support</Link>
      </div>
      <div className="search" role="search"><Icon name="search" /><input value={query} onChange={(e) => setQuery(e.target.value)} placeholder="Search help articles" aria-label="Search help" /></div>
      <div className="chips">
        <button className="chip" aria-pressed={!topic} onClick={() => setTopic('')}>All topics</button>
        {HELP_TOPICS.map((t) => <button key={t.id} className="chip" aria-pressed={topic === t.id} onClick={() => setTopic(t.id)}>{t.label}</button>)}
      </div>
      <section className="card card--pad">
        <h3>Frequently asked questions</h3>
        {faqs.length === 0 ? <p className="muted small" style={{ marginTop: 12 }}>No articles match. <Link to="/help/new" style={{ color: 'var(--c-brand)' }}>Contact support</Link></p>
          : faqs.map((f) => <details key={f.q} className="faq"><summary>{f.q}</summary><p>{f.a}</p></details>)}
      </section>
      {status === 'authenticated' && (
        <section className="stack">
          <h2>Your support requests</h2>
          {tickets.isError ? <ErrorState error={tickets.error} onRetry={() => tickets.refetch()} />
            : tickets.isPending ? <Skeleton height={80} radius={16} />
            : tickets.data.results.length === 0 ? <EmptyState icon="help" title="No support requests" message="Requests you raise will appear here with their status." />
            : (
              <div className="card list">
                {tickets.data.results.map((t) => (
                  <Link key={t.id} to={`/help/tickets/${t.id}`} className="list-row">
                    <span style={{ flex: 1, minWidth: 0 }}>
                      <span className="truncate" style={{ display: 'block', fontWeight: 600 }}>{t.subject}</span>
                      <span className="small muted">{t.reference} · {formatDateTime(t.createdAt)}{t.orderNumber ? ` · ${t.orderNumber}` : ''}</span>
                    </span>
                    <span className="badge">{TICKET_STATUS_LABEL[t.status]}</span>
                  </Link>
                ))}
              </div>
            )}
        </section>
      )}
    </div>
  );
}
