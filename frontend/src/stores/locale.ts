import { defineStore } from 'pinia'
import { computed } from 'vue'

import { SUPPORTED_LOCALES, applyLocale, i18n, type AppLocale } from '@/i18n'

/**
 * UI language. The single source of truth is the vue-i18n global locale; this store only
 * exposes it to components and persists changes.
 * TODO(#30): also save the choice to the account for logged-in users.
 */
export const useLocaleStore = defineStore('locale', () => {
  const locale = computed<AppLocale>(() => i18n.global.locale.value)

  function setLocale(next: AppLocale): void {
    applyLocale(next)
  }

  return { locale, supportedLocales: SUPPORTED_LOCALES, setLocale }
})
