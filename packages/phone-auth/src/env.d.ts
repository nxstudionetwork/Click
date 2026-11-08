/// <reference types="vite/client" />
/** Each Click app supplies these through its own Vite env (.env.local); Firebase web values are public identifiers. */
interface ImportMetaEnv {
  readonly VITE_PHONE_AUTH_PROVIDER?: 'firebase';
  readonly VITE_FIREBASE_API_KEY?: string;
  readonly VITE_FIREBASE_AUTH_DOMAIN?: string;
  readonly VITE_FIREBASE_PROJECT_ID?: string;
  readonly VITE_FIREBASE_STORAGE_BUCKET?: string;
  readonly VITE_FIREBASE_MESSAGING_SENDER_ID?: string;
  readonly VITE_FIREBASE_APP_ID?: string;
  readonly VITE_FIREBASE_AUTH_EMULATOR_HOST?: string;
}
