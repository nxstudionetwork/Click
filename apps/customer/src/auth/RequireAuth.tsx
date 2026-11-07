import type { ReactNode } from 'react';
import { Navigate, useLocation } from 'react-router-dom';
import { Skeleton } from '../components/ui';
import { useAuth } from './AuthProvider';

/** UX guard only. Authorization is enforced by the API on every request. */
export function RequireAuth({ children }: { children: ReactNode }) {
  const { status } = useAuth();
  const location = useLocation();
  if (status === 'loading') return <div className="stack"><Skeleton height={28} width="40%" /><Skeleton height={120} /></div>;
  if (status === 'anonymous') return <Navigate to={`/login?next=${encodeURIComponent(location.pathname + location.search)}`} replace />;
  return <>{children}</>;
}
