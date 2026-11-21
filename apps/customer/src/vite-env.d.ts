/// <reference types="vite/client" />
interface ImportMetaEnv {
  readonly VITE_API_BASE_URL?: string;
  readonly VITE_STORES_SOURCE?: 'api' | 'mock';
  /** Ride map tiles (XYZ URL) and their attribution. Defaults to OpenStreetMap tiles for development. */
  readonly VITE_MAP_TILE_URL?: string;
  readonly VITE_MAP_ATTRIBUTION?: string;
}
interface ImportMeta {
  readonly env: ImportMetaEnv;
}
