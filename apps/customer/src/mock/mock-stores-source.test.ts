import { describe, expect, it } from 'vitest';
import { mockStoresSource } from './mock-stores-source';
import { MOCK_STORES } from './temporary-data';

describe('TEMPORARY mock stores source', () => {
  it('provides exactly 10 clearly-identifiable mock restaurants', async () => {
    const page = await mockStoresSource.list({ type: 'restaurant' });
    expect(page.count).toBe(10);
    expect(MOCK_STORES.every((s) => s.id.startsWith('mock-'))).toBe(true);
  });

  it('filters by search (name, category and dish), category and open state', async () => {
    expect((await mockStoresSource.list({ search: 'dosa' })).results.map((s) => s.slug)).toContain('dosa-district');
    expect((await mockStoresSource.list({ search: 'butter chicken' })).count).toBeGreaterThan(0);
    expect((await mockStoresSource.list({ category: 'pizza' })).results.map((s) => s.slug)).toEqual(['crust-coal-pizzeria']);
    expect((await mockStoresSource.list({ open: true })).count).toBe(9);
    expect((await mockStoresSource.list({ search: 'zzzz' })).count).toBe(0);
  });

  it('returns menus and 404s unknown stores like the real API', async () => {
    const menu = await mockStoresSource.menu('tandoor-republic');
    expect(menu.categories[0]!.products.some((p) => !p.isAvailable)).toBe(true);
    await expect(mockStoresSource.get('nope')).rejects.toMatchObject({ status: 404 });
  });
});
