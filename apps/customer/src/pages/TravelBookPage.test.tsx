import { screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';
import { Route, Routes } from 'react-router-dom';
import { ApiError } from '@click/api';
import { renderWithProviders } from '../test/utils';

const review = (total: string) => ({
  journey: { journeyId: 'j1', mode: 'flight', operator: 'Skyline Air', number: 'SK 512', name: 'HYD → DEL', vehicle: 'Airbus A320neo', classCode: 'economy', className: 'Economy',
    fareType: 'Saver', from: 'Rajiv Gandhi International Airport', fromCity: 'Hyderabad', to: 'Indira Gandhi International Airport', toCity: 'Delhi',
    departsAt: '2099-01-10T00:50:00Z', arrivesAt: '2099-01-10T03:05:00Z', durationMinutes: 135, baggage: { cabin: '7 kg', checkIn: '15 kg' }, status: 'scheduled', notice: '' },
  passengers: [{ name: 'Asha Rao', age: 30, gender: 'female', status: 'CNF', seat: '', berth: 'Seat at check-in', queue: 0 }],
  infants: 0, unitFare: total, baseFare: total, fees: '0.00', discount: '0.00', offer: null, tax: '0.00', total, lines: [{ label: 'Fare × 1', amount: total }],
  couponError: '', refundable: true, policy: 'Cancellation: 3+ days before departure: 15% fee.', changeFee: '2250.00', points: 450, holdMinutes: 10,
  bookable: true, problem: '', statusNote: '',
});
const book = vi.fn()
  .mockRejectedValueOnce(new ApiError(409, { code: 'price_changed', message: 'The fare changed.', details: { review: review('5299.00'), previous: '4999.00' } }))
  .mockResolvedValue({ id: 'b1', paymentError: '' });
vi.mock('../auth/AuthProvider', () => ({ useAuth: () => ({ status: 'authenticated', user: { fullName: 'Asha Rao', phone: '+91 98765 43210', email: '' } }) }));
vi.mock('../features/wallet/useWallet', () => ({ walletKey: ['customer', 'wallet'], useWallet: () => ({ data: { balance: '20000.00' } }) }));
vi.mock('../lib/api', () => ({ api: { travel: { travellers: vi.fn().mockResolvedValue({ results: [] }), review: vi.fn().mockResolvedValue(review('4999.00')), book } } }));
const { TravelBookPage } = await import('./TravelBookPage');

describe('Travel booking', () => {
  it('a changed fare is shown as “Fare updated” and is only charged after the customer confirms it', async () => {
    renderWithProviders(<Routes><Route path="/travel/book" element={<TravelBookPage />} /><Route path="/travel/bookings/:id" element={<p>Booking page</p>} /></Routes>,
      { route: '/travel/book?mode=flight&origin=hyderabad&destination=delhi&date=2099-01-10&adults=1&journey=j1&from=a&to=b&class=economy' });
    expect(await screen.findByText('Passenger details')).toBeInTheDocument();
    expect(screen.queryByLabelText(/passport|aadhaar|id number/i)).toBeNull(); // no ID numbers are collected
    await userEvent.click(screen.getByRole('button', { name: 'Review journey' }));
    expect(await screen.findByRole('heading', { name: 'Review journey' })).toBeInTheDocument();
    await userEvent.click(screen.getByRole('button', { name: 'Pay & book' }));
    const sheet = await screen.findByRole('dialog', { name: 'Fare updated' });
    expect(within(sheet).getByText('₹4,999')).toBeInTheDocument();
    expect(within(sheet).getByText('₹5,299')).toBeInTheDocument();
    expect(book).toHaveBeenCalledTimes(1);
    await userEvent.click(within(sheet).getByRole('button', { name: /Continue at/ }));
    expect(await screen.findByText('Booking page')).toBeInTheDocument();
    expect(book.mock.calls[1]![0].expectedTotal).toBe('5299.00');
    expect(book.mock.calls[1]![0].idempotencyKey).not.toBe(book.mock.calls[0]![0].idempotencyKey);
  });
});
