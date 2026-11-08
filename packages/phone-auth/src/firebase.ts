/**
 * Firebase Phone Authentication adapter. Firebase only proves phone ownership:
 * after OTP we take the Firebase ID token, sign out of Firebase immediately and let
 * the Click backend verify the token and issue Click's own session. Only Firebase Auth
 * is loaded (no Analytics or other Google services), lazily, on the sign-in screens.
 */
import type { Auth, ConfirmationResult, RecaptchaVerifier } from 'firebase/auth';
import { FRIENDLY, PhoneAuthError, type PhoneAuthErrorCode, type PhoneAuthProvider } from './types';

const env = import.meta.env;
const CODES: Record<string, PhoneAuthErrorCode> = {
  'auth/invalid-phone-number': 'invalid_phone',
  'auth/missing-phone-number': 'invalid_phone',
  'auth/invalid-verification-code': 'invalid_code',
  'auth/missing-verification-code': 'invalid_code',
  'auth/code-expired': 'code_expired',
  'auth/session-expired': 'code_expired',
  'auth/too-many-requests': 'too_many_requests',
  'auth/quota-exceeded': 'quota_exceeded',
  'auth/captcha-check-failed': 'captcha_failed',
  'auth/invalid-app-credential': 'captcha_failed',
  'auth/missing-app-credential': 'captcha_failed',
  'auth/network-request-failed': 'network',
  'auth/operation-not-allowed': 'not_configured',
  'auth/invalid-api-key': 'not_configured',
  'auth/app-not-authorized': 'not_configured',
  'auth/unauthorized-domain': 'not_configured',
  'auth/internal-error': 'unavailable',
};

export function toPhoneAuthError(err: unknown): PhoneAuthError {
  if (err instanceof PhoneAuthError) return err;
  const raw = (err as { code?: string })?.code ?? '';
  const code = CODES[raw] ?? (typeof navigator !== 'undefined' && navigator.onLine === false ? 'network' : 'unknown');
  if (import.meta.env.DEV) console.warn('[phone-auth]', raw || err);  // developer diagnostics only
  return new PhoneAuthError(code, FRIENDLY[code], raw);
}

let authPromise: Promise<Auth> | null = null;

async function getFirebaseAuth(): Promise<Auth> {
  authPromise ??= (async () => {
    if (!env.VITE_FIREBASE_API_KEY || !env.VITE_FIREBASE_PROJECT_ID) throw new PhoneAuthError('not_configured', FRIENDLY.not_configured);
    const [{ initializeApp, getApps }, { initializeAuth, inMemoryPersistence, connectAuthEmulator }] = await Promise.all([import('firebase/app'), import('firebase/auth')]);
    const app = getApps()[0] ?? initializeApp({
      apiKey: env.VITE_FIREBASE_API_KEY,
      authDomain: env.VITE_FIREBASE_AUTH_DOMAIN,
      projectId: env.VITE_FIREBASE_PROJECT_ID,
      storageBucket: env.VITE_FIREBASE_STORAGE_BUCKET,
      messagingSenderId: env.VITE_FIREBASE_MESSAGING_SENDER_ID,
      appId: env.VITE_FIREBASE_APP_ID,
    });
    // Phone auth only: no popup/redirect resolver (avoids loading apis.google.com) and in-memory persistence,
    // because Firebase is signed out right after verification and Click's own session takes over.
    const auth = initializeAuth(app, { persistence: inMemoryPersistence });
    auth.useDeviceLanguage();
    if (import.meta.env.DEV && env.VITE_FIREBASE_AUTH_EMULATOR_HOST) {
      connectAuthEmulator(auth, `http://${env.VITE_FIREBASE_AUTH_EMULATOR_HOST}`, { disableWarnings: true });
    }
    return auth;
  })();
  try {
    return await authPromise;
  } catch (e) {
    authPromise = null;
    throw toPhoneAuthError(e);
  }
}

let verifier: RecaptchaVerifier | null = null;

export const firebasePhoneAuth: PhoneAuthProvider = {
  id: 'firebase',
  async start(phoneE164, container) {
    try {
      const auth = await getFirebaseAuth();
      const { RecaptchaVerifier, signInWithPhoneNumber, signOut } = await import('firebase/auth');
      verifier?.clear();
      // Invisible reCAPTCHA: Firebase's required bot protection for phone auth (never bypassed).
      verifier = new RecaptchaVerifier(auth, container, { size: 'invisible' });
      const result: ConfirmationResult = await signInWithPhoneNumber(auth, phoneE164, verifier);
      return {
        phoneNumber: phoneE164,
        async confirm(code: string) {
          try {
            const cred = await result.confirm(code);
            const token = await cred.user.getIdToken();
            await signOut(auth); // Click's session takes over; Firebase keeps no session in the app.
            return { provider: 'firebase', token };
          } catch (e) {
            throw toPhoneAuthError(e);
          }
        },
      };
    } catch (e) {
      verifier?.clear();
      verifier = null;
      throw toPhoneAuthError(e);
    }
  },
  async reset() {
    verifier?.clear();
    verifier = null;
  },
};
