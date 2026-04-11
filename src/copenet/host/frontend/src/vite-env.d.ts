/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly VITE_COPNET_WS_URL?: string;
  readonly VITE_COPNET_TOKEN?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}

interface Window {
  COPNET_TOKEN?: string;
}
