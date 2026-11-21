import type { ReactNode } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { Icon } from '../ui';

/**
 * Back for detail pages (a product, a store, a booking). Goes back in history when the customer came from inside the
 * app, otherwise to `fallback` (e.g. a shared link opened directly). Main service pages don't use it: the bottom nav
 * is their way around.
 */
export function BackBar({ fallback, label = 'Back', children }: { fallback: string; label?: string; children?: ReactNode }) {
  const navigate = useNavigate();
  const inApp = typeof window !== 'undefined' && (window.history.state?.idx ?? 0) > 0;
  return (
    <div className="backbar">
      {inApp ? (
        <button type="button" className="backbar__btn" onClick={() => navigate(-1)} aria-label={label}><Icon name="back" size={20} /></button>
      ) : (
        <Link to={fallback} className="backbar__btn" aria-label={label}><Icon name="back" size={20} /></Link>
      )}
      {children && <div className="backbar__trail">{children}</div>}
    </div>
  );
}
