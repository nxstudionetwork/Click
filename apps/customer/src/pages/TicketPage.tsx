import { Link, useLocation, useParams } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { ApiError } from '@click/api';
import { EmptyState, ErrorState, Icon, Skeleton } from '../components/ui';
import { TICKET_STATUS_LABEL } from '../features/support/status';
import { api } from '../lib/api';
import { formatDateTime } from '../lib/format';

export function TicketPage() {
  const { id = '' } = useParams();
  const location = useLocation();
  const ticket = useQuery({ queryKey: ['customer', 'support', id], queryFn: () => api.customer.support.get(id) });
  if (ticket.isError) {
    return ticket.error instanceof ApiError && ticket.error.status === 404
      ? <EmptyState icon="help" title="Request not found" action={<Link to="/help" className="btn btn--outline">Help & Support</Link>} />
      : <ErrorState error={ticket.error} onRetry={() => ticket.refetch()} />;
  }
  if (ticket.isPending) return <Skeleton height={200} radius={16} />;
  const t = ticket.data;
  return (
    <div className="stack" style={{ maxWidth: 720 }}>
      {(location.state as { created?: boolean } | null)?.created && (
        <div className="card card--pad row" style={{ background: 'var(--c-accent-soft)', borderColor: 'transparent' }} role="status">
          <Icon name="check" /> <strong>Request sent. Our team will get back to you.</strong>
        </div>
      )}
      <Link to="/help" className="btn btn--ghost btn--sm" style={{ alignSelf: 'flex-start', paddingLeft: 4 }}><Icon name="back" size={18} /> Help & Support</Link>
      <div className="page-head"><div><h1>{t.subject}</h1><p>{t.reference} · opened {formatDateTime(t.createdAt)}</p></div><span className="badge badge--brand">{TICKET_STATUS_LABEL[t.status]}</span></div>
      <section className="card card--pad stack" style={{ gap: 'var(--s-2)' }}>
        <span className="small muted" style={{ textTransform: 'capitalize' }}>Topic: {t.category}{t.orderNumber && <> · Order <Link to={`/orders/${t.orderId}`} style={{ color: 'var(--c-brand)' }}>{t.orderNumber}</Link></>}</span>
        <p style={{ whiteSpace: 'pre-wrap' }}>{t.message}</p>
      </section>
      <p className="small muted">Replies from our support team will appear in Notifications. Two-way messaging is coming soon.</p>
    </div>
  );
}
