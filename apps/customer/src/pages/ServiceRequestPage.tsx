import { useEffect, useState } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import { useMutation } from '@tanstack/react-query';
import { ApiError } from '@click/api';
import { useAuth } from '../auth/AuthProvider';
import { Button, EmptyState, Icon, useToast } from '../components/ui';
import { useThemeOverride } from '../components/layout/AppShell';
import { api } from '../lib/api';
import { useDeliveryLocation } from '../location/LocationProvider';

/** "Can't find your service?" — the request is stored for Click's team to review; nothing is promised or auto-booked. */
export function ServiceRequestPage() {
  useThemeOverride('services');
  const [sp] = useSearchParams();
  const { status } = useAuth();
  const toast = useToast();
  const { addresses, selected } = useDeliveryLocation();
  const [text, setText] = useState(sp.get('text') ?? '');
  const [addressId, setAddressId] = useState<string>(selected?.id ?? '');
  const [time, setTime] = useState('');
  const [touched, setTouched] = useState(false);
  useEffect(() => { if (!touched && !addressId && selected) setAddressId(selected.id); }, [selected, addressId, touched]);
  const m = useMutation({
    mutationFn: () => api.services.need({ text: text.trim(), addressId: addressId || null, preferredTime: time.trim() }),
    onError: (e) => toast(e instanceof ApiError ? e.message : 'Couldn’t send.', 'error'),
  });

  if (m.isSuccess) {
    return (
      <div className="sv-page" data-theme="services">
        <EmptyState icon="check" title="Request received" message="Click’s team reviews every request. We’ll let you know in Notifications if we find a suitable professional — no booking or payment happens without you."
          action={<Link to="/services" className="btn btn--primary">Back to Services</Link>} />
      </div>
    );
  }
  return (
    <div className="sv-page" data-theme="services">
      <Link to="/services" className="sv-back"><Icon name="back" size={18} /> Services</Link>
      <h1 className="sv-title">Tell Click what you need</h1>
      <p className="sv-muted">Can’t find your service? Describe it and we’ll look for a suitable professional near you.</p>
      {status !== 'authenticated' ? <p><Link to="/login">Sign in</Link> to send a request.</p> : (
        <form className="sv-form" onSubmit={(e) => { e.preventDefault(); m.mutate(); }}>
          <label className="sv-field">What do you need?
            <textarea className="sv-textarea" rows={4} minLength={5} maxLength={600} required value={text} onChange={(e) => setText(e.target.value)}
              placeholder="e.g. Someone to fix a sliding wardrobe door and oil the hinges." />
          </label>
          <label className="sv-field">Address
            <select value={addressId} onChange={(e) => { setTouched(true); setAddressId(e.target.value); }}>
              <option value="">No address</option>
              {addresses.map((a) => <option key={a.id} value={a.id}>{a.label} · {a.line1}</option>)}
            </select>
          </label>
          <label className="sv-field">Preferred time (optional)
            <input value={time} maxLength={120} onChange={(e) => setTime(e.target.value)} placeholder="e.g. Saturday morning" />
          </label>
          <Button type="submit" block loading={m.isPending} disabled={text.trim().length < 5}>Send request</Button>
        </form>
      )}
    </div>
  );
}
