import { useState } from 'react';
import { Link, Navigate } from 'react-router-dom';
import { Icon, Logo } from '@click/ui';
import type { PartnerStatus } from '@click/api';
import { cardData, PartnerCard } from '../components/PartnerCard';
import { StatusBadge } from '../components/StatusBadge';
import { iconFor } from '../config/visuals';
import { greeting } from '../lib/format';
import { usePartnerSession } from '../session/PartnerSession';

const STATUS_COPY: Partial<Record<PartnerStatus, string>> = {
  verification_pending: 'Click is reviewing your profile. You can start receiving work once you’re verified.',
  verified: 'You’re verified. Activation is the next step.',
  active: 'Your Partner account is active.',
  rejected: 'Your verification wasn’t approved. Contact Click Partner support to resolve it.',
  suspended: 'Your Partner account is suspended. Contact Click Partner support.',
  inactive: 'Your Partner account is inactive.',
};

/**
 * Minimal Partner Home for this phase: confirms who is signed in and which
 * category they belong to. Category-specific modules come from the server
 * configuration and show honest empty states; no activity is invented.
 */
export function HomePage() {
  const { partner: partnerState, logout } = usePartnerSession();
  const [menuOpen, setMenuOpen] = useState(false);
  const partner = partnerState.state?.partner;
  if (!partner?.partnerCode) return <Navigate to="/" replace />;
  const home = partner.category.configuration.home;
  const firstName = (partner.profile.contactName || partner.businessName).split(' ')[0];
  const canGoOnline = partner.status === 'active';
  const data = cardData(partner)!;

  return (
    <div className="home">
      <header className="home__bar">
        <Logo product="Partner" size={26} />
        <div className="menu">
          <button type="button" className="avatar-btn" aria-haspopup="menu" aria-expanded={menuOpen}
            onClick={() => setMenuOpen((o) => !o)} aria-label="Account menu">
            {partner.businessName.slice(0, 1).toUpperCase()}
          </button>
          {menuOpen && (
            <div className="menu__list" role="menu">
              <Link role="menuitem" to="/card" className="menu__item"><Icon name="card" size={18} /> Partner card</Link>
              <button role="menuitem" type="button" className="menu__item" onClick={() => void logout()}><Icon name="logout" size={18} /> Sign out</button>
            </div>
          )}
        </div>
      </header>
      <main id="main" className="home__main">
        <section className="home__hero" aria-labelledby="hello">
          <div>
            <p className="muted">{greeting()},</p>
            <h1 id="hello">{firstName}</h1>
            <p className="home__biz">{partner.businessName}</p>
          </div>
          <StatusBadge status={partner.status} label={partner.statusLabel} />
        </section>

        {STATUS_COPY[partner.status] && (
          <div className={`notice ${partner.isVerified ? 'notice--info' : 'notice--warning'}`} role="status">
            <Icon name={partner.isVerified ? 'shield' : 'clock'} size={18} /><span>{STATUS_COPY[partner.status]}</span>
          </div>
        )}

        <div className="home__grid">
          <section className="home__identity" aria-label="Your Partner identity">
            <PartnerCard data={data} compact />
            <dl className="id-list">
              <div><dt>Partner ID</dt><dd className="mono">{partner.partnerCode}</dd></div>
              <div><dt>Partner category</dt><dd><Icon name={iconFor(partner.category.icon)} size={16} /> {partner.category.name}</dd></div>
              <div><dt>Partner type</dt><dd>{partner.partnerType.name}</dd></div>
            </dl>
          </section>

          <section className="home__activity" aria-labelledby="today-h">
            <div className="spread">
              <h2 id="today-h">Today’s activity</h2>
              {home.availabilityLabel && (
                <span className="availability" title={canGoOnline ? undefined : 'Available once your account is active'}>
                  <span className="availability__label">{home.availabilityLabel}</span>
                  <span className="availability__state"><Icon name="clock" size={14} /> {canGoOnline ? (partner.isAvailable ? 'On' : 'Off') : 'After verification'}</span>
                </span>
              )}
            </div>
            <ul className="modules">
              {home.modules.map((m) => (
                <li key={m.key} className="module">
                  <span className="module__label">{m.label}</span>
                  <span className="module__empty">{m.empty}</span>
                </li>
              ))}
            </ul>
          </section>
        </div>
      </main>
    </div>
  );
}
