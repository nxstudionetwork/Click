import { useEffect } from 'react';
import { Link } from 'react-router-dom';
import { Icon } from '@click/ui';
import { useOSSession } from '../session/OSSession';

export function SessionEndedPage() {
  const { status, logout } = useOSSession();
  useEffect(() => { document.title = 'Session ended · Click Business OS'; }, []);
  useEffect(() => { if (status === 'expired') void logout(); }, [status, logout]);
  return (
    <main className="center-page">
      <div className="center-card">
        <div className="state__icon" style={{ width: 48, height: 48, borderRadius: '50%', display: 'grid', placeItems: 'center', background: 'var(--c-warning-soft)', color: 'var(--c-warning)' }}>
          <Icon name="clock" />
        </div>
        <h2>Your session has ended</h2>
        <p className="muted small">
          For security, Business OS signs you out after a period of inactivity, when you sign out on another device, or when an
          administrator changes your access. Nothing was lost.
        </p>
        <Link className="btn btn--primary btn--block" to="/login" style={{ textDecoration: 'none' }}>Sign in again</Link>
      </div>
    </main>
  );
}
