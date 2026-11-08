import type { ReactNode } from 'react';
import { Link } from 'react-router-dom';
import { Icon } from '../ui';

/** Consistent page title with optional back link and a themed band for service pages. */
export function PageHeader({ title, subtitle, back, actions, band = false }: {
  title: ReactNode; subtitle?: ReactNode; back?: { to: string; label: string }; actions?: ReactNode; band?: boolean;
}) {
  return (
    <header className={`phead ${band ? 'phead--band' : ''}`}>
      {back && <Link to={back.to} className="phead__back"><Icon name="back" size={18} /> {back.label}</Link>}
      <div className="phead__row">
        <div className="stack" style={{ gap: 4 }}>
          <h1>{title}</h1>
          {subtitle && <p className="phead__sub">{subtitle}</p>}
        </div>
        {actions}
      </div>
    </header>
  );
}
