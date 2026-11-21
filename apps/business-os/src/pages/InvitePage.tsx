import { useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { Button, TextField } from '@click/ui';
import { api, apiMessage } from '../lib/api';
import { useOSSession } from '../session/OSSession';
import { Alert, PageLoader } from '../components/ui';
import { AuthLayout } from './LoginPage';

export function InvitePage() {
  const { token = '' } = useParams();
  const navigate = useNavigate();
  const { completeSignIn, status } = useOSSession();
  const invite = useQuery({ queryKey: ['os', 'invite', token], queryFn: () => api.auth.invite(token), retry: false });
  const [pw, setPw] = useState('');
  const [pw2, setPw2] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  if (invite.isPending) return <PageLoader label="Checking your invitation" />;
  return (
    <AuthLayout>
      {invite.error ? (
        <>
          <h2>Invitation not valid</h2>
          <Alert tone="error">{apiMessage(invite.error)}</Alert>
          <Button variant="outline" onClick={() => navigate('/login')}>Go to sign in</Button>
        </>
      ) : (
        <form className="stack" onSubmit={async (e) => {
          e.preventDefault();
          if (pw !== pw2) { setError('The two passwords don’t match.'); return; }
          setBusy(true); setError(null);
          try {
            await completeSignIn(await api.auth.acceptInvite(token, pw));
            navigate('/onboarding', { replace: true });
          } catch (err) { setError(apiMessage(err)); } finally { setBusy(false); }
        }}>
          <div>
            <h2>Welcome to {invite.data!.organization}</h2>
            <p className="muted small">Set a password for <strong>{invite.data!.email}</strong> to activate your Click Business OS account.</p>
          </div>
          {status === 'signed_in' && <Alert tone="warning">You’re signed in as someone else in this browser. Accepting will switch accounts.</Alert>}
          {error && <Alert tone="error">{error}</Alert>}
          <TextField label="New password" type="password" autoComplete="new-password" value={pw} onChange={(e) => setPw(e.target.value)} required minLength={8} />
          <TextField label="Confirm password" type="password" autoComplete="new-password" value={pw2} onChange={(e) => setPw2(e.target.value)} required />
          <p className="xs muted">At least 8 characters; not a common password and not similar to your name or email.</p>
          <Button type="submit" block loading={busy} disabled={!pw || !pw2}>Activate account</Button>
        </form>
      )}
    </AuthLayout>
  );
}
