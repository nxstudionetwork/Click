import type { ReactNode } from 'react';
import { Link } from 'react-router-dom';
import { Icon } from '../components/ui';
import { Logo } from '../components/layout/Logo';
import { VisualCarousel } from './Visuals';

/** Full-screen onboarding layout: visual + panel side by side on desktop, stacked on mobile. */
export function AuthLayout({ children, back, step, visual = true }: { children: ReactNode; back?: { to: string; label: string; onClick?: () => void }; step?: { at: number; of: number }; visual?: boolean }) {
  return (
    <div className={`auth-shell ${visual ? '' : 'auth-shell--plain'}`}>
      {import.meta.env.DEV && <div className="mock-banner auth-shell__banner">Development build · DEVELOPMENT MOCK DATA</div>}
      {visual && <div className="auth-shell__visual"><VisualCarousel /></div>}
      <main className="auth-shell__panel" id="main">
        <div className="auth-panel">
          <div className="auth-panel__top">
            {back ? (
              <Link to={back.to} onClick={back.onClick} className="auth-back"><Icon name="back" size={18} /> {back.label}</Link>
            ) : <Logo />}
            {step && <span className="auth-step" aria-label={`Step ${step.at} of ${step.of}`}>{Array.from({ length: step.of }, (_, i) => <i key={i} className={i < step.at ? 'on' : ''} />)}</span>}
          </div>
          <div className="auth-panel__body">{children}</div>
        </div>
      </main>
    </div>
  );
}
