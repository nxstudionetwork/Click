/// <reference types="vite/client" />
interface ImportMetaEnv {
  readonly VITE_API_BASE_URL?: string;
  readonly VITE_STORES_SOURCE?: 'api' | 'mock';
}
interface ImportMeta {
  readonly env: ImportMetaEnv;
}
