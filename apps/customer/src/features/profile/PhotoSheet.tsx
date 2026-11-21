import { useRef } from 'react';
import { useMutation } from '@tanstack/react-query';
import { ApiError } from '@click/api';
import { useAuth } from '../../auth/AuthProvider';
import { Icon, Sheet, useToast } from '../../components/ui';
import { api } from '../../lib/api';

const TYPES = ['image/jpeg', 'image/png', 'image/webp'];
const MAX_BYTES = 5 * 1024 * 1024;

/** Client-side checks mirror the server's (which re-validates and re-encodes): JPG/PNG/WebP up to 5 MB. */
export function validatePhoto(file: File): string | null {
  if (!TYPES.includes(file.type)) return 'Use a JPG, PNG or WebP image.';
  if (file.size > MAX_BYTES) return 'Images must be 5 MB or smaller.';
  return null;
}

const hasCamera = () => typeof window !== 'undefined' && typeof matchMedia === 'function' && matchMedia('(pointer: coarse)').matches;

/**
 * Change profile photo: Take photo (phones/tablets), Choose from gallery, Remove (when one exists), Cancel.
 * The photo on screen changes only after the server has stored it (POST/DELETE /me/avatar).
 */
export function PhotoSheet({ open, onClose, onBusy }: { open: boolean; onClose: () => void; onBusy: (busy: boolean) => void }) {
  const { user, refreshUser } = useAuth();
  const toast = useToast();
  const camera = useRef<HTMLInputElement>(null);
  const gallery = useRef<HTMLInputElement>(null);

  const upload = useMutation({
    mutationFn: api.auth.uploadAvatar,
    onMutate: () => onBusy(true),
    onSuccess: (u) => { refreshUser(u); toast('Profile photo updated'); },
    onError: (e) => toast(e instanceof ApiError && e.code.startsWith('image_') ? e.message : 'Couldn’t update your photo. Try again.', 'error'),
    onSettled: () => onBusy(false),
  });
  const remove = useMutation({
    mutationFn: api.auth.removeAvatar,
    onMutate: () => onBusy(true),
    onSuccess: (u) => { refreshUser(u); toast('Profile photo removed'); },
    onError: () => toast('Couldn’t remove your photo. Try again.', 'error'),
    onSettled: () => onBusy(false),
  });

  const pick = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    e.target.value = '';
    if (!file) return;
    const problem = validatePhoto(file);
    if (problem) { toast(problem, 'error'); return; }
    onClose();
    upload.mutate(file);
  };

  return (
    <>
      <input ref={camera} type="file" accept="image/*" capture="user" className="visually-hidden" tabIndex={-1} aria-hidden="true" onChange={pick} />
      <input ref={gallery} type="file" accept="image/jpeg,image/png,image/webp" className="visually-hidden" tabIndex={-1} aria-hidden="true" onChange={pick} />
      <Sheet open={open} onClose={onClose} label="Change profile photo">
        <div className="psheet">
          <h2>Profile photo</h2>
          <div className="psheet__opts">
            {hasCamera() && <button type="button" className="psheet__opt" onClick={() => camera.current?.click()}><Icon name="camera" />Take photo</button>}
            <button type="button" className="psheet__opt" onClick={() => gallery.current?.click()}><Icon name="download" />Choose from gallery</button>
            {user?.avatarUrl && (
              <button type="button" className="psheet__opt psheet__opt--danger" onClick={() => { onClose(); remove.mutate(); }}><Icon name="close" />Remove photo</button>
            )}
          </div>
          <p className="small muted">JPG, PNG or WebP up to 5 MB. Location data is removed from photos.</p>
          <button type="button" className="btn btn--ghost btn--block" onClick={onClose}>Cancel</button>
        </div>
      </Sheet>
    </>
  );
}
