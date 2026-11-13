import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import type { WorkItem } from '@click/api';
import { api } from '../../lib/api';
import { PARTNER_QUERY_KEY } from '../../session/PartnerSession';

export const HOME_KEY = ['partner', 'home'] as const;
export const WORK_KEY = ['partner', 'work'] as const;
export const NOTIFICATIONS_KEY = ['partner', 'notifications'] as const;

/**
 * Click has no push channel yet (see docs/architecture.md), so live work is polled: every 10 s while the tab is
 * visible, paused in the background, and refreshed immediately when the partner returns to the tab.
 */
export const LIVE_POLL_MS = 10_000;

export function useHome() {
  return useQuery({
    queryKey: HOME_KEY,
    queryFn: api.partner.home,
    refetchInterval: LIVE_POLL_MS,
    refetchIntervalInBackground: false,
    refetchOnWindowFocus: true,
    staleTime: 5_000,
  });
}

export function useWork(view: string) {
  return useQuery({
    queryKey: [...WORK_KEY, view],
    queryFn: () => api.partner.work(view || undefined),
    refetchInterval: LIVE_POLL_MS,
    refetchIntervalInBackground: false,
    staleTime: 5_000,
  });
}

/** Performs a work action on the server; the UI only changes after the server confirms it. */
export function useWorkAction() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ item, action, reason }: { item: Pick<WorkItem, 'kind' | 'id'>; action: string; reason?: string }) =>
      api.partner.act(item, action, reason ? { reason } : undefined),
    onSettled: () => {
      void qc.invalidateQueries({ queryKey: HOME_KEY });
      void qc.invalidateQueries({ queryKey: WORK_KEY });
      void qc.invalidateQueries({ queryKey: NOTIFICATIONS_KEY });
    },
  });
}

export function useSetAvailability() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (available: boolean) => api.partner.setAvailability(available),
    onSuccess: ({ partner, onboardingStep }) => {
      qc.setQueryData(PARTNER_QUERY_KEY, { partner, onboardingStep });
    },
    onSettled: () => { void qc.invalidateQueries({ queryKey: HOME_KEY }); },
  });
}
