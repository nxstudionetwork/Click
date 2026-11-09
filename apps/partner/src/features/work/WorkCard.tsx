import { useState } from 'react';
import { Link } from 'react-router-dom';
import { Button, Icon, useToast, type IconName } from '@click/ui';
import type { WorkAction, WorkItem } from '@click/api';
import { ConfirmDialog } from '../../components/ConfirmDialog';
import { apiMessage } from '../../lib/format';
import { clockTime, formatMoney, timeAgo } from '../../lib/money';
import { useWorkAction } from '../home/queries';

const KIND_ICON: Record<string, IconName> = { ride: 'ride', order: 'receipt', show: 'film', booking: 'ticket', stock: 'grocery' };

/** Directions open in the partner's own maps app (OpenStreetMap link; Click never tracks the route). */
function directionsUrl(n: NonNullable<WorkItem['navigate']>) {
  return `https://www.openstreetmap.org/directions?to=${n.lat}%2C${n.lng}#map=16/${n.lat}/${n.lng}`;
}

/**
 * One unit of work (ride request, trip, order, show, booking, stock alert). Status is always text plus tone, never
 * colour alone. Actions go to the server; nothing is shown as done until the server confirms it.
 */
export function WorkCard({ item, emphasis = false }: { item: WorkItem; emphasis?: boolean }) {
  const toast = useToast();
  const act = useWorkAction();
  const [confirming, setConfirming] = useState<WorkAction | null>(null);
  const [error, setError] = useState<string | null>(null);

  function run(action: WorkAction, reason?: string) {
    setError(null);
    act.mutate({ item, action: action.key, reason }, {
      onSuccess: () => {
        setConfirming(null);
        toast(`${action.label}: done`);
      },
      onError: (err) => {
        const message = apiMessage(err);
        if (confirming) setError(message);
        else toast(message, 'error');
      },
    });
  }

  function onAction(action: WorkAction) {
    if (action.confirm || action.needsReason) { setError(null); setConfirming(action); }
    else run(action);
  }

  const busyKey = act.isPending ? act.variables?.action : null;
  return (
    <article className={`work work--${item.tone} ${emphasis ? 'work--emphasis' : ''}`} aria-labelledby={`w-${item.id}`}>
      <header className="work__head">
        <span className="work__icon" aria-hidden="true"><Icon name={KIND_ICON[item.kind] ?? 'receipt'} size={20} /></span>
        <div className="work__title">
          <h3 id={`w-${item.id}`}>{item.title}</h3>
          {item.subtitle && <p className="muted small">{item.subtitle}</p>}
        </div>
        <div className="work__meta">
          <span className={`tag tag--${item.tone}`}>{item.statusLabel}</span>
          {item.amount && <strong className="work__amount">{formatMoney(item.amount)}</strong>}
        </div>
      </header>

      {item.fields.length > 0 && (
        <dl className="work__fields">
          {item.fields.map((f) => <div key={f.label}><dt>{f.label}</dt><dd>{f.value}</dd></div>)}
        </dl>
      )}

      {(item.actions.length > 0 || item.navigate || item.link) && (
        <div className="work__actions">
          {item.actions.map((a) => (
            <Button key={a.key} size="sm" variant={a.style === 'primary' ? 'primary' : a.style === 'danger' ? 'danger' : 'outline'}
              loading={busyKey === a.key} disabled={act.isPending} onClick={() => onAction(a)}>
              {a.label}
            </Button>
          ))}
          {item.navigate && (
            <a className="btn btn--outline btn--sm" href={directionsUrl(item.navigate)} target="_blank" rel="noopener noreferrer">
              <Icon name="compass" size={16} /> Navigate to {item.navigate.label}
              <span className="visually-hidden"> (opens maps in a new tab)</span>
            </a>
          )}
          {item.link && !item.actions.length && <Link className="text-btn" to={item.link}>View</Link>}
        </div>
      )}
      {item.at && (
        <p className="work__time small muted">
          {item.kind === 'show' ? `Starts ${clockTime(item.at)}` : timeAgo(item.at)} · {item.ref}
        </p>
      )}

      <ConfirmDialog
        open={!!confirming}
        title={confirming?.needsReason ? `${confirming.label} ${item.title.toLowerCase().startsWith('order') ? 'this order' : ''}`.trim() : confirming?.label ?? ''}
        message={confirming?.confirm ?? ''}
        confirmLabel={confirming?.label ?? 'Confirm'}
        tone={confirming?.style === 'danger' ? 'danger' : 'primary'}
        needsReason={confirming?.needsReason}
        reasonLabel="Reason (shared with the customer)"
        pending={act.isPending}
        error={error}
        onConfirm={(reason) => confirming && run(confirming, reason)}
        onClose={() => setConfirming(null)}
      />
    </article>
  );
}
