/**
 * Firebase Phone Authentication, loaded on demand so the Firebase SDK never
 * blocks app startup. Firebase sends and checks the SMS code; Click only ever
 * receives the resulting ID token, which the backend verifies.
 */
import type { Auth, ConfirmationResult } from 'firebase/auth';
import { emulatorHost, firebaseConfig } from './config';

export class PhoneAuthUnavailable extends Error {
  constructor() {
    super('Phone sign-in is not configured.');
    this.name = 'PhoneAuthUnavailable';
  }
}

let authPromise: Promise<Auth> | null = null;

export const isPhoneAuthConfigured = () => firebaseConfig() !== null;

export function getFirebaseAuth(): Promise<Auth> {
  const config = firebaseConfig();
  if (!config) return Promise.reject(new PhoneAuthUnavailable());
  authPromise ??= (async () => {
    const [{ initializeApp, getApps }, authModule] = await Promise.all([import('firebase/app'), import('firebase/auth')]);
    const app = getApps()[0] ?? initializeApp(config);
    const auth = authModule.getAuth(app);
    auth.useDeviceLanguage();
    const host = emulatorHost();
    if (host) authModule.connectAuthEmulator(auth, `http://${host}`, { disableWarnings: true });
    return auth;
  })().catch((err) => {
    authPromise = null; // allow a retry after a failed chunk download
    throw err;
  });
  return authPromise;
}

/** Sends the OTP. `container` hosts Firebase's invisible reCAPTCHA (abuse protection). */
export async function sendVerificationCode(phoneE164: string, container: HTMLElement): Promise<ConfirmationResult> {
  const auth = await getFirebaseAuth();
  const { RecaptchaVerifier: Verifier, signInWithPhoneNumber } = await import('firebase/auth');
  // A reCAPTCHA token is single-use and bound to its element, so use a fresh verifier per send.
  const verifier = new Verifier(auth, container, { size: 'invisible' });
  try {
    return await signInWithPhoneNumber(auth, phoneE164, verifier);
  } finally {
    verifier.clear();
  }
}

/** The signed-in Firebase user's ID token, or null when Firebase has no session. */
export async function currentIdToken(forceRefresh = false): Promise<string | null> {
  const auth = await getFirebaseAuth();
  await auth.authStateReady();
  return auth.currentUser ? auth.currentUser.getIdToken(forceRefresh) : null;
}

export async function firebaseSignOut(): Promise<void> {
  if (!isPhoneAuthConfigured()) return;
  const auth = await getFirebaseAuth();
  const { signOut } = await import('firebase/auth');
  await signOut(auth);
}
