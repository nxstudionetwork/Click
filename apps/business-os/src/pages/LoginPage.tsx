import { useEffect, useState, type ReactNode } from 'react';
import { useLocation, useNavigate } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { Button, Icon, TextField, type IconName } from '@click/ui';
import type { OSAccessType, OSAuthenticated } from '@click/api';
import { api, apiMessage, errorCode } from '../lib/api';
import { useOSSession } from '../session/OSSession';
import { Alert } from '../components/ui';

type Step = 'type' | 'identifier' | 'password' | 'mfa';

const TYPES: { value: OSAccessType; label: string; hint: string; icon: IconName }[] = [
  { value: 'employee', label: 'Employee', hint: 'Click staff: work email or employee ID', icon: 'briefcase' },
  { value: 'administrator', label: 'Administrator', hint: 'Business OS administration (two-step verification)', icon: 'shield' },
  { value: 'partner', label: 'Partner / Business', hint: 'Merchants, service providers and business partners', icon: 'store' },
  { value: 'other', label: 'Other authorized account', hint: 'Auditors, consultants and other approved access', icon: 'key' },
];

export function AuthLayout({ children }: { children: ReactNode }) {
  useEffect(() => { document.title = 'Sign in · Click Business OS'; }, []);
  return (
    <div className="auth">
      <section className="auth__brand" aria-hidden="true">
        <div className="row" style={{ gap: 12 }}>
          <svg width="34" height="34" viewBox="0 0 32 32"><rect width="32" height="32" rx="9" fill="#5B3DF5" /><circle cx="16" cy="16" r="7.5" fill="none" stroke="#fff" strokeWidth="3" /><circle cx="16" cy="16" r="2.6" fill="#14C8A0" /></svg>
          <div style={{ color: '#fff', fontWeight: 800, letterSpacing: '0.2em' }}>CLICK <span style={{ fontWeight: 600, color: 'var(--c-shell-ink-2)', letterSpacing: '0.3em', fontSize: '0.75rem' }}>BUSINESS OS</span></div>
        </div>
        <div>
          <h1>The operating system for running Click.</h1>
          <p>People, finance, partners, operations, approvals and audit in one secure workspace. What you see is decided by your role, your scope and your organization.</p>
          <div className="auth__grid">
            <div className="auth__tile"><strong>Scoped access</strong>Module · action · location</div>
            <div className="auth__tile"><strong>Approvals</strong>Levels, limits, delegation</div>
            <div className="auth__tile"><strong>Full audit</strong>Every change recorded</div>
          </div>
        </div>
        <div className="auth__foot"><span>Authorized use only</span><span>Activity is monitored and audited</span></div>
      </section>
      <section className="auth__panel"><div className="auth__form">{children}</div></section>
    </div>
  );
}

