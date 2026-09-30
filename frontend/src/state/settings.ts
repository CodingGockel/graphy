import { reactive } from 'vue'
import { isLocale, loadLocale, type Locale } from '../i18n'
import { readString, writeString } from '../lib/storage'

export type Theme = 'system' | 'light' | 'dark'

export const THEMES: Theme[] = ['system', 'light', 'dark']

// Same key as the inline script in index.html.
const THEME_KEY = 'graphy.theme'
const LOCALE_KEY = 'graphy.locale'

export const settings = reactive({
  theme: initialTheme(),
  locale: initialLocale(),
})

function initialTheme(): Theme {
  const stored = readString(THEME_KEY)
  return THEMES.includes(stored as Theme) ? (stored as Theme) : 'system'
}

function initialLocale(): Locale {
  const stored = readString(LOCALE_KEY)
  if (isLocale(stored)) return stored
  for (const language of navigator.languages ?? [navigator.language]) {
    const base = language.slice(0, 2).toLowerCase()
    if (isLocale(base)) return base
  }
  return 'en'
}

/** `system` leaves `data-theme` unset so the prefers-color-scheme media query decides. */
export function applyTheme(): void {
  const root = document.documentElement
  if (settings.theme === 'system') delete root.dataset.theme
  else root.dataset.theme = settings.theme
}

export function setTheme(theme: Theme): void {
  settings.theme = theme
  writeString(THEME_KEY, theme)
  applyTheme()
}

export async function setLocale(locale: Locale): Promise<void> {
  await loadLocale(locale)
  settings.locale = locale
  writeString(LOCALE_KEY, locale)
}
