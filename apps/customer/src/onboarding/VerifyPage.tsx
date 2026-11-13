import { useEffect, useState } from 'react';
import { Navigate, useLocation, useNavigate, useSearchParams } from 'react-router-dom';
import { ApiError } from '@click/api';
import { useAuth } from '../auth/AuthProvider';
import { onboarding } from '../auth/onboarding';
import { maskPhone, phoneAuth, PhoneAuthError } from '@click/phone-auth';
import { Button, Icon } from '../components/ui';
import { api } from '../lib/api';
import { AuthLayout } from './AuthLayout';
import { OtpInput } from './OtpInput';
import { safeNext } from './LoginPage';

const RESEND_AFTER = 30;
type Phase = 'enter' | 'verifying' | 'linking' | 'success';

export function VerifyPage() {
  const navigate = useNavigate();
  const { startSession } = useAuth();
  const location = useLocation();
  const [params] = useSearchParams();
  const next = safeNext(params.get('next'));
  const [pending, setPending] = useState(onboarding.getPending());
  const [code, setCode] = useState('');
  const [phase, setPhase] = useState<Phase>('enter');
  const [error, setError] = useState('');
  const [wait, setWait] = useState(RESEND_AFTER);
  const [resending, setResending] = useState(false);

  useEffect(() => {
    if (wait <= 0) return;
    const t = setTimeout(() => setWait((w) => w - 1), 1000);
    return () => clearTimeout(t);
  }, [wait]);

  if (!pending) return <Navigate to="/login" replace />;
  const phone = pending.phoneNumber;

  async function verify(value: string) {
    if (value.length !== 6 || phase !== 'enter') return;
    setError(''); setPhase('verifying');
    let credential;
    try {
      credential = await pending!.confirm(value);
    } catch (err) {
      setPhase('enter'); setCode('');
      setError(err instanceof PhoneAuthError ? err.message : 'That code isn’t correct. Please try again.');
      return;
    }
    setPhase('linking'); // the backend verifies the code here
    try {
      const result = await api.auth.exchangeIdentity(credential);
      setPhase('success');
      await new Promise((r) => setTimeout(r, 650)); // let the success state register
      if (result.status === 'authenticated') {
        onboarding.clear();
        startSession(result);
        navigate(next, { replace: true });
      } else {
        onboarding.setPending(null);
        onboarding.saveSignup(result.signupToken, result.phoneNumber);
        navigate('/signup', { replace: true });
      }
    } catch (err) {
      setPhase('enter'); setCode('');
      // The code is checked by the Click backend during this step, so its answer (wrong / expired code) is shown as is.
      setError(err instanceof ApiError && ['invalid_code', 'code_expired', 'too_many_attempts'].includes(err.code) ? err.message
        : err instanceof ApiError && err.code === 'network_error' ? 'We couldn’t reach Click. Check your connection and try again.'
          : 'We couldn’t sign you in. Please request a new code and try again.');
    }
  }

  async function resend() {
    setResending(true); setError('');
    try {
      const p = await phoneAuth.start(phone);
      onboarding.setPending(p); setPending(p); setCode(''); setWait(RESEND_AFTER);
    } catch (err) {
      setError(err instanceof PhoneAuthError ? err.message : 'Couldn’t resend the code. Please try again.');
    } finally {
      setResending(false);
    }
  }

  const busy = phase !== 'enter';
  return (
    <AuthLayout back={{ to: '/login', label: 'Change number', onClick: () => { void phoneAuth.reset(); onboarding.setPending(null); } }}>
      <div className="auth-intro">
        <h1>Verify your phone</h1>
        <p>Enter the 6-digit code sent to <strong>{maskPhone(phone)}</strong></p>
      </div>
      {phase === 'success' ? (
        <div className="verify-success" role="status"><span className="verify-success__check"><Icon name="check" size={34} /></span><strong>Phone verified</strong></div>
      ) : (
        <div className="stack">
          <OtpInput value={code} onChange={(v) => { setCode(v); setError(''); }} onComplete={verify} disabled={busy} invalid={!!error} />
          {error && <p className="field__error" role="alert" style={{ textAlign: 'center' }}>{error}</p>}
          <Button block className="btn--lg" loading={busy} disabled={code.length !== 6} onClick={() => verify(code)}>
            {phase === 'verifying' ? 'Verifying…' : phase === 'linking' ? 'Signing you in…' : 'Verify'}
          </Button>
          <div className="spread small">
            <button type="button" className="link-btn" onClick={() => navigate('/login', { state: location.state })} disabled={busy}>Wrong number?</button>
            {wait > 0 ? <span className="muted" aria-live="polite">Resend code in 0:{String(wait).padStart(2, '0')}</span>
              : <button type="button" className="link-btn" onClick={resend} disabled={resending || busy}>{resending ? 'Sending…' : 'Resend code'}</button>}
          </div>
        </div>
      )}
    </AuthLayout>
  );
}
