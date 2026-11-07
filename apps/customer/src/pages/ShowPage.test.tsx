import { screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';
import { Route, Routes } from 'react-router-dom';
import { renderWithProviders } from '../test/utils';

const create = vi.fn();
vi.mock('../auth/AuthProvider', () => ({ useAuth: () => ({ status: 'authenticated', user: {} }) }));
vi.mock('../features/wallet/useWallet', () => ({ walletKey: ['w'], useWallet: () => ({ data: { balance: '0.00', currency: 'INR' }, isPending: false }) }));
const seat = (label: string, available = true) => ({ label, available });
vi.mock('../lib/api', () => ({ api: { events: { seatMap: vi.fn().mockResolvedValue({
  id: 'sh1', startsAt: '2030-01-01T18:00:00Z', language: 'Hindi', format: '2D', screen: 'Screen 1', price: '200.00', premiumPrice: '350.00', currency: 'INR',
  venue: { id: 'v', name: 'Click Cineplex', city: 'Bengaluru', locality: '', slug: 'v', kind: 'cinema', address: '' }, seatsLeft: 3,
  event: { slug: 'm', title: 'Orbit 9' },
  layout: { maxPerBooking: 10, rows: [{ row: 'A', tier: 'standard', seats: [seat('A1'), seat('A2', false)] }, { row: 'B', tier: 'premium', seats: [seat('B1'), seat('B2')] }] },
}) }, customer: { bookings: { create: (...a: unknown[]) => create(...a) } } } }));
const { ShowPage } = await import('./ShowPage');

describe('ShowPage seat selection', () => {
  it('booked seats are disabled; totals update; wallet disabled without balance; booking sends chosen seats', async () => {
    create.mockReturnValue(new Promise(() => {}));
    renderWithProviders(<Routes><Route path="/shows/:id" element={<ShowPage />} /></Routes>, { route: '/shows/sh1' });
    expect(await screen.findByRole('gridcell', { name: /Seat A2, standard, booked/ })).toBeDisabled();
    await userEvent.click(screen.getByRole('gridcell', { name: /Seat A1/ }));
    await userEvent.click(screen.getByRole('gridcell', { name: /Seat B1/ }));
    expect(screen.getAllByText('A1, B1').length).toBeGreaterThan(0);
    // Desktop aside + mobile booking bar render the same action (CSS shows one per breakpoint).
    expect(screen.getAllByRole('button', { name: /Confirm booking · ₹597\.2/ })).toHaveLength(2);
    expect(screen.getByRole('radio', { name: /Click Wallet/ })).toBeDisabled();
    await userEvent.click(screen.getAllByRole('button', { name: /Confirm booking/ })[0]!);
    expect(create.mock.calls[0]![0]).toMatchObject({ showId: 'sh1', seats: ['A1', 'B1'], paymentMethod: 'pay_at_venue' });
  });
});
