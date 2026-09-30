import { createApp } from 'vue'
import App from './App.vue'
import './styles/base.css'
import { loadLocale } from './i18n'
import { applyTheme, settings } from './state/settings'

applyTheme()

// Mount once the locale is in, so the UI never shows raw translation keys.
loadLocale(settings.locale)
  .catch((err) => console.error('Failed to load locale', err))
  .finally(() => createApp(App).mount('#app'))
