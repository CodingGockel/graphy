/// <reference types="vite/client" />

interface ImportMetaEnv {
  /** Base URL of the backend API. Defaults to the relative `/api/v1`. */
  readonly VITE_API_BASE_URL?: string
}

interface ImportMeta {
  readonly env: ImportMetaEnv
}
