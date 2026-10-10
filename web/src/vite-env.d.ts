/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly VITE_SMARTPLOY_API_BASE?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
