/**
 * TEMPORARY MOCK DATA SOURCE — REPLACE WITH REAL API DATA.
 * Implements the same `StoresSource` interface as the real API client.
 *
 * Dev-only scenario switch via URL: ?mockScenario=slow | empty | error
 * to exercise loading, empty and failure states.
 */
import { ApiError, type Paginated, type Store, type StoresSource } from '@click/api';
import { MOCK_CATEGORIES, MOCK_MENUS, MOCK_STORES } from './temporary-data';

const scenario = () =>
  typeof window === 'undefined' ? null : new URLSearchParams(window.location.search).get('mockScenario');

async function simulate<T>(value: () => T): Promise<T> {
  const s = scenario();
  await new Promise((r) => setTimeout(r, s === 'slow' ? 2500 : 250));
  if (s === 'error') throw new ApiError(503, { code: 'mock_error', message: 'Mock failure (mockScenario=error).' });
  return value();
}

const notFound = () => new ApiError(404, { code: 'not_found', message: 'Not found.' });

export const mockStoresSource: StoresSource = {
  list: (query) =>
    simulate((): Paginated<Store> => {
      let results = scenario() === 'empty' ? [] : MOCK_STORES.filter((s) => !query.type || s.storeType === query.type);
      if (query.category) results = results.filter((s) => s.categories.some((c) => c.slug === query.category));
      if (query.open) results = results.filter((s) => s.isOpen);
      const q = query.search?.trim().toLowerCase();
      if (q) {
        results = results.filter(
          (s) =>
            s.name.toLowerCase().includes(q) ||
            s.categories.some((c) => c.name.toLowerCase().includes(q)) ||
            (MOCK_MENUS[s.slug] ?? []).some((m) => m.products.some((p) => p.name.toLowerCase().includes(q))),
        );
      }
      return { results, count: results.length, page: 1, pageSize: 20, hasNext: false };
    }),
  get: (slug) =>
    simulate(() => {
      const store = MOCK_STORES.find((s) => s.slug === slug);
      if (!store) throw notFound();
      return store;
    }),
  menu: (slug) =>
    simulate(() => {
      const store = MOCK_STORES.find((s) => s.slug === slug);
      if (!store) throw notFound();
      return { storeId: store.id, categories: MOCK_MENUS[slug] ?? [] };
    }),
  categories: (type) => simulate(() => MOCK_CATEGORIES.filter((c) => c.storeType === type)),
};