export function LoginPage() {
  const { completeSignIn } = useOSSession();
  const navigate = useNavigate();
  const location = useLocation();
  const from = (location.state as { from?: string } | null)?.from;
  const [step, setStep] = useState<Step>('type');
  const [accessType, setAccessType] = useState<OSAccessType>('employee');
  const [identifier, setIdentifier] = useState('');
  const [password, setPassword] = useState('');
  const [code, setCode] = useState('');
  const [flowToken, setFlowToken] = useState('');
  const [mfaToken, setMfaToken] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [useRecovery, setUseRecovery] = useState(false);

  const finish = async (r: OSAuthenticated) => {
    await completeSignIn(r);
    navigate(from && from !== '/login' ? from : '/home', { replace: true });
  };

  const run = async (fn: () => Promise<void>) => {
    setBusy(true);
    setError(null);
    try { await fn(); } catch (e) {
      const c = errorCode(e);
      if (c === 'flow_expired') { setStep('identifier'); setPassword(''); setCode(''); }
      setError(apiMessage(e));
    } finally { setBusy(false); }
  };

  const submitIdentifier = () => run(async () => {
    const r = await api.auth.identify(identifier.trim(), accessType);
    setFlowToken(r.flowToken);
    setStep('password');
  });

  const submitPassword = () => run(async () => {
    const r = await api.auth.password(flowToken, password);
    setPassword('');
    if (r.status === 'mfa_required') { setMfaToken(r.mfaToken); setStep('mfa'); return; }
    await finish(r);
  });

  const submitMfa = () => run(async () => finish(await api.auth.mfa(mfaToken, code.trim())));

  const stepIndex = { type: 0, identifier: 1, password: 2, mfa: 3 }[step];
  const typeLabel = TYPES.find((t) => t.value === accessType)!.label;

  return (
    <AuthLayout>
      <div className="auth__steps" aria-hidden="true">{[0, 1, 2, 3].map((i) => <span key={i} className={i <= stepIndex ? 'on' : ''} />)}</div>
      {error && <Alert tone="error">{error}</Alert>}

      {step === 'type' && (
        <>
          <div><h2>How are you accessing Click Business OS?</h2><p className="muted small">Choose the account you were given.</p></div>
          <div className="choice-list">
            {TYPES.map((t) => (
              <button key={t.value} className="choice" onClick={() => { setAccessType(t.value); setStep('identifier'); setError(null); }}>
                <span className="choice__icon"><Icon name={t.icon} size={18} /></span>
                <span className="grow"><strong>{t.label}</strong><small>{t.hint}</small></span>
                <Icon name="right" size={16} />
              </button>
            ))}
          </div>
          <DevPersonas onSignedIn={finish} onError={setError} />
        </>
      )}

      {step === 'identifier' && (
        <form className="stack" onSubmit={(e) => { e.preventDefault(); void submitIdentifier(); }}>
          <div><h2>Sign in</h2><p className="muted small">Signing in as <strong>{typeLabel}</strong>.</p></div>
          <TextField label={accessType === 'partner' ? 'Business email' : 'Work email or employee ID'} value={identifier} autoFocus
                     onChange={(e) => setIdentifier(e.target.value)} autoComplete="username" required />
          <Button type="submit" block loading={busy} disabled={!identifier.trim()}>Continue</Button>
          <Button variant="ghost" block onClick={() => { setStep('type'); setError(null); }}>Choose a different account type</Button>
        </form>
      )}

      {step === 'password' && (
        <form className="stack" onSubmit={(e) => { e.preventDefault(); void submitPassword(); }}>
          <div><h2>Enter your password</h2></div>
          <div className="identity-chip"><span className="ellipsis">{identifier}</span><button type="button" className="btn btn--ghost btn--sm" onClick={() => setStep('identifier')}>Change</button></div>
          <input type="text" name="username" value={identifier} autoComplete="username" readOnly hidden />
          <TextField label="Password" type="password" value={password} autoFocus onChange={(e) => setPassword(e.target.value)} autoComplete="current-password" required />
          <Button type="submit" block loading={busy} disabled={!password}>Sign in</Button>
          <p className="xs muted">Forgot your password? Ask your Business OS administrator to send a new invitation. Several wrong attempts lock the account for a short while.</p>
        </form>
      )}

      {step === 'mfa' && (
        <form className="stack" onSubmit={(e) => { e.preventDefault(); void submitMfa(); }}>
          <div><h2>Two-step verification</h2>
            <p className="muted small">{useRecovery ? 'Enter one of your saved recovery codes.' : 'Enter the 6-digit code from your authenticator app.'}</p></div>
          <TextField label={useRecovery ? 'Recovery code' : 'Verification code'} value={code} autoFocus onChange={(e) => setCode(e.target.value)}
                     inputMode={useRecovery ? 'text' : 'numeric'} autoComplete="one-time-code" className={useRecovery ? '' : 'code-input-wrap'} maxLength={useRecovery ? 20 : 6} required />
          <Button type="submit" block loading={busy} disabled={!code.trim()}>Verify</Button>
          <Button variant="ghost" block onClick={() => { setUseRecovery(!useRecovery); setCode(''); }}>
            {useRecovery ? 'Use authenticator code instead' : 'Use a recovery code'}
          </Button>
        </form>
      )}
    </AuthLayout>
  );
}

/** DEVELOPMENT ONLY. The endpoint is 404 outside DEBUG, so this renders nothing in production. */
function DevPersonas({ onSignedIn, onError }: { onSignedIn: (r: OSAuthenticated) => Promise<void>; onError: (m: string) => void }) {
  const q = useQuery({ queryKey: ['os', 'dev-personas'], queryFn: api.auth.devPersonas, retry: false, staleTime: Infinity, enabled: import.meta.env.DEV });
  const [busy, setBusy] = useState<string | null>(null);
  if (!q.data?.results.length) return null;
  return (
    <div className="dev-box">
      <div className="dev-box__title">Development personas · not in production</div>
      <div className="persona-grid">
        {q.data.results.map((p) => (
          <button key={p.userId} className="persona" disabled={busy !== null} onClick={async () => {
            setBusy(p.userId);
            try { await onSignedIn(await api.auth.devLogin(p.userId)); } catch (e) { onError(apiMessage(e)); setBusy(null); }
          }}>
            <strong>{busy === p.userId ? 'Signing in…' : p.fullName}</strong>{p.persona}
          </button>
        ))}
      </div>
    </div>
  );
}
