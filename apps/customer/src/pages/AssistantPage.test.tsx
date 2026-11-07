import { screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';
import { ApiError } from '@click/api';
import { renderWithProviders } from '../test/utils';

const send = vi.fn();
vi.mock('../auth/AuthProvider', () => ({ useAuth: () => ({ status: 'authenticated', user: { fullName: 'A' } }) }));
vi.mock('../lib/api', () => ({ api: { customer: { assistant: { send: (...a: unknown[]) => send(...a) } } } }));
const { AssistantPage } = await import('./AssistantPage');

describe('AssistantPage', () => {
  it('sends the conversation to the backend and renders its reply', async () => {
    send.mockResolvedValueOnce({ message: { role: 'assistant', content: 'Your order is on the way.' } });
    renderWithProviders(<AssistantPage />);
    await userEvent.type(screen.getByLabelText('Message Click AI'), 'Where is my order?{enter}');
    expect(await screen.findByText('Your order is on the way.')).toBeInTheDocument();
    expect(send.mock.calls[0]![0]).toEqual([{ role: 'user', content: 'Where is my order?' }]);
  });

  it('is honest when no AI provider is configured (no fake answers)', async () => {
    send.mockRejectedValueOnce(new ApiError(503, { code: 'ai_unavailable', message: 'Click AI isn’t available yet.' }));
    renderWithProviders(<AssistantPage />);
    await userEvent.type(screen.getByLabelText('Message Click AI'), 'hello{enter}');
    expect(await screen.findByText('Click AI isn’t available yet')).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Help & Support' })).toBeInTheDocument();
  });
});
