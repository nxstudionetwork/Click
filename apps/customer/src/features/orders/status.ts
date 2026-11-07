import type { OrderStatus } from '@click/api';

export const STATUS_LABEL: Record<OrderStatus, string> = {
  placed: 'Order placed',
  confirmed: 'Confirmed by restaurant',
  preparing: 'Being prepared',
  ready: 'Ready for pickup',
  out_for_delivery: 'Out for delivery',
  delivered: 'Delivered',
  cancelled: 'Cancelled',
};

export const PROGRESS: OrderStatus[] = ['placed', 'confirmed', 'preparing', 'out_for_delivery', 'delivered'];

export const isTerminal = (s: OrderStatus) => s === 'delivered' || s === 'cancelled';

export function statusTone(s: OrderStatus): string {
  if (s === 'cancelled') return 'badge--danger';
  if (s === 'delivered') return 'badge--accent';
  return 'badge--brand';
}

export const PAYMENT_LABEL: Record<import('@click/api').PaymentStatus, string> = {
  pending: 'Payment pending',
  authorized: 'Payment processing',
  captured: 'Paid',
  failed: 'Payment failed',
  cancelled: 'Payment cancelled',
  refunded: 'Refunded',
};
