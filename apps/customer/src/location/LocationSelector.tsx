import { useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { useAuth } from '../auth/AuthProvider';
import { Button, Icon, Sheet } from '../components/ui';
import { AddressForm } from '../features/addresses/AddressForm';
import { useDeliveryLocation } from './LocationProvider';

export const formatAddressLine = (a: { line1: string; line2?: string; city: string }) =>
  [a.line1, a.line2, a.city].filter(Boolean).join(', ');

export function LocationSelector({ compact = false }: { compact?: boolean }) {
  const { status, user } = useAuth();
  const { addresses, selected, select, isLoading } = useDeliveryLocation();
  const [open, setOpen] = useState(false);
  const [adding, setAdding] = useState(false);
  const navigate = useNavigate();

  const label = status !== 'authenticated' ? 'Set location' : isLoading ? 'Loading…' : selected ? selected.label : 'Add address';
  const detail = selected ? formatAddressLine(selected) : status === 'authenticated' ? 'No saved address yet' : 'Sign in to save addresses';

  return (
    <>
      <button
        type="button"
        className={`location ${compact ? 'location--compact' : ''}`}
        onClick={() => (status === 'authenticated' ? setOpen(true) : navigate('/login'))}
        aria-label={`Delivery location: ${selected ? formatAddressLine(selected) : label}. Change`}
      >
        <Icon name="pin" size={20} className="location__pin" />
        <span className="location__text">
          <span className="location__label">{label} <Icon name="chevron" size={14} /></span>
          {!compact && <span className="location__detail">{detail}</span>}
        </span>
      </button>
      <Sheet open={open} onClose={() => { setOpen(false); setAdding(false); }} label="Choose delivery location">
        <div className="stack" style={{ padding: 'var(--s-5)' }}>
          <div className="spread"><h2>Deliver to</h2><button className="icon-btn" aria-label="Close" onClick={() => setOpen(false)}><Icon name="close" /></button></div>
          {adding ? (
            <AddressForm defaultName={user?.fullName} onSaved={(a) => { select(a.id); setAdding(false); setOpen(false); }} onCancel={() => setAdding(false)} />
          ) : (
            <>
              <div className="stack" style={{ gap: 'var(--s-2)' }} role="radiogroup" aria-label="Saved addresses">
                {addresses.length === 0 && <p className="muted">You haven’t saved any addresses yet.</p>}
                {addresses.map((a) => (
                  <label key={a.id} className="option">
                    <input type="radio" name="loc" checked={selected?.id === a.id} onChange={() => { select(a.id); setOpen(false); }} />
                    <div>
                      <strong style={{ textTransform: 'capitalize' }}>{a.label}</strong> {a.isDefault && <span className="badge">Default</span>}
                      <div className="muted small">{formatAddressLine(a)}</div>
                    </div>
                  </label>
                ))}
              </div>
              <div className="row">
                <Button onClick={() => setAdding(true)}>+ Add address</Button>
                <Link to="/account/addresses" className="btn btn--ghost" onClick={() => setOpen(false)}>Manage addresses</Link>
              </div>
            </>
          )}
        </div>
      </Sheet>
    </>
  );
}
