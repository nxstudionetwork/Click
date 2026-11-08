import { useEffect, useRef, useState } from 'react';
import { Navigate, useNavigate } from 'react-router-dom';
import { Button, Icon, Logo } from '@click/ui';
import { OTP_LENGTH, OtpInput } from '../components/OtpInput';
import { friendlyFirebaseError, needsNewCode } from '../firebase/errors';
import { currentIdToken, sendVerificationCode } from '../firebase/phoneAuth';
import { apiMessage, formatPhone } from '../lib/format';
import { phoneFlow } from '../session/phoneFlow';
import { usePartnerSession } from '../session/PartnerSession';
import { STEP_ROUTE } from '../session/steps';

const RESEND_AFTER_SECONDS = 30;

export function VerifyPage() {
  const navigate = useNavigate();
  const { completeSignIn } = usePartnerSession();
  const pendingVerification = phoneFlow.get();
  const [code, setCode] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [status, setStatus] = useState<'idle' | 'verifying' | 'linking' | 'resending'>('idle');
  const [codeExpired, setCodeExpired] = useState(false);
  /** Firebase verified the code but Click couldn't be reached: retry the exchange without a new code. */
  const [backendFailed, setBackendFailed] = useState(false);
  const [now, setNow] = useState(Date.now());
  const inputRef = useRef<HTMLInputElement>(null);
  const recaptchaRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const id = window.setInterval(() => setNow(Date.now()), 1000);
    return () => window.clearInterval(id);
  }, []);
  useEffect(() => { inputRef.current?.focus(); }, []);

  if (!pendingVerification) return <Navigate to="/login" replace />;
  const { phone, confirmation, sentAt } = pendingVerification;
  const wait = Math.max(0, RESEND_AFTER_SECONDS - Math.floor((now - sentAt) / 1000));
  const busy = status !== 'idle';

  async function linkToClick(idToken: string) {
    setStatus('linking');
    try {
      const state = await completeSignIn(idToken);
      navigate(STEP_ROUTE[state.onboardingStep], { replace: true });
    } catch (err) {
      setBackendFailed(true);
      setError(apiMessage(err, 'We couldn’t verify your number right now.'));
      setStatus('idle');
    }
  }

  async function verify(value = code) {
    if (busy) return;
    if (value.length !== OTP_LENGTH) return setError('Enter the 6-digit code.');
    setError(null);
    setStatus('verifying');
    try {
      const credential = await confirmation.confirm(value);
      await linkToClick(await credential.user.getIdToken());
    } catch (err) {
      setCodeExpired(needsNewCode(err));
      setError(friendlyFirebaseError(err));
      setCode('');
      setStatus('idle');
      inputRef.current?.focus();
    }
  }

  async function retryLink() {
    setError(null);
    try {
      const token = await currentIdToken(true);
      if (token) return linkToClick(token);
      setBackendFailed(false);
      setError('Your verification ended. Request a new code.');
      setCodeExpired(true);
    } catch (err) {
      setError(friendlyFirebaseError(err));
    }
  }

  async function resend() {
    setStatus('resending');
    setError(null);
    try {
      const fresh = await sendVerificationCode(phone, recaptchaRef.current!);
      phoneFlow.start(phone, fresh);
      setCode('');
      setCodeExpired(false);
      setNow(Date.now());
      inputRef.current?.focus();
    } catch (err) {
      setError(friendlyFirebaseError(err));
    } finally {
      setStatus('idle');
    }
  }

  function changeNumber() {
    phoneFlow.clear();
    navigate('/login', { replace: true });
  }

  return (
    <div className="verify">
      <header className="verify__bar">
        <button type="button" className="icon-btn" onClick={changeNumber} aria-label="Back to mobile number"><Icon name="back" /></button>
        <Logo product="Partner" size={26} />
        <span className="icon-btn icon-btn--ghost" aria-hidden="true" />
      </header>
      <main id="main" className="verify__main">
        <div className="verify__icon" aria-hidden="true"><Icon name="phone" size={28} /></div>
        <h1>Verify your number</h1>
        <p className="muted">Enter the verification code sent to</p>
        <p className="verify__phone">{formatPhone(phone)}</p>

        <form className="stack" onSubmit={(e) => { e.preventDefault(); void verify(); }} noValidate>
          <OtpInput ref={inputRef} value={code} onChange={(v) => { setCode(v); if (error && !backendFailed) setError(null); }}
            onComplete={(v) => void verify(v)} error={error} disabled={busy || backendFailed} />
          {backendFailed ? (
            <Button type="button" block onClick={() => void retryLink()} loading={status === 'linking'}>Try again</Button>
          ) : (
            <Button type="submit" block loading={status === 'verifying' || status === 'linking'} disabled={code.length !== OTP_LENGTH || codeExpired}>
              {status === 'linking' ? 'Signing you in…' : status === 'verifying' ? 'Verifying…' : 'Verify and continue'}
            </Button>
          )}
        </form>

        <div className="verify__links">
          <button type="button" className="text-btn" onClick={() => void resend()} disabled={wait > 0 || busy}>
            {status === 'resending' ? 'Sending…' : wait > 0 ? `Resend code in ${wait}s` : 'Resend code'}
          </button>
          <button type="button" className="text-btn" onClick={changeNumber} disabled={busy}>Change number</button>
        </div>
        <div ref={recaptchaRef} className="recaptcha-slot" />
      </main>
    </div>
  );
}
