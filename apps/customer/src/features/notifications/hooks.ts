import { useQuery } from '@tanstack/react-query';
import { useAuth } from '../../auth/AuthProvider';
import { api } from '../../lib/api';

export const notificationKeys = {
  all: ['customer', 'notifications'] as const,
  summary: ['customer', 'notifications', 'summary'] as const,
};

/** Unread badge count. Polls gently; realtime push replaces this later. */
export function useUnreadCount() {
  const { status } = useAuth();
  return useQuery({
    queryKey: notificationKeys.summary,
    queryFn: api.customer.notifications.summary,
    enabled: status === 'authenticated',
    refetchInterval: 60_000,
    select: (d) => d.unread,
  });
}
