import { useState, type FormEvent } from 'react';
import { Link, Navigate, useLocation, useNavigate, useSearchParams } from 'react-router-dom';
import { useAuth } from '../auth/AuthProvider';
import { onboarding } from '../auth/onboarding';
import { formatIndianMobile, INDIA, nationalDigits, phoneAuth, PhoneAuthError, toE164 } from '@click/phone-auth';
import { Button } from '../components/ui';
import { AuthLayout } from './AuthLayout';

export function safeNext(next: string | null) {
  // Only same-app relative paths (prevents open redirects).
  return next && next.startsWith('/') && !next.startsWith('//') ? next : '/';
}

export function LoginPage() {
  const { status } = useAuth();
  const navigate = useNavigate();
  const [params] = useSearchParams();
  const prefill = (useLocation().state as { phone?: string; iso?: string } | null) ?? {};
  const next = safeNext(params.get('next'));
  const [number, setNumber] = useState(nationalDigits(prefill.phone ?? ''));
  const [error, setError] = useState('');
  const [sending, setSending] = useState(false);

  if (status === 'authenticated') return <Navigate to={next} replace />;

  async function submit(e: FormEvent) {
    e.preventDefault();
    const digits = nationalDigits(number);
    if (digits.length < 10) { setError('Enter your 10-digit mobile number.'); return; }
    if (!INDIA.pattern.test(digits)) { setError('Indian mobile numbers start with 6, 7, 8 or 9.'); return; }
    setError(''); setSending(true);
    try {
      const pending = await phoneAuth.start(toE164(INDIA, digits));
      onboarding.setPending(pending);
      navigate(`/login/verify${next !== '/' ? `?next=${encodeURIComponent(next)}` : ''}`, { state: { iso: 'IN', phone: digits } });
    } catch (err) {
      setError(err instanceof PhoneAuthError ? err.message : 'Something went wrong. Please try again.');
    } finally {
      setSending(false);
    }
  }

  return (
    <AuthLayout>
      <div className="auth-intro">
        <h1>Welcome to Click</h1>
        <p>Everything you need. One Click away.</p>
      </div>
      <form className="stack" onSubmit={submit} noValidate>
        <div className="field">
          <label className="field__label" htmlFor="phone">Mobile number</label>
          <div className={`phone-input ${error ? 'phone-input--error' : ''}`}>
            <span className="phone-input__dial" aria-label="India, plus 91"><span className="flag-in" aria-hidden="true" /> +91</span>
            <input id="phone" type="tel" inputMode="numeric" autoComplete="tel-national" placeholder={INDIA.example} maxLength={11}
              value={formatIndianMobile(number)} onChange={(e) => { setNumber(nationalDigits(e.target.value)); setError(''); }}
              aria-invalid={!!error} aria-describedby={error ? 'phone-error' : 'phone-help'} disabled={sending} autoFocus />
          </div>
          {error ? <span id="phone-error" className="field__error" role="alert">{error}</span>
            : <span id="phone-help" className="small muted">We’ll text you a 6-digit code to verify it’s you.</span>}
        </div>
        <Button type="submit" block loading={sending} className="btn--lg">{sending ? 'Sending code…' : 'Continue'}</Button>
        <p className="small muted" style={{ textAlign: 'center' }}>New or returning, it’s the same: verify your number and you’re in. By continuing you agree to Click’s Terms and Privacy Policy.</p>
      </form>
      <Link to="/?guest=1" className="auth-skip">Explore Click first</Link>
    </AuthLayout>
  );
}
