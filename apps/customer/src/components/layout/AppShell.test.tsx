import { screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { renderWithProviders } from '../../test/utils';

const auth = vi.hoisted(() => ({ value: { status: 'anonymous', user: null } as { status: string; user: unknown } }));
vi.mock('../../auth/AuthProvider', () => ({ useAuth: () => auth.value }));
const api = vi.hoisted(() => ({
  catalog: { offers: vi.fn().mockResolvedValue({ results: [] }) },
  customer: {
    bookings: { list: vi.fn() }, cart: { get: vi.fn().mockResolvedValue({ itemCount: 0 }) }, notifications: { summary: vi.fn().mockResolvedValue({ unread: 3 }) },
    addresses: { list: vi.fn().mockResolvedValue([]) },
    assistant: { capabilities: vi.fn().mockResolvedValue({ mode: 'basic', voice: false, visualSearch: false }), send: vi.fn() },
  },
}));
vi.mock('../../lib/api', () => ({ api }));
const { AppShell } = await import('./AppShell');

const signedIn = { status: 'authenticated', user: { fullName: 'Asha Rao', email: 'asha@example.com' } };

describe('AppShell', () => {
  beforeEach(() => { auth.value = { status: 'anonymous', user: null }; });

  it('primary navigation is Home | Ride | Food | Explore | Profile, each with its own service colour', () => {
    renderWithProviders(<AppShell />);
    const bottom = screen.getAllByRole('navigation', { name: 'Primary' })[1]!;
    const links = within(bottom).getAllByRole('link');
    expect(links.map((a) => a.textContent)).toEqual(['Home', 'Ride', 'Food', 'Explore', 'Profile']);
    expect(links.map((a) => a.getAttribute('href'))).toEqual(['/', '/rides', '/food', '/explore', '/account']);
    expect(links.map((a) => a.dataset.theme)).toEqual(['default', 'ride', 'food', 'explore', 'profile']);
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

  it('Buddy opens a GO / MAN choice; GO is honest when voice is not enabled', async () => {
    auth.value = signedIn;
    renderWithProviders(<AppShell />);
    await userEvent.click(within(screen.getByRole('banner')).getByRole('button', { name: /^Buddy/ }));
    const sheet = screen.getByRole('dialog', { name: 'Buddy' });
    expect(within(sheet).getByRole('button', { name: /MAN/ })).toBeInTheDocument();
    await userEvent.click(within(sheet).getByRole('button', { name: /GO/ }));
    expect(await screen.findByText(/Voice isn’t switched on for Click\. yet/)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Voice unavailable' })).toBeDisabled();
    expect(screen.getByLabelText('Tell Buddy what you need')).toBeInTheDocument();
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
