import { useEffect, useRef, useState } from 'react';
import { Button, Icon, Skeleton, useToast } from '@click/ui';
import type { OperationInput, RestaurantOperations } from '@click/api';
import { apiMessage } from '../../lib/format';
import { clockTime } from '../../lib/money';
import { useOperate, useOperations } from './queries';

const label = (m: number) => (m >= 60 ? `${m / 60} hour${m === 60 ? '' : 's'}` : `${m} min`);

/** A dialog for the temporary-closure choice: how long, and why (customers see "Temporarily closed"). */
function PauseDialog({ ops, open, onClose }: { ops: RestaurantOperations; open: boolean; onClose: () => void }) {
  const ref = useRef<HTMLDialogElement>(null);
  const operate = useOperate();
  const toast = useToast();
  const [minutes, setMinutes] = useState(30);
  const [reason, setReason] = useState(ops.pauseReasons[0]?.key ?? 'other');
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    const d = ref.current;
    if (open && d && !d.open) { setError(null); d.showModal?.(); }
    if (!open && d?.open) d.close();
  }, [open]);

  function submit() {
    operate.mutate({ action: 'pause', forMinutes: minutes, reason }, {
      onSuccess: (s) => { toast(`Closed until ${clockTime(s.pausedUntil)}`); onClose(); },
      onError: (e) => setError(apiMessage(e)),
    });
  }

  return (
    <dialog ref={ref} className="dialog" aria-labelledby="pause-t" onCancel={(e) => { e.preventDefault(); onClose(); }}>
      {open && (
        <div className="dialog__body">
          <h2 id="pause-t">Close temporarily</h2>
          <p className="muted small">New orders stop right away. Orders already placed stay in your kitchen. You’ll reopen automatically.</p>
          <fieldset className="choice-set">
            <legend className="section-label">For how long?</legend>
            <div className="seg seg--wrap">
              {ops.pauseChoices.map((m) => (
                <button key={m} type="button" className={`seg__btn ${m === minutes ? 'is-active' : ''}`} aria-pressed={m === minutes}
                  onClick={() => setMinutes(m)}>{label(m)}</button>
              ))}
            </div>
          </fieldset>
          <label className="field">
            <span className="field__label">Reason</span>
            <select className="field__input" value={reason} onChange={(e) => setReason(e.target.value)}>
              {ops.pauseReasons.map((r) => <option key={r.key} value={r.key}>{r.label}</option>)}
            </select>
          </label>
          {error && <p className="field__error" role="alert">{error}</p>}
          <div className="dialog__actions">
            <button type="button" className="btn btn--ghost" onClick={onClose}>Cancel</button>
            <Button variant="danger" loading={operate.isPending} onClick={submit}>Close for {label(minutes)}</Button>
          </div>
        </div>
      )}
    </dialog>
  );
}

/**
 * Kitchen operations on Restaurant Home: busy (adds minutes to the delivery window customers see), temporary closure
 * with automatic reopening, and the usual preparation time. Open/Closed itself is the availability card above.
 */
export function OperationsCard() {
  const ops = useOperations();
  const operate = useOperate();
  const toast = useToast();
  const [pausing, setPausing] = useState(false);
  const [prep, setPrep] = useState<number | null>(null);

  if (ops.isPending) return <Skeleton height={140} radius={22} />;
  if (ops.isError) {
    return (
      <section className="mod" aria-label="Kitchen operations">
        <p className="mod__note mod__note--error" role="alert"><Icon name="alert" size={16} /> {apiMessage(ops.error)}</p>
        <Button size="sm" variant="outline" onClick={() => void ops.refetch()}>Try again</Button>
      </section>
    );
  }
  const s = ops.data;
  const run = (body: OperationInput, done: string) =>
    operate.mutate(body, { onSuccess: () => toast(done), onError: (e) => toast(apiMessage(e), 'error') });
  const prepValue = prep ?? s.prepTimeMinutes;

  return (
    <section className={`mod ops ops--${s.state}`} aria-labelledby="ops-h">
      <div className="mod__head">
        <h2 id="ops-h" className="mod__title"><Icon name="food" size={18} />Kitchen</h2>
        <span className={`tag tag--${s.state === 'open' ? 'success' : s.state === 'busy' ? 'urgent' : 'muted'}`}>{s.label}</span>
      </div>

      {s.state === 'paused' && (
        <div className="ops__banner" role="status">
          <Icon name="clock" size={18} />
          <span><strong>Temporarily closed</strong> · {s.pauseReason}. Reopens at {clockTime(s.pausedUntil)}.</span>
          <Button size="sm" loading={operate.isPending} onClick={() => run({ action: 'resume' }, 'Restaurant reopened')}>Reopen now</Button>
        </div>
      )}
      {s.state === 'busy' && (
        <div className="ops__banner ops__banner--busy" role="status">
          <Icon name="alert" size={18} />
          <span><strong>Busy right now</strong> · customers see +{s.busyExtraMinutes} min until {clockTime(s.busyUntil)} ({s.deliveryWindow}).</span>
          <Button size="sm" variant="outline" loading={operate.isPending} onClick={() => run({ action: 'not_busy' }, 'Back to normal times')}>
            Not busy
          </Button>
        </div>
      )}

      {(s.state === 'open' || s.state === 'busy') && (
        <div className="ops__row">
          <span className="ops__label">Busy? Add time for the next hour</span>
          <div className="seg">
            {s.busyChoices.map((m) => (
              <button key={m} type="button" className={`seg__btn ${s.state === 'busy' && s.busyExtraMinutes === m ? 'is-active' : ''}`}
                disabled={operate.isPending} onClick={() => run({ action: 'busy', minutes: m, forMinutes: 60 }, `Customers now see +${m} min`)}>
                +{m} min
              </button>
            ))}
          </div>
        </div>
      )}

      <div className="ops__row">
        <label className="ops__label" htmlFor="prep">Usual preparation time</label>
        <div className="ops__prep">
          <input id="prep" type="number" inputMode="numeric" min={5} max={90} step={5} className="field__input ops__num" value={prepValue}
            onChange={(e) => setPrep(Number(e.target.value))} aria-describedby="prep-hint" />
          <span className="small muted">min</span>
          {prep !== null && prep !== s.prepTimeMinutes && (
            <Button size="sm" loading={operate.isPending}
              onClick={() => operate.mutate({ action: 'prep_time', minutes: prepValue }, {
                onSuccess: () => { setPrep(null); toast('Preparation time saved'); },
                onError: (e) => toast(apiMessage(e), 'error'),
              })}>Save</Button>
          )}
        </div>
        <p id="prep-hint" className="small muted">Used for the target ready time on kitchen tickets. Delivery timing stays with Click.</p>
      </div>

      {(s.state === 'open' || s.state === 'busy') && (
        <button type="button" className="text-btn ops__pause" onClick={() => setPausing(true)}>
          <Icon name="clock" size={14} /> Close temporarily…
        </button>
      )}
      <PauseDialog ops={s} open={pausing} onClose={() => setPausing(false)} />
    </section>
  );
}
