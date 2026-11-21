import { keepPreviousData, useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { api } from '../../lib/api';
import { HOME_KEY } from '../home/queries';

export const DRIVER_KEY = ['partner', 'driver'] as const;
export const DOCUMENTS_KEY = ['partner', 'documents'] as const;

export function useDriverProfile() {
  return useQuery({ queryKey: [...DRIVER_KEY, 'profile'], queryFn: api.driver.profile, staleTime: 30_000 });
}

export function useDriverEarnings() {
  return useQuery({ queryKey: [...DRIVER_KEY, 'earnings'], queryFn: api.driver.earnings, staleTime: 15_000, refetchOnWindowFocus: true });
}

export function useDriverTrips(q: { status: string; page: number }) {
  return useQuery({ queryKey: [...DRIVER_KEY, 'trips', q], queryFn: () => api.driver.trips(q), placeholderData: keepPreviousData, staleTime: 10_000 });
}

export function useDocuments() {
  return useQuery({ queryKey: DOCUMENTS_KEY, queryFn: api.driver.documents, staleTime: 30_000 });
}

export function useRateRider() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, stars }: { id: string; stars: number }) => api.driver.rateRider(id, stars),
    onSettled: () => { void qc.invalidateQueries({ queryKey: DRIVER_KEY }); },
  });
}

export function useSafety() {
  return useMutation({ mutationFn: ({ id, kind, note }: { id: string; kind: 'sos' | 'report'; note?: string }) => api.driver.safety(id, kind, note) });
}

export function useSubmitDocument() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: api.driver.submitDocument,
    onSuccess: (data) => qc.setQueryData(DOCUMENTS_KEY, data),
    onSettled: () => {
      void qc.invalidateQueries({ queryKey: DRIVER_KEY });
      void qc.invalidateQueries({ queryKey: HOME_KEY });
    },
  });
}
