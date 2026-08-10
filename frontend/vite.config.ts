import tailwindcss from '@tailwindcss/vite';
import { sveltekit } from '@sveltejs/kit/vite';
import { defineConfig } from 'vite';

// In dev, forward /api to the local backend so the relative API_BASE_URL (/api/v1)
// works the same as it does in production behind nginx. Override the target with
// VITE_DEV_API_PROXY_TARGET if your backend runs elsewhere.
const devApiTarget = process.env.VITE_DEV_API_PROXY_TARGET ?? 'http://localhost:8000';

export default defineConfig({
	plugins: [tailwindcss(), sveltekit()],
	server: {
		proxy: {
			'/api': {
				target: devApiTarget,
				changeOrigin: true
			}
		}
	}
});
