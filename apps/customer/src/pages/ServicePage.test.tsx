import { screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { renderWithProviders } from '../test/utils';

vi.mock('../auth/AuthProvider', () => ({ useAuth: () => ({ status: 'anonymous', user: null }) }));
const list = vi.fn();
vi.mock('../data/stores-source', () => ({
  usingMockData: false,
  storesSource: {
    list: (q: unknown) => list(q),
    categories: vi.fn().mockResolvedValue([
      { id: 'c1', name: 'Biryani', slug: 'biryani', storeType: 'restaurant' },
      { id: 'c2', name: 'Pizza', slug: 'pizza', storeType: 'restaurant' },
    ]),
  },
}));
vi.mock('../lib/api', () => ({ api: {
  catalog: { offers: vi.fn().mockResolvedValue({ results: [] }), search: vi.fn().mockResolvedValue({ query: 'paneer', stores: [], products: [], events: [] }) },
  customer: { recommendedStores: vi.fn() },
} }));
const { ServicePage } = await import('./ServicePage');

const page = (results: unknown[] = []) => ({ results, count: results.length, page: 1, pageSize: 20, hasNext: false });

describe('Food page', () => {
  beforeEach(() => { list.mockReset(); list.mockResolvedValue(page()); });

  it('has the Food intro, then API cuisines, then the Food search (in that order)', async () => {
    renderWithProviders(<ServicePage storeType="restaurant" />, { route: '/food' });
    const title = screen.getByRole('heading', { level: 1, name: 'Food' });
    expect(screen.getByText('Good food. Great moments. One Click. away.')).toBeInTheDocument();
    const cuisines = screen.getByRole('navigation', { name: 'Cuisines' });
    expect(await within(cuisines).findByRole('button', { name: 'Biryani' })).toBeInTheDocument();
    expect(within(cuisines).getByRole('button', { name: 'All' })).toHaveAttribute('aria-pressed', 'true');
    const search = screen.getByRole('textbox', { name: 'Search restaurants, dishes & cuisines' });
    // Document order: title → cuisines → search.
    expect(title.compareDocumentPosition(cuisines) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    expect(cuisines.compareDocumentPosition(search) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    expect(screen.getByText('Add a delivery location to discover food near you.')).toBeInTheDocument();
  });

  it('selecting a cuisine and filters queries the API with real parameters', async () => {
    renderWithProviders(<ServicePage storeType="restaurant" />, { route: '/food' });
    await userEvent.click(await within(screen.getByRole('navigation', { name: 'Cuisines' })).findByRole('button', { name: 'Biryani' }));
    await userEvent.click(screen.getByRole('button', { name: /Pure veg/ }));
    await userEvent.click(screen.getByRole('button', { name: /Rating 4\.0\+/ }));
    await userEvent.selectOptions(screen.getByLabelText('Sort by'), 'eta');
    await waitFor(() => expect(list).toHaveBeenLastCalledWith(expect.objectContaining({
      type: 'restaurant', category: 'biryani', veg: true, minRating: 4, sort: 'eta', page: 1,
    })));
    expect(screen.getByRole('heading', { name: 'Biryani' })).toBeInTheDocument();
    expect(screen.queryByRole('option', { name: 'Distance' })).toBeNull(); // no coordinates, no distance sort
  });

  it('search is debounced, shows a helpful empty state, and clearing returns to discovery', async () => {
    renderWithProviders(<ServicePage storeType="restaurant" />, { route: '/food' });
    await userEvent.type(screen.getByRole('textbox', { name: 'Search restaurants, dishes & cuisines' }), 'zzqq');
    expect(await screen.findByRole('heading', { name: 'Results for “zzqq”' })).toBeInTheDocument();
    expect(await screen.findByText('We couldn’t find that.')).toBeInTheDocument();
    expect(list).toHaveBeenLastCalledWith(expect.objectContaining({ search: 'zzqq' }));
    await userEvent.click(screen.getByRole('button', { name: /Clear search/ }));
    expect(await screen.findByRole('heading', { name: 'All restaurants' })).toBeInTheDocument();
  });
});
