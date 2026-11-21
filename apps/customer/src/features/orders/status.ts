import type { OrderStatus, StoreType } from '@click/api';

export const STATUS_LABEL: Record<OrderStatus, string> = {
  awaiting_payment: 'Awaiting payment',
  placed: 'Order placed',
  confirmed: 'Confirmed by restaurant',
  preparing: 'Being prepared',
  ready: 'Ready for pickup',
  packed: 'Packed',
  shipped: 'Shipped',
  out_for_delivery: 'Out for delivery',
  delivered: 'Delivered',
  cancelled: 'Cancelled',
};

/** Shopping orders are confirmed by the seller and travel as parcels. */
const RETAIL_LABEL: Partial<Record<OrderStatus, string>> = { confirmed: 'Confirmed by seller' };

/** Grocery orders are accepted by the store, packed, then handed to delivery. */
const GROCERY_LABEL: Partial<Record<OrderStatus, string>> = { confirmed: 'Accepted by store', preparing: 'Packing', ready: 'Packed, awaiting pickup' };

export const statusLabel = (s: OrderStatus, storeType?: StoreType) =>
  (storeType === 'retail' && RETAIL_LABEL[s]) || (storeType === 'grocery' && GROCERY_LABEL[s]) || STATUS_LABEL[s];

export const PROGRESS: OrderStatus[] = ['placed', 'confirmed', 'preparing', 'out_for_delivery', 'delivered'];
/** The steps a Shopping order actually goes through (only states the backend supports). */
export const RETAIL_PROGRESS: OrderStatus[] = ['placed', 'confirmed', 'packed', 'shipped', 'out_for_delivery', 'delivered'];

/** Groceries: every step the store and delivery actually record. */
export const GROCERY_PROGRESS: OrderStatus[] = ['placed', 'confirmed', 'preparing', 'ready', 'out_for_delivery', 'delivered'];

export const progressFor = (storeType?: StoreType) => (storeType === 'retail' ? RETAIL_PROGRESS : storeType === 'grocery' ? GROCERY_PROGRESS : PROGRESS);

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
