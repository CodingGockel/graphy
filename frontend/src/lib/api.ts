// Single source of truth for the backend API base URL.
//
// In production the SPA is served same-origin behind nginx, which proxies
// `/api/...` to the backend — so a relative base needs no per-environment config.
// In dev, Vite's server proxy (see vite.config.ts) forwards `/api` to the local
// backend, so the same relative base works there too.
//
// To point the frontend at a backend on a different origin (e.g. local dev against
// a remote backend), set VITE_API_BASE_URL at build time.
//
// NOTE: a build arg can come through as an empty string (e.g. `VITE_API_BASE_URL=`
// in the Docker build). `??` only falls back on null/undefined, so an empty string
// would leak through and produce paths like `/chat` (missing the /api/v1 prefix,
// → nginx 405). Treat empty/whitespace as "not set".
const configured = import.meta.env.VITE_API_BASE_URL;
export const API_BASE_URL: string =
	configured && configured.trim() !== '' ? configured : '/api/v1';
