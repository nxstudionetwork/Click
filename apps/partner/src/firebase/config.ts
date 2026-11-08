/**
 * Firebase Web SDK configuration comes only from environment variables.
 * These values are public client identifiers; nothing secret belongs here.
 */
export interface FirebaseWebConfig {
  apiKey: string;
  authDomain: string;
  projectId: string;
  appId: string;
}

export function firebaseConfig(env: ImportMetaEnv = import.meta.env): FirebaseWebConfig | null {
  const config = {
    apiKey: env.VITE_FIREBASE_API_KEY ?? '',
    authDomain: env.VITE_FIREBASE_AUTH_DOMAIN ?? '',
    projectId: env.VITE_FIREBASE_PROJECT_ID ?? '',
    appId: env.VITE_FIREBASE_APP_ID ?? '',
  };
  return Object.values(config).every(Boolean) ? config : null;
}

export const emulatorHost = () => import.meta.env.VITE_FIREBASE_AUTH_EMULATOR_HOST ?? '';
