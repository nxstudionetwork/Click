/**
 * DEVELOPMENT ONLY. Rendered behind `import.meta.env.DEV`, so Vite removes it from production
 * builds; the backend endpoint also 404s unless DEBUG is on. Separate from normal authentication.
 */
import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { useAuth } from '../auth/AuthProvider';
import { Button } from '../components/ui';
import { api } from '../lib/api';

export function DevLoginPanel({ next }: { next: string }) {
  const { devLogin } = useAuth();
  const navigate = useNavigate();
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const info = useQuery({ queryKey: ['dev-login'], queryFn: api.auth.devLoginInfo, retry: false });
  if (!info.data?.enabled) return null;
  const c = info.data.customer;
  return (
    <section className="dev-panel" aria-label="Development login">
      <span className="dev-panel__tag">Development mode</span>
      {c ? (
        <>
          <div className="small"><strong>{c.name}</strong> · {c.customerCode}<br /><span className="muted">{c.email}</span></div>
          <Button variant="outline" block loading={busy} onClick={async () => {
            setBusy(true); setError('');
            try { await devLogin(); navigate(next, { replace: true }); } catch (e) { setError(e instanceof Error ? e.message : 'Dev login failed'); } finally { setBusy(false); }
          }}>Login as Test Customer</Button>
        </>
      ) : <p className="small">{info.data.hint}</p>}
      {error && <p className="field__error">{error}</p>}
    </section>
  );
}
