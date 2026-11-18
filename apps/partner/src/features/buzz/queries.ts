import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import type { BuzzPostAction, BuzzPostInput, BuzzReportReason } from '@click/api';
import { api } from '../../lib/api';

export const BUZZ_KEY = ['partner', 'buzz'] as const;

export function useBuzzOverview() {
  return useQuery({ queryKey: BUZZ_KEY, queryFn: () => api.buzz.overview(), staleTime: 15_000, refetchOnWindowFocus: true });
}

export function useBuzzCommunity(enabled: boolean) {
  return useQuery({ queryKey: [...BUZZ_KEY, 'community'], queryFn: api.buzz.community, enabled, staleTime: 30_000 });
}

function useInvalidate() {
  const qc = useQueryClient();
  return () => { void qc.invalidateQueries({ queryKey: BUZZ_KEY }); };
}

export function useSavePost() {
  const done = useInvalidate();
  return useMutation({
    mutationFn: ({ id, body }: { id?: string; body: BuzzPostInput }) => (id ? api.buzz.update(id, body) : api.buzz.create(body)),
    onSettled: done,
  });
}

export function usePostAction() {
  const done = useInvalidate();
  return useMutation({
    mutationFn: ({ id, action }: { id: string; action: Exclude<BuzzPostAction, 'edit'> }) =>
      action === 'delete' ? api.buzz.remove(id).then(() => null) : api.buzz.act(id, action),
    onSettled: done,
  });
}

export function useUploadMedia() {
  return useMutation({ mutationFn: (file: File) => api.buzz.upload(file) });
}

export function useCommunityLike() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => api.buzzEngage.like(id),
    onSettled: () => { void qc.invalidateQueries({ queryKey: [...BUZZ_KEY, 'community'] }); },
  });
}

export function useReportPost() {
  return useMutation({ mutationFn: ({ id, reason, note }: { id: string; reason: BuzzReportReason; note?: string }) => api.buzzEngage.report(id, reason, note) });
}
