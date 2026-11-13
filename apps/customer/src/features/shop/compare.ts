import { useSyncExternalStore } from 'react';

/** The compare tray: up to 4 products from one category, kept per device (a convenience, never sent anywhere). */
export interface CompareItem { id: string; name: string; categorySlug: string | null }

const KEY = 'click.shopCompare';
export const COMPARE_MAX = 4;
const listeners = new Set<() => void>();
let cache: CompareItem[] | null = null;

function read(): CompareItem[] {
  if (cache) return cache;
  try {
    const v = JSON.parse(localStorage.getItem(KEY) ?? '[]');
    cache = Array.isArray(v) ? v.filter((x) => x && typeof x.id === 'string').slice(0, COMPARE_MAX) : [];
  } catch {
    cache = [];
  }
  return cache;
}

function write(items: CompareItem[]) {
  cache = items;
  try { localStorage.setItem(KEY, JSON.stringify(items)); } catch { /* storage unavailable */ }
  listeners.forEach((l) => l());
}

export const compareStore = {
  get: read,
  subscribe(l: () => void) { listeners.add(l); return () => { listeners.delete(l); }; },
  has: (id: string) => read().some((x) => x.id === id),
  /** Adds an item. Returns 'added', 'full' or 'other_category' (the tray only holds one category at a time). */
  add(item: CompareItem): 'added' | 'full' | 'other_category' {
    const items = read();
    if (items.some((x) => x.id === item.id)) return 'added';
    if (items.length && items[0]!.categorySlug !== item.categorySlug) return 'other_category';
    if (items.length >= COMPARE_MAX) return 'full';
    write([...items, item]);
    return 'added';
  },
  replaceWith: (item: CompareItem) => write([item]),
  remove: (id: string) => write(read().filter((x) => x.id !== id)),
  clear: () => write([]),
};

export const useCompare = () => useSyncExternalStore(compareStore.subscribe, compareStore.get, compareStore.get);
