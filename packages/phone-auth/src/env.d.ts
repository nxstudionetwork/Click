/// <reference types="vite/client" />
/** Each Click app supplies these through its own Vite env. */
interface ImportMetaEnv {
  /** Click API base (defaults to the dev proxy at /api/v1). */
  readonly VITE_API_BASE_URL?: string;
}
