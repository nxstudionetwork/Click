import { useState, type FormEvent } from 'react';
import { Link, Navigate, useLocation, useNavigate, useSearchParams } from 'react-router-dom';
import { useAuth } from '../auth/AuthProvider';
import { onboarding } from '../auth/onboarding';
import { COUNTRIES, phoneAuth, PhoneAuthError, toE164 } from '@click/phone-auth';
import { Button } from '../components/ui';
import { DevLoginPanel } from '../dev/DevLoginPanel';
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
  const [iso, setIso] = useState(prefill.iso ?? 'IN');
  const [number, setNumber] = useState(prefill.phone ?? '');
  const [error, setError] = useState('');
  const [sending, setSending] = useState(false);
  const country = COUNTRIES.find((c) => c.iso === iso)!;

  if (status === 'authenticated') return <Navigate to={next} replace />;

  async function submit(e: FormEvent) {
    e.preventDefault();
    const digits = number.replace(/\D/g, '');
    if (!country.pattern.test(digits)) { setError(`Enter a valid ${country.name} mobile number, e.g. ${country.example}.`); return; }
    setError(''); setSending(true);
    try {
      const pending = await phoneAuth.start(toE164(country, digits));
      onboarding.setPending(pending);
      navigate(`/login/verify${next !== '/' ? `?next=${encodeURIComponent(next)}` : ''}`, { state: { iso, phone: digits } });
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
            <label className="visually-hidden" htmlFor="country">Country code</label>
            <select id="country" value={iso} onChange={(e) => { setIso(e.target.value); setError(''); }} disabled={sending}>
              {COUNTRIES.map((c) => <option key={c.iso} value={c.iso}>{c.flag} {c.dial}</option>)}
            </select>
            <input id="phone" type="tel" inputMode="numeric" autoComplete="tel-national" placeholder={country.example}
              value={number} onChange={(e) => { setNumber(e.target.value.replace(/[^\d\s]/g, '').slice(0, 15)); setError(''); }}
              aria-invalid={!!error} aria-describedby={error ? 'phone-error' : 'phone-help'} disabled={sending} />
          </div>
          {error ? <span id="phone-error" className="field__error" role="alert">{error}</span>
            : <span id="phone-help" className="small muted">We’ll text you a 6-digit code to verify it’s you.</span>}
        </div>
        <Button type="submit" block loading={sending} className="btn--lg">{sending ? 'Sending code…' : 'Continue'}</Button>
        <p className="small muted" style={{ textAlign: 'center' }}>New or returning, it’s the same: verify your number and you’re in. By continuing you agree to Click’s Terms and Privacy Policy.</p>
      </form>
      {import.meta.env.DEV && (
        <>
          <DevLoginPanel next={next} />
          <p className="small muted dev-note">Development: the 6-digit code is printed in the API terminal instead of being texted.</p>
        </>
      )}
      <Link to="/?guest=1" className="auth-skip">Explore Click first</Link>
    </AuthLayout>
  );
}
