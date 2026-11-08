import { firebasePhoneAuth } from './firebase';
import type { PhoneAuthProvider } from './types';

const PROVIDERS: Record<string, PhoneAuthProvider> = { firebase: firebasePhoneAuth };

/** The configured phone-OTP provider (VITE_PHONE_AUTH_PROVIDER, default "firebase"). */
export const phoneAuth: PhoneAuthProvider = PROVIDERS[import.meta.env.VITE_PHONE_AUTH_PROVIDER ?? 'firebase'] ?? firebasePhoneAuth;

export * from './types';
