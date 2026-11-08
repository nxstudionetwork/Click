import { useRef, useState, type FormEvent } from 'react';
import { useNavigate } from 'react-router-dom';
import { Button, Icon, Logo } from '@click/ui';
import { StoryReel } from '../components/StoryReel';
import { isPhoneAuthConfigured, phoneAuth, PhoneAuthError, toE164 } from '@click/phone-auth';
import { COUNTRIES, PhoneField, validateNational } from '../components/PhoneField';
import { ECOSYSTEM_STORY } from '../config/visuals';
import { phoneFlow } from '../session/phoneFlow';
import { usePartnerSession } from '../session/PartnerSession';

export function LoginPage() {
  const navigate = useNavigate();
  const { bootError, retryBoot } = usePartnerSession();
  const country = COUNTRIES[0]!;
  const [digits, setDigits] = useState(() => phoneFlow.get()?.phone.replace(country.dial, '') ?? '');
  const [error, setError] = useState<string | null>(null);
  const [pending, setPending] = useState(false);
  const recaptchaRef = useRef<HTMLDivElement>(null);
  const configured = isPhoneAuthConfigured();

  async function submit(e: FormEvent) {
    e.preventDefault();
    const invalid = validateNational(country, digits);
    if (invalid) return setError(invalid);
    setError(null);
    setPending(true);
    try {
      const phone = toE164(country, digits);
      const verification = await phoneAuth.start(phone, recaptchaRef.current!);
      phoneFlow.start(phone, verification);
      navigate('/verify');
    } catch (err) {
      setError(err instanceof PhoneAuthError ? err.message : 'We couldn’t send a code right now. Please try again.');
    } finally {
      setPending(false);
    }
  }

  return (
    <div className="auth">
      <section className="auth__visual" aria-label="What partners do on Click">
        <StoryReel scenes={ECOSYSTEM_STORY} label="Partners on Click" sizes="(min-width: 960px) 55vw, 100vw" eagerFirst />
        <div className="auth__visual-top"><Logo tone="dark" product="Partner" size={30} /></div>
      </section>
      <main id="main" className="auth__panel">
        <form className="auth__form" onSubmit={submit} noValidate aria-describedby="login-intro">
          <div className="stack-sm">
            <p className="eyebrow">Partner Login / Sign up</p>
            <h1>Welcome to Click Partner</h1>
            <p id="login-intro" className="muted">Grow your business with Click. Enter your mobile number and we’ll text you a verification code.</p>
          </div>
          {bootError && (
            <div className="notice notice--warning" role="alert">
              <Icon name="alert" size={18} />
              <span>{bootError}</span>
              <button type="button" className="text-btn" onClick={retryBoot}>Retry</button>
            </div>
          )}
          {!configured && (
            <div className="notice notice--warning" role="alert">
              <Icon name="alert" size={18} />
              <span>Phone sign-in isn’t set up for this environment yet. Add the Firebase settings to enable it.</span>
            </div>
          )}
          <PhoneField country={country} value={digits} onChange={(v) => { setDigits(v); if (error) setError(null); }} error={error} disabled={pending} />
          <Button type="submit" block loading={pending} disabled={!configured}>
            {pending ? 'Sending code…' : 'Continue'}
          </Button>
          <p className="legal small muted">
            By continuing, you agree to Click’s Partner Terms and acknowledge the Privacy Policy. Standard SMS rates may apply.
          </p>
          <ul className="auth__trust small" aria-label="Why partners trust Click">
            <li><Icon name="shield" size={16} /> Your number is verified securely by SMS</li>
            <li><Icon name="store" size={16} /> One Partner account for your business</li>
          </ul>
          <div ref={recaptchaRef} className="recaptcha-slot" />
        </form>
      </main>
    </div>
  );
}
