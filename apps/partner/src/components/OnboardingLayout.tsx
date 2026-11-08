import type { ReactNode } from 'react';
import { Link } from 'react-router-dom';
import { Icon, Logo } from '@click/ui';
import type { OnboardingStep } from '@click/api';
import { ONBOARDING_STEPS } from '../session/steps';
import { usePartnerSession } from '../session/PartnerSession';

export function OnboardingLayout({ step, title, subtitle, back, aside, children, footer }: {
  step: OnboardingStep; title: string; subtitle?: string; back?: string; aside?: ReactNode; children: ReactNode; footer?: ReactNode;
}) {
  const { logout } = usePartnerSession();
  const index = ONBOARDING_STEPS.findIndex((s) => s.step === step);
  return (
    <div className="onb">
      <header className="onb__bar">
        {back ? (
          <Link to={back} className="icon-btn" aria-label="Back"><Icon name="back" /></Link>
        ) : <span className="icon-btn icon-btn--ghost" aria-hidden="true" />}
        <Logo product="Partner" size={26} />
        <button type="button" className="text-btn" onClick={() => void logout()}>Sign out</button>
      </header>
      <div className="onb__body">
        <main id="main" className="onb__main">
          <nav className="steps" aria-label="Onboarding progress">
            <ol>
              {ONBOARDING_STEPS.map((s, i) => (
                <li key={s.step} className={i < index ? 'is-done' : i === index ? 'is-current' : ''} aria-current={i === index ? 'step' : undefined}>
                  <span className="steps__dot" aria-hidden="true">{i < index ? <Icon name="check" size={13} /> : i + 1}</span>
                  <span className="steps__label">{s.label}<span className="visually-hidden">{i < index ? ' (done)' : i === index ? ' (current step)' : ''}</span></span>
                </li>
              ))}
            </ol>
          </nav>
          <div className="onb__head">
            <p className="eyebrow">Step {index + 1} of {ONBOARDING_STEPS.length}</p>
            <h1>{title}</h1>
            {subtitle && <p className="muted">{subtitle}</p>}
          </div>
          {children}
          {footer && <div className="onb__footer">{footer}</div>}
        </main>
        {aside && <aside className="onb__aside" aria-label="Category preview">{aside}</aside>}
      </div>
    </div>
  );
}

export function PageLoader({ label = 'Loading' }: { label?: string }) {
  return (
    <div className="page-loader" role="status" aria-live="polite">
      <span className="spinner" aria-hidden="true" />
      <span className="visually-hidden">{label}</span>
    </div>
  );
}
