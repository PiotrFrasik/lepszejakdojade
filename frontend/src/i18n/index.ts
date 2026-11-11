import { createI18n } from 'vue-i18n'

import en from '@/locales/en.json'
import pl from '@/locales/pl.json'
import { STORAGE_KEYS, readStorage, writeStorage } from '@/utils/storage'

/** Polish is the source of truth for the message schema; `en.json` must have identical keys. */
export type MessageSchema = typeof pl

export const SUPPORTED_LOCALES = ['pl', 'en'] as const
export type AppLocale = (typeof SUPPORTED_LOCALES)[number]

export const DEFAULT_LOCALE: AppLocale = 'pl'
export const FALLBACK_LOCALE: AppLocale = 'en'

export function isSupportedLocale(value: unknown): value is AppLocale {
  return typeof value === 'string' && (SUPPORTED_LOCALES as readonly string[]).includes(value)
}

/**
 * Initial locale: the stored choice, otherwise the default.
 * TODO(#30): fall back to browser language detection before the default.
 */
export function getInitialLocale(): AppLocale {
  const stored = readStorage(STORAGE_KEYS.locale)
  return isSupportedLocale(stored) ? stored : DEFAULT_LOCALE
}

export const i18n = createI18n<[MessageSchema], AppLocale, false>({
  legacy: false,
  locale: getInitialLocale(),
  fallbackLocale: FALLBACK_LOCALE,
  messages: { pl, en },
})

/** Current UI locale, usable outside components (e.g. the API client). */
export function getCurrentLocale(): AppLocale {
  return i18n.global.locale.value
}

/** Sets `<html lang>` to the given locale. */
export function syncDocumentLang(locale: AppLocale): void {
  if (typeof document !== 'undefined') {
    document.documentElement.lang = locale
  }
}

/** Switches the UI locale, updates `<html lang>` and remembers the choice. */
export function applyLocale(locale: AppLocale): void {
  i18n.global.locale.value = locale
  syncDocumentLang(locale)
  writeStorage(STORAGE_KEYS.locale, locale)
}
