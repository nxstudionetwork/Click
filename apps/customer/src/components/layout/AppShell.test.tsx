import { screen, within } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { renderWithProviders } from '../../test/utils';

vi.mock('../../auth/AuthProvider', () => ({ useAuth: () => ({ status: 'anonymous', user: null }) }));
const { AppShell } = await import('./AppShell');

describe('AppShell navigation', () => {
  it('mobile bottom nav prioritises 5 destinations; sidebar exposes all services', () => {
    renderWithProviders(<AppShell />);
    const bottom = screen.getAllByRole('navigation', { name: 'Primary' })[0]!;
    expect(within(bottom).getAllByRole('link').map((a) => a.textContent)).toEqual(['Home', 'Explore', 'Orders', 'Rewards', 'Account']);
    const side = screen.getByRole('complementary', { name: 'Main navigation' });
    for (const name of ['Food', 'Groceries', 'Shopping', 'Rides', 'Deliveries', 'Tickets', 'Services', 'Wishlist', 'Offers', 'Help & Support', 'Settings']) {
      expect(within(side).getByRole('link', { name: new RegExp(name) })).toBeInTheDocument();
    }
  });

  it('shows AI entry point and sign-in for anonymous users, no notification bell', () => {
    renderWithProviders(<AppShell />);
    expect(screen.getByRole('link', { name: 'Ask Click AI' })).toHaveAttribute('href', '/assistant');
    expect(screen.getByRole('link', { name: 'Sign in' })).toBeInTheDocument();
    expect(within(screen.getByRole('banner')).queryByRole('link', { name: /^Notifications/ })).toBeNull();
  });
});
