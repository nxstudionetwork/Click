import { useState } from 'react';
import { Link, Navigate } from 'react-router-dom';
import { ApiError, type Partner, type PartnerField } from '@click/api';
import { Button, Icon } from '@click/ui';
import { OnboardingLayout } from '../../components/OnboardingLayout';
import { iconFor } from '../../config/visuals';
import { api } from '../../lib/api';
import { apiMessage, formatPhone } from '../../lib/format';
import { useDraftPartner } from './useOnboarding';

function displayValue(field: PartnerField, value: unknown) {
  const label = (v: unknown) => field.options?.find((o) => o.value === v)?.label ?? String(v);
  return Array.isArray(value) ? value.map(label).join(', ') : label(value);
}

function Summary({ partner }: { partner: Partner }) {
  const { profile, address, category } = partner;
  const fields = category.configuration.fields.filter((f) => profile.details[f.key] !== undefined);
  return (
    <div className="summary">
      <section className="summary__block" aria-labelledby="sum-cat">
        <div className="spread"><h2 id="sum-cat">Partner category</h2><Link to="/onboarding/category">Change</Link></div>
        <p className="row"><Icon name={iconFor(category.icon)} size={18} /> <strong>{category.name}</strong> <span className="muted">· {partner.partnerType.name}</span></p>
      </section>
      <section className="summary__block" aria-labelledby="sum-prof">
        <div className="spread"><h2 id="sum-prof">Profile</h2><Link to="/onboarding/profile">Edit</Link></div>
        <dl>
          <div><dt>{category.configuration.identity.businessNameLabel}</dt><dd>{partner.businessName}</dd></div>
          {!category.configuration.identity.individual && <div><dt>Contact person</dt><dd>{profile.contactName}</dd></div>}
          <div><dt>Mobile</dt><dd>{formatPhone(partner.verifiedPhone)} <span className="muted small">(verified)</span></dd></div>
          {profile.email && <div><dt>Email</dt><dd>{profile.email}</dd></div>}
          {fields.map((f) => <div key={f.key}><dt>{f.label}</dt><dd>{displayValue(f, profile.details[f.key])}</dd></div>)}
        </dl>
      </section>
      <section className="summary__block" aria-labelledby="sum-loc">
        <div className="spread"><h2 id="sum-loc">Location</h2><Link to="/onboarding/location">Edit</Link></div>
        {address ? (
          <dl>
            <div><dt>Address</dt><dd>{[address.line1, address.line2, address.landmark, address.city, address.state, address.postalCode].filter(Boolean).join(', ')}</dd></div>
            {address.serviceArea && <div><dt>Service area</dt><dd>{address.serviceArea}</dd></div>}
            {address.serviceRadiusKm && <div><dt>Service radius</dt><dd>{address.serviceRadiusKm} km</dd></div>}
            {address.latitude && <div><dt>Pinned location</dt><dd>Yes</dd></div>}
          </dl>
        ) : <p className="muted">No location yet.</p>}
      </section>
    </div>
  );
}

export function ReviewPage() {
  const { partner, setPartnerState } = useDraftPartner();
  const [error, setError] = useState<string | null>(null);
  const [missing, setMissing] = useState<string[]>([]);
  const [saving, setSaving] = useState(false);
  if (!partner) return <Navigate to="/onboarding/category" replace />;

  async function submit() {
    setSaving(true);
    setError(null);
    setMissing([]);
    try {
      // The route guard moves a completed partner to their new Partner card.
      setPartnerState(await api.partner.submit());
    } catch (err) {
      setError(apiMessage(err));
      if (err instanceof ApiError && err.code === 'onboarding_incomplete' && err.details) setMissing(Object.keys(err.details));
    } finally {
      setSaving(false);
    }
  }

  return (
    <OnboardingLayout step="review" back="/onboarding/location" title="Review and create your Partner ID"
      subtitle="Check your details. Creating your Partner ID submits your profile to Click for verification.">
      <Summary partner={partner} />
      <div className="notice notice--info">
        <Icon name="shield" size={18} />
        <span>Your permanent Click Partner ID is created now. Click then reviews your profile; until that’s done your status shows <strong>Verification pending</strong>.</span>
      </div>
      {error && (
        <div className="field__error" role="alert">
          {error}
          {missing.length > 0 && (
            <ul>{missing.map((m) => <li key={m}><Link to={`/onboarding/${m}`}>Finish {m}</Link></li>)}</ul>
          )}
        </div>
      )}
      <Button block onClick={() => void submit()} loading={saving}>{saving ? 'Creating your Partner ID…' : 'Create my Partner ID'}</Button>
    </OnboardingLayout>
  );
}
