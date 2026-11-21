import { useEffect, useState, type FormEvent } from 'react';
import { ApiError } from '@click/api';
import { maskPhone } from '@click/phone-auth';
import { useAuth } from '../../auth/AuthProvider';
import { Button, Icon, Sheet, TextField, useToast } from '../../components/ui';
import { api } from '../../lib/api';
import { PhotoSheet } from './PhotoSheet';

export const displayPhone = (phone: string) => maskPhone(phone.replace(/[^\d+]/g, ''));

/** Name rules (mirrors the server): 2–150 characters, letters required. */
export function validateName(name: string): string | null {
  const n = name.trim();
  if (n.length < 2) return 'Enter at least 2 characters.';
  if (n.length > 150) return 'Keep it under 150 characters.';
  if (!/\p{L}/u.test(n)) return 'Use letters in your name.';
  return null;
}

/** Who the customer is: photo (editable), name (editable), immutable Click. ID (copyable), verified phone, email. */
export function ProfileIdentity() {
  const { user } = useAuth();
  const toast = useToast();
  const [photoOpen, setPhotoOpen] = useState(false);
  const [nameOpen, setNameOpen] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [copied, setCopied] = useState(false);
  if (!user) return null;
  const initial = (user.fullName || user.email || '?').trim()[0]!.toUpperCase();

  async function copyId() {
    try {
      await navigator.clipboard.writeText(user!.customerCode ?? '');
      setCopied(true);
      setTimeout(() => setCopied(false), 1800);
    } catch {
      toast('Couldn’t copy. Select the ID to copy it.', 'error');
    }
  }

  return (
    <section className="pid" aria-label="Your Click. identity">
      <div className="pid__avatar-wrap">
        <button type="button" className={`pid__avatar ${uploading ? 'is-busy' : ''}`} onClick={() => setPhotoOpen(true)}
          aria-label={user.avatarUrl ? 'Change profile photo' : 'Add a profile photo'} disabled={uploading}>
          {user.avatarUrl ? <img src={user.avatarUrl} alt="" /> : <span aria-hidden="true">{initial}</span>}
          {uploading && <span className="pid__uploading" role="status">Uploading…</span>}
        </button>
        <span className="pid__edit" aria-hidden="true"><Icon name="edit" size={14} /></span>
      </div>

      <div className="pid__name">
        <h2>{user.fullName || 'Your name'}</h2>
        <button type="button" className="icon-btn pid__name-edit" aria-label="Edit your name" onClick={() => setNameOpen(true)}><Icon name="edit" size={16} /></button>
      </div>

      {user.customerCode && (
        <div className="pid__id">
          <span className="pid__id-label">Click. ID</span>
          <code>{user.customerCode}</code>
          <button type="button" className="pid__copy" onClick={copyId} aria-label={copied ? 'Click. ID copied' : 'Copy your Click. ID'}>
            <Icon name={copied ? 'check' : 'copy'} size={14} />{copied ? 'Copied' : 'Copy'}
          </button>
        </div>
      )}

      <dl className="pid__facts">
        {user.phone && (
          <div><dt>Phone</dt><dd>{displayPhone(user.phone)} {user.phoneVerified && <span className="pid__verified"><Icon name="check" size={12} />Verified</span>}</dd></div>
        )}
        <div><dt>Email</dt><dd>{user.email || <span className="muted">Not added</span>}</dd></div>
      </dl>

      <PhotoSheet open={photoOpen} onClose={() => setPhotoOpen(false)} onBusy={setUploading} />
      <NameSheet open={nameOpen} onClose={() => setNameOpen(false)} />
    </section>
  );
}

function NameSheet({ open, onClose }: { open: boolean; onClose: () => void }) {
  const { user, refreshUser } = useAuth();
  const toast = useToast();
  const [name, setName] = useState(user?.fullName ?? '');
  const [error, setError] = useState('');
  const [saving, setSaving] = useState(false);
  useEffect(() => { if (open) { setName(user?.fullName ?? ''); setError(''); } }, [open, user?.fullName]);

  async function save(e: FormEvent) {
    e.preventDefault();
    const problem = validateName(name);
    if (problem) { setError(problem); return; }
    setSaving(true);
    try {
      refreshUser(await api.auth.updateMe({ fullName: name.trim() }));
      toast('Name updated');
      onClose();
    } catch (err) {
      setError(err instanceof ApiError ? err.fieldErrors().fullName ?? err.message : 'Couldn’t save. Try again.');
    } finally {
      setSaving(false);
    }
  }

  return (
    <Sheet open={open} onClose={onClose} label="Edit your name">
      <form className="psheet" onSubmit={save} noValidate>
        <h2>Your name</h2>
        <TextField label="Full name" value={name} onChange={(e) => { setName(e.target.value); setError(''); }} error={error} autoComplete="name" maxLength={150} autoFocus />
        <p className="small muted">Shown on your Click. card and to partners serving your orders.</p>
        <div className="row"><Button type="submit" loading={saving}>Save</Button><Button variant="ghost" onClick={onClose}>Cancel</Button></div>
      </form>
    </Sheet>
  );
}
