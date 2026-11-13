import { screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { renderWithProviders } from '../test/utils';
import { validatePhoto } from '../features/profile/PhotoSheet';
import { validateName } from '../features/profile/ProfileIdentity';

const logout = vi.fn().mockResolvedValue(undefined);
const refreshUser = vi.fn();
const user = { fullName: 'Asha Rao', email: 'asha@example.com', phone: '+919876543210', phoneVerified: true, customerCode: 'CLK-CS-000042', avatarUrl: null as string | null };
vi.mock('../auth/AuthProvider', () => ({ useAuth: () => ({ status: 'authenticated', user, logout, refreshUser }) }));
const api = vi.hoisted(() => ({
  auth: { updateMe: vi.fn(), uploadAvatar: vi.fn(), removeAvatar: vi.fn() },
  customer: {
    profileSummary: vi.fn().mockResolvedValue({ activity: { orders: 20, bookings: 4, total: 24 }, wishlist: 8, addresses: 0, unreadNotifications: 3, rewardsBalance: 1250 }),
    wallet: vi.fn().mockResolvedValue({ balance: '3806.15', currency: 'INR', transactions: [], topUpAvailable: false }),
  },
}));
vi.mock('../lib/api', () => ({ api }));
const { ProfilePage } = await import('./ProfilePage');

describe('Profile', () => {
  beforeEach(() => { vi.clearAllMocks(); });

  it('shows the real identity: name, immutable Click. ID with copy, masked verified phone, email', async () => {
    const writeText = vi.fn().mockResolvedValue(undefined);
    Object.assign(navigator, { clipboard: { writeText } });
    renderWithProviders(<ProfilePage />);
    expect(screen.getByRole('heading', { level: 1, name: 'Profile' })).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: 'Asha Rao' })).toBeInTheDocument();
    expect(screen.getByText('CLK-CS-000042')).toBeInTheDocument();
    expect(screen.queryByRole('textbox', { name: /Click\. ID/ })).toBeNull(); // the ID is never editable
    expect(screen.getByText(/\+91 9876••••10/)).toBeInTheDocument();
    expect(document.body.textContent).not.toContain('9876543210'); // the full number is never shown
    expect(screen.getByText('Verified')).toBeInTheDocument();
    expect(screen.getByText('asha@example.com')).toBeInTheDocument();
    await userEvent.click(screen.getByRole('button', { name: 'Copy your Click. ID' }));
    expect(writeText).toHaveBeenCalledWith('CLK-CS-000042');
    expect(await screen.findByRole('button', { name: 'Click. ID copied' })).toBeInTheDocument();
  });

  it('badges show real counts; the wallet stays masked and is fetched only when revealed', async () => {
    renderWithProviders(<ProfilePage />);
    expect(await screen.findByText('24 items')).toBeInTheDocument();
    expect(screen.getByText('8 saved')).toBeInTheDocument();
    expect(screen.getByText('1,250 pts')).toBeInTheDocument();
    expect(screen.getByText('₹ ••••')).toBeInTheDocument();
    expect(api.customer.wallet).not.toHaveBeenCalled();
    await userEvent.click(screen.getByRole('button', { name: 'Show wallet balance' }));
    expect(await screen.findByText(/3,806\.15/)).toBeInTheDocument();
    expect(screen.getByRole('link', { name: /Activity/ })).toHaveAttribute('href', '/activity');
    expect(screen.getByRole('link', { name: /Wishlist/ })).toHaveAttribute('href', '/wishlist');
  });

  it('account rows open the existing pages and show unread notifications', async () => {
    renderWithProviders(<ProfilePage />);
    const account = screen.getByRole('navigation', { name: 'Account' });
    expect(within(account).getAllByRole('link').map((l) => l.getAttribute('href'))).toEqual([
      '/account/card', '/account/addresses', '/account/payments', '/account/invoices', '/account/reviews', '/gift-cards/mine', '/safety', '/notifications', '/settings', '/help',
    ]);
    expect(await within(account).findByLabelText('3 unread')).toBeInTheDocument();
    expect(screen.getByText('A venture of IFX Group')).toBeInTheDocument();
  });

  it('log out asks for confirmation, then signs out and returns to sign in', async () => {
    renderWithProviders(<ProfilePage />);
    await userEvent.click(screen.getByRole('button', { name: /Log out/ }));
    const dialog = screen.getByRole('dialog', { name: 'Log out of Click.?' });
    await userEvent.click(within(dialog).getByRole('button', { name: 'Cancel' }));
    expect(logout).not.toHaveBeenCalled();
    await userEvent.click(screen.getByRole('button', { name: /Log out/ }));
    await userEvent.click(within(screen.getByRole('dialog', { name: 'Log out of Click.?' })).getByRole('button', { name: 'Log out' }));
    expect(logout).toHaveBeenCalledOnce();
  });

  it('editing the name validates and saves through the API', async () => {
    api.auth.updateMe.mockResolvedValue({ ...user, fullName: 'Asha R' });
    renderWithProviders(<ProfilePage />);
    await userEvent.click(screen.getByRole('button', { name: 'Edit your name' }));
    const field = screen.getByLabelText('Full name');
    await userEvent.clear(field);
    await userEvent.type(field, '1');
    await userEvent.click(screen.getByRole('button', { name: 'Save' }));
    expect(screen.getByText('Enter at least 2 characters.')).toBeInTheDocument();
    expect(api.auth.updateMe).not.toHaveBeenCalled();
    await userEvent.clear(field);
    await userEvent.type(field, 'Asha R');
    await userEvent.click(screen.getByRole('button', { name: 'Save' }));
    expect(api.auth.updateMe).toHaveBeenCalledWith({ fullName: 'Asha R' });
    expect(refreshUser).toHaveBeenCalledWith(expect.objectContaining({ fullName: 'Asha R' }));
  });

  it('photo and name rules match the server', () => {
    expect(validatePhoto(new File(['x'], 'a.gif', { type: 'image/gif' }))).toMatch(/JPG, PNG or WebP/);
    expect(validatePhoto(new File([new Uint8Array(6 * 1024 * 1024)], 'a.jpg', { type: 'image/jpeg' }))).toMatch(/5 MB/);
    expect(validatePhoto(new File(['x'], 'a.webp', { type: 'image/webp' }))).toBeNull();
    expect(validateName('12345')).toMatch(/letters/);
    expect(validateName('  Asha  ')).toBeNull();
  });
});
