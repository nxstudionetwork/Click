import { useState, type FormEvent } from 'react';
import { Navigate, useNavigate } from 'react-router-dom';
import { Button, Icon, TextField } from '@click/ui';
import { OnboardingLayout } from '../../components/OnboardingLayout';
import { api } from '../../lib/api';
import { apiMessage, fieldErrors } from '../../lib/format';
import { useDraftPartner } from './useOnboarding';

const STATES = [
  'Andaman and Nicobar Islands', 'Andhra Pradesh', 'Arunachal Pradesh', 'Assam', 'Bihar', 'Chandigarh', 'Chhattisgarh',
  'Dadra and Nagar Haveli and Daman and Diu', 'Delhi', 'Goa', 'Gujarat', 'Haryana', 'Himachal Pradesh', 'Jammu and Kashmir',
  'Jharkhand', 'Karnataka', 'Kerala', 'Ladakh', 'Lakshadweep', 'Madhya Pradesh', 'Maharashtra', 'Manipur', 'Meghalaya',
  'Mizoram', 'Nagaland', 'Odisha', 'Puducherry', 'Punjab', 'Rajasthan', 'Sikkim', 'Tamil Nadu', 'Telangana', 'Tripura',
  'Uttar Pradesh', 'Uttarakhand', 'West Bengal',
];
const RADII = [2, 5, 10, 15, 25, 50];

type Coords = { latitude: number; longitude: number; accuracy: number };
type GeoState = { status: 'idle' | 'locating' | 'done' | 'error'; message?: string; coords?: Coords };

