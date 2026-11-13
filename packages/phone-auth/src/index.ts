import { clickOtpAuth } from './click-otp';
import type { PhoneAuthProvider } from './types';

/** Phone sign-in: Click's own OTP (the backend texts and verifies the code). */
export const phoneAuth: PhoneAuthProvider = clickOtpAuth;

/** The app needs no client-side configuration; whether codes can be sent is decided by the backend. */
export const isPhoneAuthConfigured = () => true;

export * from './types';
export * from './countries';
export { toPhoneAuthError } from './click-otp';
