import { useEffect, useId, useRef, useState, type FormEvent } from 'react';
import { Button } from '@click/ui';

/**
 * Native <dialog> (focus trap, Escape and inert background come from the browser). Used only where an action has
 * real consequences: going offline/closed, rejecting an order, completing a trip.
 */
export function ConfirmDialog({ open, title, message, confirmLabel, tone = 'primary', needsReason = false, reasonLabel = 'Reason',
  pending = false, error, onConfirm, onClose }: {
  open: boolean; title: string; message: string; confirmLabel: string; tone?: 'primary' | 'danger'; needsReason?: boolean;
  reasonLabel?: string; pending?: boolean; error?: string | null; onConfirm: (reason?: string) => void; onClose: () => void;
}) {
  const ref = useRef<HTMLDialogElement>(null);
  const [reason, setReason] = useState('');
  const [touched, setTouched] = useState(false);
  const id = useId();

  useEffect(() => {
    const d = ref.current;
    if (!d) return;
    if (open && !d.open) { setReason(''); setTouched(false); d.showModal?.(); }
    if (!open && d.open) d.close();
  }, [open]);

  const invalid = needsReason && reason.trim().length < 3;

  function submit(e: FormEvent) {
    e.preventDefault();
    setTouched(true);
    if (invalid) return;
    onConfirm(needsReason ? reason.trim() : undefined);
  }

  return (
    <dialog ref={ref} className="dialog" aria-labelledby={`${id}-t`} aria-describedby={`${id}-m`}
      onCancel={(e) => { e.preventDefault(); if (!pending) onClose(); }}
      onClick={(e) => { if (e.target === ref.current && !pending) onClose(); }}>
      {open && (
        <form className="dialog__body" onSubmit={submit} noValidate>
          <h2 id={`${id}-t`}>{title}</h2>
          <p id={`${id}-m`} className="muted">{message}</p>
          {needsReason && (
            <label className={`field ${touched && invalid ? 'field--error' : ''}`}>
              <span className="field__label">{reasonLabel}</span>
              <textarea className="field__input dialog__reason" rows={3} maxLength={200} value={reason} autoFocus
                onChange={(e) => setReason(e.target.value)} aria-invalid={touched && invalid} />
              {touched && invalid && <span className="field__error" role="alert">Enter a short reason the customer will see.</span>}
            </label>
          )}
          {error && <p className="notice notice--warning" role="alert"><span>{error}</span></p>}
          <div className="dialog__actions">
            <Button type="button" variant="outline" onClick={onClose} disabled={pending}>Cancel</Button>
            <Button type="submit" loading={pending} variant={tone === 'danger' ? 'danger' : 'primary'}>{confirmLabel}</Button>
          </div>
        </form>
      )}
    </dialog>
  );
}
