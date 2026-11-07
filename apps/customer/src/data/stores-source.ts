import type { StoresSource } from '@click/api';
import { api } from '../lib/api';
import { mockStoresSource } from '../mock/mock-stores-source';

/**
 * The single switch between real API data and TEMPORARY MOCK DATA for discovery.
 * Components never import mock data directly; they use `storesSource`.
 * Set VITE_STORES_SOURCE=mock to develop the UI without the backend.
 */
export const usingMockData = import.meta.env.VITE_STORES_SOURCE === 'mock';

export const storesSource: StoresSource = usingMockData ? mockStoresSource : api.stores;
