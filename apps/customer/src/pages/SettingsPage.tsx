import { useEffect, useState, type FormEvent } from 'react';
import { ApiError } from '@click/api';
import { useAuth } from '../auth/AuthProvider';
import { Button, TextField, useToast } from '../components/ui';
import { api } from '../lib/api';
import { useAppearance, type Appearance } from '../appearance';

const APPEARANCES: { id: Appearance; label: string }[] = [
  { id: 'light', label: 'White' },
  { id: 'dark', label: 'Dark' },
  { id: 'system', label: 'Match device' },
];

export function SettingsPage() {
  const { user, logout, refreshUser } = useAuth();
  const toast = useToast();
  const [fullName, setFullName] = useState(user?.fullName ?? '');
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [saving, setSaving] = useState(false);
  const { appearance, setAppearance } = useAppearance();

  useEffect(() => { setFullName(user?.fullName ?? ''); }, [user]);

  async function save(e: FormEvent) {
    e.preventDefault();
    setSaving(true);
    setErrors({});
    try {
      refreshUser(await api.auth.updateMe({ fullName: fullName.trim() }));
      toast('Profile saved');
    } catch (err) {
      setErrors(err instanceof ApiError ? { ...err.fieldErrors(), _: err.code === 'validation_error' ? '' : err.message } : { _: 'Could not save.' });
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="stack">
      <h1>Settings</h1>
      <form className="card card--pad stack" onSubmit={save} noValidate>
        <h3>Profile</h3>
        <div className="form-grid">
          <TextField label="Full name" value={fullName} onChange={(e) => setFullName(e.target.value)} error={errors.fullName} autoComplete="name" maxLength={150} />
          <TextField label={user?.phoneVerified ? 'Phone (verified)' : 'Phone'} type="tel" value={user?.phone ?? ''} disabled readOnly />
          <TextField label="Email" value={user?.email ?? ''} disabled readOnly />
        </div>
        {errors._ && <p className="field__error" role="alert">{errors._}</p>}
        <Button type="submit" loading={saving} style={{ alignSelf: 'flex-start' }}>Save changes</Button>
      </form>
      <section className="card card--pad stack" aria-labelledby="appearance-h">
        <h3 id="appearance-h">Appearance</h3>
        <p className="small muted">White is Click.’s standard look. Dark uses deep navy, easier on the eyes at night.</p>
        <div className="chips" role="radiogroup" aria-labelledby="appearance-h">
          {APPEARANCES.map((a) => (
            <button key={a.id} type="button" role="radio" aria-checked={appearance === a.id} aria-pressed={appearance === a.id} className="chip" onClick={() => setAppearance(a.id)}>{a.label}</button>
          ))}
        </div>
      </section>
      <section className="card card--pad stack">
        <h3>Session</h3>
        <p className="small muted">Signing out ends this session on this device.</p>
        <Button variant="outline" onClick={logout} style={{ alignSelf: 'flex-start' }}>Sign out</Button>
      </section>
    </div>
  );
}
