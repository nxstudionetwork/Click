import { useEffect, useRef, useState } from 'react';
import { Button, Icon } from '@click/ui';
import type { SafetyResult } from '@click/api';
import { apiMessage } from '../../lib/format';
import { useSafety } from './queries';

/**
 * Safety during an active trip: always one tap away. Emergency tells Click's safety team (with the trip) and puts the
 * 112 call button in front of the driver; "Report an issue" files a note for follow-up.
 */
export function TripSafety({ trip, label = 'Safety' }: { trip: { id: string; ref: string }; label?: string }) {
  const ref = useRef<HTMLDialogElement>(null);
  const safety = useSafety();
  const [open, setOpen] = useState(false);
  const [note, setNote] = useState('');
  const [done, setDone] = useState<SafetyResult | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const d = ref.current;
    if (open && d && !d.open) { setDone(null); setError(null); setNote(''); d.showModal?.(); }
    if (!open && d?.open) d.close();
  }, [open]);

  const send = (kind: 'sos' | 'report') =>
    safety.mutate({ id: trip.id, kind, note }, { onSuccess: setDone, onError: (e) => setError(apiMessage(e)) });

  return (
    <>
      <div className="safety-bar">
        <button type="button" className="btn btn--danger btn--sm" onClick={() => setOpen(true)}>
          <Icon name="shield" size={16} /> {label}
        </button>
        <span className="small muted">Emergency help and reporting for this trip</span>
      </div>
      <dialog ref={ref} className="dialog" aria-labelledby="sf-t" onCancel={(e) => { e.preventDefault(); setOpen(false); }}>
        {open && (
          <div className="dialog__body">
            <h2 id="sf-t">Safety · {trip.ref}</h2>
            {done ? (
              <>
                <p role="status">{done.message}</p>
                <a className="btn btn--danger btn--block" href={`tel:${done.emergencyNumber}`}><Icon name="phone" size={18} /> Call {done.emergencyNumber}</a>
                <div className="dialog__actions"><button type="button" className="btn btn--outline" onClick={() => setOpen(false)}>Close</button></div>
              </>
            ) : (
              <>
                <p className="muted small">If anyone is in danger, call 112 first. Click’s safety team gets this trip’s details either way.</p>
                <a className="btn btn--danger btn--block" href="tel:112" onClick={() => send('sos')}><Icon name="phone" size={18} /> Emergency: call 112</a>
                <Button variant="outline" block loading={safety.isPending && safety.variables?.kind === 'sos'} onClick={() => send('sos')}>
                  Alert Click safety team (no call)
                </Button>
                <label className="field">
                  <span className="field__label">Or report an issue</span>
                  <textarea className="field__input" rows={3} maxLength={500} value={note} onChange={(e) => setNote(e.target.value)}
                    placeholder="What happened?" />
                </label>
                {error && <p className="field__error" role="alert">{error}</p>}
                <div className="dialog__actions">
                  <button type="button" className="btn btn--ghost" onClick={() => setOpen(false)}>Cancel</button>
                  <Button disabled={note.trim().length < 5} loading={safety.isPending && safety.variables?.kind === 'report'} onClick={() => send('report')}>
                    Send report
                  </Button>
                </div>
              </>
            )}
          </div>
        )}
      </dialog>
    </>
  );
}
