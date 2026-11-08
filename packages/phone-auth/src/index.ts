import { firebasePhoneAuth } from './firebase';
import type { PhoneAuthProvider } from './types';

const PROVIDERS: Record<string, PhoneAuthProvider> = { firebase: firebasePhoneAuth };

/** The configured phone-OTP provider (VITE_PHONE_AUTH_PROVIDER, default "firebase"). */
export const phoneAuth: PhoneAuthProvider = PROVIDERS[import.meta.env.VITE_PHONE_AUTH_PROVIDER ?? 'firebase'] ?? firebasePhoneAuth;

/** True when the app has the Firebase web configuration it needs for phone sign-in. */
export const isPhoneAuthConfigured = () => Boolean(import.meta.env.VITE_FIREBASE_API_KEY && import.meta.env.VITE_FIREBASE_PROJECT_ID);

export * from './types';
export * from './countries';
export { toPhoneAuthError } from './firebase';
