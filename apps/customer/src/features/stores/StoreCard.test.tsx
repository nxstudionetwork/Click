import { screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { MOCK_STORES } from '../../mock/temporary-data';
import { renderWithProviders } from '../../test/utils';
vi.mock('../../auth/AuthProvider', () => ({ useAuth: () => ({ status: 'anonymous', user: null }) }));
const { StoreCard } = await import('./StoreCard');

const base = MOCK_STORES[0]!;

describe('StoreCard', () => {
  it('shows name, rating, ETA, fee, categories, offer and links to the store', () => {
    renderWithProviders(<StoreCard store={base} />);
    expect(screen.getByRole('heading', { name: base.name })).toBeInTheDocument();
    expect(screen.getByText('4.6')).toBeInTheDocument();
    expect(screen.getByText('25–35 min')).toBeInTheDocument();
    expect(screen.getByText(/delivery$/)).toBeInTheDocument();
    expect(screen.getByText('20% off up to ₹100')).toBeInTheDocument();
    expect(screen.getByRole('link')).toHaveAttribute('href', `/stores/${base.slug}`);
  });

  it('renders a branded fallback when there is no image', () => {
    renderWithProviders(<StoreCard store={{ ...base, imageUrl: '' }} />);
    expect(screen.getByRole('img', { name: base.name })).toHaveTextContent('SS');
  });

  it('marks closed stores and hides their offers', () => {
    renderWithProviders(<StoreCard store={{ ...base, isOpen: false }} />);
    expect(screen.getByText('Currently closed')).toBeInTheDocument();
    expect(screen.queryByText('20% off up to ₹100')).not.toBeInTheDocument();
  });

  it('shows "New" for unrated stores and free delivery', () => {
    renderWithProviders(<StoreCard store={{ ...base, ratingAverage: '0.0', deliveryFee: '0.00' }} />);
    expect(screen.getByText('New')).toBeInTheDocument();
    expect(screen.getByText('Free delivery')).toBeInTheDocument();
  });
});
