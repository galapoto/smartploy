/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly VITE_SMARTPLOY_API_BASE?: string;
  readonly VITE_SMARTPLOY_CHROME_WEB_STORE_ID?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
