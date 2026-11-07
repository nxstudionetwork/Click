import { useQuery } from '@tanstack/react-query';
import { api } from '../../lib/api';

export const addressesKey = ['customer', 'addresses'] as const;
export const useAddresses = (enabled = true) =>
  useQuery({ queryKey: addressesKey, queryFn: api.customer.addresses.list, enabled });
