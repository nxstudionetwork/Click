import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { useState } from 'react';
import type { Partner, PartnerField } from '@click/api';
import { friendlyFirebaseError, needsNewCode } from '../firebase/errors';
import { firebaseConfig } from '../firebase/config';
import { canVisit } from '../session/steps';
import { COUNTRIES, validateNational } from '../components/PhoneField';
import { DynamicField, type FieldValue } from '../components/DynamicField';
import { cardData, PartnerCard } from '../components/PartnerCard';
import { StatusBadge } from '../components/StatusBadge';
import { visualFor, FALLBACK_VISUAL } from '../config/visuals';

describe('Firebase errors', () => {
  it('maps codes to friendly messages and never echoes raw errors', () => {
    expect(friendlyFirebaseError({ code: 'auth/invalid-verification-code', message: 'Firebase: Error (auth/...)' }))
      .toBe('That code isn’t correct. Please try again.');
    expect(friendlyFirebaseError({ code: 'auth/code-expired' })).toMatch(/expired. Request a new one/);
    expect(friendlyFirebaseError({ code: 'auth/too-many-requests' })).toMatch(/Too many attempts/);
    expect(friendlyFirebaseError(new Error('Firebase: internal stack'))).toBe('We couldn’t verify your number right now. Please try again.');
    expect(needsNewCode({ code: 'auth/code-expired' })).toBe(true);
    expect(needsNewCode({ code: 'auth/invalid-verification-code' })).toBe(false);
  });
});

describe('Firebase config', () => {
  it('is null unless every required value is provided (no invented credentials)', () => {
    expect(firebaseConfig({ VITE_FIREBASE_API_KEY: 'k' } as ImportMetaEnv)).toBeNull();
    expect(firebaseConfig({
      VITE_FIREBASE_API_KEY: 'k', VITE_FIREBASE_AUTH_DOMAIN: 'd', VITE_FIREBASE_PROJECT_ID: 'p', VITE_FIREBASE_APP_ID: 'a',
    } as ImportMetaEnv)).toEqual({ apiKey: 'k', authDomain: 'd', projectId: 'p', appId: 'a' });
  });
});

describe('onboarding steps', () => {
  it('allows going back but never skipping ahead of the server step', () => {
    expect(canVisit('category', 'location')).toBe(true);
    expect(canVisit('review', 'profile')).toBe(false);
    expect(canVisit('profile', 'profile')).toBe(true);
  });
});

describe('phone validation', () => {
  const IN = COUNTRIES[0];
  it.each([['', /Enter your mobile/], ['98765', /all 10 digits/], ['1234567890', /doesn’t look right/]])('%s is rejected', (v, msg) => {
    expect(validateNational(IN, v)).toMatch(msg);
  });
  it('accepts a valid Indian mobile', () => expect(validateNational(IN, '9876543210')).toBeNull());
});

describe('DynamicField', () => {
  function Harness({ field }: { field: PartnerField }) {
    const [v, setV] = useState<FieldValue>(field.default);
    return <><DynamicField field={field} value={v} onChange={setV} /><output data-testid="v">{JSON.stringify(v)}</output></>;
  }
  it('renders multiselect as accessible checkboxes', async () => {
    render(<Harness field={{ key: 'cuisines', label: 'Cuisines', kind: 'multiselect', required: true,
      options: [{ value: 'a', label: 'Alpha' }, { value: 'b', label: 'Beta' }] }} />);
    await userEvent.click(screen.getByLabelText('Beta'));
    await userEvent.click(screen.getByLabelText('Alpha'));
    expect(screen.getByTestId('v')).toHaveTextContent('["a","b"]');
    expect(screen.getByRole('group', { name: 'Cuisines' })).toBeInTheDocument();
  });
  it('uses the category default for single choice', () => {
    render(<Harness field={{ key: 'vehicleType', label: 'Vehicle type', kind: 'select', required: true, default: 'auto',
      options: [{ value: 'car', label: 'Car' }, { value: 'auto', label: 'Auto' }] }} />);
    expect(screen.getByLabelText('Auto')).toBeChecked();
  });
});

const partner = {
  partnerCode: 'CLK-PT-000042', status: 'verification_pending', statusLabel: 'Verification pending', isVerified: false,
  onboardingStep: 'complete', partnerType: { slug: 'food', name: 'Food & Dining', icon: 'food' },
  category: { slug: 'restaurant', name: 'Restaurant', icon: 'food' }, businessName: 'Spice Route',
  verifiedPhone: '+919876543210', profile: { contactName: 'Meera', email: 'm@x.in', description: '', details: {} },
  address: { line1: '12 MG Road', city: 'Bengaluru' },
} as unknown as Partner;

describe('Partner card', () => {
  it('shows only public-safe details', () => {
    const data = cardData(partner)!;
    expect(Object.keys(data).sort()).toEqual(['businessName', 'categoryIcon', 'categoryName', 'partnerCode', 'status', 'statusLabel', 'typeName', 'typeSlug']);
    const { container } = render(<PartnerCard data={data} />);
    expect(screen.getByText('CLK-PT-000042')).toBeInTheDocument();
    expect(container.textContent).not.toMatch(/9876543210|MG Road|m@x.in/);
  });
  it('has no card before a Partner ID exists', () => {
    expect(cardData({ ...partner, partnerCode: null })).toBeNull();
  });
});

describe('status and visuals', () => {
  it('status is conveyed in text, not colour alone', () => {
    render(<StatusBadge status="verification_pending" label="Verification pending" />);
    expect(screen.getByText('Verification pending')).toBeVisible();
  });
  it('unknown future partner types fall back to default visuals', () => {
    expect(visualFor('space-tourism')).toBe(FALLBACK_VISUAL);
    expect(visualFor('transport').scenes[0]!.photo).toBe('driving');
  });
});

describe('API error messages', () => {
  it('never shows raw HTTP failures', async () => {
    const { ApiError } = await import('@click/api');
    const { apiMessage } = await import('../lib/format');
    expect(apiMessage(new ApiError(502, { code: 'http_error', message: 'Request failed (502).' }))).toMatch(/having trouble/);
    expect(apiMessage(new ApiError(0, { code: 'network_error', message: 'x' }))).toMatch(/can’t reach Click/);
    expect(apiMessage(new ApiError(503, { code: 'phone_auth_unavailable', message: 'We couldn’t verify your number right now.' })))
      .toBe('We couldn’t verify your number right now.');
  });
});
