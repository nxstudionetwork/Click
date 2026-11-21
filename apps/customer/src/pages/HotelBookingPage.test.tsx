import { screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';
import { Route, Routes } from 'react-router-dom';
import { renderWithProviders } from '../test/utils';

const base = {
  id: 'b1', number: 'HTL-TEST0001', kind: 'hotel', status: 'pending_payment', statusLabel: 'Pending payment', paymentStatus: 'pending', paymentStatusLabel: 'Payment pending',
  property: { id: 'p1', name: 'Orbit Business Hotel', area: 'HITEC City', destination: 'Hyderabad', imageUrl: '', accent: '#7dd3fc' },
  roomName: 'Deluxe King', checkIn: '2099-01-10', checkOut: '2099-01-12', nights: 2, rooms: 1, adults: 2, children: 0, total: '10640.00',
  createdAt: '2099-01-01T10:00:00Z', isActive: true, reviewed: false,
  guest: { name: 'Asha Rao', email: '', phone: '+91 98765 43210', others: [] }, specialRequests: '', rateName: 'Room only', mealPlan: 'room_only',
  mealLabel: 'Room only', paymentMode: 'pay_now', paymentModeLabel: 'Pay now', policy: 'Free cancellation until 08 Jan 2099, 2:00 PM.', refundable: true,
  freeCancelUntil: '2099-01-08T08:30:00Z', nightly: [{ date: '2099-01-10', price: '4750.00' }, { date: '2099-01-11', price: '4750.00' }], roomTotal: '9500.00',
  discount: '0.00', offerTitle: '', tax: '1140.00', refunded: '0.00', address: 'HITEC City, Hyderabad', latitude: 17.44, longitude: 78.37,
  checkInTime: '14:00', checkOutTime: '11:00', policies: [], holdExpiresAt: new Date(Date.now() + 10 * 60000).toISOString(),
  timeline: [{ to: 'pending_payment', label: 'Pending payment', note: 'Room held', at: '2099-01-01T10:00:00Z' }], payment: null,
  cancellation: { allowed: true, fee: '0.00', refund: null, note: 'Nothing has been charged online.' }, canPay: true, canReview: false, review: null,
  cancelReason: '', tickets: [], modification: 'Changing dates isn’t supported online yet.',
};
const paid = { ...base, status: 'confirmed', statusLabel: 'Confirmed', paymentStatus: 'paid', paymentStatusLabel: 'Paid', canPay: false, holdExpiresAt: null,
  payment: { method: 'wallet', status: 'captured', amount: '10640.00', reference: 'ABCD1234' } };
const act = vi.fn().mockResolvedValue(paid);
vi.mock('../auth/AuthProvider', () => ({ useAuth: () => ({ status: 'authenticated', user: {} }) }));
vi.mock('../lib/api', () => ({ api: { hotels: { booking: vi.fn().mockResolvedValueOnce(base).mockResolvedValue(paid), act } } }));
const { HotelBookingPage } = await import('./HotelBookingPage');

describe('Hotel booking page', () => {
  it('a failed payment keeps the room held with a retry, and confirmation only follows a server-verified payment', async () => {
    renderWithProviders(<Routes><Route path="/hotels/bookings/:id" element={<HotelBookingPage />} /></Routes>, { route: '/hotels/bookings/b1' });
    expect(await screen.findByText('Orbit Business Hotel')).toBeInTheDocument();
    expect(screen.queryByText('Hotel booked successfully')).toBeNull();
    const hold = screen.getByRole('alert');
    expect(within(hold).getByText(/held for you/)).toBeInTheDocument();
    await userEvent.click(within(hold).getByRole('button', { name: /Retry payment/ }));
    expect(act).toHaveBeenCalledWith('b1', 'pay', {});
    expect((await screen.findAllByText('Confirmed')).length).toBeGreaterThan(0);
    expect(screen.getByText(/ref ABCD1234/)).toBeInTheDocument();
    await userEvent.click(screen.getByRole('button', { name: 'Cancel booking' }));
    const sheet = screen.getByRole('dialog', { name: 'Cancel booking' });
    expect(within(sheet).getByText('Free cancellation until 08 Jan 2099, 2:00 PM.')).toBeInTheDocument();
  });
});
