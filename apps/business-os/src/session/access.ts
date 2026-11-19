import { useMemo } from 'react';
import { useOS } from './OSSession';

/**
 * Client-side permission checks are UX only (hide what you can't use). Every request is re-checked by the API,
 * including record-level scope, so nothing here is a security boundary.
 */
export function useAccess() {
  const ctx = useOS();
  return useMemo(() => {
    const perms = new Map(ctx.permissions.map((p) => [p.code, p.scope]));
    const can = (code: string) => perms.has(code);
    return {
      can,
      canAny: (...codes: string[]) => codes.some(can),
      scopeOf: (code: string) => perms.get(code) ?? 'none',
      mfaBlocked: (code: string) => ctx.mfaBlocked.includes(code),
      navKeys: new Set(ctx.navigation.flatMap((g) => g.items.map((i) => i.key))),
    };
  }, [ctx]);
}
