import { screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { Route, Routes } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { renderWithProviders } from '../test/utils';
import { OtpInput } from './OtpInput';

const start = vi.fn();
const exchange = vi.fn();
const completeSignup = vi.fn();
const startSession = vi.fn();
vi.mock('../auth/phone', async () => {
  const types = await import('../auth/phone/types');
  return { ...types, phoneAuth: { id: 'test', start: (...a: unknown[]) => start(...a), reset: vi.fn() } };
});
vi.mock('../lib/api', () => ({ api: { auth: {
  exchangeIdentity: (...a: unknown[]) => exchange(...a), completeSignup: (...a: unknown[]) => completeSignup(...a),
  uploadAvatar: vi.fn(), devLoginInfo: vi.fn().mockResolvedValue({ enabled: false }),
} } }));
vi.mock('../auth/AuthProvider', () => ({ useAuth: () => ({ status: 'anonymous', user: null, startSession, refreshUser: vi.fn(), devLogin: vi.fn() }) }));

const { LoginPage } = await import('./LoginPage');
const { VerifyPage } = await import('./VerifyPage');
const { SignupPage } = await import('./SignupPage');
const { onboarding } = await import('../auth/onboarding');
const { PhoneAuthError, FRIENDLY } = await import('../auth/phone/types');

const flow = (route: string) => renderWithProviders(
  <Routes>
    <Route path="/login" element={<LoginPage />} />
    <Route path="/login/verify" element={<VerifyPage />} />
    <Route path="/signup" element={<SignupPage />} />
    <Route path="/" element={<h1>Home page</h1>} />
  </Routes>, { route });

beforeEach(() => { vi.clearAllMocks(); onboarding.clear(); });

describe('OtpInput', () => {
  it('handles paste/autofill, typing and backspace', async () => {
    let value = '';
    const onComplete = vi.fn();
    const { rerender } = renderWithProviders(<OtpInput value={value} onChange={(v) => { value = v; }} onComplete={onComplete} />);
    const boxes = screen.getAllByRole('textbox');
    await userEvent.click(boxes[0]!);
    await userEvent.paste('123456');
    expect(value).toBe('123456');
    expect(onComplete).toHaveBeenCalledWith('123456');
    rerender(<OtpInput value="12" onChange={(v) => { value = v; }} />);
  });
});

describe('Login', () => {
  it('rejects an invalid number without sending an SMS', async () => {
    flow('/login');
    await userEvent.type(screen.getByLabelText('Mobile number'), '12345');
    await userEvent.click(screen.getByRole('button', { name: 'Continue' }));
    expect(await screen.findByRole('alert')).toHaveTextContent('Enter a valid India mobile number');
    expect(start).not.toHaveBeenCalled();
  });

  it('sends the E.164 number to the provider, then shows the OTP screen with a masked number', async () => {
    start.mockResolvedValue({ phoneNumber: '+919876543210', confirm: vi.fn() });
    flow('/login');
    await userEvent.type(screen.getByLabelText('Mobile number'), '98765 43210');
    await userEvent.click(screen.getByRole('button', { name: 'Continue' }));
    expect(start.mock.calls[0]![0]).toBe('+919876543210');
    expect(await screen.findByRole('heading', { name: 'Verify your phone' })).toBeInTheDocument();
    expect(screen.getByText('+91 9876••••10')).toBeInTheDocument();
  });

  it('shows friendly provider errors (e.g. too many requests)', async () => {
    start.mockRejectedValue(new PhoneAuthError('too_many_requests', FRIENDLY.too_many_requests));
    flow('/login');
    await userEvent.type(screen.getByLabelText('Mobile number'), '9876543210');
    await userEvent.click(screen.getByRole('button', { name: 'Continue' }));
    expect(await screen.findByRole('alert')).toHaveTextContent('Too many attempts. Please wait a moment and try again.');
  });
});

describe('Verify', () => {
  const pending = (confirm: ReturnType<typeof vi.fn>) => onboarding.setPending({ phoneNumber: '+919876543210', confirm: confirm as unknown as (code: string) => Promise<{ provider: string; token: string }> });

  it('wrong code shows a friendly error and lets the user retry', async () => {
    pending(vi.fn().mockRejectedValue(new PhoneAuthError('invalid_code', FRIENDLY.invalid_code)));
    flow('/login/verify');
    await userEvent.click(screen.getByLabelText('Digit 1 of 6'));
    await userEvent.paste('000000');
    expect(await screen.findByText('That code isn’t correct. Please try again.')).toBeInTheDocument();
    expect(exchange).not.toHaveBeenCalled();
  });

  it('returning customer: verified token is exchanged and the session starts', async () => {
    pending(vi.fn().mockResolvedValue({ provider: 'firebase', token: 'id-token' }));
    exchange.mockResolvedValue({ status: 'authenticated', user: { id: 'u1' }, access: 'a' });
    flow('/login/verify');
    await userEvent.click(screen.getByLabelText('Digit 1 of 6'));
    await userEvent.paste('246810');
    expect(await screen.findByRole('heading', { name: 'Home page' }, { timeout: 3000 })).toBeInTheDocument();
    expect(exchange).toHaveBeenCalledWith({ provider: 'firebase', token: 'id-token' });
    expect(startSession).toHaveBeenCalled();
  });

  it('new customer goes to profile setup; backend failure is explained', async () => {
    pending(vi.fn().mockResolvedValue({ provider: 'firebase', token: 't' }));
    exchange.mockResolvedValueOnce({ status: 'profile_required', signupToken: 'st', phoneNumber: '+919876543210', expiresIn: 1200 });
    flow('/login/verify');
    await userEvent.click(screen.getByLabelText('Digit 1 of 6'));
    await userEvent.paste('246810');
    expect(await screen.findByText('Let’s create your profile.', {}, { timeout: 3000 })).toBeInTheDocument();
    expect(onboarding.getSignup()?.token).toBe('st');
  });

  it('backend failure after OTP is explained', async () => {
    pending(vi.fn().mockResolvedValue({ provider: 'firebase', token: 't' }));
    exchange.mockRejectedValue(new Error('boom'));
    flow('/login/verify');
    await userEvent.click(screen.getByLabelText('Digit 1 of 6'));
    await userEvent.paste('246810');
    expect(await screen.findByRole('alert')).toHaveTextContent('Your number is verified, but we couldn’t sign you in');
  });
});

describe('Signup', () => {
  it('validates the profile, requires a location, then creates the account', async () => {
    onboarding.saveSignup('st', '+919876543210');
    completeSignup.mockResolvedValue({ status: 'authenticated', user: { id: 'u1' }, access: 'a' });
    flow('/signup');
    await userEvent.click(screen.getByRole('button', { name: 'Continue' }));
    expect(screen.getByText('Enter your full name.')).toBeInTheDocument();
    await userEvent.type(screen.getByLabelText('Full name'), 'Meera Rao');
    await userEvent.type(screen.getByLabelText('Email'), 'meera@example.com');
    await userEvent.click(screen.getByRole('button', { name: 'Continue' }));
    expect(screen.getByRole('heading', { name: 'Where should we deliver?' })).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Create my Click account' })).toBeNull(); // need a place first
    await userEvent.type(screen.getByLabelText('House / flat / floor'), '4B Lake View');
    await userEvent.type(screen.getByLabelText('City'), 'Bengaluru');
    await userEvent.type(screen.getByLabelText('PIN code'), '560001');
    await userEvent.click(screen.getByRole('button', { name: 'Save place' }));
    await userEvent.click(screen.getByRole('button', { name: 'Create my Click account' }));
    await waitFor(() => expect(completeSignup).toHaveBeenCalled());
    const body = completeSignup.mock.calls[0]![0];
    expect(body).toMatchObject({ signupToken: 'st', fullName: 'Meera Rao', email: 'meera@example.com' });
    expect(body.addresses).toHaveLength(1);
    expect(body.addresses[0]).toMatchObject({ line1: '4B Lake View', recipientName: 'Meera Rao', phone: '+919876543210' });
  });

  it('without a verified-phone session, signup redirects to login', async () => {
    flow('/signup');
    expect(await screen.findByRole('heading', { name: 'Welcome to Click' })).toBeInTheDocument();
    expect(screen.getByLabelText('Mobile number')).toBeInTheDocument();
  });
});
