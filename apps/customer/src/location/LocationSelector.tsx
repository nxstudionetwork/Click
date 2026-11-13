import { useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { useAuth } from '../auth/AuthProvider';
import { Icon, Sheet } from '../components/ui';
import { useDeliveryLocation } from './LocationProvider';

export const formatAddressLine = (a: { line1: string; line2?: string; city: string }) =>
  [a.line1, a.line2, a.city].filter(Boolean).join(', ');

/** Short "area, city" line for the header (the full address is in the selector). */
export const formatArea = (a: { line2?: string; city: string; state?: string }) =>
  [a.line2 || a.city, a.line2 ? a.city : a.state].filter(Boolean).join(', ');

/**
 * Home's location selector: choose the active app location from the addresses already saved in
 * Profile → Addresses. It never creates or edits addresses; that happens on the Addresses page.
 */
export function LocationSelector({ compact = false }: { compact?: boolean }) {
  const { status } = useAuth();
  const { addresses, selected, select, isLoading } = useDeliveryLocation();
  const [open, setOpen] = useState(false);
  const navigate = useNavigate();

  const label = status !== 'authenticated' ? 'Set location' : isLoading ? 'Locating…' : selected ? selected.label : 'Choose a location';
  const detail = selected ? formatArea(selected) : status === 'authenticated' ? 'Pick a saved address' : 'Sign in to use your addresses';

  return (
    <>
      <button
        type="button" className={`location ${compact ? 'location--compact' : ''}`}
        onClick={() => (status === 'authenticated' ? setOpen(true) : navigate('/login'))}
        aria-label={`Delivering to ${selected ? `${selected.label}, ${formatAddressLine(selected)}` : label}. Change location`}
      >
        <span className="location__pin"><Icon name="pin" size={18} /></span>
        <span className="location__text">
          <span className="location__eyebrow">Delivering to</span>
          <span className="location__label"><span className="location__name">{label}</span><span className="location__detail"> · {detail}</span></span>
        </span>
        <Icon name="chevron" size={16} className="location__chev" />
      </button>

      <Sheet open={open} onClose={() => setOpen(false)} label="Choose your location">
        <div className="stack loc-sheet">
          <div className="spread">
            <h2>Choose location</h2>
            <button className="icon-btn" aria-label="Close" onClick={() => setOpen(false)}><Icon name="close" /></button>
          </div>
          {addresses.length === 0 ? (
            <div className="hstate">
              <span className="hstate__icon"><Icon name="pin" size={18} /></span>
              <div><strong>No saved addresses yet</strong><span>Add your addresses in Profile → Addresses, then choose one here.</span></div>
              <Link to="/account/addresses" className="btn btn--primary btn--sm" onClick={() => setOpen(false)}>Go to Addresses</Link>
            </div>
          ) : (
            <div className="stack" style={{ gap: 'var(--s-2)' }} role="radiogroup" aria-label="Saved addresses">
              {addresses.map((a) => (
                <label key={a.id} className={`loc-option ${selected?.id === a.id ? 'loc-option--on' : ''}`}>
                  <input type="radio" name="loc" className="visually-hidden" checked={selected?.id === a.id} onChange={() => { select(a.id); setOpen(false); }} />
                  <span className="loc-option__icon"><Icon name={a.label === 'work' ? 'briefcase' : a.label === 'home' ? 'home' : 'pin'} size={18} /></span>
                  <span className="loc-option__text">
                    <strong>{a.label}{a.isDefault && <span className="badge" style={{ marginLeft: 6 }}>Default</span>}</strong>
                    <span className="small muted">{formatAddressLine(a)}</span>
                  </span>
                  {selected?.id === a.id && <Icon name="check" size={18} className="loc-option__check" />}
                </label>
              ))}
            </div>
          )}
        </div>
      </Sheet>
    </>
  );
}
