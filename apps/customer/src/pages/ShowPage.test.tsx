import { screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';
import { Route, Routes } from 'react-router-dom';
import { renderWithProviders } from '../test/utils';

const hold = vi.fn();
vi.mock('../auth/AuthProvider', () => ({ useAuth: () => ({ status: 'authenticated', user: {} }) }));
const seat = (row: string, n: number, state = 'available', accessible = false) => ({ label: `${row}${n}`, number: n, state, accessible });
vi.mock('../lib/api', () => ({ api: {
  events: { seatMap: vi.fn().mockResolvedValue({
    id: 'sh1', startsAt: '2030-01-01T18:00:00Z', language: 'Hindi', format: 'IMAX', screen: 'Audi 1', sound: 'Dolby Atmos', currency: 'INR',
    venue: { id: 'v', name: 'Click Cineplex', city: 'Bengaluru', locality: 'Indiranagar', slug: 'v', address: '', facilities: [], latitude: null, longitude: null },
    event: { slug: 'm', title: 'Orbit 9', genres: [], posterUrl: '', kind: 'movie' },
    tiers: [{ code: 'classic', name: 'Classic', price: '200.00' }, { code: 'recliner', name: 'Recliner', price: '450.00' }],
    rows: [
      { row: 'A', tier: 'classic', gaps: [1], seats: [seat('A', 1, 'available', true), seat('A', 2, 'booked'), seat('A', 3, 'unavailable')] },
      { row: 'B', tier: 'recliner', gaps: [], seats: [seat('B', 1), seat('B', 2, 'held')] },
    ],
    maxPerBooking: 10, holdMinutes: 8, myHold: null, cancellationHours: 2,
  }) },
  showtime: { hold: (...a: unknown[]) => hold(...a) },
} }));
const { ShowPage } = await import('./ShowPage');

describe('Showtime seat selection', () => {
  it('uses the screen layout and tier prices, blocks taken seats and holds the chosen ones', async () => {
    hold.mockReturnValue(new Promise(() => {}));
    renderWithProviders(<Routes><Route path="/shows/:id" element={<ShowPage />} /></Routes>, { route: '/shows/sh1' });
    expect(await screen.findByRole('button', { name: /Seat A2, Classic, taken/ })).toBeDisabled();
    expect(screen.getByRole('button', { name: /Seat B2, Recliner, taken/ })).toBeDisabled();
    expect(screen.getByText(/Recliner · ₹450/)).toBeInTheDocument();
    await userEvent.click(screen.getByRole('button', { name: /Seat A1, Classic, accessible/ }));
    await userEvent.click(screen.getByRole('button', { name: /Seat B1, Recliner/ }));
    expect(screen.getByText('2 seats: A1, B1')).toBeInTheDocument();
    expect(screen.getByText('₹650')).toBeInTheDocument();
    await userEvent.click(screen.getByRole('button', { name: 'Continue' }));
    expect(hold).toHaveBeenCalledWith('sh1', ['A1', 'B1']);
  });
});
