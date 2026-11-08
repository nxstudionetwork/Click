import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import type { Ride } from '@click/api';

vi.mock('../features/ride/RideMap', () => ({ RideMap: () => <div data-testid="map" /> }));
const api = vi.hoisted(() => ({ customer: { rides: { get: vi.fn(), cancel: vi.fn(), rate: vi.fn(), safety: vi.fn() } } }));
vi.mock('../lib/api', () => ({ api }));
const { RideTripPage } = await import('./RideTripPage');

const place = (label: string) => ({ label, address: `${label}, Bengaluru`, lat: 12.97, lng: 77.64 });
const ride = (over: Partial<Ride>): Ride => ({
  id: 'r1', number: 'CLK-R-TEST001', status: 'searching', statusLabel: 'Finding your ride',
  rideType: { code: 'auto', name: 'Auto', description: '', icon: 'auto', seats: 3 },
  pickup: place('Home'), drop: place('Koramangala'), stops: [], distanceKm: '5.82', durationMinutes: 18,
  fare: { base: '30', distance: '70', time: '27', fees: '3', subtotal: '130', discount: '26', total: '104' },
  offerTitle: '20% off your ride', currency: 'INR', paymentMethod: 'wallet', payment: { method: 'wallet', status: 'captured' },
  passengerName: '', scheduledFor: null, driver: null, driverAssignedAt: null, startedAt: null, completedAt: null, cancelledAt: null,
  events: [], rating: null, canCancel: true, createdAt: '2026-11-08T16:40:00Z', ...over,
} as Ride);
const driver = { name: 'Suresh', rating: null, ratingCount: 0, vehicleType: 'auto', vehicleModel: 'Bajaj RE', vehicleColor: 'Green & yellow', plate: 'KA 03 C 7788' };

function renderTrip() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={['/rides/r1']}><Routes><Route path="/rides/:id" element={<RideTripPage />} /></Routes></MemoryRouter>
    </QueryClientProvider>,
  );
}

describe('Ride trip', () => {
  beforeEach(() => { vi.clearAllMocks(); });

  it('while searching it says so honestly, with no driver invented', async () => {
    api.customer.rides.get.mockResolvedValue(ride({}));
    renderTrip();
    expect(await screen.findByRole('heading', { name: 'Finding your ride' })).toBeInTheDocument();
    expect(screen.queryByText('KA 03 C 7788')).toBeNull();
    expect(screen.getByText('CLK-R-TEST001')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Cancel ride' })).toBeInTheDocument();
  });

  it('shows the assigned driver and plate, and labels an old location as not live', async () => {
    api.customer.rides.get.mockResolvedValue(ride({ status: 'driver_assigned', statusLabel: 'Driver on the way',
      driver: { ...driver, location: { lat: 12.97, lng: 77.64, reportedAt: '2026-11-08T16:41:00Z', live: false } } }));
    renderTrip();
    expect(await screen.findByText('KA 03 C 7788')).toBeInTheDocument();
    expect(screen.getByText('Suresh')).toBeInTheDocument();
    expect(screen.getByText(/Driver location from/)).toBeInTheDocument();
    expect(screen.queryByText(/Live/)).toBeNull();
  });

  it('a completed ride keeps the driver for reference and can be rated once', async () => {
    api.customer.rides.get.mockResolvedValue(ride({ status: 'completed', statusLabel: 'Completed', canCancel: false,
      completedAt: '2026-11-08T17:00:00Z', startedAt: '2026-11-08T16:45:00Z', driver: { ...driver, location: null } }));
    api.customer.rides.rate.mockResolvedValue(ride({ status: 'completed', rating: { stars: 4, comment: '' }, driver: { ...driver, location: null } }));
    renderTrip();
    expect(await screen.findByText('Suresh')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Cancel ride' })).toBeNull();
    await userEvent.click(screen.getByRole('radio', { name: '4 stars' }));
    await userEvent.click(screen.getByRole('button', { name: 'Safe driving' }));
    await userEvent.click(screen.getByRole('button', { name: 'Submit rating' }));
    expect(api.customer.rides.rate).toHaveBeenCalledWith('r1', expect.objectContaining({ stars: 4 }));
  });
});
