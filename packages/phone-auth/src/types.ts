/**
 * Provider-neutral phone sign-in. The app talks only to this interface; Firebase is one adapter.
 * To switch providers later (e.g. an SMS gateway), add an adapter here + a backend verifier in
 * apps/identity and change VITE_PHONE_AUTH_PROVIDER. No screen needs to change.
 */
export interface PhoneVerification {
  /** E.164 number the code was sent to. */
  phoneNumber: string;
  /** Verifies the code; returns a credential for POST /auth/identity/exchange. */
  confirm(code: string): Promise<{ provider: string; token: string }>;
}

export interface PhoneAuthProvider {
  id: string;
  /** Sends an OTP. `verifierContainer` hosts any bot-protection widget (e.g. invisible reCAPTCHA). */
  start(phoneE164: string, verifierContainer: HTMLElement): Promise<PhoneVerification>;
  /** Releases widgets/sessions held by the provider. */
  reset(): Promise<void>;
}

export type PhoneAuthErrorCode =
  | 'invalid_phone' | 'invalid_code' | 'code_expired' | 'too_many_requests' | 'quota_exceeded'
  | 'captcha_failed' | 'network' | 'not_configured' | 'unavailable' | 'unknown';

export class PhoneAuthError extends Error {
  constructor(readonly code: PhoneAuthErrorCode, message: string, readonly detail?: string) {
    super(message);
    this.name = 'PhoneAuthError';
  }
}

export const FRIENDLY: Record<PhoneAuthErrorCode, string> = {
  invalid_phone: 'That phone number doesn’t look right. Please check it and try again.',
  invalid_code: 'That code isn’t correct. Please try again.',
  code_expired: 'That code has expired. Tap “Resend code” to get a new one.',
  too_many_requests: 'Too many attempts. Please wait a moment and try again.',
  quota_exceeded: 'We can’t send more codes right now. Please try again a little later.',
  captcha_failed: 'We couldn’t confirm you’re not a robot. Please try again.',
  network: 'You seem to be offline. Check your connection and try again.',
  not_configured: 'Phone sign-in isn’t set up yet. Please try again later.',
  unavailable: 'Phone sign-in is temporarily unavailable. Please try again shortly.',
  unknown: 'Something went wrong. Please try again.',
};
