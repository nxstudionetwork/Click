import { useEffect, useState, type FormEvent } from 'react';
import { ApiError } from '@click/api';
import { useAuth } from '../auth/AuthProvider';
import { Button, TextField, useToast } from '../components/ui';
import { api } from '../lib/api';

export function SettingsPage() {
  const { user, logout, refreshUser } = useAuth();
  const toast = useToast();
  const [fullName, setFullName] = useState(user?.fullName ?? '');
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [saving, setSaving] = useState(false);

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
      <section className="card card--pad stack">
        <h3>Session</h3>
        <p className="small muted">Signing out ends this session on this device.</p>
        <Button variant="outline" onClick={logout} style={{ alignSelf: 'flex-start' }}>Sign out</Button>
      </section>
    </div>
  );
}
