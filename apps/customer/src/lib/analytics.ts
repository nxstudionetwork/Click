import { api } from './api';

/**
 * Product analytics (for Business OS). Events are queued and sent in small batches; names and properties must be on
 * the backend's allow-list (apps/analytics), and only identifiers / counts are sent — never free text, contact
 * details or payment data. Sending is best effort and never blocks the UI.
 */
export type EventName = 'app_opened' | 'screen_viewed' | 'search_performed' | 'category_viewed' | 'store_viewed' | 'product_viewed' | 'cart_created'
  | 'checkout_started' | 'offer_viewed' | 'offer_used' | 'support_requested' | 'referral_shared' | 'buddy_opened' | 'discover_opened';

const queue: { name: EventName; props?: Record<string, string | number>; at: string }[] = [];
const session = (() => { try { return crypto.randomUUID().slice(0, 18); } catch { return `s-${Date.now()}`; } })();
let timer: ReturnType<typeof setTimeout> | undefined;

function flush() {
  timer = undefined;
  if (!queue.length) return;
  const events = queue.splice(0, 20);
  void api.money.analytics.send({ session, platform: 'web', events }).catch(() => undefined);
  if (queue.length) timer = setTimeout(flush, 2000);
}

export function track(name: EventName, props?: Record<string, string | number>) {
  queue.push({ name, props, at: new Date().toISOString() });
  if (queue.length >= 10) flush();
  else if (!timer) timer = setTimeout(flush, 5000);
}

if (typeof document !== 'undefined') {
  document.addEventListener('visibilitychange', () => { if (document.visibilityState === 'hidden') flush(); });
}
