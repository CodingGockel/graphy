import adapter from '@sveltejs/adapter-static';

/** @type {import('@sveltejs/kit').Config} */
const config = {
	compilerOptions: {
		// Force runes mode for the project, except for libraries. Can be removed in svelte 6.
		runes: ({ filename }) => (filename.split(/[/\\]/).includes('node_modules') ? undefined : true)
	},
	kit: {
		// Build to a static client-rendered SPA (no Node server). The app is entirely
		// browser-driven (client-side fetch + Leaflet), so SSR is disabled in
		// src/routes/+layout.ts and a SPA fallback handles client-side routing.
		// The static output is served by nginx, which also proxies /api to the backend.
		adapter: adapter({ fallback: 'index.html' })
	}
};

export default config;
