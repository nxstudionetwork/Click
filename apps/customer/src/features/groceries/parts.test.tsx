import { screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import type { GroceryListing } from '@click/api';
import { renderWithProviders } from '../../test/utils';

vi.mock('../../auth/AuthProvider', () => ({ useAuth: () => ({ status: 'anonymous', user: null }) }));
vi.mock('../../lib/api', () => ({ api: { customer: { cart: { get: vi.fn() } } } }));
const { ProductCard } = await import('./parts');

const base: GroceryListing = {
  id: 'p1', itemId: 'i1', name: 'Basmati Rice', brand: 'Golden Harvest', size: '5 kg', category: { slug: 'rice-atta', name: 'Rice & Atta' },
  price: '650.00', mrp: '799.00', discountPercent: 19, dealEndsAt: null, perUnit: '₹130/kg', inStock: true, orderable: true, stockLeft: null,
  imageUrl: '', imageCredit: '', dietary: 'vegan', attributes: [], variableWeight: false, freshToday: false, receivedOn: null, rating: null,
  store: { id: 's1', slug: 'near-mart', name: 'Near Mart', etaLabel: '15–25 min', isOpen: true },
};

describe('Grocery product card', () => {
  it('shows the seller MRP, per-unit price, store and an Add button for orderable stock', () => {
    renderWithProviders(<ProductCard l={base} />);
    expect(screen.getByText('MRP ₹799')).toBeInTheDocument();
    expect(screen.getByText(/₹130\/kg/)).toBeInTheDocument();
    expect(screen.getByText(/Near Mart/)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Add Basmati Rice 5 kg' })).toBeEnabled();
    // No licensed photo: a labelled placeholder, never an invented image.
    expect(screen.getByRole('img', { name: 'Basmati Rice (no photo yet)' })).toBeInTheDocument();
  });

  it('never offers Add for out-of-stock items and labels a deal reference as the usual price, not MRP', () => {
    renderWithProviders(<ProductCard l={{ ...base, inStock: false, orderable: false, mrp: '700.00', dealEndsAt: '2030-01-01T00:00:00Z' }} />);
    expect(screen.getByText('Out of stock')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /Add Basmati/ })).toBeNull();
    expect(screen.getByLabelText('Usual price ₹700')).toBeInTheDocument();
  });
});
