import { keepPreviousData, useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import type { MenuItemInput, OfferInput, OperationInput } from '@click/api';
import { api } from '../../lib/api';
import { usePartnerSession } from '../../session/PartnerSession';
import { HOME_KEY, LIVE_POLL_MS, RESTAURANT_KEY } from '../home/queries';

/** Restaurant mode is decided by the server (partner.mode); the app only reads it. */
export function useIsRestaurant() {
  const { partner } = usePartnerSession();
  return partner.state?.partner?.mode === 'restaurant';
}

const live = { refetchInterval: LIVE_POLL_MS, refetchIntervalInBackground: false, refetchOnWindowFocus: true, staleTime: 4_000 };

export function useKitchen() {
  return useQuery({ queryKey: [...RESTAURANT_KEY, 'kitchen'], queryFn: () => api.restaurant.kitchen(), ...live });
}

export function useOperations() {
  return useQuery({ queryKey: [...RESTAURANT_KEY, 'operations'], queryFn: () => api.restaurant.operations(), ...live });
}

export function useRestaurantOrders(q: { status: string; q: string; date: string; page: number }) {
  return useQuery({
    queryKey: [...RESTAURANT_KEY, 'orders', q], queryFn: () => api.restaurant.orders(q), placeholderData: keepPreviousData, ...live,
  });
}

export function useMenu() {
  return useQuery({ queryKey: [...RESTAURANT_KEY, 'menu'], queryFn: () => api.restaurant.menu(), staleTime: 15_000 });
}

export function useOffers() {
  return useQuery({ queryKey: [...RESTAURANT_KEY, 'offers'], queryFn: () => api.restaurant.offers(), staleTime: 15_000 });
}

export function useInsights(days: 1 | 7 | 30) {
  return useQuery({ queryKey: [...RESTAURANT_KEY, 'insights', days], queryFn: () => api.restaurant.insights(days), staleTime: 30_000,
    placeholderData: keepPreviousData });
}

/** Every write goes to the server; the screen changes only after the server confirms it, then everything refreshes. */
function useRestaurantMutation<V, R>(fn: (v: V) => Promise<R>, alsoHome = false) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: fn,
    onSettled: () => {
      void qc.invalidateQueries({ queryKey: RESTAURANT_KEY });
      if (alsoHome) void qc.invalidateQueries({ queryKey: HOME_KEY });
    },
  });
}

export const useOperate = () => useRestaurantMutation((body: OperationInput) => api.restaurant.operate(body), true);
export const useCreateCategory = () => useRestaurantMutation((name: string) => api.restaurant.createCategory(name));
export const useUpdateCategory = () =>
  useRestaurantMutation(({ id, body }: { id: string; body: { name?: string; isActive?: boolean } }) => api.restaurant.updateCategory(id, body));
export const useDeleteCategory = () => useRestaurantMutation((id: string) => api.restaurant.deleteCategory(id));
export const useReorderCategories = () => useRestaurantMutation((ids: string[]) => api.restaurant.reorderCategories(ids));
export const useReorderItems = () =>
  useRestaurantMutation(({ categoryId, ids }: { categoryId: string; ids: string[] }) => api.restaurant.reorderItems(categoryId, ids));
export const useSaveItem = () =>
  useRestaurantMutation(({ id, body }: { id?: string; body: MenuItemInput }) =>
    (id ? api.restaurant.updateItem(id, body) : api.restaurant.createItem(body)), true);
export const useCreateOffer = () => useRestaurantMutation((body: OfferInput) => api.restaurant.createOffer(body));
export const useOfferPause = () =>
  useRestaurantMutation(({ id, paused }: { id: string; paused: boolean }) => api.restaurant.setOfferPaused(id, paused));
