import { keepPreviousData, useQuery } from '@tanstack/react-query';
import type { StoreQuery, StoreType } from '@click/api';
import { storesSource } from '../../data/stores-source';

export const storeKeys = {
  list: (q: StoreQuery) => ['stores', 'list', q] as const,
  detail: (slug: string) => ['stores', 'detail', slug] as const,
  menu: (slug: string) => ['stores', 'menu', slug] as const,
  categories: (type: StoreType) => ['stores', 'categories', type] as const,
};

export const useStores = (query: StoreQuery) =>
  useQuery({ queryKey: storeKeys.list(query), queryFn: () => storesSource.list(query), placeholderData: keepPreviousData });

export const useStore = (slug: string) => useQuery({ queryKey: storeKeys.detail(slug), queryFn: () => storesSource.get(slug) });

export const useMenu = (slug: string) => useQuery({ queryKey: storeKeys.menu(slug), queryFn: () => storesSource.menu(slug) });

export const useStoreCategories = (type: StoreType) =>
  useQuery({ queryKey: storeKeys.categories(type), queryFn: () => storesSource.categories(type), staleTime: 10 * 60_000 });
