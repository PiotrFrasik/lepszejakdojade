import { createI18n } from 'vue-i18n'

import en from '@/locales/en.json'
import pl from '@/locales/pl.json'
import { STORAGE_KEYS, readStorage, writeStorage } from '@/utils/storage'

import { datetimeFormats, numberFormats } from './formats'

/** Polish is the source of truth for the message schema; `en.json` must have identical keys. */
export type MessageSchema = typeof pl

export const SUPPORTED_LOCALES = ['pl', 'en'] as const
export type AppLocale = (typeof SUPPORTED_LOCALES)[number]

export const DEFAULT_LOCALE: AppLocale = 'pl'
export const FALLBACK_LOCALE: AppLocale = 'en'

export function isSupportedLocale(value: unknown): value is AppLocale {
  return typeof value === 'string' && (SUPPORTED_LOCALES as readonly string[]).includes(value)
}

/** The browser's preferred languages, most preferred first; empty when unavailable. */
function browserLanguages(): readonly string[] {
  try {
    if (typeof navigator === 'undefined') return []
    if (Array.isArray(navigator.languages) && navigator.languages.length > 0) {
      return navigator.languages
    }
    return navigator.language ? [navigator.language] : []
  } catch {
    return []
  }
}

/**
 * First supported locale among language tags such as `navigator.languages`, compared by base
 * language (`en-US` → `en`, `PL` → `pl`). Returns `null` when none is supported.
 */
export function detectLocale(languages: readonly string[] = browserLanguages()): AppLocale | null {
  for (const tag of languages) {
    if (typeof tag !== 'string') continue
    const base = tag.trim().toLowerCase().split(/[-_]/)[0]
    if (isSupportedLocale(base)) return base
  }
  return null
}

/**
 * Initial locale: the stored choice, otherwise the first supported browser language, otherwise
 * the default (Polish). A detected language is not stored; only an explicit choice is.
 */
export function getInitialLocale(): AppLocale {
  const stored = readStorage(STORAGE_KEYS.locale)
  if (isSupportedLocale(stored)) return stored
  return detectLocale() ?? DEFAULT_LOCALE
}

export const i18n = createI18n<[MessageSchema], AppLocale, false>({
  legacy: false,
  locale: getInitialLocale(),
  fallbackLocale: FALLBACK_LOCALE,
  messages: { pl, en },
  datetimeFormats,
  numberFormats,
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

// `<html lang>` must match the UI from the very first render, not only after switching.
syncDocumentLang(getCurrentLocale())

/** Switches the UI locale, updates `<html lang>` and remembers the choice. */
export function applyLocale(locale: AppLocale): void {
  i18n.global.locale.value = locale
  syncDocumentLang(locale)
  writeStorage(STORAGE_KEYS.locale, locale)
}
