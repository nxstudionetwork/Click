import { screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { ApiError, type StoresSource } from '@click/api';
import { renderWithProviders } from '../test/utils';

const source = vi.hoisted(() => ({ current: null as unknown as StoresSource }));
vi.mock('../data/stores-source', async () => {
  const { mockStoresSource } = await import('../mock/mock-stores-source');
  source.current = { ...mockStoresSource };
  return { usingMockData: true, get storesSource() { return source.current; } };
});

const { FoodPage } = await import('./FoodPage');
const { mockStoresSource } = await import('../mock/mock-stores-source');

describe('FoodPage', () => {
  beforeEach(() => { source.current = { ...mockStoresSource }; });

  it('shows skeletons while loading, then all restaurants', async () => {
    const { container } = renderWithProviders(<FoodPage />, { route: '/food' });
    expect(container.querySelectorAll('.skeleton').length).toBeGreaterThan(0);
    expect(await screen.findByText('10 restaurants')).toBeInTheDocument();
    expect(screen.getAllByRole('link')).toHaveLength(10);
  });

  it('filters by category chip and search from the URL', async () => {
    renderWithProviders(<FoodPage />, { route: '/food?search=dosa' });
    expect(await screen.findByRole('heading', { name: 'Dosa District' })).toBeInTheDocument();
    await userEvent.click(await screen.findByRole('button', { name: 'Desserts' }));
    expect(await screen.findByText('No matches')).toBeInTheDocument();
  });

  it('shows an empty state with a clear-filters action', async () => {
    renderWithProviders(<FoodPage />, { route: '/food?search=zzzz' });
    expect(await screen.findByText('No matches')).toBeInTheDocument();
    await userEvent.click(screen.getByRole('button', { name: 'Clear filters' }));
    expect(await screen.findByText('10 restaurants')).toBeInTheDocument();
  });

  it('shows an error state and recovers on retry', async () => {
    const list = vi.fn()
      .mockRejectedValueOnce(new ApiError(503, { code: 'unavailable', message: 'Service down' }))
      .mockImplementation(mockStoresSource.list);
    source.current = { ...mockStoresSource, list };
    renderWithProviders(<FoodPage />, { route: '/food' });
    expect(await screen.findByText('Service down')).toBeInTheDocument();
    await userEvent.click(screen.getByRole('button', { name: 'Try again' }));
    await waitFor(() => expect(screen.getByText('10 restaurants')).toBeInTheDocument());
  });
});
