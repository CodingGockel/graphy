// Disable SSR for the whole app: it is a client-rendered SPA (browser-only fetch
// and Leaflet). `prerender = false` + the adapter-static `fallback` produces a
// single index.html that handles all client-side routes.
export const ssr = false;
export const prerender = false;
