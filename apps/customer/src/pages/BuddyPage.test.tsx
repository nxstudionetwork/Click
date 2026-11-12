import { screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';
import { renderWithProviders } from '../test/utils';

const buddy = vi.hoisted(() => ({
  start: vi.fn(), say: vi.fn(), act: vi.fn(), decide: vi.fn(), track: vi.fn(), conversation: vi.fn(),
  conversations: vi.fn().mockResolvedValue({ results: [], hasMore: false }), edit: vi.fn(), remove: vi.fn(),
}));
vi.mock('../auth/AuthProvider', () => ({ useAuth: () => ({ status: 'authenticated', user: { fullName: 'A' } }) }));
vi.mock('../lib/api', () => ({ api: { buddy, customer: { assistant: { capabilities: vi.fn().mockResolvedValue({ mode: 'basic', voice: false, visualSearch: false }), transcribe: vi.fn() } } } }));
vi.mock('../features/menu/useAddToCart', () => ({ useAddToCart: () => ({ addToCart: vi.fn(), isAdding: false }) }));
const { BuddyPage } = await import('./BuddyPage');

const order = { id: 'o1', number: 'CLK-ABC', status: 'placed', store: { id: 's', slug: 's', name: 'Dosa District', storeType: 'restaurant', imageUrl: '' },
  total: '200.00', currency: 'INR', itemCount: 1, itemNames: ['Dosa'], lineCount: 1, paymentStatus: 'pending', createdAt: '2026-11-07T10:00:00Z' };
const conv = { id: 'c1', title: 'Your orders', archived: false, mode: 'man', topic: 'orders', updatedAt: '2026-11-07T10:00:00Z' };
const msg = (content: string, extra = {}) => ({ id: `m-${content}`, role: 'assistant', content, cards: [], actions: [], attachment: {}, viaVoice: false, createdAt: '2026-11-07T10:00:00Z', ...extra });

describe('Buddy MAN', () => {
  it('is its own workspace: Buddy header, welcome, input bar with pin and honest voice; replies render real cards', async () => {
    buddy.start.mockResolvedValue(conv);
    buddy.say.mockResolvedValueOnce({ message: msg('Your latest order CLK-ABC is placed.', { cards: [{ type: 'order', order }], actions: [{ label: 'Open order', path: '/orders/o1' }] }),
      conversation: conv, understoodAs: null, mode: 'basic' });
    renderWithProviders(<BuddyPage />);
    const header = screen.getByRole('banner');
    for (const n of ['New chat', 'Click. Home', 'Recent chats']) expect(within(header).getByRole('button', { name: n })).toBeInTheDocument();
    expect(screen.queryByRole('navigation', { name: 'Primary' })).toBeNull(); // no Click bottom navigation
    expect(screen.getByText('Hi, I’m Buddy.')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Attach Click. context' })).toBeInTheDocument();
    expect(await screen.findByRole('button', { name: 'Voice isn’t switched on yet' })).toBeDisabled();
    await userEvent.type(screen.getByLabelText('Ask Buddy anything'), 'Show my recent orders');
    await userEvent.click(screen.getByRole('button', { name: 'Send' }));
    expect(await screen.findByText('Your latest order CLK-ABC is placed.')).toBeInTheDocument();
    expect(screen.getByText('Dosa District')).toBeInTheDocument();
    expect(buddy.start).toHaveBeenCalledWith('man');
    expect(buddy.say.mock.calls[0]!.slice(0, 2)).toEqual(['c1', 'Show my recent orders']);
  });

  it('confirmation-tier actions wait for an explicit Confirm; failures keep the message for a retry', async () => {
    buddy.start.mockResolvedValue(conv);
    buddy.say.mockResolvedValueOnce({ message: msg('I can cancel it — you’ll confirm first.', { actions: [{ label: 'Cancel CLK-ABC', action: 'cancel_order', args: { orderId: 'o1' } }] }),
      conversation: conv, understoodAs: null, mode: 'basic' });
    buddy.act.mockResolvedValueOnce({ id: 'r1', action: 'cancel_order', tier: 'confirm', status: 'awaiting_confirmation', summary: 'Cancel order CLK-ABC from Dosa District (₹200)?', result: {}, error: '', expiresAt: null });
    buddy.decide.mockResolvedValueOnce({ id: 'r1', action: 'cancel_order', tier: 'confirm', status: 'confirmed', summary: '', result: { message: 'Order CLK-ABC cancelled.' }, error: '', expiresAt: null });
    renderWithProviders(<BuddyPage />);
    await userEvent.type(screen.getByLabelText('Ask Buddy anything'), 'Cancel my order');
    await userEvent.click(screen.getByRole('button', { name: 'Send' }));
    await userEvent.click(await screen.findByRole('button', { name: /Cancel CLK-ABC/ }));
    const card = await screen.findByRole('alertdialog');
    expect(within(card).getByText('Cancel order CLK-ABC from Dosa District (₹200)?')).toBeInTheDocument();
    expect(buddy.decide).not.toHaveBeenCalled(); // nothing happens before the customer confirms
    await userEvent.click(within(card).getByRole('button', { name: 'Confirm' }));
    expect(buddy.decide).toHaveBeenCalledWith('r1', 'confirm');
    expect((await screen.findAllByText('Order CLK-ABC cancelled.')).length).toBeGreaterThan(0);

    buddy.say.mockRejectedValueOnce(Object.assign(new Error('Buddy couldn’t answer right now.'), { code: 'ai_error' }));
    await userEvent.type(screen.getByLabelText('Ask Buddy anything'), 'hello');
    await userEvent.click(screen.getByRole('button', { name: 'Send' }));
    expect(await screen.findByRole('alert')).toHaveTextContent(/couldn’t answer/);
    expect(screen.getByRole('button', { name: 'Retry' })).toBeInTheDocument();
    expect(screen.getByText('hello')).toBeInTheDocument(); // the message is kept
  });
});
