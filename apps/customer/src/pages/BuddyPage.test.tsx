import { screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';
import { renderWithProviders } from '../test/utils';

const send = vi.fn();
vi.mock('../auth/AuthProvider', () => ({ useAuth: () => ({ status: 'authenticated', user: { fullName: 'A' } }) }));
vi.mock('../lib/api', () => ({ api: { customer: { assistant: { send: (...a: unknown[]) => send(...a) } } } }));
vi.mock('../features/menu/useAddToCart', () => ({ useAddToCart: () => ({ addToCart: vi.fn(), isAdding: false }) }));
const { BuddyPage } = await import('./BuddyPage');

const order = { id: 'o1', number: 'CLK-ABC', status: 'preparing', store: { id: 's', slug: 's', name: 'Dosa District', storeType: 'restaurant', imageUrl: '' },
  total: '200.00', currency: 'INR', itemCount: 1, itemNames: ['Dosa'], paymentStatus: 'pending', createdAt: '2026-11-07T10:00:00Z' };

describe('BuddyPage', () => {
  it('renders the backend reply with real cards and follow-up actions', async () => {
    send.mockResolvedValueOnce({ message: { role: 'assistant', content: 'Your latest order CLK-ABC is being prepared.' },
      cards: [{ type: 'order', order }], actions: [{ label: 'Open order', path: '/orders/o1' }], mode: 'basic' });
    renderWithProviders(<BuddyPage />);
    await userEvent.click(screen.getByRole('button', { name: 'Where is my order?' }));
    expect(await screen.findByText('Your latest order CLK-ABC is being prepared.')).toBeInTheDocument();
    expect(screen.getByText('Dosa District')).toBeInTheDocument();
    expect(screen.getByRole('link', { name: /Open order/ })).toHaveAttribute('href', '/orders/o1');
    expect(send.mock.calls[0]![0]).toEqual([{ role: 'user', content: 'Where is my order?' }]);
    expect(screen.getByText('Basic mode')).toBeInTheDocument();
  });

  it('new chat clears the conversation; failures are explained, never faked', async () => {
    send.mockRejectedValueOnce(Object.assign(new Error('Buddy couldn’t answer right now.'), { code: 'ai_error' }));
    renderWithProviders(<BuddyPage />);
    await userEvent.type(screen.getByLabelText('Message Buddy'), 'hello{enter}');
    expect(await screen.findByText('Buddy couldn’t answer')).toBeInTheDocument();
    await userEvent.click(screen.getByRole('button', { name: 'New chat' }));
    expect(screen.getByText('How can I help?')).toBeInTheDocument();
  });
});
