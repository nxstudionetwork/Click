import { useState } from 'react';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { useAuth } from '../auth/AuthProvider';
import { Button, ErrorState, Skeleton, useToast } from '../components/ui';
import { AddressForm } from '../features/addresses/AddressForm';
import { addressesKey, useAddresses } from '../features/addresses/useAddresses';
import { api } from '../lib/api';

export function AccountPage() {
  const { user, logout } = useAuth();
  const addresses = useAddresses();
  const qc = useQueryClient();
  const toast = useToast();
  const [adding, setAdding] = useState(false);
  const onError = (e: unknown) => toast(e instanceof Error ? e.message : 'Something went wrong.', 'error');
  const invalidate = () => qc.invalidateQueries({ queryKey: addressesKey });
  const remove = useMutation({ mutationFn: api.customer.addresses.remove, onSuccess: invalidate, onError });
  const makeDefault = useMutation({ mutationFn: (id: string) => api.customer.addresses.update(id, { isDefault: true }), onSuccess: invalidate, onError });

  return (
    <div className="stack">
      <h1>Account</h1>
      <section className="card card--pad spread">
        <div>
          <strong>{user?.fullName || 'Click member'}</strong>
          <div className="muted small">{user?.email}</div>
        </div>
        <Button variant="outline" size="sm" onClick={logout}>Sign out</Button>
      </section>

      <section className="card card--pad stack">
        <div className="spread"><h3>Saved addresses</h3>{!adding && <Button variant="ghost" size="sm" onClick={() => setAdding(true)}>+ Add</Button>}</div>
        {adding && <AddressForm defaultName={user?.fullName} onSaved={() => setAdding(false)} onCancel={() => setAdding(false)} />}
        {addresses.isError ? <ErrorState error={addresses.error} onRetry={() => addresses.refetch()} />
          : addresses.isPending ? <Skeleton height={64} />
          : addresses.data.length === 0 && !adding ? <p className="muted small">No saved addresses yet.</p>
          : addresses.data.map((a) => (
            <div key={a.id} className="spread" style={{ borderTop: '1px solid var(--c-line)', paddingTop: 12 }}>
              <div>
                <strong style={{ textTransform: 'capitalize' }}>{a.label}</strong> {a.isDefault && <span className="badge badge--accent">Default</span>}
                <div className="muted small">{[a.line1, a.city, a.postalCode].filter(Boolean).join(', ')}</div>
              </div>
              <div className="row">
                {!a.isDefault && <Button variant="ghost" size="sm" onClick={() => makeDefault.mutate(a.id)}>Make default</Button>}
                <Button variant="ghost" size="sm" onClick={() => window.confirm('Delete this address?') && remove.mutate(a.id)}>Delete</Button>
              </div>
            </div>
          ))}
      </section>
    </div>
  );
}
