import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Button, TextArea, TextField } from '@click/ui';
import { api, apiMessage, fieldErrors } from '../lib/api';
import { useOS, useOSSession } from '../session/OSSession';
import { Alert, Avatar } from '../components/ui';
import { AuthLayout } from './LoginPage';
import { LANGUAGES, MUTABLE_TYPES, TIMEZONES } from './settings/options';

/**
 * First sign-in. People confirm what HR holds and set their own preferences. Department, designation, location and
 * access are read-only here: corrections go to HR, and nobody can give themselves permissions.
 */
export function OnboardingPage() {
  const ctx = useOS();
  const { setContext, logout } = useOSSession();
  const navigate = useNavigate();
  const [step, setStep] = useState(0);
  const [name, setName] = useState(ctx.user.fullName);
  const [tz, setTz] = useState(ctx.account.timezone || ctx.organization.timezone);
  const [lang, setLang] = useState(ctx.account.language || 'en');
  const [muted, setMuted] = useState<string[]>(ctx.account.preferences.notifications?.muted ?? []);
  const [correct, setCorrect] = useState(true);
  const [note, setNote] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [errs, setErrs] = useState<Record<string, string>>({});

  const emp = ctx.employee;
  const steps = ['Your details', 'Preferences', 'Security'];

  const finish = async (goSecurity: boolean) => {
    setBusy(true); setError(null);
    try {
      const next = await api.me.onboarding({ fullName: name, timezone: tz, language: lang, notifications: { muted }, correctionNote: correct ? '' : note });
      setContext(next);
      navigate(goSecurity ? '/settings/security?setup=mfa' : '/home', { replace: true });
    } catch (e) {
      setErrs(fieldErrors(e)); setError(apiMessage(e)); setStep(0);
    } finally { setBusy(false); }
  };

  return (
    <AuthLayout>
      <div className="auth__steps" aria-hidden="true">{steps.map((s, i) => <span key={s} className={i <= step ? 'on' : ''} />)}</div>
      <div><span className="xs muted">Step {step + 1} of {steps.length}</span><h2>{step === 0 ? `Welcome, ${ctx.user.fullName.split(' ')[0] || 'there'}` : steps[step]}</h2></div>
      {error && <Alert tone="error">{error}</Alert>}

      {step === 0 && (
        <div className="stack">
          <div className="row"><Avatar name={name} src={ctx.user.avatarUrl} size="lg" /><p className="small muted">You can add a profile photo later from your profile.</p></div>
          <TextField label="Your name" value={name} onChange={(e) => setName(e.target.value)} error={errs.fullName} />
          <div className="card"><div className="card__body">
            <dl className="kv">
              <dt>Employee ID</dt><dd>{emp?.employeeId ?? '—'}</dd>
              <dt>Designation</dt><dd>{emp?.designation ?? '—'}</dd>
              <dt>Department</dt><dd>{ctx.orgContext.department?.name ?? '—'}</dd>
              <dt>Location</dt><dd>{ctx.orgContext.location?.name ?? '—'}</dd>
              <dt>Manager</dt><dd>{emp?.manager?.fullName ?? '—'}</dd>
              <dt>Access</dt><dd>{ctx.roles.map((r) => r.name).join(', ') || 'No roles yet'}</dd>
            </dl>
          </div></div>
          <label className="row small"><input type="checkbox" checked={correct} onChange={(e) => setCorrect(e.target.checked)} /> These details are correct</label>
          {!correct && <TextArea label="What should HR correct?" value={note} onChange={(e) => setNote(e.target.value)} maxLength={500} />}
          <p className="xs muted">Your organization details come from HR and your access from your administrator. You can’t change them here.</p>
          <Button block onClick={() => setStep(1)} disabled={name.trim().length < 2 || (!correct && !note.trim())}>Continue</Button>
        </div>
      )}

      {step === 1 && (
        <div className="stack">
          <div className="field"><label className="field__label" htmlFor="tz">Time zone</label>
            <select id="tz" className="field__input" value={tz} onChange={(e) => setTz(e.target.value)}>{TIMEZONES.map((t) => <option key={t}>{t}</option>)}</select></div>
          <div className="field"><label className="field__label" htmlFor="lang">Language</label>
            <select id="lang" className="field__input" value={lang} onChange={(e) => setLang(e.target.value)}>{LANGUAGES.map((l) => <option key={l.value} value={l.value}>{l.label}</option>)}</select>
            <span className="field__hint">The interface is in English today; your choice is saved for when translations arrive.</span></div>
          <fieldset className="stack" style={{ border: 0, padding: 0, margin: 0, gap: 6 }}>
            <legend className="field__label">Notify me about</legend>
            {MUTABLE_TYPES.map((t) => (
              <label key={t.value} className="row small"><input type="checkbox" checked={!muted.includes(t.value)}
                onChange={(e) => setMuted((m) => (e.target.checked ? m.filter((x) => x !== t.value) : [...m, t.value]))} />{t.label}</label>
            ))}
            <span className="field__hint">Security alerts and approval requests always reach you.</span>
          </fieldset>
          <div className="row"><Button variant="outline" onClick={() => setStep(0)}>Back</Button><Button className="grow" onClick={() => setStep(2)}>Continue</Button></div>
        </div>
      )}

      {step === 2 && (
        <div className="stack">
          <p className="small">Protect your account with <strong>two-step verification</strong>: after your password you’ll enter a code from an authenticator app (Google Authenticator, Microsoft Authenticator, 1Password …).</p>
          {ctx.mfaBlocked.length > 0 && <Alert tone="warning">Some of your access (for example administration or sensitive data) only works once two-step verification is on.</Alert>}
          <Button block loading={busy} onClick={() => finish(true)}>Set up two-step verification</Button>
          <Button block variant="outline" disabled={busy} onClick={() => finish(false)}>Skip for now</Button>
          <Button block variant="ghost" onClick={() => setStep(1)}>Back</Button>
        </div>
      )}
      <button className="btn btn--ghost btn--sm" onClick={() => void logout()}>Sign out</button>
    </AuthLayout>
  );
}
