import type { Dietary } from '@click/api';
import { Icon } from './Icon';

export function Rating({ value, count }: { value: string; count?: number }) {
  const n = Number(value);
  if (!n) return <span className="badge">New</span>;
  return (
    <span className="rating" aria-label={`Rated ${value} out of 5${count ? ` by ${count} people` : ''}`}>
      <Icon name="star" size={15} className="rating__star" />
      {n.toFixed(1)}
      {count !== undefined && <span className="muted small">({count >= 1000 ? `${(count / 1000).toFixed(1)}k` : count})</span>}
    </span>
  );
}

const DIET_LABEL: Record<Dietary, string> = { veg: 'Vegetarian', vegan: 'Vegan', non_veg: 'Non-vegetarian', unspecified: '' };

export function DietMark({ dietary }: { dietary: Dietary }) {
  if (dietary === 'unspecified') return null;
  return <span className={`diet diet--${dietary}`} role="img" aria-label={DIET_LABEL[dietary]} title={DIET_LABEL[dietary]} />;
}

export function QuantityStepper({ value, onChange, busy, max = 50, label }: {
  value: number; onChange: (next: number) => void; busy?: boolean; max?: number; label: string;
}) {
  return (
    <div className="stepper" role="group" aria-label={`Quantity of ${label}`}>
      <button type="button" aria-label="Decrease" disabled={busy} onClick={(e) => { e.stopPropagation(); onChange(value - 1); }}>−</button>
      <span aria-live="polite">{value}</span>
      <button type="button" aria-label="Increase" disabled={busy || value >= max} onClick={(e) => { e.stopPropagation(); onChange(value + 1); }}>+</button>
    </div>
  );
}
