import { screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';
import { Route, Routes } from 'react-router-dom';
import { renderWithProviders } from '../test/utils';

const base = {
  id: 'b1', number: 'SRV-TEST0001', status: 'quote_pending', statusLabel: 'Quote awaiting approval',
  category: { slug: 'plumbing', name: 'Plumbing', accent: '#38bdf8', icon: 'drop' }, job: { id: 'j1', name: 'Leak inspection' }, mode: 'now',
  scheduledStart: null, addressLabel: 'Home', pricing: 'quote', pricingLabel: 'Quote after inspection', agreedAmount: null, total: null,
  createdAt: '2030-01-01T10:00:00Z', isActive: true, reviewed: false,
  provider: { id: 'p1', name: 'Ramesh Kumar', profession: 'Plumber', photoUrl: '', rating: { average: '4.8', count: 31 }, verified: true },
  address: {}, description: 'Tap leaking at the base', unitPrice: null, priceLabel: 'Quote', hours: null, billedHours: null, inspectionFee: '149.00',
  excludes: [], discount: '0.00', offerTitle: '', tax: '0.00', paymentMethod: '', etaMinutes: null, acceptedAt: '2030-01-01T10:01:00Z',
  timeline: [{ to: 'requested', label: 'Requested', note: '', at: '2030-01-01T10:00:00Z' }, { to: 'confirmed', label: 'Confirmed', note: '', at: '2030-01-01T10:01:00Z' },
    { to: 'arrived', label: 'Arrived', note: '', at: '2030-01-01T10:20:00Z' }, { to: 'quote_pending', label: 'Quote sent', note: '', at: '2030-01-01T10:25:00Z' }],
  quotes: [{ id: 'q1', amount: '650.00', note: 'Replace the cartridge', status: 'pending', createdAt: '2030-01-01T10:25:00Z' }],
  photos: [], payment: null, cancellation: { allowed: false, note: 'The professional has arrived. Contact support to cancel.' },
  canPay: false, awaitingCash: false, canReview: false, review: null, tickets: [], tracking: 'status_only',
};
const act = vi.fn().mockResolvedValue({ ...base, status: 'in_progress', statusLabel: 'Work in progress', agreedAmount: '650.00',
  quotes: [{ ...base.quotes[0], status: 'approved' }], timeline: [...base.timeline, { to: 'in_progress', label: 'Work started', note: '', at: '2030-01-01T10:27:00Z' }] });
vi.mock('../auth/AuthProvider', () => ({ useAuth: () => ({ status: 'authenticated', user: {} }) }));
vi.mock('../lib/api', () => ({ api: { services: { booking: vi.fn().mockResolvedValue(base), act }, customer: { wallet: vi.fn() } } }));
const { ServiceBookingPage } = await import('./ServiceBookingPage');

describe('Service booking page', () => {
  it('shows the real professional and quote, sends approval to the server, and never offers a cancel the server refuses', async () => {
    renderWithProviders(<Routes><Route path="/services/bookings/:id" element={<ServiceBookingPage />} /></Routes>, { route: '/services/bookings/b1' });
    expect(await screen.findByText('Leak inspection')).toBeInTheDocument();
    expect(screen.getByText('Ramesh Kumar')).toBeInTheDocument();
    const quote = screen.getByRole('region', { name: 'Approve the quote?' });
    expect(within(quote).getByText(/650/)).toBeInTheDocument();
    expect(within(quote).getByText(/only the visit fee/)).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Cancel booking' })).toBeNull();
    expect(screen.queryByRole('button', { name: /Pay now/ })).toBeNull(); // nothing to pay before completion
    await userEvent.click(within(quote).getByRole('button', { name: 'Approve' }));
    expect(act).toHaveBeenCalledWith('b1', 'quote', { approve: true });
    expect(await screen.findByText('Work in progress', { selector: '.sv-status' })).toBeInTheDocument();
    expect(screen.queryByRole('region', { name: 'Approve the quote?' })).toBeNull();
  });
});
