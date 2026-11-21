import { screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';
import { Route, Routes } from 'react-router-dom';
import { renderWithProviders } from '../test/utils';

const place = (label: string) => ({ label, address: `${label} road`, lat: 12.97, lng: 77.64 });
const parcel = {
  id: 'p1', number: 'PCL-TEST0001', mode: 'send', modeLabel: 'Send', status: 'assigned', statusLabel: 'Partner assigned',
  service: { code: 'standard', name: 'Standard' }, vehicle: { code: 'bike', name: 'Bike', icon: 'bike' }, total: '167.56', currency: 'INR',
  createdAt: '2030-01-01T10:00:00Z', scheduledFor: null, deliverBy: '2030-01-02T14:30:00Z', deliveredAt: null, isActive: true,
  pickup: { ...place('Home'), name: 'Asha', phoneMasked: '••••• 3210', instructions: '', store: null, storeReference: '' },
  drop: { ...place('Office'), name: 'Ravi', phoneMasked: '••••• 1111', instructions: '' }, stops: [],
  package: { category: 'Gift', categoryCode: 'gift', size: 'small', sizeLabel: 'Small', weightKg: '1.0', dims: null, declaredValue: null, notes: '' },
  fare: { base: '30.00', distance: '128.00', service: '-16.00', stops: '0.00', tax: '25.56', discount: '0.00', total: '167.56', cancellationFee: '0.00' },
  distanceKm: '16.0', durationMinutes: 49, estimateBasis: 'straight_line', payment: { method: 'wallet', status: 'captured', refunded: false },
  pins: { pickup: '4821', delivery: '9356' },
  partner: { name: 'Naveen', vehicle: 'Bike', vehicleNumber: 'KA 01 EP 2201', position: null },
  timeline: [{ status: 'searching', label: 'Finding a delivery partner', at: '2030-01-01T10:00:00Z' }, { status: 'assigned', label: 'Partner assigned', at: '2030-01-01T10:02:00Z' },
    { status: 'at_pickup', label: 'Partner at pickup', at: null }],
  events: [], proofs: [], cancellation: { allowed: false, fee: null, note: '' }, failureReason: '', cancelReason: '', supportRequired: false, tickets: [],
};
vi.mock('../auth/AuthProvider', () => ({ useAuth: () => ({ status: 'authenticated', user: {} }) }));
vi.mock('../lib/api', () => ({ api: { parcels: { get: vi.fn().mockResolvedValue(parcel), cancel: vi.fn(), share: vi.fn() } } }));
const { ParcelDetailPage } = await import('./ParcelDetailPage');

describe('Parcel tracking page', () => {
  it('shows the real timeline and partner, hides PINs until asked, and offers cancel only when the server allows it', async () => {
    renderWithProviders(<Routes><Route path="/parcels/:id" element={<ParcelDetailPage />} /></Routes>, { route: '/parcels/p1' });
    expect(await screen.findByText('PCL-TEST0001')).toBeInTheDocument();
    expect(screen.getByText('Naveen')).toBeInTheDocument();
    expect(screen.queryByText('Live')).toBeNull(); // no reported position: no live claim and no map
    expect(screen.queryByText('4821')).toBeNull();
    await userEvent.click(screen.getByRole('button', { name: 'Show' }));
    expect(screen.getByText('4821')).toBeInTheDocument();
    expect(screen.getByText('9356')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /Cancel parcel/ })).toBeNull();
    expect(screen.getByText(/Estimated from straight-line distance/)).toBeInTheDocument();
  });
});
