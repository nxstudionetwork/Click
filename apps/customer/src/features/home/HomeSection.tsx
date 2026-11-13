import type { ReactNode } from 'react';
import { Link } from 'react-router-dom';
import { Icon, type IconName } from '../../components/ui';
import type { Theme } from '../../config/services';

/** A Home section: heading with optional subtitle and "see all", in the section's service colour. */
export function HomeSection({ id, title, subtitle, to, linkLabel = 'See all', icon, theme, children, className = '' }: {
  id: string; title: ReactNode; subtitle?: ReactNode; to?: string; linkLabel?: string; icon?: IconName; theme?: Theme; children: ReactNode; className?: string;
}) {
  return (
    <section className={`hsec ${className}`} aria-labelledby={`${id}-h`} data-theme={theme}>
      <div className="hsec__head">
        <div className="hsec__titles">
          <h2 id={`${id}-h`}>{icon && <span className="hsec__icon"><Icon name={icon} size={16} /></span>}{title}</h2>
          {subtitle && <p>{subtitle}</p>}
        </div>
        {to && <Link to={to} className="hsec__link">{linkLabel}<Icon name="right" size={14} /></Link>}
      </div>
      {children}
    </section>
  );
}

/** Horizontally scrolling, snap-aligned row (swipe on phones, wraps into the width on desktop via CSS). */
export function Rail({ children, label, variant = 'cards' }: { children: ReactNode; label: string; variant?: 'cards' | 'wide' | 'tall' | 'chips' }) {
  return <div className={`rail rail--${variant}`} role="list" aria-label={label}>{children}</div>;
}

export function RailItem({ children }: { children: ReactNode }) {
  return <div className="rail__item" role="listitem">{children}</div>;
}

/** Friendly, actionable section states (no raw errors, no blank areas). */
export function SectionError({ onRetry }: { onRetry: () => void }) {
  return (
    <div className="hstate" role="alert">
      <span className="hstate__icon hstate__icon--error"><Icon name="alert" size={18} /></span>
      <div><strong>Something went wrong.</strong><span>We couldn’t load this right now.</span></div>
      <button className="btn btn--outline btn--sm" onClick={onRetry}>Try again</button>
    </div>
  );
}

export function SectionEmpty({ icon = 'compass', title, text, action }: { icon?: IconName; title: string; text?: string; action?: ReactNode }) {
  return (
    <div className="hstate">
      <span className="hstate__icon"><Icon name={icon} size={18} /></span>
      <div><strong>{title}</strong>{text && <span>{text}</span>}</div>
      {action}
    </div>
  );
}

export function RailSkeleton({ count = 4, variant = 'cards' }: { count?: number; variant?: 'cards' | 'wide' | 'tall' }) {
  return (
    <div className={`rail rail--${variant}`} aria-busy="true" aria-label="Loading">
      {Array.from({ length: count }, (_, i) => (
        <div key={i} className="rail__item"><div className={`skeleton skel-card skel-card--${variant}`} /></div>
      ))}
    </div>
  );
}
