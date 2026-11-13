import { useQuery } from '@tanstack/react-query';
import { useAuth } from '../../auth/AuthProvider';
import { api } from '../../lib/api';

export const walletKey = ['customer', 'wallet'] as const;
/** `enabled` lets summary screens fetch the balance only when the customer asks to see it. */
export function useWallet(enabled = true) {
  const { status } = useAuth();
  return useQuery({ queryKey: walletKey, queryFn: api.customer.wallet, enabled: enabled && status === 'authenticated' });
}
