import { useState, type FormEvent } from 'react';
import { ApiError, type Address, type AddressInput, type AddressLabel } from '@click/api';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { Button, TextField } from '../../components/ui';
import { api } from '../../lib/api';
import { addressesKey } from './useAddresses';

const EMPTY: AddressInput = {
  label: 'home', recipientName: '', phone: '', line1: '', line2: '', landmark: '',
  city: '', state: '', postalCode: '', country: 'IN', isDefault: false,
};

export function AddressForm({ onSaved, onCancel, defaultName = '' }: { onSaved: (a: Address) => void; onCancel?: () => void; defaultName?: string }) {
  const [form, setForm] = useState<AddressInput>({ ...EMPTY, recipientName: defaultName });
  const [errors, setErrors] = useState<Record<string, string>>({});
  const qc = useQueryClient();
  const save = useMutation({
    mutationFn: api.customer.addresses.create,
    onSuccess: (a) => { qc.invalidateQueries({ queryKey: addressesKey }); onSaved(a); },
    onError: (e) => setErrors(e instanceof ApiError ? { ...e.fieldErrors(), _: e.code === 'validation_error' ? '' : e.message } : { _: 'Could not save address.' }),
  });

  const set = (k: keyof AddressInput) => (e: { target: { value: string } }) => setForm((f) => ({ ...f, [k]: e.target.value }));

  function submit(e: FormEvent) {
    e.preventDefault();
    const required: (keyof AddressInput)[] = ['recipientName', 'phone', 'line1', 'city', 'postalCode'];
    const missing = Object.fromEntries(required.filter((k) => !String(form[k]).trim()).map((k) => [k, 'Required']));
    setErrors(missing);
    if (Object.keys(missing).length === 0) save.mutate(form);
  }

  return (
    <form className="stack" onSubmit={submit} noValidate>
      <div className="chips" role="radiogroup" aria-label="Address label">
        {(['home', 'work', 'college', 'family', 'other'] as AddressLabel[]).map((l) => (
          <button key={l} type="button" className="chip" aria-pressed={form.label === l} onClick={() => setForm((f) => ({ ...f, label: l }))}>
            {l[0]!.toUpperCase() + l.slice(1)}
          </button>
        ))}
      </div>
      <div className="form-grid">
        <TextField label="Full name" value={form.recipientName} onChange={set('recipientName')} error={errors.recipientName} autoComplete="name" />
        <TextField label="Phone" value={form.phone} onChange={set('phone')} error={errors.phone} type="tel" autoComplete="tel" />
        <TextField className="span-2" label="House / flat, street" value={form.line1} onChange={set('line1')} error={errors.line1} autoComplete="address-line1" />
        <TextField className="span-2" label="Area (optional)" value={form.line2} onChange={set('line2')} autoComplete="address-line2" />
        <TextField label="City" value={form.city} onChange={set('city')} error={errors.city} autoComplete="address-level2" />
        <TextField label="PIN code" value={form.postalCode} onChange={set('postalCode')} error={errors.postalCode} inputMode="numeric" autoComplete="postal-code" />
        <TextField className="span-2" label="Landmark (optional)" value={form.landmark} onChange={set('landmark')} />
        <TextField className="span-2" label="Delivery instructions (optional)" value={form.deliveryInstructions ?? ''} onChange={set('deliveryInstructions')} maxLength={200} />
      </div>
      {errors._ && <p className="field__error" role="alert">{errors._}</p>}
      <div className="row">
        <Button type="submit" loading={save.isPending}>Save address</Button>
        {onCancel && <Button variant="ghost" onClick={onCancel}>Cancel</Button>}
      </div>
    </form>
  );
}
