import { screen, waitForElementToBeRemoved, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { renderWithProviders } from '../../test/utils';

const auth = vi.hoisted(() => ({ value: { status: 'anonymous', user: null } as { status: string; user: unknown } }));
vi.mock('../../auth/AuthProvider', () => ({ useAuth: () => auth.value }));
const api = vi.hoisted(() => ({
  catalog: { offers: vi.fn().mockResolvedValue({ results: [] }) },
  customer: {
    wallet: vi.fn().mockResolvedValue({ balance: '10.00', currency: 'INR' }), rewards: vi.fn().mockResolvedValue({ balance: 5 }),
    bookings: { list: vi.fn() }, cart: { get: vi.fn().mockResolvedValue({ itemCount: 0 }) }, notifications: { summary: vi.fn().mockResolvedValue({ unread: 3 }) },
    addresses: { list: vi.fn().mockResolvedValue([]) },
    assistant: { capabilities: vi.fn().mockResolvedValue({ mode: 'basic', voice: false, visualSearch: false }), send: vi.fn() },
  },
  buddy: { track: vi.fn() },
}));
vi.mock('../../lib/api', () => ({ api }));
const { AppShell } = await import('./AppShell');

const signedIn = { status: 'authenticated', user: { fullName: 'Asha Rao', email: 'asha@example.com' } };

describe('AppShell', () => {
  beforeEach(() => { auth.value = { status: 'anonymous', user: null }; });

  it('primary navigation is Home | Ride | Food | Shop | Explore, each with its own service colour', () => {
    renderWithProviders(<AppShell />);
    const bottom = screen.getAllByRole('navigation', { name: 'Primary' })[1]!;
    const items = [...bottom.children] as HTMLElement[];
    expect(items.map((a) => a.textContent)).toEqual(['Home', 'Ride', 'Food', 'Shop', 'Explore']);
    expect(items.map((a) => a.getAttribute('href'))).toEqual(['/', '/rides', '/food', '/shopping', null]);
    expect(items.map((a) => a.dataset.theme)).toEqual(['default', 'ride', 'food', 'shopping', 'explore']);
  });

  it('the global search bar appears only on Home; other pages keep just the fixed header', () => {
    const { unmount } = renderWithProviders(<AppShell />, { route: '/' });
    expect(within(screen.getByRole('banner')).getAllByLabelText('Search Click.').length).toBeGreaterThan(0);
    unmount();
    renderWithProviders(<AppShell />, { route: '/wallet' });
    expect(within(screen.getByRole('banner')).queryByLabelText('Search Click.')).toBeNull();
    expect(within(screen.getByRole('banner')).getByRole('img', { name: 'Click.' })).toBeInTheDocument();
  });

  it('the location selector lives only on Home; other pages never show or ask for location in the header', () => {
    auth.value = signedIn;
    const { unmount } = renderWithProviders(<AppShell />, { route: '/' });
    expect(screen.getAllByRole('button', { name: /Change location/ }).length).toBeGreaterThan(0);
    unmount();
    for (const route of ['/rides', '/food', '/shopping', '/showtime']) {
      const r = renderWithProviders(<AppShell />, { route });
      expect(screen.queryByRole('button', { name: /Change location/ })).toBeNull();
      r.unmount();
    }
  });

  it('Explore opens as a bottom sheet over the page for signed-in customers, and closes with Escape', async () => {
    auth.value = signedIn;
    renderWithProviders(<AppShell />);
    const bottom = screen.getAllByRole('navigation', { name: 'Primary' })[1]!;
    await userEvent.click(within(bottom).getByRole('button', { name: 'Explore' }));
    const sheet = await screen.findByRole('dialog', { name: 'Explore' });
    expect(within(sheet).getByRole('link', { name: /^Food:/ })).toHaveAttribute('href', '/food');
    expect(within(sheet).getByRole('link', { name: /^Rides:/ })).toHaveAttribute('href', '/rides');
    expect(within(bottom).getByRole('button', { name: 'Explore' })).toHaveClass('active');
    await userEvent.keyboard('{Escape}');
    await waitForElementToBeRemoved(() => screen.queryByRole('dialog', { name: 'Explore' }));
  });

  it('header shows the Click. logo first, then Buddy, notifications and profile; no development labels', () => {
    auth.value = signedIn;
    renderWithProviders(<AppShell />);
    const header = screen.getByRole('banner');
    const logo = within(header).getByRole('img', { name: 'Click.' });
    expect(logo.querySelector('img')!.getAttribute('src')).toBe('/brand/click-icon-96.png');
    expect(logo.textContent).toBe('Click.');
    expect(within(header).getByRole('button', { name: /^Buddy/ })).toBeInTheDocument();
    expect(within(header).getByRole('link', { name: /^Notifications/ })).toHaveAttribute('href', '/notifications');
    expect(within(header).getByRole('link', { name: 'Your profile' })).toHaveAttribute('href', '/account');
    expect(document.body.textContent).not.toMatch(/development|mock data|dev mode|debug/i);
  });

  it('Buddy opens a premium Man / Go choice first, not a chat', async () => {
    auth.value = signedIn;
    renderWithProviders(<AppShell />);
    await userEvent.click(within(screen.getByRole('banner')).getByRole('button', { name: /^Buddy/ }));
    const sheet = screen.getByRole('dialog', { name: 'Choose Buddy' });
    expect(within(sheet).getByRole('button', { name: /Man.*Talk, ask, search, plan and control Click\./ })).toBeInTheDocument();
    expect(within(sheet).getByRole('button', { name: /Go.*Just speak\. Tell Click what you need\./ })).toBeInTheDocument();
    expect(api.buddy.track).toHaveBeenCalledWith('opened');
  });

  it('search offers voice and camera, and shows hints when focused', async () => {
    renderWithProviders(<AppShell />);
    const header = screen.getByRole('banner');
    await userEvent.click(within(header).getAllByLabelText('Search Click.')[0]!);
    expect(screen.getByRole('dialog', { name: 'Search suggestions' })).toBeInTheDocument();
    expect(within(header).getAllByRole('button', { name: 'Search by voice' }).length).toBeGreaterThan(0);
    expect(within(header).getAllByRole('button', { name: 'Search with camera' }).length).toBeGreaterThan(0);
  });

  it('anonymous users see Sign in instead of a profile, and the Buzz entry is always reachable', () => {
    renderWithProviders(<AppShell />);
    const header = screen.getByRole('banner');
    expect(within(header).getByRole('link', { name: 'Sign in' })).toHaveAttribute('href', '/login');
    expect(within(header).queryByRole('link', { name: 'Your profile' })).toBeNull();
    expect(screen.getByRole('link', { name: 'Open Click. Buzz' })).toHaveAttribute('href', '/buzz');
  });
});
