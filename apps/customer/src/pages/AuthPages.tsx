import { useState, type FormEvent } from 'react';
import { Link, Navigate, useNavigate, useSearchParams } from 'react-router-dom';
import { ApiError } from '@click/api';
import { useAuth } from '../auth/AuthProvider';
import { Button, TextField } from '../components/ui';

function safeNext(next: string | null) {
  // Only allow same-app relative paths (prevents open redirects).
  return next && next.startsWith('/') && !next.startsWith('//') ? next : '/';
}

function useAuthForm<T extends Record<string, string>>(initial: T, action: (v: T) => Promise<void>) {
  const [values, setValues] = useState(initial);
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [pending, setPending] = useState(false);
  const [params] = useSearchParams();
  const navigate = useNavigate();
  const set = (k: keyof T) => (e: { target: { value: string } }) => setValues((v) => ({ ...v, [k]: e.target.value }));
  async function submit(e: FormEvent) {
    e.preventDefault();
    setPending(true);
    setErrors({});
    try {
      await action(values);
      navigate(safeNext(params.get('next')), { replace: true });
    } catch (err) {
      if (err instanceof ApiError) setErrors({ ...err.fieldErrors(), _: err.code === 'validation_error' ? '' : err.message });
      else setErrors({ _: 'Something went wrong.' });
    } finally {
      setPending(false);
    }
  }
  return { values, errors, pending, set, submit, next: params.get('next') };
}

export function LoginPage() {
  const { login, status } = useAuth();
  const f = useAuthForm({ email: '', password: '' }, (v) => login(v.email, v.password));
  if (status === 'authenticated') return <Navigate to={safeNext(f.next)} replace />;
  return (
    <form className="auth card card--pad stack" onSubmit={f.submit} noValidate>
      <h1>Welcome back</h1>
      <TextField label="Email" type="email" autoComplete="email" value={f.values.email} onChange={f.set('email')} error={f.errors.email} required />
      <TextField label="Password" type="password" autoComplete="current-password" value={f.values.password} onChange={f.set('password')} error={f.errors.password} required />
      {f.errors._ && <p className="field__error" role="alert">{f.errors._}</p>}
      <Button type="submit" block loading={f.pending}>Sign in</Button>
      <p className="small muted">New to Click? <Link to={`/register${f.next ? `?next=${encodeURIComponent(f.next)}` : ''}`} style={{ color: 'var(--c-brand)', fontWeight: 600 }}>Create an account</Link></p>
    </form>
  );
}

export function RegisterPage() {
  const { register, status } = useAuth();
  const f = useAuthForm({ fullName: '', email: '', password: '' }, (v) => register(v));
  if (status === 'authenticated') return <Navigate to={safeNext(f.next)} replace />;
  return (
    <form className="auth card card--pad stack" onSubmit={f.submit} noValidate>
      <h1>Create your account</h1>
      <TextField label="Full name" autoComplete="name" value={f.values.fullName} onChange={f.set('fullName')} error={f.errors.fullName} />
      <TextField label="Email" type="email" autoComplete="email" value={f.values.email} onChange={f.set('email')} error={f.errors.email} required />
      <TextField label="Password" type="password" autoComplete="new-password" value={f.values.password} onChange={f.set('password')} error={f.errors.password ?? f.errors.nonFieldErrors} required minLength={8} />
      {f.errors._ && <p className="field__error" role="alert">{f.errors._}</p>}
      <Button type="submit" block loading={f.pending}>Create account</Button>
      <p className="small muted">Already have an account? <Link to={`/login${f.next ? `?next=${encodeURIComponent(f.next)}` : ''}`} style={{ color: 'var(--c-brand)', fontWeight: 600 }}>Sign in</Link></p>
    </form>
  );
}
