import { useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { maskPhone } from '@click/phone-auth';
import { useAuth } from '../auth/AuthProvider';
import { Button, Icon, Sheet, type IconName } from '../components/ui';
import type { Theme } from '../config/services';
import { ProfileBadges } from '../features/profile/ProfileBadges';
import { ProfileIdentity } from '../features/profile/ProfileIdentity';
import { api } from '../lib/api';

interface Row { to: string; title: string; hint: string; icon: IconName; theme: Theme; badge?: number }

/**
 * Profile: the customer's identity and personal account. A dedicated page with its own header (no app header,
 * search, location or bottom navigation). Identity comes from /me (the backend resolves the signed-in customer);
 * counts come from /customer/profile/summary, and detail pages load their own data when opened.
 */
export function ProfilePage() {
  const { user } = useAuth();
  const navigate = useNavigate();
  const summary = useQuery({ queryKey: ['customer', 'profile', 'summary'], queryFn: api.customer.profileSummary });
  const [securityOpen, setSecurityOpen] = useState(false);
  const [logoutOpen, setLogoutOpen] = useState(false);
  const back = () => (window.history.state?.idx > 0 ? navigate(-1) : navigate('/'));

  const account: Row[] = [
    { to: '/account/card', title: 'My Click. ID Card', hint: 'Your digital Click. identity', icon: 'card', theme: 'default' },
    { to: '/account/addresses', title: 'Addresses', hint: summary.data ? `${summary.data.addresses} saved` : 'Home, work and other places', icon: 'pin', theme: 'grocery' },
    { to: '/account/payments', title: 'Payments', hint: 'Payment methods and history', icon: 'card', theme: 'wallet' },
    { to: '/notifications', title: 'Notifications', hint: 'Updates about orders and rewards', icon: 'bell', theme: 'parcel', badge: summary.data?.unreadNotifications },
    { to: '/settings', title: 'Settings', hint: 'Profile, appearance and privacy', icon: 'settings', theme: 'profile' },
    { to: '/help', title: 'Help & Support', hint: 'FAQs and support requests', icon: 'help', theme: 'services' },
  ];

  // Completeness counts only things the customer can actually do in the app and that genuinely help.
  const checks = [!!user?.avatarUrl, !!user?.phoneVerified, (summary.data?.addresses ?? 0) > 0];
  const complete = Math.round((checks.filter(Boolean).length / checks.length) * 100);
  const needsAddress = summary.data?.addresses === 0;

  return (
    <div className="profile" data-theme="profile">
      <header className="profile__head">
        <button type="button" className="icon-btn" aria-label="Back" onClick={back}><Icon name="back" /></button>
        <h1>Profile</h1>
        <span className="profile__head-spacer" aria-hidden="true" />
      </header>

      <main className="profile__main" id="main">
        <ProfileIdentity />

        {summary.isSuccess && complete < 100 && (
          <div className="pcomplete">
            <span className="pcomplete__text"><strong>Profile {complete}% complete</strong>
              <span>{!user?.avatarUrl ? 'Tap your photo above to add one, so partners recognise you.' : 'Add an address for faster checkout.'}</span></span>
            <span className="pcomplete__bar" role="progressbar" aria-valuenow={complete} aria-valuemin={0} aria-valuemax={100} aria-label="Profile completeness"><span style={{ width: `${complete}%` }} /></span>
            {needsAddress && <Link to="/account/addresses" className="btn btn--secondary btn--sm">Add address</Link>}
          </div>
        )}

        {summary.isError ? (
          <div className="hstate" role="alert">
            <span className="hstate__icon hstate__icon--error"><Icon name="alert" size={18} /></span>
            <div><strong>We couldn’t load your profile.</strong><span>Your details are safe. Please try again.</span></div>
            <button className="btn btn--outline btn--sm" onClick={() => summary.refetch()}>Try again</button>
          </div>
        ) : (
          <section aria-labelledby="yours-h" className="profile__sec">
            <h2 id="yours-h" className="profile__h">Your Click.</h2>
            <ProfileBadges summary={summary} />
          </section>
        )}

        <section aria-labelledby="account-h" className="profile__sec">
          <h2 id="account-h" className="profile__h">Account</h2>
          <nav className="prows" aria-labelledby="account-h">
            {account.map((r) => (
              <Link key={r.to} to={r.to} className="prow" data-theme={r.theme}>
                <span className="prow__icon"><Icon name={r.icon} size={19} /></span>
                <span className="prow__text"><strong>{r.title}</strong><span>{r.hint}</span></span>
                {!!r.badge && <span className="prow__badge" aria-label={`${r.badge} unread`}>{r.badge > 99 ? '99+' : r.badge}</span>}
                <Icon name="right" size={18} className="prow__chev" />
              </Link>
            ))}
          </nav>
        </section>

        <section aria-labelledby="security-h" className="profile__sec">
          <h2 id="security-h" className="profile__h">Security</h2>
          <div className="prows">
            <button type="button" className="prow" data-theme="profile" onClick={() => setSecurityOpen(true)}>
              <span className="prow__icon"><Icon name="shield" size={19} /></span>
              <span className="prow__text"><strong>Security</strong><span>How you sign in and this device’s session</span></span>
              <Icon name="right" size={18} className="prow__chev" />
            </button>
            <button type="button" className="prow prow--logout" onClick={() => setLogoutOpen(true)}>
              <span className="prow__icon"><Icon name="logout" size={19} /></span>
              <span className="prow__text"><strong>Log out</strong><span>Sign out of Click. on this device</span></span>
            </button>
          </div>
        </section>

        <footer className="profile__brand">
          <span className="brand__word">Click<span className="brand__dot">.</span></span>
          <span>A venture of IFX Group</span>
        </footer>
      </main>

      <SecuritySheet open={securityOpen} onClose={() => setSecurityOpen(false)} onLogout={() => { setSecurityOpen(false); setLogoutOpen(true); }} />
      <LogoutDialog open={logoutOpen} onClose={() => setLogoutOpen(false)} />
    </div>
  );
}

function SecuritySheet({ open, onClose, onLogout }: { open: boolean; onClose: () => void; onLogout: () => void }) {
  const { user } = useAuth();
  return (
    <Sheet open={open} onClose={onClose} label="Security">
      <div className="psheet">
        <h2>Security</h2>
        <dl className="psec">
          <div><dt>Sign-in method</dt><dd>One-time code sent to your phone</dd></div>
          {user?.phone && <div><dt>Verified phone</dt><dd>{maskPhone(user.phone.replace(/[^\d+]/g, ''))}{user.phoneVerified ? ' · verified' : ''}</dd></div>}
          <div><dt>This device</dt><dd>Signed in until you log out. Your session renews securely in the background.</dd></div>
        </dl>
        <p className="small muted">Changing your phone number needs a fresh verification and isn’t available in the app yet. Contact Help & Support if you’ve lost access to your number.</p>
        <div className="row" style={{ flexWrap: 'wrap' }}>
          <Link to="/help/new?category=account" className="btn btn--outline" onClick={onClose}>Contact support</Link>
          <Button variant="ghost" onClick={onLogout}>Log out</Button>
        </div>
      </div>
    </Sheet>
  );
}

function LogoutDialog({ open, onClose }: { open: boolean; onClose: () => void }) {
  const { logout } = useAuth();
  const navigate = useNavigate();
  const [busy, setBusy] = useState(false);
  async function confirm() {
    setBusy(true);
    await logout();
    // Replace history so Back can't return to protected pages; they redirect to sign in anyway.
    navigate('/login', { replace: true });
  }
  return (
    <Sheet open={open} onClose={onClose} label="Log out of Click.?">
      <div className="psheet" role="alertdialog" aria-labelledby="logout-h" aria-describedby="logout-d">
        <h2 id="logout-h">Log out of Click.?</h2>
        <p id="logout-d" className="muted">You’ll need to sign in again to access your account.</p>
        <div className="row"><Button variant="outline" onClick={onClose} disabled={busy}>Cancel</Button><Button variant="danger" onClick={confirm} loading={busy}>Log out</Button></div>
      </div>
    </Sheet>
  );
}
