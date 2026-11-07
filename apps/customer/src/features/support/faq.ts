/** Help-centre content (editorial copy, not user data). Moves to a CMS/Business OS later. */
import type { SupportCategory } from '@click/api';

export interface FaqEntry { topic: SupportCategory; q: string; a: string }

export const HELP_TOPICS: { id: SupportCategory; label: string }[] = [
  { id: 'order', label: 'Orders' },
  { id: 'payment', label: 'Payments' },
  { id: 'delivery', label: 'Delivery' },
  { id: 'ride', label: 'Rides' },
  { id: 'account', label: 'Account' },
  { id: 'service', label: 'Services' },
  { id: 'other', label: 'Other' },
];

export const FAQ: FaqEntry[] = [
  { topic: 'order', q: 'How do I track my order?', a: 'Open Orders and select your order to see its current status. Status updates also arrive in Notifications.' },
  { topic: 'order', q: 'Can I cancel my order?', a: 'You can cancel while the order is placed or confirmed by the store. Once the store starts preparing it, cancellation is no longer available in the app. Raise a support request instead.' },
  { topic: 'order', q: 'An item was missing or wrong', a: 'Open the order, tap “Get help” and describe the problem. Your request is linked to the order so our team can see the details.' },
  { topic: 'payment', q: 'Which payment methods are available?', a: 'Cash on delivery (cash or UPI to the delivery partner) is available today. Secure online payments are coming soon.' },
  { topic: 'payment', q: 'I was charged but my order was cancelled', a: 'For cash on delivery nothing is charged up front. For any payment concern, raise a payment support request with the order attached.' },
  { topic: 'delivery', q: 'How is the delivery time estimated?', a: 'Each store sets a delivery window based on preparation and travel time. The estimated arrival is shown on the order page.' },
  { topic: 'delivery', q: 'Can I change my delivery address after ordering?', a: 'Addresses can’t be changed after placing an order yet. Contact support quickly and we’ll try to help.' },
  { topic: 'ride', q: 'When will rides be available?', a: 'Rides are coming to Click soon. We’ll let you know in Notifications when they launch in your city.' },
  { topic: 'account', q: 'How do I update my name or phone number?', a: 'Go to Settings and edit your profile. Your email is your sign-in ID and can’t be changed in the app yet.' },
  { topic: 'account', q: 'How do Click points work?', a: 'You earn points on delivered orders. See Rewards for your balance, history and expiry dates.' },
  { topic: 'service', q: 'What services does Click offer?', a: 'Food, groceries and shopping are live. Rides, deliveries, tickets and local services are on the way. See Explore.' },
];
