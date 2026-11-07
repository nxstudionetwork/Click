import { useEffect, useMemo, useState, type FormEvent } from 'react';
import { Navigate, useNavigate } from 'react-router-dom';
import { ApiError, type AddressInput, type AddressLabel } from '@click/api';
import { useAuth } from '../auth/AuthProvider';
import { onboarding } from '../auth/onboarding';
import { maskPhone } from '../auth/phone/countries';
import { Button, Icon, TextArea, TextField } from '../components/ui';
import { api } from '../lib/api';
import { AuthLayout } from './AuthLayout';

const MAX = 5;
const LABELS: { id: AddressLabel; text: string }[] = [
  { id: 'home', text: 'Home' }, { id: 'work', text: 'Work' }, { id: 'college', text: 'College' }, { id: 'family', text: 'Family' }, { id: 'other', text: 'Other' },
];
const EMAIL = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
type Draft = AddressInput & { key: number };

const emptyDraft = (name: string, phone: string): Draft => ({
  key: Date.now(), label: 'home', recipientName: name, phone, line1: '', line2: '', landmark: '', city: '', state: '',
  postalCode: '', country: 'IN', isDefault: false, deliveryInstructions: '', latitude: null, longitude: null,
});

export function SignupPage() {
  const signup = onboarding.getSignup();
  const navigate = useNavigate();
  const { startSession, refreshUser } = useAuth();
  const [step, setStep] = useState<1 | 2>(1);
  const [name, setName] = useState('');
  const [email, setEmail] = useState('');
  const [avatar, setAvatar] = useState<File | null>(null);
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [addresses, setAddresses] = useState<Draft[]>([]);
  const [editing, setEditing] = useState<Draft | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const preview = useMemo(() => (avatar ? URL.createObjectURL(avatar) : null), [avatar]);
  useEffect(() => () => { if (preview) URL.revokeObjectURL(preview); }, [preview]);

  if (!signup) return <Navigate to="/login" replace />;
  const phone = signup.phoneNumber;

  function nextStep(e: FormEvent) {
    e.preventDefault();
    const err: Record<string, string> = {};
    if (name.trim().length < 2) err.name = 'Enter your full name.';
    if (!EMAIL.test(email.trim())) err.email = 'Enter a valid email address.';
    setErrors(err);
    if (Object.keys(err).length) return;
    setStep(2);
    if (!addresses.length) setEditing(emptyDraft(name.trim(), phone));
  }

  function pickAvatar(file: File | undefined) {
    if (!file) return;
    if (!['image/jpeg', 'image/png', 'image/webp'].includes(file.type)) return setErrors((e) => ({ ...e, avatar: 'Use a JPG, PNG or WebP image.' }));
    if (file.size > 5 * 1024 * 1024) return setErrors((e) => ({ ...e, avatar: 'Images must be 5 MB or smaller.' }));
    setErrors((e) => ({ ...e, avatar: '' }));
    setAvatar(file);
  }

  function saveDraft(d: Draft) {
    setAddresses((list) => (list.some((a) => a.key === d.key) ? list.map((a) => (a.key === d.key ? d : a)) : [...list, d]));
    setEditing(null);
  }

  async function createAccount() {
    if (!addresses.length) return;
    setSubmitting(true); setErrors({});
    try {
      const session = await api.auth.completeSignup({
        signupToken: signup!.token, fullName: name.trim(), email: email.trim(),
        addresses: addresses.map(({ key: _k, ...a }) => a),
      });
      startSession(session);
      onboarding.clear();
      // Photo is optional: if the upload fails the account still works and it can be added from Settings.
      if (avatar) await api.auth.uploadAvatar(avatar).then(refreshUser).catch(() => undefined);
      navigate('/welcome/card', { replace: true });
    } catch (err) {
      if (err instanceof ApiError && (err.code === 'signup_expired' || err.code === 'signup_invalid')) {
        onboarding.clear();
        navigate('/login', { replace: true, state: null });
        return;
      }
      if (err instanceof ApiError && err.code === 'email_taken') { setStep(1); setErrors({ email: err.message }); }
      else setErrors({ _: err instanceof Error ? err.message : 'Could not create your account.' });
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <AuthLayout step={{ at: step, of: 2 }} back={step === 2 ? { to: '#', label: 'Profile', onClick: () => setStep(1) } : undefined}>
      {step === 1 ? (
        <form key="s1" className="stack step-in" onSubmit={nextStep} noValidate>
          <div className="auth-intro">
            <h1>Welcome to Click</h1>
            <p>Let’s create your profile.</p>
          </div>
          <div className="avatar-pick">
            <label className="avatar-pick__circle" aria-label="Add a profile photo (optional)">
              {preview ? <img src={preview} alt="Your profile photo" /> : <Icon name="camera" size={26} />}
              <input type="file" accept="image/jpeg,image/png,image/webp" onChange={(e) => pickAvatar(e.target.files?.[0])} />
            </label>
            <div className="small"><strong>Profile photo</strong><span className="muted" style={{ display: 'block' }}>Optional. You can add it later.</span></div>
          </div>
          {errors.avatar && <span className="field__error">{errors.avatar}</span>}
          <TextField label="Full name" value={name} onChange={(e) => setName(e.target.value)} error={errors.name} autoComplete="name" maxLength={150} autoFocus />
          <TextField label="Email" type="email" value={email} onChange={(e) => setEmail(e.target.value)} error={errors.email} autoComplete="email" inputMode="email" maxLength={254} />
          <div className="field">
            <span className="field__label">Phone</span>
            <div className="verified-field"><span>{maskPhone(phone)}</span><span className="badge badge--accent"><Icon name="check" size={14} /> Verified</span></div>
          </div>
          <Button type="submit" block className="btn--lg">Continue</Button>
        </form>
      ) : (
        <div key="s2" className="stack step-in">
          <div className="auth-intro">
            <h1>Where should we deliver?</h1>
            <p>Add at least one place. You can save up to {MAX}.</p>
          </div>
          {addresses.map((a, idx) => (
            <div key={a.key} className="addr-card">
              <span className="list-row__icon"><Icon name="pin" size={18} /></span>
              <div style={{ flex: 1, minWidth: 0 }}>
                <strong style={{ textTransform: 'capitalize' }}>{a.label}</strong> {idx === 0 && <span className="badge">Default</span>}
                <div className="small muted truncate">{[a.line1, a.line2, a.city, a.postalCode].filter(Boolean).join(', ')}</div>
              </div>
              <button className="icon-btn" aria-label={`Edit ${a.label} address`} onClick={() => setEditing(a)}><Icon name="settings" size={18} /></button>
              <button className="icon-btn" aria-label={`Remove ${a.label} address`} onClick={() => setAddresses((l) => l.filter((x) => x.key !== a.key))}><Icon name="close" size={18} /></button>
              {idx > 0 && <button className="link-btn small" onClick={() => setAddresses((l) => [a, ...l.filter((x) => x.key !== a.key)])}>Make default</button>}
            </div>
          ))}
          {editing ? (
            <AddressDraftForm draft={editing} onSave={saveDraft} onCancel={addresses.length ? () => setEditing(null) : undefined} />
          ) : addresses.length < MAX ? (
            <Button variant="outline" onClick={() => setEditing(emptyDraft(name.trim(), phone))}><Icon name="plus" size={18} /> Add another place</Button>
          ) : <p className="small muted">You’ve added the maximum of {MAX} places.</p>}
          {errors._ && <p className="field__error" role="alert">{errors._}</p>}
          {!editing && (
            <Button block className="btn--lg" loading={submitting} disabled={!addresses.length} onClick={createAccount}>Create my Click account</Button>
          )}
        </div>
      )}
    </AuthLayout>
  );
}

function AddressDraftForm({ draft, onSave, onCancel }: { draft: Draft; onSave: (d: Draft) => void; onCancel?: () => void }) {
  const [d, setD] = useState(draft);
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [locating, setLocating] = useState<'idle' | 'busy' | 'denied' | 'unavailable'>('idle');
  const set = (k: keyof AddressInput) => (e: { target: { value: string } }) => setD((x) => ({ ...x, [k]: e.target.value }));

  function locate() {
    if (!('geolocation' in navigator)) return setLocating('unavailable');
    setLocating('busy');
    navigator.geolocation.getCurrentPosition(
      (pos) => { setD((x) => ({ ...x, latitude: pos.coords.latitude.toFixed(6), longitude: pos.coords.longitude.toFixed(6) })); setLocating('idle'); },
      (err) => setLocating(err.code === err.PERMISSION_DENIED ? 'denied' : 'unavailable'),
      { enableHighAccuracy: true, timeout: 10_000 },
    );
  }

  function submit(e: FormEvent) {
    e.preventDefault();
    const req: (keyof AddressInput)[] = ['recipientName', 'phone', 'line1', 'city', 'postalCode'];
    const err = Object.fromEntries(req.filter((k) => !String(d[k] ?? '').trim()).map((k) => [k, 'Required']));
    if (d.phone && !/^\+?[0-9 \-]{7,20}$/.test(d.phone)) err.phone = 'Enter a valid phone number.';
    setErrors(err);
    if (!Object.keys(err).length) onSave(d);
  }

  return (
    <form className="stack addr-form" onSubmit={submit} noValidate>
      <div className="chips" role="radiogroup" aria-label="Label" style={{ flexWrap: 'wrap' }}>
        {LABELS.map((l) => <button key={l.id} type="button" className="chip" aria-pressed={d.label === l.id} onClick={() => setD((x) => ({ ...x, label: l.id }))}>{l.text}</button>)}
      </div>
      <button type="button" className="locate-btn" onClick={locate} disabled={locating === 'busy'}>
        <Icon name="pin" size={18} />
        {d.latitude ? `Location pinned (${Number(d.latitude).toFixed(4)}, ${Number(d.longitude).toFixed(4)})` : locating === 'busy' ? 'Finding your location…' : 'Pin my current location'}
      </button>
      {locating === 'denied' && <span className="small muted">Location permission is off. No problem: just type your address below.</span>}
      {locating === 'unavailable' && <span className="small muted">Couldn’t get your location. Type your address below.</span>}
      <div className="form-grid">
        <TextField className="span-2" label="House / flat / floor" value={d.line1} onChange={set('line1')} error={errors.line1} autoComplete="address-line1" />
        <TextField className="span-2" label="Street and area" value={d.line2} onChange={set('line2')} autoComplete="address-line2" />
        <TextField label="City" value={d.city} onChange={set('city')} error={errors.city} autoComplete="address-level2" />
        <TextField label="PIN code" value={d.postalCode} onChange={set('postalCode')} error={errors.postalCode} inputMode="numeric" autoComplete="postal-code" />
        <TextField label="State" value={d.state} onChange={set('state')} autoComplete="address-level1" />
        <TextField label="Landmark (optional)" value={d.landmark} onChange={set('landmark')} />
        <TextField label="Receiver’s name" value={d.recipientName} onChange={set('recipientName')} error={errors.recipientName} autoComplete="name" />
        <TextField label="Receiver’s phone" type="tel" value={d.phone} onChange={set('phone')} error={errors.phone} autoComplete="tel" />
        <TextArea className="span-2" label="Delivery instructions (optional)" value={d.deliveryInstructions ?? ''} onChange={set('deliveryInstructions')} maxLength={200} rows={2} placeholder="e.g. Ring the bell twice" />
      </div>
      <div className="row">
        <Button type="submit">Save place</Button>
        {onCancel && <Button variant="ghost" onClick={onCancel}>Cancel</Button>}
      </div>
    </form>
  );
}
