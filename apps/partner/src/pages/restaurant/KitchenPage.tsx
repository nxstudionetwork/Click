import { Link } from 'react-router-dom';
import { Button, Icon, Skeleton } from '@click/ui';
import type { KitchenCard } from '@click/api';
import { AppShell } from '../../components/AppShell';
import { Empty } from '../../features/home/sections';
import { useKitchen } from '../../features/restaurant/queries';
import { WorkCard } from '../../features/work/WorkCard';
import { apiMessage } from '../../lib/format';
import { clockTime } from '../../lib/money';

/** One kitchen ticket: the items to cook first, then timing, then the one next step. */
function Ticket({ card }: { card: KitchenCard }) {
  const k = card.kitchen;
  return (
    <WorkCard item={card} className={`ticket ${k.late ? 'ticket--late' : ''}`} body={(
      <div className="ticket__body">
        <ul className="ticket__lines">
          {k.lines.map((l, i) => (
            <li key={i}>
              <span className="ticket__qty">{l.quantity}×</span>
              <span><strong>{l.name}</strong>{l.options && <span className="small muted"> · {l.options}</span>}
                {l.note && <span className="ticket__note">“{l.note}”</span>}</span>
            </li>
          ))}
        </ul>
        {k.note && <p className="ticket__instr"><Icon name="alert" size={14} /> {k.note}</p>}
        <p className="small ticket__timing">
          {k.orderType} · placed {clockTime(k.placedAt)}
          {k.readyBy && <> · <strong className={k.late ? 'tone-danger' : ''}>{k.late ? 'Late — target was' : 'Ready by'} {clockTime(k.readyBy)}</strong></>}
          {k.handover && <> · {k.handover}</>}
        </p>
      </div>
    )} />
  );
}

/**
 * The Kitchen: every live order in its stage (New → Accepted → Preparing → Ready), oldest first. Columns on wide
 * screens (kitchen tablet / display), stacked on a phone. Refreshes every few seconds; actions are server-confirmed.
 */
export function KitchenPage() {
  const kitchen = useKitchen();
  const data = kitchen.data;
  const total = data?.columns.reduce((n, c) => n + c.items.length, 0) ?? 0;

  return (
    <AppShell>
      <div className="page page--wide">
        <div className="page__head spread">
          <div>
            <h1>Kitchen</h1>
            <p className="muted small">
              {data ? `Target preparation ${data.prepTimeMinutes} min · ${data.operations.label}` : 'Live orders by stage'} · updates every few seconds
            </p>
          </div>
          <Link to="/restaurant/orders" className="btn btn--outline btn--sm">All orders</Link>
        </div>

        {kitchen.isPending ? (
          <div className="kitchen" aria-busy="true">{[0, 1, 2, 3].map((i) => <Skeleton key={i} height={220} radius={20} />)}</div>
        ) : kitchen.isError && !data ? (
          <div className="dash__error" role="alert">
            <h2>Couldn’t load the kitchen</h2><p className="muted">{apiMessage(kitchen.error)}</p>
            <Button onClick={() => void kitchen.refetch()}>Try again</Button>
          </div>
        ) : total === 0 ? (
          <Empty icon="check" title="No orders in the kitchen right now."
            message={data!.operations.state === 'open' || data!.operations.state === 'busy'
              ? 'New orders appear here the moment customers place them.' : `Your restaurant is ${data!.operations.label.toLowerCase()}. Open it from Home to receive orders.`} />
        ) : (
          <div className="kitchen">
            {data!.columns.map((col) => (
              <section key={col.key} className={`kitchen__col kitchen__col--${col.key}`} aria-labelledby={`kc-${col.key}`}>
                <h2 id={`kc-${col.key}`} className="kitchen__title">{col.label}<span className="tabs__count">{col.items.length}</span></h2>
                {col.items.length === 0 ? <p className="small muted kitchen__empty">Nothing here.</p>
                  : <div className="work-list">{col.items.map((c) => <Ticket key={c.id} card={c} />)}</div>}
              </section>
            ))}
          </div>
        )}
        {kitchen.isError && data && <p className="mod__note" role="status"><Icon name="alert" size={16} /> Can’t refresh right now. Showing the last update.</p>}
      </div>
    </AppShell>
  );
}
