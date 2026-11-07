import { useQuery } from '@tanstack/react-query';
import { useAuth } from '../../auth/AuthProvider';
import { api } from '../../lib/api';

export const walletKey = ['customer', 'wallet'] as const;
export function useWallet() {
  const { status } = useAuth();
  return useQuery({ queryKey: walletKey, queryFn: api.customer.wallet, enabled: status === 'authenticated' });
}
