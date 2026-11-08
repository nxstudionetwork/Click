import { useQuery } from '@tanstack/react-query';
import { useAuth } from '../../auth/AuthProvider';
import { api } from '../../lib/api';

/** What Buddy can do on this deployment (voice, visual search). Server-decided; never assumed by the client. */
export function useCapabilities() {
  const { status } = useAuth();
  return useQuery({
    queryKey: ['assistant', 'capabilities'],
    queryFn: api.customer.assistant.capabilities,
    enabled: status === 'authenticated',
    staleTime: 10 * 60_000,
  });
}
