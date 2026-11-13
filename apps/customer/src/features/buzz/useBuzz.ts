import { useQuery } from '@tanstack/react-query';
import { api } from '../../lib/api';

export const useBuzz = (limit = 12) =>
  useQuery({ queryKey: ['buzz', limit], queryFn: () => api.catalog.buzz(limit), staleTime: 60_000 });
