import { readonly, ref } from 'vue'

export type Locale = 'de' | 'en' | 'fr'

export const LOCALES: Locale[] = ['de', 'en', 'fr']

/** Language names are shown in their own language, independent of the UI locale. */
export const LOCALE_NAMES: Record<Locale, string> = {
  de: 'Deutsch',
  en: 'English',
  fr: 'Français',
}

type Messages = { [key: string]: string | Messages }

// Each locale is its own chunk; only the selected one is loaded.
const loaders: Record<Locale, () => Promise<{ default: Messages }>> = {
  de: () => import('../locales/de.json'),
  en: () => import('../locales/en.json'),
  fr: () => import('../locales/fr.json'),
}

const messages = ref<Messages>({})
const current = ref<Locale>('en')

export function isLocale(value: unknown): value is Locale {
  return LOCALES.includes(value as Locale)
}

export async function loadLocale(locale: Locale): Promise<void> {
  messages.value = (await loaders[locale]()).default
  current.value = locale
  document.documentElement.lang = locale
}

function lookup(key: string): string | undefined {
  let node: string | Messages | undefined = messages.value
  for (const part of key.split('.')) {
    if (typeof node !== 'object') return undefined
    node = node[part]
  }
  return typeof node === 'string' ? node : undefined
}

/** Whether the current locale has a string for `key`. */
export function te(key: string): boolean {
  return lookup(key) !== undefined
}

/** Translate a dot-separated key, e.g. `t('chat.send')`. `{name}` placeholders are filled from `params`. */
export function t(key: string, params?: Record<string, string | number>): string {
  const text = lookup(key) ?? key
  if (!params) return text
  return text.replace(/\{(\w+)\}/g, (match, name: string) => (name in params ? String(params[name]) : match))
}

export function useI18n() {
  return { t, te, locale: readonly(current) }
}