export function LocationPage() {
  const navigate = useNavigate();
  const { partner, setPartnerState } = useDraftPartner();
  const saved = partner?.address;
  const [values, setValues] = useState({
    line1: saved?.line1 ?? '', line2: saved?.line2 ?? '', landmark: saved?.landmark ?? '', city: saved?.city ?? '',
    state: saved?.state ?? '', postalCode: saved?.postalCode ?? '', serviceArea: saved?.serviceArea ?? '',
  });
  const [radius, setRadius] = useState<number | null>(saved?.serviceRadiusKm ?? null);
  const [geo, setGeo] = useState<GeoState>(() => saved?.latitude && saved.longitude
    ? { status: 'done', coords: { latitude: Number(saved.latitude), longitude: Number(saved.longitude), accuracy: 0 } }
    : { status: 'idle' });
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [formError, setFormError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  if (!partner) return <Navigate to="/onboarding/category" replace />;
  const loc = partner.category.configuration.location;
  const set = (k: keyof typeof values) => (e: { target: { value: string } }) => setValues((v) => ({ ...v, [k]: e.target.value }));

  // Location is only read after the partner taps the button and the browser asks for permission.
  function useCurrentLocation() {
    if (!('geolocation' in navigator)) {
      setGeo({ status: 'error', message: 'Your browser can’t share location. Enter your address below.' });
      return;
    }
    setGeo({ status: 'locating' });
    navigator.geolocation.getCurrentPosition(
      (pos) => setGeo({ status: 'done', coords: { latitude: pos.coords.latitude, longitude: pos.coords.longitude, accuracy: pos.coords.accuracy } }),
      (err) => setGeo({
        status: 'error',
        message: err.code === err.PERMISSION_DENIED
          ? 'Location permission was denied. You can still enter your address manually.'
          : 'We couldn’t get your location. Enter your address manually.',
      }),
      { enableHighAccuracy: true, timeout: 15000, maximumAge: 60000 },
    );
  }

  async function submit(e: FormEvent) {
    e.preventDefault();
    const errs: Record<string, string> = {};
    if (values.line1.trim().length < 3) errs.line1 = 'Enter the building and street.';
    if (values.city.trim().length < 2) errs.city = 'Enter the city.';
    if (values.state.trim().length < 2) errs.state = 'Enter the state.';
    if (!/^[1-9][0-9]{5}$/.test(values.postalCode.trim())) errs.postalCode = 'Enter a valid 6-digit PIN code.';
    setErrors(errs);
    if (Object.keys(errs).length) return setFormError('Please check the highlighted fields.');
    setSaving(true);
    setFormError(null);
    try {
      setPartnerState(await api.partner.saveLocation({
        ...Object.fromEntries(Object.entries(values).map(([k, v]) => [k, v.trim()])) as typeof values,
        latitude: geo.status === 'done' ? geo.coords!.latitude : null,
        longitude: geo.status === 'done' ? geo.coords!.longitude : null,
        serviceRadiusKm: loc.serviceRadius ? radius : null,
      }));
      navigate('/onboarding/review');
    } catch (err) {
      setErrors(fieldErrors(err));
      setFormError(apiMessage(err));
    } finally {
      setSaving(false);
    }
  }

  return (
    <OnboardingLayout step="location" back="/onboarding/profile" title={loc.title ?? 'Add your location'}
      subtitle="Customers and Click use this to send you nearby work. Your full address is never shown on your Partner card.">
      <form className="stack form" onSubmit={submit} noValidate onChange={() => formError && setFormError(null)}>
        <section className="form-section" aria-labelledby="pin-h">
          <h2 id="pin-h" className="form-section__title">Pin your location <span className="optional">(optional)</span></h2>
          {geo.status === 'done' && geo.coords ? (
            <div className="pin pin--done" role="status">
              <Icon name="pin" size={20} />
              <span>
                <strong>Location pinned</strong>
                <span className="muted small"> {geo.coords.latitude.toFixed(5)}, {geo.coords.longitude.toFixed(5)}
                  {geo.coords.accuracy ? ` · within ${Math.round(geo.coords.accuracy)} m` : ''}</span>
              </span>
              <button type="button" className="text-btn" onClick={() => setGeo({ status: 'idle' })}>Remove</button>
            </div>
          ) : (
            <Button variant="outline" block onClick={useCurrentLocation} loading={geo.status === 'locating'}>
              <Icon name="locate" size={18} /> Use my current location
            </Button>
          )}
          {geo.status === 'error' && <p className="notice notice--warning" role="alert"><Icon name="alert" size={18} /><span>{geo.message}</span></p>}
        </section>

        <section className="form-section" aria-labelledby="addr-h">
          <h2 id="addr-h" className="form-section__title">{loc.addressLabel ?? 'Address'}</h2>
          <TextField label="Building, street" value={values.line1} onChange={set('line1')} error={errors.line1} autoComplete="address-line1" required maxLength={255} />
          <TextField label="Area / locality (optional)" value={values.line2} onChange={set('line2')} error={errors.line2} autoComplete="address-line2" maxLength={255} />
          <TextField label="Landmark (optional)" value={values.landmark} onChange={set('landmark')} error={errors.landmark} maxLength={255} />
          <div className="form-grid">
            <TextField label="City" value={values.city} onChange={set('city')} error={errors.city} autoComplete="address-level2" required maxLength={100} />
            <TextField label="PIN code" value={values.postalCode} onChange={(e) => setValues((v) => ({ ...v, postalCode: e.target.value.replace(/\D/g, '').slice(0, 6) }))}
              error={errors.postalCode} autoComplete="postal-code" inputMode="numeric" required />
          </div>
          <TextField label="State" value={values.state} onChange={set('state')} error={errors.state} autoComplete="address-level1" list="in-states" required maxLength={100} />
          <datalist id="in-states">{STATES.map((s) => <option key={s} value={s} />)}</datalist>
        </section>

        {(loc.serviceArea || loc.serviceRadius) && (
          <section className="form-section" aria-labelledby="area-h">
            <h2 id="area-h" className="form-section__title">Service area</h2>
            {loc.serviceArea && (
              <TextField label="Areas you serve (optional)" placeholder="e.g. Indiranagar, Koramangala, HSR Layout"
                value={values.serviceArea} onChange={set('serviceArea')} error={errors.serviceArea} maxLength={255} />
            )}
            {loc.serviceRadius && (
              <fieldset className="field choice">
                <legend className="field__label">How far do you serve? <span className="optional">(optional)</span></legend>
                <div className="choice__list">
                  {RADII.map((r) => (
                    <label key={r} className={`choice__chip ${radius === r ? 'is-checked' : ''}`}>
                      <input type="radio" name="radius" checked={radius === r} onChange={() => setRadius(r)} />
                      {radius === r && <Icon name="check" size={16} />} {r} km
                    </label>
                  ))}
                </div>
              </fieldset>
            )}
          </section>
        )}
        {formError && <p className="field__error" role="alert">{formError}</p>}
        <Button type="submit" block loading={saving}>Save location</Button>
      </form>
    </OnboardingLayout>
  );
}
