import { useState, type FormEvent } from 'react';
import { Navigate, useNavigate } from 'react-router-dom';
import { Button, Icon, TextField } from '@click/ui';
import type { PartnerDetails, PartnerField } from '@click/api';
import { DynamicField, type FieldValue } from '../../components/DynamicField';
import { OnboardingLayout } from '../../components/OnboardingLayout';
import { iconFor } from '../../config/visuals';
import { api } from '../../lib/api';
import { apiMessage, fieldErrors, formatPhone } from '../../lib/format';
import { useDraftPartner } from './useOnboarding';

const EMAIL_RE = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

function initialDetails(fields: PartnerField[], saved: PartnerDetails): Record<string, FieldValue> {
  return Object.fromEntries(fields.map((f) => [f.key, saved[f.key] ?? f.default]));
}

function validate(fields: PartnerField[], details: Record<string, FieldValue>) {
  const errors: Record<string, string> = {};
  for (const f of fields) {
    const v = details[f.key];
    const empty = v === undefined || v === '' || (Array.isArray(v) && v.length === 0);
    if (empty) {
      if (f.required) errors[f.key] = f.kind === 'multiselect' || f.kind === 'select' ? 'Choose an option.' : 'This field is required.';
      continue;
    }
    if (f.kind === 'number') {
      const n = Number(v);
      if (!Number.isInteger(n)) errors[f.key] = 'Enter a whole number.';
      else if (f.min !== undefined && n < f.min) errors[f.key] = `Must be at least ${f.min}.`;
      else if (f.max !== undefined && n > f.max) errors[f.key] = `Must be at most ${f.max}.`;
    }
  }
  return errors;
}

export function ProfilePage() {
  const navigate = useNavigate();
  const { partner, setPartnerState } = useDraftPartner();
  const config = partner?.category.configuration;
  const [businessName, setBusinessName] = useState(partner?.businessName ?? '');
  const [contactName, setContactName] = useState(partner?.profile.contactName ?? '');
  const [email, setEmail] = useState(partner?.profile.email ?? '');
  const [details, setDetails] = useState(() => (config ? initialDetails(config.fields, partner!.profile.details) : {}));
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [detailErrors, setDetailErrors] = useState<Record<string, string>>({});
  const [formError, setFormError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  if (!partner || !config) return <Navigate to="/onboarding/category" replace />;
  const individual = config.identity.individual;

  async function submit(e: FormEvent) {
    e.preventDefault();
    const errs: Record<string, string> = {};
    if (businessName.trim().length < 2) errs.businessName = 'Enter at least 2 characters.';
    if (!individual && !contactName.trim()) errs.contactName = 'Enter the contact person’s name.';
    if (email.trim() && !EMAIL_RE.test(email.trim())) errs.email = 'Enter a valid email address.';
    const dErrs = validate(config!.fields, details);
    setErrors(errs);
    setDetailErrors(dErrs);
    if (Object.keys(errs).length || Object.keys(dErrs).length) {
      setFormError('Please check the highlighted fields.');
      return;
    }
    setSaving(true);
    setFormError(null);
    const cleanDetails: PartnerDetails = {};
    for (const f of config!.fields) {
      const v = details[f.key];
      if (v === undefined || v === '' || (Array.isArray(v) && !v.length)) continue;
      cleanDetails[f.key] = f.kind === 'number' ? Number(v) : (v as string | string[]);
    }
    try {
      setPartnerState(await api.partner.saveProfile({
        businessName: businessName.trim(), contactName: individual ? undefined : contactName.trim(),
        email: email.trim(), details: cleanDetails,
      }));
      navigate('/onboarding/location');
    } catch (err) {
      setErrors(fieldErrors(err));
      setDetailErrors(fieldErrors(err, 'details'));
      setFormError(apiMessage(err));
    } finally {
      setSaving(false);
    }
  }

  return (
    <OnboardingLayout
      step="profile" back="/onboarding/category"
      title="Set up your Partner profile"
      subtitle={`Just the basics for a ${partner.category.name}. You can add more later.`}
    >
      <form className="stack form" onSubmit={submit} noValidate id="profile-form" onChange={() => formError && setFormError(null)}>
        <div className="selected-cat">
          <span className="selected-cat__icon" aria-hidden="true"><Icon name={iconFor(partner.category.icon)} size={20} /></span>
          <span><strong>{partner.category.name}</strong><span className="muted"> · {partner.partnerType.name}</span></span>
        </div>

        <section className="form-section" aria-labelledby="basics-h">
          <h2 id="basics-h" className="form-section__title">{individual ? 'About you' : 'Business details'}</h2>
          <TextField label={config.identity.businessNameLabel} value={businessName} onChange={(e) => setBusinessName(e.target.value)}
            error={errors.businessName} autoComplete={individual ? 'name' : 'organization'} maxLength={150} required />
          {!individual && (
            <TextField label="Contact person" value={contactName} onChange={(e) => setContactName(e.target.value)}
              error={errors.contactName} autoComplete="name" maxLength={150} required />
          )}
          <TextField label="Email (optional)" type="email" value={email} onChange={(e) => setEmail(e.target.value)}
            error={errors.email} autoComplete="email" inputMode="email" maxLength={254} />
          <div className="verified-phone">
            <span className="field__label">Mobile number</span>
            <span className="verified-phone__value">{formatPhone(partner.verifiedPhone)}
              <span className="status status--success"><Icon name="check" size={13} /> Verified by SMS</span>
            </span>
          </div>
        </section>

        {config.fields.length > 0 && (
          <section className="form-section" aria-labelledby="details-h">
            <h2 id="details-h" className="form-section__title">{partner.category.name} details</h2>
            {config.fields.map((f) => (
              <DynamicField key={f.key} field={f} value={details[f.key]} error={detailErrors[f.key]}
                onChange={(v) => { setDetails((d) => ({ ...d, [f.key]: v })); setDetailErrors(({ [f.key]: _, ...rest }) => rest); setFormError(null); }} />
            ))}
          </section>
        )}
        {formError && <p className="field__error" role="alert">{formError}</p>}
        <Button type="submit" block loading={saving}>Save and continue</Button>
      </form>
    </OnboardingLayout>
  );
}
