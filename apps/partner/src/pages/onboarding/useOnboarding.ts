import { useQuery } from '@tanstack/react-query';
import { api } from '../../lib/api';
import { usePartnerSession } from '../../session/PartnerSession';

export function useCatalog() {
  return useQuery({ queryKey: ['partner', 'catalog'], queryFn: () => api.partner.catalog(), staleTime: Infinity });
}

/** The signed-in partner's draft. Route guards guarantee it exists past the category step. */
export function useDraftPartner() {
  const { partner, setPartnerState } = usePartnerSession();
  return { partner: partner.state?.partner ?? null, setPartnerState };
}
