import { Link } from 'react-router-dom';
import type { OrderSummary } from '@click/api';
import { SmartImage } from '../../components/ui';
import { formatDateTime, formatMoney } from '../../lib/format';
import { PAYMENT_LABEL, STATUS_LABEL, statusTone } from './status';

export function OrderCard({ order }: { order: OrderSummary }) {
  const more = order.itemCount - order.itemNames.length;
  return (
    <Link to={`/orders/${order.id}`} className="order-row">
      <SmartImage src={order.store.imageUrl} alt={order.store.name} />
      <div style={{ flex: 1, minWidth: 0 }}>
        <div className="spread"><strong>{order.store.name}</strong><strong>{formatMoney(order.total, order.currency)}</strong></div>
        <div className="small truncate">{order.itemNames.join(', ')}{more > 0 ? ` +${more} more` : ''}</div>
        <div className="muted small">{formatDateTime(order.createdAt)} · {order.number}</div>
        <div className="row" style={{ marginTop: 6, flexWrap: 'wrap' }}>
          <span className={`badge ${statusTone(order.status)}`}>{STATUS_LABEL[order.status]}</span>
          {order.paymentStatus && <span className="badge">{PAYMENT_LABEL[order.paymentStatus]}</span>}
        </div>
      </div>
    </Link>
  );
}
