import { screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';
import { renderWithProviders } from '../../test/utils';

vi.mock('../../auth/AuthProvider', () => ({ useAuth: () => ({ status: 'anonymous', user: null }) }));
vi.mock('../../lib/api', () => ({ api: {
  catalog: { offers: vi.fn().mockResolvedValue({ results: [] }) },
  customer: { bookings: { list: vi.fn() }, cart: { get: vi.fn() }, notifications: { summary: vi.fn() }, addresses: { list: vi.fn() } },
} }));
const { AppShell } = await import('./AppShell');

describe('AppShell', () => {
  it('primary navigation is Home | Ride | Food | Services | Menu', () => {
    renderWithProviders(<AppShell />);
    const bottom = screen.getAllByRole('navigation', { name: 'Primary' })[1]!;
    expect(within(bottom).getAllByRole('link').map((a) => a.textContent)).toEqual(['Home', 'Ride', 'Food', 'Services']);
    expect(within(bottom).getByRole('button', { name: 'Menu' })).toBeInTheDocument();
  });

  it('Menu opens the service hub with every service group and account areas', async () => {
    renderWithProviders(<AppShell />);
    await userEvent.click(within(screen.getAllByRole('navigation', { name: 'Primary' })[1]!).getByRole('button', { name: 'Menu' }));
    const hub = screen.getByRole('dialog', { name: 'Click menu' });
    for (const name of ['Food', 'Groceries', 'Shopping', 'Rides', 'Parcels', 'Movies & Events', 'Home Services', 'Click Buzz', 'Buddy AI', 'Wallet', 'Bookings', 'Help & Support']) {
      expect(within(hub).getByRole('link', { name: new RegExp(name) })).toBeInTheDocument();
    }
  });

  it('header has unified search (text, voice, camera, Buddy) and an honest voice sheet', async () => {
    renderWithProviders(<AppShell />);
    const header = screen.getByRole('banner');
    expect(within(header).getAllByLabelText('Search Click').length).toBeGreaterThan(0);
    await userEvent.click(within(header).getAllByRole('button', { name: 'Search by voice' })[0]!);
    expect(await screen.findByText('Voice search is coming')).toBeInTheDocument();
    expect(within(header).getAllByRole('button', { name: 'Ask Buddy' }).length).toBeGreaterThan(0);
    expect(within(header).getByRole('button', { name: 'Buddy, Click AI' })).toBeInTheDocument();
  });

  it('anonymous users see Sign in and no notification bell', () => {
    renderWithProviders(<AppShell />);
    const header = screen.getByRole('banner');
    expect(within(header).getByRole('link', { name: 'Sign in' })).toBeInTheDocument();
    expect(within(header).queryByRole('link', { name: /^Notifications/ })).toBeNull();
  });
});
